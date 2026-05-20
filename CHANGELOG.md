# Changelog

All notable changes to the MCP server component (`server/`) are tracked here.
The sync utility (`sync/`) tracks its own version separately in its `pyproject.toml`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses semantic versioning.

## [0.2.0]

PM-flow tools and structured search output.

### Added
- `code_context_get_readme(repo)` — one-shot fetch of the top-level README so PMs (and the agent) can orient on a repo's purpose before drilling into code.
- `code_context_recent_changes(repos, days, max_per_repo)` — cross-repo summary of recent commits, sorted by volume. Answers "what shipped across these services this week" without per-repo `git_log` calls.
- `code_context_list_facets()` — enumerates all tags, owners, and providers with repo counts, so the agent can offer faceted entry points before searching.
- `code_context_list_repos` now surfaces `head_commit`, `last_commit_date`, and `current_branch` for every repo, and includes an onboarding `hint` when no repos are configured yet.

### Changed
- **Breaking:** `code_context_search` now returns structured `matches: [{path, line, column, text}]` instead of raw ripgrep lines. Clients that parsed the previous string array need to switch to the structured form.
- **Breaking:** `code_context_list_repos` returns `{count, repos, hint?}` instead of a bare list, so it has room for first-run guidance.
- Tool docstrings now carry concrete PM trigger phrases to help the agent pick the right tool for a given question.

### Refactored
- Skill prompts (`skills/claude/code-context/SKILL.md` and `skills/codex/code-context/SKILL.md`) rewritten with a discover-first investigation flow, a tool map keyed by PM-style questions, tightened research-mode playbooks, and an explicit negative scope to avoid triggering on engineer debugging tasks.

## [0.1.0]

Initial release.

- Read-only MCP server with: `code_context_list_repos`, `code_context_find_projects`, `code_context_get_project`, `code_context_list_directory`, `code_context_read_file`, `code_context_tree`, `code_context_search`, `code_context_git_log`, `code_context_git_show`, `code_context_git_diff`, `code_context_git_blame`.
- Visibility policy (gitignore-style) with allow/deny patterns per repo.
- Repo sync utility (`sync/`) supporting `none`, `basic`, `bearer`, `token_header`, and `ssh` auth modes.
- Docker Compose deployment with read-only filesystem and dropped capabilities.
- Skill prompts for Claude Desktop / Claude Code and Codex.
