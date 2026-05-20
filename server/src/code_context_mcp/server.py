from __future__ import annotations

import argparse
import os
import pathspec
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP


DEFAULT_MAX_READ_CHARS = 80_000
DEFAULT_MAX_SEARCH_RESULTS = 200
DEFAULT_COMMAND_TIMEOUT = 30
README_CANDIDATES = (
    "README.md",
    "README.MD",
    "Readme.md",
    "readme.md",
    "README.rst",
    "README.txt",
    "README",
)
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    ".next",
}

mcp = FastMCP(
    "code_context_mcp",
    host=os.environ.get("CODE_CONTEXT_MCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("CODE_CONTEXT_MCP_PORT", "8000")),
    stateless_http=True,
)


@dataclass(frozen=True)
class RepoConfig:
    name: str
    local_path: str
    provider: str = "git"
    url: str | None = None
    ssh_url: str | None = None
    branch: str | None = None
    tags: tuple[str, ...] = ()
    description: str = ""
    owner: str = ""
    raw: dict[str, Any] | None = None

    def public_dict(self, include_stats: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "provider": self.provider,
            "local_path": self.local_path,
            "url": self.url,
            "ssh_url": self.ssh_url,
            "branch": self.branch,
            "tags": list(self.tags),
            "description": self.description,
            "owner": self.owner,
            "exists": self.root.exists(),
        }
        if include_stats:
            data.update(_git_short_stats(self))
        return data

    @property
    def root(self) -> Path:
        return (_repos_root() / self.local_path).resolve()


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


def _repos_root() -> Path:
    return _env_path("CODE_CONTEXT_REPOS_ROOT", "./repos")


def _config_path() -> Path:
    return _env_path("CODE_CONTEXT_CONFIG", "./config/repos.yaml")


def _visibility_path() -> Path:
    return _env_path("CODE_CONTEXT_VISIBILITY_CONFIG", "./config/visibility.yaml")


def _max_read_chars() -> int:
    return int(os.environ.get("CODE_CONTEXT_MAX_READ_CHARS", str(DEFAULT_MAX_READ_CHARS)))


def _load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return {"repositories": []}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if isinstance(data, list):
        return {"repositories": data}
    if not isinstance(data, dict):
        return {"repositories": []}
    return data


def _load_visibility_config() -> dict[str, Any]:
    path = _visibility_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _compile_gitwildmatch(patterns: list[str]) -> pathspec.PathSpec:
    normalized: list[str] = []
    for pattern in patterns:
        item = str(pattern).strip()
        if not item:
            continue
        if item.endswith("/"):
            item = f"{item}**"
        normalized.append(item)
    return pathspec.PathSpec.from_lines("gitwildmatch", normalized)


def _policy_patterns(repo: RepoConfig) -> tuple[list[str], list[str]]:
    config = _load_visibility_config()
    defaults = config.get("defaults") or {}
    repos = config.get("repositories") or {}
    repo_policy = repos.get(repo.name) or repos.get(repo.local_path) or {}
    default_deny = [
        ".git/**",
        "**/.env",
        "**/.env.*",
        "**/*secret*",
        "**/*credential*",
        "**/*private*",
        "**/*.pem",
        "**/*.key",
        "**/*.p12",
        "**/*.pfx",
    ]
    allow = repo_policy.get("allow", defaults.get("allow", ["**"]))
    deny = repo_policy.get("deny", defaults.get("deny", default_deny))
    allow_list = [str(item) for item in (allow or ["**"])]
    deny_list = [str(item) for item in (deny or [])]
    return allow_list, deny_list


def _path_visible(repo: RepoConfig, relative_path: str, is_dir: bool = False) -> bool:
    rel = relative_path.strip("/")
    if not rel:
        return True
    candidate = f"{rel}/" if is_dir else rel
    allow, deny = _policy_patterns(repo)
    allow_spec = _compile_gitwildmatch(allow or ["**"])
    deny_spec = _compile_gitwildmatch(deny)
    allowed = allow_spec.match_file(candidate) or (is_dir and allow_spec.match_file(f"{rel}/__dir__"))
    denied = deny_spec.match_file(candidate) or (is_dir and deny_spec.match_file(f"{rel}/__dir__"))
    return bool(allowed and not denied)


def _assert_visible(repo: RepoConfig, relative_path: str, is_dir: bool = False) -> None:
    if not _path_visible(repo, relative_path, is_dir=is_dir):
        raise PermissionError(f"path is hidden by visibility policy: {relative_path}")


def _visible_deny_globs(repo: RepoConfig) -> list[str]:
    _, deny = _policy_patterns(repo)
    output: list[str] = []
    for pattern in deny:
        item = str(pattern).strip()
        if not item:
            continue
        if item.endswith("/"):
            item = f"{item}**"
        output.append(item)
    return output


def _repo_from_entry(entry: dict[str, Any]) -> RepoConfig:
    name = str(entry.get("name") or entry.get("local_path") or "").strip()
    local_path = str(entry.get("local_path") or name).strip()
    if not name or not local_path:
        raise ValueError("Each repository entry must include name and local_path")
    tags = tuple(str(tag) for tag in (entry.get("tags") or []))
    return RepoConfig(
        name=name,
        local_path=local_path,
        provider=str(entry.get("provider") or "git"),
        url=entry.get("url"),
        ssh_url=entry.get("ssh_url"),
        branch=entry.get("branch"),
        tags=tags,
        description=str(entry.get("description") or ""),
        owner=str(entry.get("owner") or ""),
        raw=entry,
    )


def _configured_repos() -> list[RepoConfig]:
    repos: list[RepoConfig] = []
    for entry in _load_config().get("repositories", []):
        if isinstance(entry, dict):
            repos.append(_repo_from_entry(entry))
    return repos


def _scanned_repos() -> list[RepoConfig]:
    root = _repos_root()
    if not root.exists():
        return []
    repos: list[RepoConfig] = []
    for path in sorted(root.rglob(".git")):
        repo_root = path.parent
        rel = repo_root.relative_to(root)
        repos.append(RepoConfig(name=repo_root.name, local_path=str(rel)))
    return repos


def _all_repos() -> list[RepoConfig]:
    configured = _configured_repos()
    if configured:
        return configured
    return _scanned_repos()


def _get_repo(name: str) -> RepoConfig:
    query = name.strip()
    for repo in _all_repos():
        if repo.name == query or repo.local_path == query:
            if not repo.root.exists():
                raise FileNotFoundError(
                    f"Repository '{repo.name}' is configured at {repo.root}, but it does not exist. "
                    "Run the repo sync step or update CODE_CONTEXT_REPOS_ROOT."
                )
            return repo
    available = [repo.name for repo in _all_repos()]
    raise KeyError(f"Repository not found: {name}. Available repositories: {available}")


def _normal_relative_path(path: str | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if candidate.is_absolute():
        raise ValueError("path must be relative, not absolute")
    normalized = Path(os.path.normpath(path))
    if str(normalized) == ".":
        return ""
    if any(part == ".." for part in normalized.parts):
        raise ValueError("path must not contain '..'")
    return str(normalized)


def _safe_path(repo_root: Path, relative_path: str | None) -> Path:
    normalized = _normal_relative_path(relative_path)
    target = (repo_root / normalized).resolve()
    if target != repo_root and repo_root not in target.parents:
        raise ValueError("path escapes repository root")
    return target


def _safe_display_path(repo: RepoConfig, path: Path) -> str:
    return str(path.resolve().relative_to(repo.root))


def _safe_visible_path(repo: RepoConfig, relative_path: str | None, require_visible: bool = True) -> Path:
    target = _safe_path(repo.root, relative_path)
    rel = _safe_display_path(repo, target) if target != repo.root else ""
    if require_visible:
        _assert_visible(repo, rel, is_dir=target.is_dir())
    return target


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _run_command(args: list[str], cwd: Path | None = None, max_chars: int = 80_000) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=DEFAULT_COMMAND_TIMEOUT,
            check=False,
            env={
                **os.environ,
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
            },
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"command timed out after {DEFAULT_COMMAND_TIMEOUT}s"}

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    truncated = False
    if len(stdout) > max_chars:
        stdout = stdout[:max_chars]
        truncated = True
    if len(stderr) > 4000:
        stderr = stderr[:4000]
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": truncated,
    }


