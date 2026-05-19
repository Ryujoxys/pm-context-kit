# PM Context Kit

中文 | [English](README.en.md)

PM Context Kit 是一套面向产研协作的只读代码上下文工具。它让产品经理在写需求、判断方案、评估影响面之前，可以通过 AI 了解真实系统边界，减少因为不了解现有实现而产生的错误判断。

它不是一个完整聊天产品，也不绑定任何模型。核心能力是一个只读 MCP server；Skill 只是可选的工作流说明，给支持 Skill 的 Agent 使用。

## 给产品经理看：它解决什么问题

很多需求风险不是来自“实现难”，而是来自前期判断不完整：

- 以为系统已有某个能力，实际只有部分场景支持
- 以为只改一个页面，实际牵动多个服务、状态机、定时任务或审核流程
- PRD 漏掉历史兼容、权限、异常分支、数据同步、灰度配置
- 产品和研发沟通时，双方对“当前系统事实”的理解不一致

PM Context Kit 的目标是提供一个需求前置调研入口：

- 先看当前系统事实，再写方案
- 先确认业务流程、状态、边界，再判断需求复杂度
- 先找出可能误判点，再和研发讨论
- 输出更贴近实现的 PRD 背景、影响范围和待确认问题

典型问题：

```text
用 code-context 梳理订单退款现在是怎么实现的，哪些模块会受影响？
```

```text
帮我检查这个需求是否和当前用户登录逻辑有冲突，列出需要研发确认的问题。
```

```text
最近 10 次提交主要影响了哪些业务模块？是否会影响搜索、登录或订单？
```

## 安全模型

安全边界由研发控制：

- MCP 只暴露读工具，不暴露写文件、删文件、改 Git、提交 PR 等能力
- 代码同步到研发控制的内网服务器或本机目录
- MCP 只读访问本地代码镜像
- 研发通过 `visibility.yaml` 决定哪些仓库、目录、文件允许 AI 看到
- 产品经理看到的是经过可见性策略过滤后的代码事实

这不是用来防内部恶意盗取代码的系统，而是一个受控、只读、可审计的产研协作工具。

## MCP 和 Skill 的关系

MCP 是核心能力，Skill 是可选增强。

| 部分 | 是否必需 | 作用 |
|---|---:|---|
| MCP server | 必需 | 提供只读工具：列仓库、搜代码、读文件、查 Git 历史 |
| repo-sync | 可选 | 从 Git 托管平台同步代码到本地镜像 |
| Skill | 可选 | 告诉 Agent 如何用这些工具做 PM 友好的业务逻辑梳理 |

如果你的 AI 客户端不支持 Skill，只接 MCP 也能工作。Skill 不读取代码，也不提供权限；它只是工作流说明。

## MCP 工具能力

当前 MCP 只暴露这些只读工具：

```text
code_context_list_repos
code_context_find_projects
code_context_get_project
code_context_list_directory
code_context_read_file
code_context_tree
code_context_search
code_context_git_log
code_context_git_show
code_context_git_diff
code_context_git_blame
```

明确不支持：

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

## 给研发看：快速部署

### 1. 准备配置

```bash
cd pm-context-kit
cp .env.example .env
cp config/repos.example.yaml config/repos.yaml
cp config/visibility.example.yaml config/visibility.yaml
```

编辑 `.env`，填入只读 Git 凭证。不要提交 `.env`。

编辑 `config/repos.yaml`，配置要暴露给 AI 的仓库。真实配置文件已被 `.gitignore` 忽略。

编辑 `config/visibility.yaml`，配置 AI 可见范围。真实配置文件也已被 `.gitignore` 忽略。

### 2. 同步仓库

```bash
set -a
source .env
set +a
uv run --project sync code-context-sync-once
```

默认代码会同步到：

```text
./repos
```

生产环境建议配置为服务器路径，例如：

```text
/data/code-context/repos
```

### 3. 本地 stdio MCP

适合 Codex、Claude Code、Cursor 等本地 Agent 客户端：

