# Install the software factory

You are a coding agent installing this factory into the user's project. Copy
what's generic, adapt what's repo-specific, verify it, and report. Work in the
project's root. Don't clone this repository.

The source is the repository the user pointed you at. On GitHub, read files from
`https://raw.githubusercontent.com/pmd-coutinho/software-factory/main/<path>`.

## 0. Check the project

Stop and tell the user if any of these fail:

- It's a git repo with an `origin` on GitHub, and `gh auth status` shows a user
  who can push branches and open/update pull requests.
- Its default branch (`gh repo view --json defaultBranchRef`) exists on
  `origin`.
- Claude's Atlassian / Jira MCP connector is configured and can read Jira
  tickets/epics and post comments.
- `claude --version` is 2.1.257 or later (the intake agent runs on Fable).
- `python3 --version` is 3.10 or later. The scripts use only the standard
  library.
- None of the files in step 1 already exist. If one does, show the user the
  clash and ask before overwriting.

## 1. Copy

Copy these files to the same paths in the project, unchanged:

```
.claude/skills/factory/SKILL.md
.claude/agents/intake.md
.claude/agents/spec-writer.md
.claude/agents/builder.md
.claude/agents/review-fixer.md
.claude/agents/reviewer-code.md
.claude/agents/reviewer-security.md
.claude/agents/reviewer-ux.md
.claude/agents/reviewer-ui.md
.claude/agents/approver.md
factory/config.json
factory/checks.sh
factory/patterns.md
factory/bin/job
factory/bin/gate
factory/bin/route
factory/dashboard.html
```

```bash
SRC=https://raw.githubusercontent.com/pmd-coutinho/software-factory/main
for f in <the paths above>; do
  mkdir -p "$(dirname "$f")" && curl -fsSL "$SRC/$f" -o "$f"
done
chmod +x factory/checks.sh factory/bin/job factory/bin/gate factory/bin/route
```

Don't copy `README.md`, `DESIGN.md`, `INSTALL.md`, `LICENSE`, `examples/` or
`docs/`. They describe the reference, not the user's project.

## 2. Adapt

**`factory/checks.sh`.** Replace the placeholder with the project's real
checks: install dependencies if a fresh worktree needs them, then lint,
typecheck, tests and build, whichever the project has. Find them in
`AGENTS.md`, `CLAUDE.md`, `package.json` scripts, `Makefile`, `pyproject.toml`
and CI config. The script runs with a job's worktree as its working directory.
It must be non-interactive, must not rewrite files (no `--fix`, no
`--update-snapshots`), and must exit non-zero on any failure. Keep
`set -euo pipefail`.

**`factory/patterns.md` (Codebase audit).** Inspect the codebase thoroughly and
replace the `TODO` placeholders in `factory/patterns.md` with a concise,
high-leverage reference that `spec-writer` (Opus high), `builder` (Haiku),
`review-fixer` (Haiku), and `reviewer-code` read on every job.

How to audit:
- Survey the directory structure, package manifests, entry points, routing/API
  layer, data/DB layer, auth/permissions, UI/styling system, shared utilities,
  and test suites.
- Identify 1–2 **real, clean exemplar files** per major feature type (e.g., an
  API route/handler, a UI component/page, a service/data module, a test file).
  Avoid legacy or half-migrated files; check recent git history if unsure.
- Keep `factory/patterns.md` **under ~150 lines**. Prefer exact file paths and
  symbol names ("mirror `src/features/billing/api.ts`", "use `apiClient` from
  `src/lib/http.ts`") over long prose explanations, so it stays accurate and
  doesn't bloat agent context.
- Fill all five sections:
  1. **Architecture & Boundaries** — where new code belongs and forbidden
     imports / layer violations.
  2. **Canonical Exemplars** — real file paths to copy when adding each kind of
     code.
  3. **Shared Primitives** — auth, API/DB clients, error wrappers, state/query
     hooks, design tokens / shared UI components.
  4. **Testing & Fixtures** — test file placement, factories/fixtures, mocking
     conventions.
  5. **Gotchas & Anti-patterns** — traps linters don't catch and deprecated
     patterns not to imitate.

**`factory/config.json`.**

- `base_branch`: the default branch.
- `protected_paths`: keep the two factory entries and don't add the project's
  tests. Features legitimately change existing tests (a new required field
  changes every fixture), and a protected test blocks the job with no way
  through. The code reviewer catches weakened or special-cased tests instead.
  Add a path only when no job should ever change it. They are fnmatch
  patterns, so `*` also matches `/`.
- `ports`: move `base` if the project already uses ports 5100–5199.
- Leave `concurrency`, `max_rounds`, `reviewers`, `reviewer_effort` and
  `prices_usd_per_mtok` as they are unless the user asks.

**Agents.** The checklists are general on purpose. Tailor them to the stack
without changing their structure, file names, first-line formats or one-line
replies:

- `reviewer-security.md`: this project's hot spots (its auth, its data access
  rules, its payment and webhook code, where user input meets queries or HTML).