def _git_short_stats(repo: RepoConfig) -> dict[str, Any]:
    root = repo.root
    empty = {"head_commit": None, "last_commit_date": None, "current_branch": None}
    if not root.exists() or not (root / ".git").exists():
        return empty
    head = _run_command(
        ["git", "-C", str(root), "--no-pager", "log", "-1", "--pretty=format:%h%x09%ad", "--date=short"],
        max_chars=200,
    )
    branch = _run_command(
        ["git", "-C", str(root), "--no-pager", "branch", "--show-current"],
        max_chars=200,
    )
    head_commit = None
    last_commit_date = None
    if head.get("ok") and head.get("stdout"):
        parts = head["stdout"].strip().split("\t", 1)
        if len(parts) == 2:
            head_commit, last_commit_date = parts[0], parts[1]
    current_branch = branch.get("stdout", "").strip() if branch.get("ok") else ""
    return {
        "head_commit": head_commit,
        "last_commit_date": last_commit_date,
        "current_branch": current_branch or None,
    }


def _parse_rg_match(line: str, base: Path) -> dict[str, Any] | None:
    parts = line.split(":", 3)
    if len(parts) != 4:
        return None
    path_str, line_no, col, text = parts
    if not (line_no.isdigit() and col.isdigit()):
        return None
    rel = path_str
    try:
        abs_path = Path(path_str)
        if abs_path.is_absolute():
            try:
                rel = str(abs_path.relative_to(base))
            except ValueError:
                rel = path_str
    except (OSError, ValueError):
        rel = path_str
    return {
        "path": rel,
        "line": int(line_no),
        "column": int(col),
        "text": text,
    }


