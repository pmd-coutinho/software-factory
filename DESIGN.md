# Design

How the v2 factory works, and why it's built this way. The source is small
enough to read in one sitting: one skill, nine agents, three scripts and a
config file.

## The idea

A software factory turns a queue of requests into review-ready PRs with a fixed
pipeline. Scripts handle the deterministic stages, such as running the tests,
enforcing guards, and moving state. Agents do the judgment in between: whether a
request is worth building, what exactly to build, the code itself, and whether
it's good. Each stage leaves a file behind, so you can see what happened and
why. Every step's file opens with a `## Summary` of three to five bullets, so a
human can skim a job on the dashboard and read the detail only where it matters.

## Pieces

| Piece | File | Job |
|---|---|---|
| Queue | Jira tickets (Atlassian MCP) or GitHub issues labeled `factory` (`gh`) | What to build. Controlled by `tracker` in `factory/config.json`. |
| Orchestrator | `.claude/skills/factory/SKILL.md` | The session that runs `/factory`. Starts jobs, spawns agents, calls the scripts. Writes nothing itself. |
| Agents | `.claude/agents/*.md` | One file per role. Each reads files, writes its artifact, and replies with one line. |
| State | `factory/jobs/<job-id>/` | `job.json`, `events.jsonl`, plus every agent's file. Gitignored, local to the machine running the factory. |
| Spine | `factory/bin/job`, `gate`, `route` | Deterministic. `job` is the only writer of `job.json` and refuses illegal moves. |
| Checks | `factory/checks.sh` | The repo's test, lint, typecheck and build commands. The only repo-specific script. |
| Patterns | `factory/patterns.md` | Curated codebase exemplars, shared primitives, and gotchas read by spec, build, and review agents. |
| Exit | the PR | Every passing job ends as a PR with a human-review summary, marked ready for review. Merging it is the human approval. |

## Pipeline

```
Jira epic / ticket keys (Atlassian MCP)  OR  GitHub issues labeled `factory` (`gh`)
intake (fable)           → ACCEPT (scope possibly changed) | NEEDS-INFO | REJECT, posted as a comment
route (script)           → assigns reviewers from config.json (code + security always; ux + ui on `ui` surface)
worktree                 → factory/<job-id> from origin/<base>
spec-writer (opus high)  → spec.md with small, ordered chunks (## Implementation Plan)
builder (haiku)          → runs each chunk sequentially on the same worktree; final chunk pushes + opens draft PR
gate (script)            → clean-tree + protected-paths + timed checks.sh; FAIL → Haiku builder gets the log
reviewers (opus high)    → routed reviewers in parallel; WAIT FOR ALL
                           CHANGES → deduplicated Haiku review-fixer subagents → gate → reviewers
approver (opus high)     → writes human-review summary (decision.md) → PR comment (+ conflict check) → gh pr ready (NO auto-merge)
```

`stage` in `job.json` is one of `intake`, `needs-info`, `spec`, `build`,
`gate`, `review`, `approve`, `needs-human`, `merged`, `rejected`.
The legal moves are in `TRANSITIONS` at the top of `factory/bin/job`.

## Decisions

**Dual tracker support; you trigger the run.** `tracker` in `config.json`
selects `"jira"` (explicit epic/ticket keys via Atlassian MCP) or `"github"`
(open `factory`-labeled issues via `gh`). Nothing runs in GitHub Actions or on
a schedule: the factory runs on your machine, on your Claude plan, when you
start it.

**One orchestrator for every job.** The session running `/factory run` starts up
to `concurrency` jobs and spawns every agent as a background subagent. There
are no per-job orchestrators to coordinate. Its context stays small because
agents reply with one line and the scripts print one line; the detail lives in
files the next agent reads.

**Fable at the door, once.** Intake is the only Fable call per job. It decides
whether the ticket is worth building, rewrites the scope when it's too big or
vague, and asks the author when only they can answer. Questions go to the author
before a spec exists, so the spec writer never stalls on one.

**Opus plans and reviews; Haiku executes in small chunks.** `spec-writer` runs
on Opus (high) and breaks the work into small, ordered chunks with exact file
paths and signatures. Fresh Haiku `builder` subagents execute one chunk at a
time on the same worktree, and fresh Haiku `review-fixer` subagents fix
deduplicated review findings point by point.

