# PM Context Kit

[中文](README.md) | English

PM Context Kit is a read-only code context toolkit for product-engineering collaboration. It helps product managers understand the real behavior and boundaries of existing systems before writing requirements, judging feasibility, or estimating impact.

It is not a full chat product and it does not bind you to a specific model. The core capability is a read-only MCP server. Skills are optional workflow instructions for Agent clients that support them.

## For Product Managers

Many product risks come from incomplete assumptions:

- assuming a capability already exists when only part of it is implemented
- assuming a small UI change when the actual impact crosses services, state machines, background jobs, or review flows
- missing compatibility, permissions, failure branches, sync jobs, or feature flags in a PRD
- product and engineering discussing a requirement without a shared view of current system facts

PM Context Kit provides a pre-requirement research layer:

- inspect current system behavior before writing a proposal
- understand workflows, states, boundaries, and constraints before judging complexity
- identify likely misjudgments before review meetings
- produce PRD context, impact areas, and engineering questions grounded in code facts

Example prompts:

```text
Use code-context to explain how refunds work today and which modules may be affected.
```

```text
Check whether this requirement conflicts with the current login flow and list questions for engineering.
```

```text
Review the last 10 commits and summarize which business modules were affected.
```

## Security Model

Engineering owns the deployment and visibility boundary:

- the MCP server exposes read-only tools only
- code is mirrored to an internal server or local directory controlled by engineering
- the MCP server reads the local mirror read-only
- engineering controls what the AI can see through `visibility.yaml`
- PMs receive code facts filtered by visibility policy

This is not designed to stop a malicious insider who already has code access. It is designed as a controlled, read-only, auditable collaboration layer.

## MCP vs Skill

MCP is the core capability. Skill is optional.

| Part | Required | Purpose |
|---|---:|---|
| MCP server | Yes | Read-only tools: list repos, search code, read files, inspect Git history |
| repo-sync | Optional | Mirror Git repositories locally |
| Skill | Optional | Teach an Agent how to produce PM-friendly code research |

If your AI client does not support Skills, connect only the MCP server. Skills do not grant permissions and do not read code; they only describe a workflow.

## MCP Tools

The MCP server exposes only these read-only tools:

```text
code_context_list_repos
code_context_find_projects
code_context_get_project
code_context_list_facets
code_context_list_directory
code_context_read_file
code_context_get_readme
code_context_tree
code_context_search
code_context_git_log
code_context_git_show
code_context_git_diff
code_context_git_blame
code_context_recent_changes
```

It does not expose:

```text
write_file
mkdir
rm
mv
git checkout
git commit
git reset
git push
create_pull_request
```

## Quick Start for Engineering

### 1. Prepare Config

```bash
cd pm-context-kit
cp .env.example .env
cp config/repos.example.yaml config/repos.yaml
cp config/visibility.example.yaml config/visibility.yaml
```

Edit `.env` with read-only Git credentials. Do not commit `.env`.

Edit `config/repos.yaml` to configure repositories exposed to AI. The real config file is ignored by git.

Edit `config/visibility.yaml` to configure what AI is allowed to see. The real visibility config is also ignored by git.

### 2. Sync Repositories

```bash
set -a
source .env
set +a
uv run --project sync code-context-sync-once
```

By default, repositories are mirrored to:

```text
./repos
```

For production, use a server path such as:

```text
/data/code-context/repos
```

### 3. Local stdio MCP

Best for local Agent clients such as Codex, Claude Code, and Cursor:

```bash
CODE_CONTEXT_REPOS_ROOT=/absolute/path/to/pm-context-kit/repos \
CODE_CONTEXT_CONFIG=/absolute/path/to/pm-context-kit/config/repos.yaml \
CODE_CONTEXT_VISIBILITY_CONFIG=/absolute/path/to/pm-context-kit/config/visibility.yaml \
uv run --project server code-context-mcp
```

### 4. Shared HTTP MCP

Best for an internal server shared by multiple clients:

