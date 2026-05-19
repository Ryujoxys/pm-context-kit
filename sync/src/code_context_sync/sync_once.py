from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


DEFAULT_TIMEOUT = 900


def _path_from_env(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


def _repos_root() -> Path:
    return _path_from_env("CODE_CONTEXT_REPOS_ROOT", "./repos")


def _config_path() -> Path:
    return _path_from_env("CODE_CONTEXT_CONFIG", "./config/repos.yaml")


def _load_config() -> dict[str, Any]:
    path = _config_path()
    if not path.exists():
        raise FileNotFoundError(f"Repository config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if isinstance(data, list):
        return {"repositories": data}
    if not isinstance(data, dict):
        raise ValueError("Repository config must be a mapping or list")
    return data


def _askpass_script(directory: Path) -> Path:
    script = directory / "git-askpass.sh"
    script.write_text(
        """#!/bin/sh
case "$1" in
  *Username*) printf "%s" "$CODE_CONTEXT_GIT_USERNAME" ;;
  *Password*) printf "%s" "$CODE_CONTEXT_GIT_PASSWORD" ;;
  *) printf "%s" "$CODE_CONTEXT_GIT_PASSWORD" ;;
esac
""",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def _auth_env(auth: dict[str, Any] | None, tempdir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    if not auth:
        return env

    mode = str(auth.get("mode") or "none")
    token_env = auth.get("token_env")
    token = os.environ.get(str(token_env), "") if token_env else ""
    if mode in {"token_header", "bearer"}:
        if not token:
            raise ValueError(f"auth token env var is empty or missing: {token_env}")
        scheme = "Bearer" if mode == "bearer" else "token"
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"Authorization: {scheme} {token}"
    elif mode == "basic":
        if not token:
            raise ValueError(f"auth token env var is empty or missing: {token_env}")
        username = str(auth.get("username") or "")
        username_env = auth.get("username_env")
        if username_env:
            username = os.environ.get(str(username_env), username)
        if not username:
            raise ValueError("basic auth requires username or username_env")
        env["CODE_CONTEXT_GIT_USERNAME"] = username
        env["CODE_CONTEXT_GIT_PASSWORD"] = token
        env["GIT_ASKPASS"] = str(_askpass_script(tempdir))
    elif mode in {"none", "ssh"}:
        pass
    else:
        raise ValueError(f"Unsupported auth mode: {mode}")
    return env


def _run(args: list[str], env: dict[str, str], cwd: Path | None = None) -> None:
    display = " ".join(args[:4] + (["..."] if len(args) > 4 else []))
    print(f"[sync] {display}", flush=True)
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(details)


def _repo_url(entry: dict[str, Any]) -> str:
    auth = entry.get("auth") or {}
    if str(auth.get("mode") or "") == "ssh" and entry.get("ssh_url"):
        return str(entry["ssh_url"])
    return str(entry.get("url") or entry.get("ssh_url") or "")


def _sync_repo(entry: dict[str, Any]) -> None:
    name = str(entry.get("name") or entry.get("local_path") or "").strip()
    local_path = str(entry.get("local_path") or name).strip()
    url = _repo_url(entry)
    if not name or not local_path or not url:
        raise ValueError(f"Invalid repository entry: {entry}")
    target = (_repos_root() / local_path).resolve()
    branch = entry.get("branch")

    with tempfile.TemporaryDirectory(prefix="code-context-git-") as temp:
        env = _auth_env(entry.get("auth"), Path(temp))
        if (target / ".git").exists():
            _run(["git", "-C", str(target), "fetch", "--prune", "origin"], env)
            if branch:
                _run(["git", "-C", str(target), "reset", "--hard", f"origin/{branch}"], env)
            else:
                _run(["git", "-C", str(target), "pull", "--ff-only"], env)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and any(target.iterdir()):
                raise RuntimeError(f"target exists but is not a git repository: {target}")
            if target.exists():
                target.rmdir()
            tmp_target = target.parent / f".{target.name}.clone.tmp"
            if tmp_target.exists():
                shutil.rmtree(tmp_target)
            clone = ["git", "clone", "--quiet"]
            if branch:
                clone.extend(["--branch", str(branch)])
            clone.extend([url, str(tmp_target)])
            try:
                _run(clone, env)
                tmp_target.rename(target)
            except Exception:
                shutil.rmtree(tmp_target, ignore_errors=True)
                raise


def main() -> None:
    if shutil.which("git") is None:
        raise RuntimeError("git executable is required")
    repos = _load_config().get("repositories") or []
    failures: list[str] = []
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("local_path")
        try:
            print(f"[sync] start {name}", flush=True)
            _sync_repo(entry)
            print(f"[sync] done {name}", flush=True)
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[sync][error] {name}: {exc}", file=sys.stderr, flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
