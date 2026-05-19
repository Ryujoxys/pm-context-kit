---
name: code-context
description: Use when helping product managers or product-engineering teams understand existing system behavior through read-only code_context_mcp tools, especially before writing requirements, checking PRD assumptions, judging feasibility, tracing business logic, mapping impact, reviewing recent changes, or identifying implementation boundaries.
---

# Code Context

Use this skill when a product manager or product-engineering team wants code-grounded product context before making decisions, writing requirements, or discussing scope with engineering.

## Non-Negotiables

- Treat repositories as read-only. Never write files, run mutating git commands, or suggest write-capable MCP tools.
- Use `code_context_mcp` facts before relying on memory. Cite repository names and file paths for concrete claims.
- Respect visibility policy. If a path is hidden, say it is outside the visible code context.
- Separate facts, inferences, and open questions.
- Mirror the user's language and keep PM-facing answers business-readable.
- Do not overclaim. If code evidence is partial, say what is confirmed and what still needs engineering confirmation.

## Investigation Flow

1. Discover scope with `code_context_find_projects` or `code_context_list_repos`.
2. Search broadly with business terms, English terms, route names, statuses, table names, config keys, event names, and job names using `code_context_search`.
3. Map structure with `code_context_tree` or `code_context_list_directory` when entry points are unclear.
4. Read only the smallest relevant files and line ranges with `code_context_read_file`.
5. Use `code_context_git_log`, `code_context_git_show`, `code_context_git_diff`, or `code_context_git_blame` when the user asks about history, ownership, recent changes, or why a rule exists.
6. Reconcile evidence across modules before summarizing.

## Common Product Research Modes

### Requirement Reality Check

Use when the user has a feature idea or PRD draft.

Answer with:
- current system behavior
- whether the requested behavior already exists, partially exists, or conflicts with current logic
- affected modules, APIs, jobs, states, permissions, data models, and configs
- likely implementation boundaries
- risky assumptions and questions for engineering

### Business Flow Reconstruction

Use when the user asks how a business process works.

Trace:
- entry points: UI route, API route, controller, command, worker, webhook, or scheduled job
- main flow: validation, state transition, service calls, persistence, external calls
- side effects: notifications, audit logs, cache updates, search indexing, async tasks
- failure and retry behavior
- user-visible outcomes

### Impact Analysis

Use when the user asks what a change may affect.

Check:
- direct code paths and downstream consumers
- cross-repository dependencies
- permissions, roles, feature flags, and configuration
- database fields, status enums, cache keys, queues, topics, tasks, cron jobs
- API contracts and backward compatibility
- admin/operation tools and reporting impact
- test coverage or missing verification signals when visible

### PRD Assumption Review

Use when the user shares a PRD, requirement, or product rule.

Compare the requirement against code evidence and output:
- supported assumptions
- contradicted assumptions
- unverified assumptions
- missing edge cases
- terms that need precise definitions
- suggested PRD clarifications grounded in current system behavior

### Change and Release Understanding

Use when the user asks about recent changes.

Use Git tools to summarize:
- what changed
- affected business modules
- user-visible behavior
- migration or compatibility implications
- rollback or risk points visible from code
- owners or authors when useful

### New-vs-Old or Migration Comparison

Use when there are old/new modules, duplicate services, or migration paths.

Compare:
- responsibilities
- overlapping capabilities
- divergent rules
- compatibility shims
- data migration or dual-write behavior
- remaining unknowns

## What To Look For

When searching code, consider these surfaces:

- API routes, controllers, handlers, resolvers, commands
- service/domain modules, state machines, validators
- database schemas, migrations, models, repositories, DAO layers
- status enums, constants, error codes, permission checks
- feature flags, config files, environment keys
- message queues, events, webhooks, scheduled jobs, async workers
- cache, search index, notification, audit log, analytics, reporting code
- admin tools and operation scripts
- tests, fixtures, seed data, mock data
- README, docs, changelogs, comments when code evidence needs context

## Output Patterns

### Default PM Research Answer

Use this shape unless the user asks for something else:

- Conclusion: short answer and confidence level
- Current System Facts: what the visible code proves
- Flow: end-to-end business process
- Key Modules: repo/path list with short purpose
- Product Boundaries: states, permissions, configs, async work, data limits
- Misjudgment Risks: likely ways a PRD could be wrong
- Engineering Questions: precise questions to confirm
- Sources: key repositories and file paths

### Impact Matrix

Use for scope or feasibility questions:

| Area | Evidence | Impact | Risk | Needs confirmation |
|---|---|---|---|---|

### Code Location Answer

When the user asks where something is implemented, list exact repo/path candidates first, then explain what each file does.

## Handling Hidden or Missing Context

If visibility policy blocks files, say:

"This area is outside the visible code context. I can summarize adjacent visible behavior, but engineering should confirm the hidden implementation."

If evidence is missing, say:

"I did not find visible code proving this behavior. It may be implemented outside the configured repositories, behind hidden paths, or in an external system."