```bash
CODE_CONTEXT_MCP_HOST=0.0.0.0 \
CODE_CONTEXT_MCP_PORT=8000 \
CODE_CONTEXT_REPOS_ROOT=/data/code-context/repos \
CODE_CONTEXT_CONFIG=/data/code-context/config/repos.yaml \
CODE_CONTEXT_VISIBILITY_CONFIG=/data/code-context/config/visibility.yaml \
uv run --project server code-context-mcp --transport streamable-http
```

Default HTTP MCP path:

```text
http://localhost:8000/mcp
```

### 5. Docker Compose

```bash
cd deploy
docker compose up -d --build
```

Compose starts:

- `code-context-mcp`: read-only MCP server
- `repo-sync`: one-shot sync worker

In production, `repo-sync` can be replaced by cron, systemd timer, CI job, or Kubernetes CronJob.

## Repository Config

Repository metadata lives in `config/repos.yaml`:

```yaml
repositories:
  - name: order-service
    provider: git
    url: https://git.example.com/product/order-service.git
    ssh_url: git@git.example.com:product/order-service.git
    local_path: product/order-service
    branch: main
    tags: [order, refund, payment]
    description: Order, payment, and refund service.
    owner: product-platform
    auth:
      mode: basic
      token_env: ORDER_SERVICE_GIT_TOKEN
      username_env: ORDER_SERVICE_GIT_USERNAME
```

Fields:

| Field | Meaning |
|---|---|
| `name` | Unique repository name exposed to MCP |
| `provider` | Informational; v1 uses generic Git protocol |
| `url` | HTTPS Git URL or local Git path |
| `ssh_url` | Optional SSH Git URL |
| `local_path` | Relative path under `CODE_CONTEXT_REPOS_ROOT` |
| `branch` | Branch to sync; empty means remote default branch |
| `tags` | Business tags for PM and Agent discovery |
| `description` | Business-facing description |
| `owner` | Owner or owning team |
| `auth.mode` | `none`, `basic`, `token_header`, `bearer`, or `ssh` |

Auth modes:

| `auth.mode` | Use case |
|---|---|
| `none` | Public HTTPS repo or local Git path |
| `basic` | HTTPS username + token as password |
| `token_header` | `Authorization: token <token>` |
| `bearer` | `Authorization: Bearer <token>` |
| `ssh` | Use `ssh_url` and the current SSH key/agent |

## Visibility Config

Visibility policy lives in `config/visibility.yaml` and is maintained by engineering.

```yaml
defaults:
  allow:
    - "**"
  deny:
    - ".git/**"
    - "**/.env"
    - "**/.env.*"
    - "**/*secret*"
    - "**/*credential*"
    - "**/*.pem"
    - "**/*.key"

repositories:
  order-service:
    allow:
      - "**"
    deny:
      - "**/payment/core/**"
      - "**/risk/core/**"
      - "**/security/**"
```

Rules:

- `allow` defaults to `["**"]`
- `deny` wins over `allow`
- patterns use gitignore-style globs relative to repo root
- directory patterns should use `some/path/**`
- do not only block `read_file`; search and Git diff can also leak content. This project enforces visibility centrally across tools

Policy applies to all tools:

- `list_directory` / `tree`: hidden paths are not listed
- `read_file`: hidden paths are rejected
- `search`: hidden paths are excluded from search
- `git_show` / `git_diff` / `git_blame`: content is blocked when hidden paths are involved

## Client Integration

### Codex

See:

```text
adapters/codex/mcp.example.toml
skills/codex/code-context/
```

MCP is required. Skill is optional.

### Claude Code

See:

```text
adapters/claude/claude_desktop_config.example.json
skills/claude/code-context/
```

MCP is required. Skill is optional.

### Clients Without Skill Support

Configure only the MCP server. You can copy the Skill instructions into a system prompt or team usage guide.

## Good Fit / Bad Fit

Good fit:

- pre-requirement research
- PRD assumption checks
- business flow and state-machine summaries
- multi-repository impact analysis
- onboarding PMs or cross-team collaboration

Bad fit:

- replacing engineering review
- generating final technical plans automatically
- letting PMs bypass engineers to modify code
- defending against malicious insiders who already have code access

## Development Checks

```bash
uv run --project server python -m py_compile server/src/code_context_mcp/server.py
uv run --project sync python -m py_compile sync/src/code_context_sync/sync_once.py
```