- `reviewer-ui.md`: where the design tokens, theme and shared components live.
- `reviewer-ux.md`: the kinds of users the app has.
- `approver.md`: what a human must always see in this project, added to the
  ESCALATE list.
- `intake.md`: one line under **Decide** saying what the project is for, so
  intake can tell what belongs.

**`AGENTS.md`** (or `CLAUDE.md`, whichever the project uses; create `AGENTS.md`
if neither exists). Every agent reads it. Make sure it says:

- how to set up a fresh checkout (install dependencies, env files to copy);
- how to start the dev server on a given port, if the project has one;
- the validation commands, matching `factory/checks.sh`.

Then add a short section:

```markdown
## Software factory

`/factory run <EPIC-KEY | KEY-1 KEY-2 ...>` builds Jira tickets (via the
Atlassian/Jira MCP connector) through intake → spec (Opus high, chunked) →
build (sequential Haiku chunks) → gate → 4× Opus (high) reviews (with Haiku
point-by-point fixes) → PR human-review summary, one PR per ticket (never
auto-merged). State is in `factory/jobs/` (gitignored); `factory/bin/job` is
its only writer. Checks: `factory/checks.sh`. Dashboard:
`cd factory && python3 -m http.server`, then open http://localhost:8000/dashboard.html.

Each job works in its own git worktree, a full checkout of the repo at
`.worktrees/<job-id>` (gitignored). A tool run from the repo root that doesn't
read `.gitignore` sees those copies too; exclude `.worktrees/` in its config.
```

**`.gitignore`.** Append these two lines:

```gitignore
/factory/jobs/
/.worktrees/
```

`factory/jobs/` is runtime state (job metadata, specs, reviews, check logs)
local to the machine running the factory. Each job's worktree is a full
checkout in `.worktrees/<job-id>`. Neither belongs in the repo. Everything you
copied in step 1 does: the skill in `.claude/skills/factory/`, the agents in
`.claude/agents/` and the rest of `factory/` are part of the project and get
committed, so ignore only these two paths, never `.claude/` or `factory/`.

## 3. Verify

1. In the project root, on the current branch, `bash factory/checks.sh` exits 0.
   If it fails there, the factory can never pass a job: fix the
   script (not the project) or tell the user what's broken.
2. `factory/bin/job status` runs without an error (and bare `factory/bin/job queue`
   exits non-zero reminding you to pass ticket keys).
3. Each file in `.claude/agents/` has only these frontmatter keys: `name`,
   `description`, `tools`, `model`, and optional `effort`. Claude Code ignores
   unknown keys without a warning, so a typo silently changes behaviour.
4. `python3 -m json.tool factory/config.json` succeeds.
5. `factory/patterns.md` has no `TODO` placeholders left, cites real paths that
   exist in the repo, and stays concise (~150 lines or fewer).
6. `git check-ignore factory/jobs/x .worktrees/x` prints both paths, and
   `git status --porcelain --untracked-files=all` lists every file from step 1
   (the skill, the agents and `factory/`) as committable.

## 4. Hand over

Stay on the branch the user is on: don't create or check out another branch.
Commit the install there with a one-line message and show the user the diff.
Ask before pushing: the factory branches every job from `origin/<base_branch>`,
so the install must be on that branch there before the first run.

Then tell the user, in a few lines:

- Run `/factory run <EPIC-KEY>` or `/factory run <KEY-1> <KEY-2>` in Claude
  Code from the project root (there is no bare `/factory run`).
- Every passing job ends as a PR with a human-review summary comment, marked
  ready for review — the factory never auto-merges. Merge it on GitHub to
  approve, or tell the factory what to change with `/factory <anything>`.
- Intake runs on Fable, once per ticket. Depending on their plan, Fable can
  bill to usage credits rather than the plan's included usage.
- To start carefully, set `concurrency` to 1 in `factory/config.json` and read
  every PR until they trust it.