**Surface-gated Opus (high) reviewers, configured in `config.json`.** Intake
rates risk (`low`, `medium`, `high`) and surfaces (`ui`, `security`).
`factory/bin/route` reads `reviewers` from `config.json`: by default `code` and
`security` run on every job (`"when": "always"`), while `ux` and `ui` run when
the `ui` surface is present (`"when": "surface:ui"`). Changing any entry to
`"always"` makes it unconditional without touching a prompt.

**Scripts decide whether it works.** `factory/bin/gate` runs the main checkout's
`checks.sh` inside the job's worktree with a configurable timeout
(`gate_timeout_seconds`, killing the process group on timeout). It fails any
branch with a dirty worktree or any add/modify/rename/delete under
`protected_paths` (factory scripts, checks, config, patterns, and agent/skill
definitions). `job advance build gate` also verifies `build.md` carries matching
`ROUND` and `COMMIT` headers so stale `STATUS: READY` files from earlier rounds
are rejected.

**Agents judge what scripts can't.** Reviewers don't re-run the test suite;
they read the diff for correctness, scope, security, UX and visual fit.

**You approve by merging — never auto-merged.** Every passing job ends with
`approver` writing a human-review summary in `decision.md`. `job advance`
checks PR mergeability (appending a conflict warning if needed), posts the
summary on the PR, and marks it ready for review (`gh pr ready`). Merge it on
GitHub to approve, or tell the factory what to change with `/factory <anything>`:
your words go to the builder as `feedback-<k>.md` (archiving `decision.md`) and
the job runs another round. Use `job cancel`, `job reject`, `job retry`, and
`job gc` for lifecycle management.

**State is files, so runs resume.** Every fact the orchestrator needs is in
`factory/jobs/` (`job.json`, `events.jsonl`, and stage artifacts). A global lock
serializes job creation and concurrency slots, and `pending_jira_comment` tracks
unposted Jira comments so crashes don't leave tickets silently parked.

**Cost and observability per job.** `factory/bin/job` parses Claude Code
subagent transcripts (cached in `factory/jobs/.cost-cache.json` by mtime/size),
prefix-matches models against `prices_usd_per_mtok` (warning rather than
crashing on unknown models), and records `cost_usd`, `cost_breakdown` (per-model
and token counts), `progress` (active chunk/fix), `updated_at` (for stale-job
detection on the dashboard), and an append-only `events.jsonl` timeline.

## Guardrails

- In `jira` mode, only explicitly named tickets/epics run. In `github` mode,
  only issues labeled `factory` run (labels need triage or write access).
- Ticket/issue text reaches agents as quoted data in `issue.md`, never pasted
  into a prompt. Intake has no shell.
- `protected_paths` blocks branches from touching factory scripts, config,
  checks, patterns, or agent/skill definitions.
- `build.md` `ROUND`/`COMMIT` headers prevent stale artifacts from advancing
  across rounds; `decision.md` is archived on feedback.
- Agents push only `factory/*` branches. The factory never auto-merges and never
  deploys.
- One PR per ticket/issue; at most `max_rounds` build rounds per job before a
  human is asked.
- `job cleanup-ports` deterministically reaps dev servers and browser sessions
  on a job's assigned ports after builder/UX/UI runs.

## What changed from v1

| v1 | v2 | Asked for by |
|---|---|---|
| `/factory <feature>`, one job per session | `/factory run` drains the issue queue, `concurrency` jobs at once, one orchestrator | Alex; @spec2k5, @MrHossamsaraya |
| Copy-paste build prompt | One install prompt pointing at this folder | @felipeclavijo1736 |
| Every job gets all four reviewers | Fable intake rates risk and surfaces; a script routes reviewers and models | @mptrista, @Robin-ox2mz |
| Every verdict is an LLM opinion | `checks.sh` gates before review and before merge | @Robin-ox2mz |
| Local `git merge`, needs a clean main checkout | A PR per issue, merged with `gh pr merge` | v1 on-camera merge failures |
| `/factory approve` | Merge the PR on GitHub | v1 |
| The spec writer can stall on questions | Intake asks on the issue and parks the job | @acidrazor |
| Cost invisible | Cost and time per job on the dashboard and in the run summary | the most common comment |
| No license | GPLv3, commercial licensing available | @mapledev9335 |
