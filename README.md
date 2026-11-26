# Software Factory for Claude Code (v2)

A software factory that works through **Jira tickets** (via Claude's
Atlassian/Jira MCP connector) or **GitHub Issues** — chosen at install time in
`factory/config.json` (`"tracker": "jira" | "github"`). Agents decide whether
each ticket/issue is worth building, write a chunked spec on Opus (high),
execute each chunk sequentially on Haiku, test it with your own checks, run
all four mandatory Opus (high) reviewers, fix review findings point by point
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
Jira epic or space-separated ticket keys (Atlassian/Jira MCP connector)
        │
        ▼
intake (fable)          ── NEEDS-INFO → asks the reporter on Jira, waits for a reply
        │                  REJECT     → says why on Jira
        ▼ ACCEPT, maybe rescoped; rates risk + surfaces
route (script)          assigns all 4 mandatory reviewers on opus (high)
        ▼
spec-writer (opus high) → spec.md with small, ordered chunks
        ▼
builder (haiku)         → runs each chunk sequentially on the same worktree;
        │                 final chunk pushes + opens a draft PR
        ▼                 ▲
gate (script) ──FAIL──────┤  factory/checks.sh; no reviewer runs on a failing build
        ▼ PASS            │
reviewers (4× opus high)  │  code, security, ux, ui (ALL 4 MANDATORY) in parallel
        │   └─CHANGES─────┘  Haiku review-fixer subagents fix findings point by point
        ▼ all 4 PASS
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

## The guide

This folder is the companion to **A Developer's Guide to Software Factories**,
a short PDF on how factories like this one work and how to run yours. I'll send
you a copy when you [sign up to my newsletter](https://zazencodes.com/newsletter?utm_source=github&utm_medium=referral&utm_campaign=software-factory-claude-code-v2).

<p align="center">
  <a href="https://zazencodes.com/newsletter?utm_source=github&utm_medium=referral&utm_campaign=software-factory-claude-code-v2">
    <img
      src="docs/assets/software-factories-guide-promo.png"
      alt="Software Factories — a developer's guide to issue-driven pipelines for coding agents"
      width="100%"
    >
  </a>
  <br>
  <a href="https://zazencodes.com/newsletter?utm_source=github&utm_medium=referral&utm_campaign=software-factory-claude-code-v2">Get the free PDF</a>
</p>

## What's in here

```
.claude/
  skills/factory/SKILL.md     the orchestrator: Jira connector, concurrency, the pipeline
  agents/
    intake.md                 fable       worth building? at what scope? risk + surfaces
    spec-writer.md            opus high   spec.md with chunked implementation plan
    builder.md                haiku       executes spec chunks sequentially, commits, draft PR
    review-fixer.md           haiku       fixes review findings point by point
    reviewer-code.md          opus high   mandatory: correctness, simplicity, tests
    reviewer-security.md      opus high   mandatory: security
    reviewer-ux.md            opus high   mandatory: user experience
    reviewer-ui.md            opus high   mandatory: visual design
    approver.md               opus high   writes human-review summary on PR (no auto-merge)
factory/
  config.json                 concurrency, rounds, mandatory reviewers, protected paths, prices
  checks.sh                   your repo's checks (the installer fills it in)
  patterns.md                 curated codebase patterns, exemplars & primitives (installer audits & fills)
  bin/job                     the only writer of job.json; refuses illegal moves; marks PR ready
  bin/gate                    runs checks.sh in a job's worktree → round-N/checks.md
  bin/route                   assigns all 4 mandatory Opus (high) reviewers
  dashboard.html              the board
examples/jobs/                finished jobs from a real run
INSTALL.md                    instructions for the installing agent
DESIGN.md                     how it works and why
```

[`DESIGN.md`](DESIGN.md) explains each decision and lists what changed from
[v1](../software-factory-claude-code).

## Dashboard

```bash
cd factory && python3 -m http.server
```

Open <http://localhost:8000/dashboard.html>. Each job is a card with its issue
and PR, a row of gate and review chips per round, its risk, cost and
time. Click a card to read every file the job wrote; each one opens with a
short summary of what happened in that step. To see the example
jobs, copy `examples/jobs/` to `factory/jobs/` first.

Cost is the API-equivalent price of each job's agents, read from Claude Code's
transcripts. On a subscription plan it shows where the spend goes, not what
you're billed.

## The example jobs

They come from a test run on a small private calculator repo, with
`concurrency: 2` and every agent on Haiku to keep it cheap.

- **001-add-a-subtract-function**: low risk, no UI, so only the code reviewer
  ran. Approved and merged through its PR.
- **002-show-a-history-of**: a UI change, so the UX and UI reviewers ran too.
  Merged.
- **003-add-multiply-divide-power**: intake cut an oversized "scientific
  calculator" issue down to three functions. The gate failed round 1 because
  the builder edited a protected test file, and the job went to a human after
  three rounds.
- **005-add-a-crypto-miner**: rejected at intake.

## Cost and safety

- It opens and merges real PRs and runs on your Claude plan. Start with
  `concurrency: 1` and read every PR until you trust it.
- Intake runs on Fable once per issue. Depending on your plan, Fable can bill
  to usage credits rather than your plan's included usage.
- Only issues labeled `factory` run, and only people with triage or write
  access can add labels. Issue text reaches the agents as quoted data, never
  as their instructions.
- The factory pushes only `factory/*` branches, merges only through
  `gh pr merge`, and never deploys.

## More from ZazenCodes

- **Agentic Coding Fundamentals**, the full course:
  <https://zazencodes.com/courses/agentic-coding-fundamentals>
- **Newsletter**, one email a week: <https://zazencodes.com/newsletter>
- **YouTube**: <https://youtube.com/@ZazenCodes>

## License

[GPLv3](LICENSE). You can use, modify and share this code, and any version you
distribute must also be released under GPLv3.

Want to use this in closed-source or commercial software? Get in touch for a commercial license.

<p align="center">
  <a href="https://zazencodes.com/?utm_source=github&utm_medium=referral&utm_campaign=software-factory-claude-code-v2">
    <img
      src="docs/assets/zazencodes-banner.png"
      alt="ZazenCodes — Engineering for the Agentic Era"
      width="100%"
    >
  </a>
  <br>
  Created by <a href="https://zazencodes.com/">ZazenCodes</a>
</p>