def _git_changed_paths(repo: RepoConfig, args_after_git: list[str]) -> list[str]:
    result = _run_command(
        ["git", "-C", str(repo.root), "--no-pager", *args_after_git],
        max_chars=200_000,
    )
    if not result.get("ok"):
        return []
    return [line.strip() for line in result.get("stdout", "").splitlines() if line.strip()]


def _hidden_paths(paths: list[str], repo: RepoConfig) -> list[str]:
    hidden: list[str] = []
    for path in paths:
        normalized = _normal_relative_path(path)
        if not _path_visible(repo, normalized, is_dir=False):
            hidden.append(normalized)
    return hidden


def _blocked_git_result(repo: RepoConfig, hidden: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "repo": repo.name,
        "error": "git output blocked by visibility policy because it includes hidden paths",
        "hidden_paths": sorted(set(hidden))[:50],
    }


def _validate_revision(revision: str, field_name: str = "revision") -> str:
    rev = revision.strip()
    if not rev:
        raise ValueError(f"{field_name} must not be empty")
    if len(rev) > 120:
        raise ValueError(f"{field_name} is too long")
    if rev.startswith("-") or any(ch.isspace() for ch in rev):
        raise ValueError(f"{field_name} must be a git revision, not an option or spaced string")
    return rev


@mcp.tool()
def code_context_list_repos() -> dict[str, Any]:
    """Read-only: list all configured or discovered repositories with business metadata and mirror freshness (head_commit, last_commit_date, current_branch).

    Use this first when the PM has not named a specific repository, or to confirm which mirrors are available and recent.
    """
    repos = [repo.public_dict() for repo in _all_repos()]
    if not repos:
        return {
            "count": 0,
            "repos": [],
            "hint": (
                f"No repositories configured. Copy config/repos.example.yaml to {_config_path()} and "
                f"list the repositories you want PMs to query, then run the repo sync step. "
                f"You can also set CODE_CONTEXT_CONFIG and CODE_CONTEXT_REPOS_ROOT to point elsewhere."
            ),
        }
    return {"count": len(repos), "repos": repos}


