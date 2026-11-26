# Software Factory for Claude Code (v2)

A software factory that works through **Jira tickets** (via Claude's
Atlassian/Jira MCP connector) or **GitHub Issues** — chosen at install time in
`factory/config.json` (`"tracker": "jira" | "github"`). Agents decide whether
each ticket/issue is worth building, write a chunked spec on Opus (high),
execute each chunk sequentially on Haiku, test it with your own checks, run
Opus (high) reviewers (`code` + `security` always, plus `ux` + `ui` on UI
surfaces, configurable in `config.json`), fix review findings point by point
on Haiku, write a human-review summary on the PR, and mark the PR ready for
review (never auto-merging).

## Install

Open Claude Code in your project and paste:

```text
Install this software factory in this project from the reference repository:

https://github.com/pmd-coutinho/software-factory
```

Your agent reads [`INSTALL.md`](INSTALL.md), copies the skill, agents, scripts
and dashboard, fills `factory/checks.sh` with your project's real test, lint,
typecheck and build commands, audits your codebase into `factory/patterns.md`,
tailors the reviewers to your stack, and checks that `checks.sh` passes on `main`.

You need Claude Code 2.1.257 or later, `python3`, and an authenticated
[`gh`](https://cli.github.com/) that can push to the repo.

## The loop

```
Jira epic / ticket keys (Atlassian MCP)  OR  GitHub issues labeled `factory` (`gh`)
        │
        ▼
intake (fable)          ── NEEDS-INFO → asks the reporter, waits for a reply
        │                  REJECT     → says why on ticket/issue
        ▼ ACCEPT, maybe rescoped; rates risk + surfaces
route (script)          assigns reviewers from config.json (code + security always; ux + ui on `ui` surface)
        ▼
spec-writer (opus high) → spec.md with small, ordered chunks
        ▼
builder (haiku)         → runs each chunk sequentially on the same worktree;
        │                 final chunk pushes + opens a draft PR
        ▼                 ▲
gate (script) ──FAIL──────┤  clean-tree + protected-paths + timed factory/checks.sh
        ▼ PASS            │
reviewers (opus high)     │  routed reviewers in parallel (later rounds: those that asked
        │   └─CHANGES─────┘  for changes + code/security); Haiku review-fixers fix findings point by point
        ▼ all PASS
approver (opus high)    → writes human-review summary on PR → marks PR ready (NO auto-merge)
```

One Claude Code session orchestrates every job, `concurrency` at a time
(default 3). Each job gets its own git worktree and branch. All state lives in
`factory/jobs/`, so if the session dies, re-running `/factory run <keys>` picks
every job back up.

## Commands

**Jira mode** (`"tracker": "jira"` — no bare `/factory run`):
```
/factory run <EPIC-KEY>            expand the epic's open child tickets and run them
/factory run <KEY-1> <KEY-2> ...   run specific Jira tickets (space-separated)
```

**GitHub Issues mode** (`"tracker": "github"`):
```
/factory run                       drain the queue: every open `factory`-labeled issue
/factory run <n> [<m> ...]         run specific GitHub issue(s) now
```

**Both modes:**
```
/factory <anything>                ask about jobs, give feedback, reject, or refresh-patterns
```

You approve by merging the PR on GitHub—the factory never auto-merges. To
change a PR, tell the factory what you want with `/factory`. To drop a job
that waits on you or on its reporter, tell the factory to reject it.

## What's in here

```
.claude/
  skills/factory/SKILL.md     the orchestrator: Jira/GitHub queue, concurrency, the pipeline
  agents/
    intake.md                 fable       worth building? at what scope? risk + surfaces
    spec-writer.md            opus high   spec.md with chunked implementation plan
    builder.md                haiku       executes spec chunks sequentially, commits, draft PR
    review-fixer.md           haiku       fixes review findings point by point
    reviewer-code.md          opus high   always-on: correctness, simplicity, tests
    reviewer-security.md      opus high   always-on: security
    reviewer-ux.md            opus high   ui surface (or always): user experience
    reviewer-ui.md            opus high   ui surface (or always): visual design
    approver.md               opus high   writes human-review summary on PR (no auto-merge)
factory/
  config.json                 concurrency, rounds, reviewer routing, timeouts, protected paths, prices
  checks.sh                   your repo's checks (the installer fills it in)
  patterns.md                 curated codebase patterns, exemplars & primitives (installer audits & fills)
  bin/job                     the only writer of job.json; guards, events, progress, cancel/retry/gc
  bin/gate                    clean-tree + protected-paths + timed checks.sh → round-N/checks.md
  bin/route                   assigns Opus (high) reviewers based on config.json & intake surfaces
  dashboard.html              the board (cards, chunk/fix progress, timeline, cost breakdown, logs)
INSTALL.md                    instructions for the installing agent
DESIGN.md                     how it works and why
```

[`DESIGN.md`](DESIGN.md) explains each decision and lists what changed from v1.

## Dashboard

```bash
cd factory && python3 -m http.server --bind 127.0.0.1
```

Keep `--bind 127.0.0.1`: without it the server listens on every interface and
anyone on your network can read ticket text, specs and check logs.

Open <http://localhost:8000/dashboard.html>. Each job is a card with its
ticket/issue and PR, active chunk/fix progress, a row of gate and review chips
per round, its risk, cost, stale indicator, and elapsed time. Click a card to
read every file the job wrote (including `checks.log` and the `events.jsonl`
timeline); each markdown file opens with a short summary of what happened in
that step.

Cost is the API-equivalent price of each job's agents, cached from Claude Code's
transcripts with per-model and token breakdowns. On a subscription plan it shows
where the spend goes, not what you're billed.

## Cost and safety

- It opens real PRs and runs on your Claude plan. Start with `concurrency: 1`
  and read every PR until you trust it.
- Intake runs on Fable once per ticket/issue. Depending on your plan, Fable can
  bill to usage credits rather than your plan's included usage.
- In `jira` mode, only explicitly named tickets/epics run. In `github` mode,
  only issues labeled `factory` run (labels need triage or write access). Ticket
  text reaches agents as quoted data in `issue.md`, never as their instructions.
- `protected_paths` fails any branch that adds, changes or deletes factory
  scripts, checks, config, patterns, agent/skill definitions, Claude settings,
  `.mcp.json`, CODEOWNERS or CI workflows. Workflows matter most: a factory
  branch lives in your repo, so a workflow it adds would run with the repo's
  secrets before anyone reviews the PR.
- In `jira` mode, only comments by the reporter, the operator and
  `jira_trusted_commenters` reach the agents (in `github` mode, the issue
  author's and the operator's).
- Agents are told to push only their `factory/*` branch. The factory never
  auto-merges and never deploys. If the PR head moves after the gate passed,
  the review summary on the PR says those commits weren't checked.

## License

[GPLv3](LICENSE). You can use, modify and share this code, and any version you
distribute must also be released under GPLv3.
