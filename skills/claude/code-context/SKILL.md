---
name: code-context
description: Activate for product managers, product-engineering leads, or PRD authors asking how an existing system actually works, what a proposed change would touch, whether a requirement is already implemented, what shipped recently, who owns a module, or why a business rule exists — even when they phrase the question in pure business terms (审批流 / 工单 / 权限 / 通知 / 计费 / 数据看板 / 状态机 / 灰度 / approval flow / dashboard / billing / quota / webhook / audit log / SLA / feature flag) drawn from any domain (SaaS, B2B, e-commerce, fintech, internal tools, platform) and never mention code, repos, files, or git. Use for PRD reality checks, feasibility judgement, impact analysis, business-flow reconstruction, recent-change roundups, and old-vs-new comparisons grounded in the read-only `code_context_mcp` tools. Do NOT use for engineer-style debugging, refactoring decisions, build failures, or stack-trace analysis.
---

# Code Context

The PM is the customer here. Engineers can read code on their own; PMs need code translated into product facts before they write requirements, scope features, or talk to engineering. This skill turns the `code_context_mcp` read-only toolkit into a disciplined investigation loop that produces business-readable, citation-grounded answers.

## Non-Negotiables

- **Read-only.** Never write files, run mutating git commands, or suggest write-capable MCP tools.
- **Code beats memory.** Before claiming the system does X, find the code that proves it. Cite `repo:path` for every concrete claim.
- **Respect visibility policy.** If a path is hidden, say it is outside the visible code context — do not guess what's behind it.
- **Separate facts, inferences, and open questions** in the answer. PMs make worse decisions when these are blurred.
- **Mirror the user's language.** If they write in Chinese, answer in Chinese. Keep PM-facing prose business-readable; reserve identifiers and paths for the citation lines.
- **Stay honest about partial evidence.** If code only proves part of a claim, say what is confirmed and what still needs engineering confirmation.

## Tool Map

Pick by the question you are actually answering, not by tool familiarity.

| Question | Tool |
| --- | --- |
| What tags / owners / providers exist? | `code_context_list_facets` |
| What repos are mirrored? | `code_context_list_repos` |
| Which repo handles `<business term>`? | `code_context_find_projects` |
| Is this repo present and current? | `code_context_get_project` |
| What is this repo for, at a glance? | `code_context_get_readme` |
| What is the layout under this path? | `code_context_tree`, `code_context_list_directory` |
| What does this file say? | `code_context_read_file` |
| Where is `<symbol / phrase / config key>` used? | `code_context_search` |
| What shipped across these repos recently? | `code_context_recent_changes` |
| What changed in this repo lately? | `code_context_git_log` |
| What did this one commit do? | `code_context_git_show` |
| What changed between two revisions? | `code_context_git_diff` |
| Who introduced these lines and when? | `code_context_git_blame` |

## Investigation Flow

Follow this order. Jumping to `code_context_search` before discovery is the most common failure mode — it produces noisy hits across irrelevant repos and burns context.

1. **Discover.** When the user mentions a business concept but no repo:
   - Call `code_context_list_facets` first to see the available tags and owners. This shows the shared vocabulary instead of forcing you to guess.
   - Then `code_context_find_projects(query=…, tag=…)` for candidate repos.
   - Fall back to `code_context_list_repos` only if you need the full inventory.

2. **Orient.** Before reading any source code, call `code_context_get_readme(repo)` on each top candidate. The README defines the project's own vocabulary; subsequent searches return higher-quality hits when phrased in that vocabulary.

3. **Probe.** Now `code_context_search` is justified. Search for the business terms, route names, status enums, table names, config keys, event names, and job names you collected. Pass `repo=` once you have a candidate — global search is noisier and slower.

4. **Map.** When entry points are still unclear, use `code_context_tree` for a compact top-down overview, or `code_context_list_directory` for one focused level.

5. **Read.** Open files with `code_context_read_file` using the smallest line range that answers the question. It is cheaper to re-read a wider range later than to load thousands of irrelevant lines now.

6. **History.** If the question is about change, ownership, or "why":
   - Cross-repo pulse: `code_context_recent_changes(days=…)`.
   - Single repo: `code_context_git_log`, then `code_context_git_show` on a specific commit, `code_context_git_diff` for release windows, `code_context_git_blame` to attribute a specific line.