```bash
CODE_CONTEXT_REPOS_ROOT=/absolute/path/to/pm-context-kit/repos \
CODE_CONTEXT_CONFIG=/absolute/path/to/pm-context-kit/config/repos.yaml \
CODE_CONTEXT_VISIBILITY_CONFIG=/absolute/path/to/pm-context-kit/config/visibility.yaml \
uv run --project server code-context-mcp
```

### 4. 共享 HTTP MCP

适合部署在内网服务器，供多个客户端访问：

```bash
CODE_CONTEXT_MCP_HOST=0.0.0.0 \
CODE_CONTEXT_MCP_PORT=8000 \
CODE_CONTEXT_REPOS_ROOT=/data/code-context/repos \
CODE_CONTEXT_CONFIG=/data/code-context/config/repos.yaml \
CODE_CONTEXT_VISIBILITY_CONFIG=/data/code-context/config/visibility.yaml \
uv run --project server code-context-mcp --transport streamable-http
```

默认 HTTP MCP 路径：

```text
http://localhost:8000/mcp
```

### 5. Docker Compose

```bash
cd deploy
docker compose up -d --build
```

Compose 会启动：

- `code-context-mcp`：只读 MCP server
- `repo-sync`：一次性同步 worker

实际生产可以把 `repo-sync` 改成 cron、systemd timer、CI job 或 Kubernetes CronJob。

## 仓库配置说明

仓库配置写在 `config/repos.yaml`：

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

字段说明：

| 字段 | 说明 |
|---|---|
| `name` | 仓库在 MCP 里的唯一名称 |
| `provider` | 信息字段，第一版只依赖通用 Git 协议 |
| `url` | HTTPS Git URL 或本地 Git 路径 |
| `ssh_url` | 可选，SSH Git URL |
| `local_path` | 仓库同步到 `CODE_CONTEXT_REPOS_ROOT` 下的相对路径 |
| `branch` | 要同步的分支；为空时使用远端默认分支 |
| `tags` | 给产品/Agent 搜索用的业务标签 |
| `description` | 面向产品的业务描述 |
| `owner` | 负责人或负责团队 |
| `auth.mode` | `none`、`basic`、`token_header`、`bearer`、`ssh` |

支持的认证方式：

| `auth.mode` | 用途 |
|---|---|
| `none` | 公共 HTTPS 仓库或本地 Git 路径 |
| `basic` | HTTPS 用户名 + token 作为密码 |
| `token_header` | `Authorization: token <token>` |
| `bearer` | `Authorization: Bearer <token>` |
| `ssh` | 使用 `ssh_url` 和当前 SSH key/agent |

## 可见性配置说明

可见性策略写在 `config/visibility.yaml`，由研发维护。

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

规则说明：

- `allow` 默认是 `["**"]`
- `deny` 优先级高于 `allow`
- pattern 使用 gitignore 风格，相对仓库根目录
- 目录 pattern 可以写成 `some/path/**`
- 不要只屏蔽 `read_file`，因为搜索和 Git diff 也可能泄露内容。本项目在工具层统一执行策略

策略影响所有工具：

- `list_directory` / `tree`：不展示隐藏路径
- `read_file`：拒绝读取隐藏路径
- `search`：不搜索隐藏路径
- `git_show` / `git_diff` / `git_blame`：涉及隐藏路径时不返回内容

## 客户端接入

### Codex

参考：

```text
adapters/codex/mcp.example.toml
skills/codex/code-context/
```

MCP 是必需的；Skill 可选。

### Claude Code

参考：

```text
adapters/claude/claude_desktop_config.example.json
skills/claude/code-context/
```

MCP 是必需的；Skill 可选。

### 不支持 Skill 的客户端

只配置 MCP server 即可。可以把 Skill 里的说明复制到系统提示词或团队使用说明里。

## 适用与不适用

适合：

- 需求评审前调研现有系统
- PRD 假设校验
- 业务流程和状态机梳理
- 多仓库影响面分析
- 新 PM 或跨团队协作时快速了解系统边界

不适合：

- 替代研发评审
- 自动生成最终技术方案
- 让产品经理绕过研发直接改代码
- 防范已经有代码访问权限的内部恶意人员

## 开发验证

```bash
uv run --project server python -m py_compile server/src/code_context_mcp/server.py
uv run --project sync python -m py_compile sync/src/code_context_sync/sync_once.py
```
