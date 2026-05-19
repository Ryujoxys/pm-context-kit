---
name: code-context
description: Use when helping product managers or product-engineering teams understand existing system behavior through read-only code_context_mcp tools, especially before writing requirements, judging feasibility, checking PRD assumptions, tracing business logic, or finding implementation boundaries.
---

# Code Context

Use this skill when a product manager or product-engineering team wants to understand existing system behavior before making product decisions, writing requirements, or judging implementation impact.

## Rules

- Treat all repositories as read-only. Do not write files, run mutating git commands, or suggest using write-capable tools.
- Prefer MCP facts over memory. Cite repository names and file paths when making claims.
- Respect visibility policy. If a path is hidden, say it is outside the visible code context instead of trying to bypass it.
- Start broad, then narrow: project metadata -> code search -> targeted file reads -> git history if needed.
- Keep answers business-readable: explain current system facts, workflow, states, constraints, edge cases, and product impact before low-level implementation details.
- State uncertainty explicitly when the available code does not prove a claim.

## Workflow

1. Use `code_context_find_projects` or `code_context_list_repos` to identify relevant repositories.
2. Use `code_context_search` for terms, routes, handlers, services, config keys, database tables, or domain words.
3. Use `code_context_tree` or `code_context_list_directory` to map structure when entry points are unclear.
4. Use `code_context_read_file` on the smallest relevant files and line ranges.
5. Use `code_context_git_log`, `code_context_git_show`, `code_context_git_diff`, or `code_context_git_blame` only when recent changes or authorship matter.

## Output Shape

For business logic explanations, answer with:

- current system facts
- involved repositories and key modules
- end-to-end business flow
- important states, roles, validations, and side effects
- likely product boundaries and common misjudgment points
- impact area for a new requirement
- questions that need engineering confirmation

For code location questions, answer with the exact repo and path list first, then a short explanation.