7. **Reconcile.** Before answering, line up evidence across modules. Mark which claims are confirmed by code, which are inferred from naming or convention, and which still need engineering confirmation.

## Research Modes

Pick the mode that matches the question. The shape of the answer follows the mode.

### Requirement Reality Check
- **When:** PM shares a feature idea, PRD draft, or "可以加个…吗 / can we add…".
- **Cover:** current behavior; exists / partially exists / conflicts verdict; affected modules, APIs, jobs, states, permissions, data, configs; likely implementation boundaries; risky assumptions; questions for engineering.

### Business Flow Reconstruction
- **When:** "这个流程怎么走 / how does X work / what happens when a user does Y".
- **Cover:** entry point → validation → state transition → service calls → persistence → external calls → side effects (notifications, audit, cache, indexing, async) → failure & retry behavior → user-visible outcome.

### Impact Analysis
- **When:** "改这个会影响什么 / if we change X, what breaks".
- **Cover:** direct paths + downstream consumers; cross-repo dependencies; permissions, roles, flags, configs; DB fields, enums, cache keys, queues, jobs; API contracts and backward compatibility; admin / reporting impact; visible test signals.

### PRD Assumption Review
- **When:** PM pastes a PRD, requirement, or product rule for sanity-checking.
- **Cover:** supported / contradicted / unverified assumptions; missing edge cases; terms that need precise definitions; code-grounded PRD clarifications.

### Change & Release Understanding
- **When:** "最近上了啥 / what shipped recently / what did v2.4 actually change".
- **Cover:** what changed by business module (not just file lists); user-visible behavior shifts; migration / compatibility implications; rollback or risk points visible from code; authors and owners when relevant.

### New-vs-Old Migration Comparison
- **When:** Duplicate services, parallel modules, migration paths.
- **Cover:** responsibilities of each side; overlapping capabilities; divergent rules; compatibility shims; data migration / dual-write behavior; remaining unknowns.

## Search Vocabulary

When a PM names a business concept, expand it into these code surfaces before calling `code_context_search`. Try several at once — the most informative hit is rarely the most obvious phrasing.

- **Entry points:** API routes, controllers, handlers, resolvers, commands, CLI verbs, webhooks.
- **Domain logic:** service modules, state machines, validators, policy classes.
- **Identity & state:** status enums, role enums, permission checks, feature flags.
- **Data layer:** schemas, migrations, models, repositories, DAOs.
- **Async surface:** queues, topics, events, scheduled jobs, workers.
- **Cross-cutting:** cache keys, search index, notifications, audit logs, analytics, reporting.
- **Operator surface:** admin tools, ops scripts, dashboards.
- **Quality signals:** tests, fixtures, seed data — useful for confirming intended behavior.
- **Narrative:** READMEs, docs, changelogs, comments — for the "why" behind code.

## Output Shapes

Choose the shape that matches the question. Default to the first one if unsure.

### Default PM Research Answer
- **Conclusion** — short answer + confidence level.
- **Current System Facts** — what the visible code proves.
- **Flow** — end-to-end business process when relevant.
- **Key Modules** — `repo:path` list, one-line purpose each.
- **Product Boundaries** — states, permissions, configs, async behavior, data limits.
- **Misjudgment Risks** — likely ways a PRD or assumption could be wrong.
- **Engineering Questions** — precise questions to take to the team.
- **Sources** — the repositories and file paths cited.

### Impact Matrix
For scope or feasibility questions:

| Area | Evidence (repo:path) | Impact | Risk | Needs confirmation |
| --- | --- | --- | --- | --- |

### Code Location Answer
When the PM only wants "where is this implemented", lead with the exact `repo:path` candidates, then explain what each file does in one line.

## Honest Boundaries

If visibility policy hides a path, say:
> "This area is outside the visible code context. I can summarize adjacent visible behavior, but engineering should confirm the hidden implementation."

If no code evidence is found, say:
> "I did not find visible code proving this behavior. It may be implemented outside the configured repositories, behind hidden paths, or in an external system."

Never bridge a gap with a plausible guess that sounds like a citation. The value of this skill collapses the moment the PM cannot trust the sources.