@mcp.tool()
def code_context_find_projects(query: str = "", tag: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Read-only: find repositories by business term, tag, owner, provider, or description.

    Use when the PM mentions a business concept (e.g. "refund", "下单", "user growth") but no specific repo name. Combine with code_context_list_facets to discover available tags and owners.
    """
    q = query.strip().lower()
    tag_q = tag.strip().lower()
    capped_limit = max(1, min(limit, 100))
    scored: list[tuple[int, RepoConfig]] = []
    for repo in _all_repos():
        score = 0
        fields = [
            repo.name,
            repo.local_path,
            repo.provider,
            repo.description,
            repo.owner,
            " ".join(repo.tags),
        ]
        haystack = " ".join(fields).lower()
        if q:
            if q in repo.name.lower():
                score += 5
            if any(q in item.lower() for item in repo.tags):
                score += 3
            if q in repo.description.lower():
                score += 2
            if q in haystack:
                score += 1
            else:
                continue
        if tag_q:
            if any(tag_q in item.lower() for item in repo.tags):
                score += 4
            else:
                continue
        scored.append((score, repo))
    scored.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    return [repo.public_dict() for _, repo in scored[:capped_limit]]


@mcp.tool()
def code_context_get_project(name: str) -> dict[str, Any]:
    """Read-only: get one repository's metadata and mirror freshness by name or local_path.

    Use to confirm a repo exists, check its tags/owner, or report the latest synced commit.
    """
    return _get_repo(name).public_dict()


@mcp.tool()
def code_context_list_directory(
    repo: str,
    path: str = "",
    include_hidden: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    """Read-only: list files and directories at a repository path.

    Use to map the layout when entry points are unclear, or to confirm a path exists before reading.
    """
    repo_cfg = _get_repo(repo)
    target = _safe_visible_path(repo_cfg, path)
    if not target.exists():
        raise FileNotFoundError(f"path does not exist: {path}")
    if not target.is_dir():
        raise NotADirectoryError(f"path is not a directory: {path}")

    entries: list[dict[str, Any]] = []
    capped_limit = max(1, min(limit, 1000))
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name == ".git":
            continue
        if not include_hidden and child.name.startswith("."):
            continue
        rel = _safe_display_path(repo_cfg, child)
        if not _path_visible(repo_cfg, rel, is_dir=child.is_dir()):
            continue
        stat_result = child.lstat()
        if child.is_symlink():
            kind = "symlink"
        elif child.is_dir():
            kind = "directory"
        elif child.is_file():
            kind = "file"
        else:
            kind = "other"
        entries.append(
            {
                "name": child.name,
                "path": rel,
                "type": kind,
                "size": stat_result.st_size,
            }
        )
        if len(entries) >= capped_limit:
            break
    return {
        "repo": repo_cfg.name,
        "path": _normal_relative_path(path),
        "count": len(entries),
        "limit": capped_limit,
        "entries": entries,
        "truncated": len(entries) >= capped_limit,
    }


@mcp.tool()
def code_context_read_file(
    repo: str,
    path: str,
    start_line: int = 1,
    max_lines: int = 300,
    include_line_numbers: bool = True,
) -> dict[str, Any]:
    """Read-only: read a text file from a repository with line and byte limits.

    Prefer the smallest relevant line range to keep PM-facing answers focused. For top-level repo intent, prefer code_context_get_readme.
    """
    repo_cfg = _get_repo(repo)
    target = _safe_visible_path(repo_cfg, path)
    if not target.exists():
        raise FileNotFoundError(f"file does not exist: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"path is not a file: {path}")

    max_bytes = _max_read_chars() * 4
    with target.open("rb") as f:
        data = f.read(max_bytes + 1)
    byte_truncated = len(data) > max_bytes
    data = data[:max_bytes]
    if b"\x00" in data[:8192]:
        return {
            "repo": repo_cfg.name,
            "path": _safe_display_path(repo_cfg, target),
            "binary": True,
            "content": "",
            "error": "binary file skipped",
        }
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    total_lines = len(lines)
    safe_start = max(1, start_line)
    safe_max = max(1, min(max_lines, 2000))
    selected = lines[safe_start - 1 : safe_start - 1 + safe_max]
    if include_line_numbers:
        content = "\n".join(f"{safe_start + index}: {line}" for index, line in enumerate(selected))
    else:
        content = "\n".join(selected)
    return {
        "repo": repo_cfg.name,
        "path": _safe_display_path(repo_cfg, target),
        "binary": False,
        "start_line": safe_start,
        "end_line": safe_start + len(selected) - 1 if selected else safe_start,
        "total_lines": total_lines,
        "content": content,
        "truncated": byte_truncated or safe_start - 1 + safe_max < total_lines,
    }


@mcp.tool()
def code_context_tree(repo: str, path: str = "", max_depth: int = 3, limit: int = 300) -> dict[str, Any]:
    """Read-only: return a compact directory tree for a repository path.

    Use for a fast structural overview before drilling into files. Cheaper than repeated list_directory calls.
    """
    repo_cfg = _get_repo(repo)
    root = _safe_visible_path(repo_cfg, path)
    if not root.exists():
        raise FileNotFoundError(f"path does not exist: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"path is not a directory: {path}")

    capped_depth = max(0, min(max_depth, 8))
    capped_limit = max(1, min(limit, 2000))
    lines: list[str] = []
    count = 0

    def visit(directory: Path, prefix: str, depth: int) -> None:
        nonlocal count
        if depth > capped_depth or count >= capped_limit:
            return
        children = [
            item
            for item in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            if item.name != ".git"
            and not _is_skipped(item.relative_to(root))
            and _path_visible(repo_cfg, _safe_display_path(repo_cfg, item), is_dir=item.is_dir())
        ]
        for index, child in enumerate(children):
            if count >= capped_limit:
                return
            connector = "`-- " if index == len(children) - 1 else "|-- "
            suffix = "/" if child.is_dir() and not child.is_symlink() else ""
            lines.append(f"{prefix}{connector}{child.name}{suffix}")
            count += 1
            if child.is_dir() and not child.is_symlink():
                next_prefix = prefix + ("    " if index == len(children) - 1 else "|   ")
                visit(child, next_prefix, depth + 1)

    lines.append(f"{root.name}/")
    visit(root, "", 1)
    return {
        "repo": repo_cfg.name,
        "path": _normal_relative_path(path),
        "tree": "\n".join(lines),
        "count": count,
        "truncated": count >= capped_limit,
    }


@mcp.tool()
def code_context_search(
    pattern: str,
    repo: str = "",
    path: str = "",
    case_insensitive: bool = True,
    file_glob: str = "",
    max_results: int = DEFAULT_MAX_SEARCH_RESULTS,
) -> dict[str, Any]:
    """Read-only: ripgrep-powered code search across one repo or all configured repos.

    Use for business terms, route names, status enums, table names, config keys, event names, job names, or feature flags. Pattern uses ripgrep regex syntax. Returns structured matches with path, line, column, and text.
    """
    if not pattern or len(pattern) > 500:
        raise ValueError("pattern must be 1-500 characters")
    if shutil.which("rg") is None:
        raise RuntimeError("ripgrep executable 'rg' is not installed")

    if repo:
        repo_cfg = _get_repo(repo)
        search_root = _safe_visible_path(repo_cfg, path)
        repo_name: str | None = repo_cfg.name
        deny_globs = _visible_deny_globs(repo_cfg)
    else:
        search_root = _repos_root()
        if path:
            search_root = _safe_path(search_root, path)
        repo_name = None
        deny_globs = []
    if not search_root.exists():
        raise FileNotFoundError(f"search path does not exist: {path or search_root}")

    capped_limit = max(1, min(max_results, 1000))
    cmd = [
        "rg",
        "--no-heading",
        "--line-number",
        "--column",
        "--with-filename",
        "--color",
        "never",
        "--max-filesize",
        "2M",
        "-g",
        "!.git",
        "-g",
        "!node_modules",
        "-g",
        "!dist",
        "-g",
        "!build",
    ]
    for deny in deny_globs:
        cmd.extend(["-g", f"!{deny}"])
    if case_insensitive:
        cmd.append("-i")
    if file_glob:
        cmd.extend(["-g", file_glob])
    cmd.extend([pattern, str(search_root)])

    result = _run_command(cmd, max_chars=250_000)
    stdout = result.get("stdout", "")
    if result.get("returncode") == 1:
        lines: list[str] = []
    elif not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("stderr") or "ripgrep failed",
            "returncode": result.get("returncode"),
        }
    else:
        lines = stdout.splitlines()
    selected = lines[:capped_limit]
    matches: list[dict[str, Any]] = []
    for raw in selected:
        parsed = _parse_rg_match(raw, search_root)
        if parsed is not None:
            matches.append(parsed)
    return {
        "ok": True,
        "repo": repo_name,
        "search_root": str(search_root),
        "pattern": pattern,
        "count": len(matches),
        "truncated": len(lines) > capped_limit or bool(result.get("truncated")),
        "matches": matches,
    }


@mcp.tool()
def code_context_git_log(repo: str, max_count: int = 20, path: str = "") -> dict[str, Any]:
    """Read-only: recent commits for a repository or path.

    Use when the PM asks "what changed recently", "who worked on this", or wants release context. For cross-repo summaries, prefer code_context_recent_changes.
    """
    repo_cfg = _get_repo(repo)
    capped = max(1, min(max_count, 100))
    args = [
        "git",
        "-C",
        str(repo_cfg.root),
        "--no-pager",
        "log",
        f"--max-count={capped}",
        "--date=iso",
        "--pretty=format:%H%x09%ad%x09%an%x09%s",
    ]
    if path:
        _safe_visible_path(repo_cfg, path)
        args.extend(["--", _normal_relative_path(path)])
    result = _run_command(args)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("stderr"), "returncode": result.get("returncode")}
    commits = []
    for line in result.get("stdout", "").splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return {"ok": True, "repo": repo_cfg.name, "count": len(commits), "commits": commits}


@mcp.tool()
def code_context_git_show(repo: str, revision: str = "HEAD", max_chars: int = 60_000) -> dict[str, Any]:
    """Read-only: full diff and stats for one revision.

    Use to understand the substance of a specific commit (what was changed, which files, what user-visible behavior shifted).
    """
    repo_cfg = _get_repo(repo)
    rev = _validate_revision(revision)
    changed = _git_changed_paths(repo_cfg, ["show", "--pretty=format:", "--name-only", rev])
    hidden = _hidden_paths(changed, repo_cfg)
    if hidden:
        return _blocked_git_result(repo_cfg, hidden) | {"revision": rev}
    capped_chars = max(1000, min(max_chars, 200_000))
    result = _run_command(
        [
            "git",
            "-C",
            str(repo_cfg.root),
            "--no-pager",
            "show",
            "--stat",
            "--patch",
            "--no-ext-diff",
            "--find-renames",
            rev,
        ],
        max_chars=capped_chars,
    )
    return {"ok": result.get("ok"), "repo": repo_cfg.name, "revision": rev, **result}


@mcp.tool()
def code_context_git_diff(
    repo: str,
    base: str = "HEAD~1",
    head: str = "HEAD",
    path: str = "",
    max_chars: int = 80_000,
) -> dict[str, Any]:
    """Read-only: diff between two revisions, optionally limited to one path.

    Use for "what shipped between v1 and v2" or release-window comparisons.
    """
    repo_cfg = _get_repo(repo)
    base_rev = _validate_revision(base, "base")
    head_rev = _validate_revision(head, "head")
    capped_chars = max(1000, min(max_chars, 200_000))
    changed_args = ["diff", "--name-only", f"{base_rev}..{head_rev}"]
    if path:
        _safe_visible_path(repo_cfg, path)
        changed_args.extend(["--", _normal_relative_path(path)])
    changed = _git_changed_paths(repo_cfg, changed_args)
    hidden = _hidden_paths(changed, repo_cfg)
    if hidden:
        return _blocked_git_result(repo_cfg, hidden) | {"base": base_rev, "head": head_rev}
    args = [
        "git",
        "-C",
        str(repo_cfg.root),
        "--no-pager",
        "diff",
        "--no-ext-diff",
        "--find-renames",
        f"{base_rev}..{head_rev}",
    ]
    if path:
        args.extend(["--", _normal_relative_path(path)])
    result = _run_command(args, max_chars=capped_chars)
    return {"ok": result.get("ok"), "repo": repo_cfg.name, "base": base_rev, "head": head_rev, **result}


@mcp.tool()
def code_context_git_blame(
    repo: str,
    path: str,
    start_line: int = 1,
    end_line: int = 80,
    max_chars: int = 80_000,
) -> dict[str, Any]:
    """Read-only: blame for a bounded line range in one file.

    Use to find who introduced a rule, when a constant changed, or why a code path exists.
    """
    repo_cfg = _get_repo(repo)
    target = _safe_visible_path(repo_cfg, path)
    if not target.is_file():
        raise FileNotFoundError(f"file does not exist: {path}")
    safe_start = max(1, start_line)
    safe_end = max(safe_start, min(end_line, safe_start + 500))
    result = _run_command(
        [
            "git",
            "-C",
            str(repo_cfg.root),
            "--no-pager",
            "blame",
            "-L",
            f"{safe_start},{safe_end}",
            "--",
            _normal_relative_path(path),
        ],
        max_chars=max(1000, min(max_chars, 120_000)),
    )
    return {
        "ok": result.get("ok"),
        "repo": repo_cfg.name,
        "path": _normal_relative_path(path),
        "start_line": safe_start,
        "end_line": safe_end,
        **result,
    }


@mcp.tool()
def code_context_get_readme(repo: str, max_chars: int = 20_000) -> dict[str, Any]:
    """Read-only: fetch the top-level README for a repository.

    Use this as the first reading step to understand a repo's purpose, scope, and conventions before drilling into code. Looks for common README filenames (README.md, README.rst, README.txt, README) at the repo root.
    """
    repo_cfg = _get_repo(repo)
    cap = max(1000, min(max_chars, 80_000))
    for candidate in README_CANDIDATES:
        target = repo_cfg.root / candidate
        if not target.is_file():
            continue
        rel = _safe_display_path(repo_cfg, target)
        if not _path_visible(repo_cfg, rel, is_dir=False):
            continue
        with target.open("rb") as f:
            data = f.read(cap + 1)
        truncated = len(data) > cap
        data = data[:cap]
        if b"\x00" in data[:8192]:
            continue
        return {
            "ok": True,
            "repo": repo_cfg.name,
            "path": rel,
            "content": data.decode("utf-8", errors="replace"),
            "truncated": truncated,
        }
    return {
        "ok": False,
        "repo": repo_cfg.name,
        "error": "no README file found at repo root within the visible code context",
        "looked_for": list(README_CANDIDATES),
    }


@mcp.tool()
def code_context_recent_changes(
    repos: list[str] | None = None,
    days: int = 7,
    max_per_repo: int = 10,
) -> dict[str, Any]:
    """Read-only: cross-repo summary of recent commits.

    Use when the PM asks "what shipped recently across these services" or wants a release pulse. If repos is empty, includes every existing configured repository. Results are sorted by commit volume.
    """
    capped_days = max(1, min(days, 90))
    capped_per_repo = max(1, min(max_per_repo, 50))
    since = f"{capped_days}.days.ago"

    targets: list[RepoConfig] = []
    missing: list[str] = []
    if repos:
        for name in repos:
            try:
                targets.append(_get_repo(name))
            except (KeyError, FileNotFoundError):
                missing.append(name)
    else:
        targets = [r for r in _all_repos() if r.root.exists()]

    summaries: list[dict[str, Any]] = []
    for repo in targets:
        result = _run_command(
            [
                "git",
                "-C",
                str(repo.root),
                "--no-pager",
                "log",
                f"--since={since}",
                f"--max-count={capped_per_repo}",
                "--date=iso",
                "--pretty=format:%h%x09%ad%x09%an%x09%s",
            ],
            max_chars=40_000,
        )
        commits: list[dict[str, Any]] = []
        if result.get("ok"):
            for line in result.get("stdout", "").splitlines():
                parts = line.split("\t", 3)
                if len(parts) == 4:
                    commits.append(
                        {
                            "hash": parts[0],
                            "date": parts[1],
                            "author": parts[2],
                            "subject": parts[3],
                        }
                    )
        summaries.append(
            {
                "repo": repo.name,
                "commit_count": len(commits),
                "commits": commits,
            }
        )
    summaries.sort(key=lambda item: (item["commit_count"], item["repo"]), reverse=True)
    return {
        "ok": True,
        "days": capped_days,
        "max_per_repo": capped_per_repo,
        "repo_count": len(summaries),
        "missing_repos": missing,
        "repos": summaries,
    }


@mcp.tool()
def code_context_list_facets() -> dict[str, Any]:
    """Read-only: enumerate available tags, owners, and providers across all configured repositories.

    Use to discover faceted entry points before calling code_context_find_projects. Each facet entry has a value and a repo count, sorted by frequency.
    """
    tag_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    repos = _all_repos()
    for repo in repos:
        for tag in repo.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if repo.owner:
            owner_counts[repo.owner] = owner_counts.get(repo.owner, 0) + 1
        if repo.provider:
            provider_counts[repo.provider] = provider_counts.get(repo.provider, 0) + 1

    def to_list(counts: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"value": value, "count": count}
            for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    return {
        "total_repos": len(repos),
        "tags": to_list(tag_counts),
        "owners": to_list(owner_counts),
        "providers": to_list(provider_counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the read-only code context MCP server.")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http", "sse"],
        help="MCP transport. stdio is best for local clients; streamable-http is best for shared services.",
    )
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
