#!/usr/bin/env python3
"""Focused unit & integration tests for factory/bin/{job,gate,route}."""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1]


class FactoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sf-test-"))
        self.origin = self.tmp / "origin.git"
        self.repo = self.tmp / "repo"
        self.fake_bin = self.tmp / "fake-bin"
        self.claude_dir = self.tmp / "claude"
        self.fake_bin.mkdir()
        self.claude_dir.mkdir()

        # Bare origin + working repo
        self._git(["init", "--bare", str(self.origin)], cwd=self.tmp)
        self._git(["init", "-b", "main", str(self.repo)], cwd=self.tmp)
        self._git(["config", "user.email", "test@example.com"], cwd=self.repo)
        self._git(["config", "user.name", "Tester"], cwd=self.repo)
        self._git(["remote", "add", "origin", str(self.origin)], cwd=self.repo)

        # Copy factory files into temp repo
        shutil.copytree(SRC_ROOT / "factory", self.repo / "factory")
        (self.repo / ".claude" / "agents").mkdir(parents=True)
        (self.repo / ".claude" / "agents" / "intake.md").write_text("# intake\n")
        (self.repo / "factory" / "checks.sh").write_text("#!/usr/bin/env bash\nset -euo pipefail\necho checks-ok\n")
        (self.repo / "factory" / "checks.sh").chmod(0o755)
        (self.repo / "app.txt").write_text("hello\n")

        self._git(["add", "."], cwd=self.repo)
        self._git(["commit", "-m", "initial"], cwd=self.repo)
        self._git(["push", "-u", "origin", "main"], cwd=self.repo)

        # Fake `gh` CLI controlled by GH_STATE_FILE
        self.gh_state_file = self.tmp / "gh-state.json"
        self.gh_state_file.write_text(json.dumps({
            "user": "tester",
            "pr_state": "OPEN",
            "is_draft": True,
            "mergeable": "MERGEABLE",
            "comments": [],
            "ready_calls": [],
            "closed_calls": [],
        }))
        gh_shim = self.fake_bin / "gh"
        gh_shim.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "sf = Path(os.environ['GH_STATE_FILE'])\n"
            "st = json.loads(sf.read_text())\n"
            "args = sys.argv[1:]\n"
            "if args[:2] == ['api', 'user']:\n"
            "    print(st['user'])\n"
            "elif args[:2] == ['pr', 'list']:\n"
            "    print(json.dumps([{'number': 42, 'url': 'https://example.test/pr/42'}]))\n"
            "elif args[:2] == ['pr', 'view']:\n"
            "    print(json.dumps({'state': st['pr_state'], 'isDraft': st['is_draft'], 'mergeable': st['mergeable'], 'mergeStateStatus': 'CLEAN'}))\n"
            "elif args[:2] == ['pr', 'comment']:\n"
            "    st['comments'].append(args)\n"
            "    sf.write_text(json.dumps(st))\n"
            "elif args[:2] == ['pr', 'ready']:\n"
            "    st['ready_calls'].append(args)\n"
            "    st['is_draft'] = False\n"
            "    sf.write_text(json.dumps(st))\n"
            "elif args[:2] == ['pr', 'close']:\n"
            "    st['closed_calls'].append(args)\n"
            "    sf.write_text(json.dumps(st))\n"
            "else:\n"
            "    sys.exit(0)\n"
        )
        gh_shim.chmod(gh_shim.stat().st_mode | stat.S_IEXEC)

        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.fake_bin}:{self.env['PATH']}"
        self.env["GH_STATE_FILE"] = str(self.gh_state_file)
        self.env["CLAUDE_CONFIG_DIR"] = str(self.claude_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, args, cwd):
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if res.returncode != 0:
            raise AssertionError(f"git {args} failed: {res.stderr}")
        return res.stdout.strip()

    def run_bin(self, name, *args, stdin=None, check=True):
        cmd = [str(self.repo / "factory" / "bin" / name), *args]
        res = subprocess.run(cmd, cwd=self.repo, input=stdin, capture_output=True, text=True, env=self.env)
        if check and res.returncode != 0:
            raise AssertionError(f"{name} {args} failed ({res.returncode}): {res.stderr}\n{res.stdout}")
        return res

    def create_jira_job(self, key="PROJ-101", title="Add export endpoint"):
        ticket = json.dumps({
            "key": key,
            "title": title,
            "author": "Alice",
            "url": f"https://jira.example.test/browse/{key}",
            "description": "Export data as CSV.",
            "comments": [{"author": "Alice", "created": "2026-01-01T00:00:00Z", "body": "Please include headers."}],
        })
        return self.run_bin("job", "create", key, stdin=ticket).stdout.strip()

    def write_intake(self, job_id, decision="ACCEPT", risk="low", surfaces="none"):
        (self.repo / "factory" / "jobs" / job_id / "intake.md").write_text(
            f"DECISION: {decision}\nRISK: {risk}\nSURFACES: {surfaces}\nRESCOPED: no\n\n## Summary\n- ok\n"
        )

    def advance_to_build(self, job_id, surfaces="none"):
        self.write_intake(job_id, "ACCEPT", "low", surfaces)
        self.run_bin("route", job_id)
        self.run_bin("job", "advance", job_id, "spec")
        self.run_bin("job", "jira-commented", job_id)
        (self.repo / "factory" / "jobs" / job_id / "spec.md").write_text("# Spec\n\n## Summary\n- ok\n")
        self.run_bin("job", "advance", job_id, "build")
        return json.loads((self.repo / "factory" / "jobs" / job_id / "job.json").read_text())

    def test_surface_gated_and_legacy_routing(self):
        jid1 = self.create_jira_job("PROJ-1", "Backend job")
        self.write_intake(jid1, surfaces="none")
        out = self.run_bin("route", jid1).stdout
        job1 = json.loads((self.repo / "factory" / "jobs" / jid1 / "job.json").read_text())
        self.assertEqual(set(job1["agents"]["reviewers"].keys()), {"code", "security"})
        self.assertIn("skipped: ux", out)

        jid2 = self.create_jira_job("PROJ-2", "Frontend job")
        self.write_intake(jid2, surfaces="ui")
        self.run_bin("route", jid2)
        job2 = json.loads((self.repo / "factory" / "jobs" / jid2 / "job.json").read_text())
        self.assertEqual(set(job2["agents"]["reviewers"].keys()), {"code", "security", "ux", "ui"})

    def test_stale_build_md_guard_and_gate_checks(self):
        jid = self.create_jira_job("PROJ-10", "Guard test")
        job = self.advance_to_build(jid)
        wt = Path(job["worktree"])
        (wt / "app.txt").write_text("changed\n")
        self._git(["add", "app.txt"], cwd=wt)
        self._git(["commit", "-m", "change app"], cwd=wt)
        self._git(["push", "-u", "origin", job["branch"]], cwd=wt)
        head = self._git(["rev-parse", "HEAD"], cwd=wt)

        # Missing ROUND / COMMIT must be refused
        (self.repo / "factory" / "jobs" / jid / "build.md").write_text("STATUS: READY\n\n# Build\n")
        res = self.run_bin("job", "advance", jid, "gate", check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("ROUND", res.stderr)

        # Wrong COMMIT must be refused
        (self.repo / "factory" / "jobs" / jid / "build.md").write_text(
            "STATUS: READY\nROUND: 1\nCOMMIT: deadbeef\n\n# Build\n"
        )
        res = self.run_bin("job", "advance", jid, "gate", check=False)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("COMMIT", res.stderr)

        # Matching ROUND and COMMIT succeeds
        (self.repo / "factory" / "jobs" / jid / "build.md").write_text(
            f"STATUS: READY\nROUND: 1\nCOMMIT: {head}\n\n# Build\n"
        )
        self.run_bin("job", "advance", jid, "gate")

        # Dirty worktree fails gate
        (wt / "untracked.tmp").write_text("oops")
        res = self.run_bin("gate", jid, check=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn("dirty worktree", res.stdout)
        (wt / "untracked.tmp").unlink()

        # Adding a file into protected `.claude/agents/*` fails gate
        (wt / ".claude" / "agents" / "evil.md").write_text("pwn")
        self._git(["add", ".claude/agents/evil.md"], cwd=wt)
        self._git(["commit", "-m", "try adding agent"], cwd=wt)
        res = self.run_bin("gate", jid, check=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn("protected paths changed", res.stdout)

        # Revert and confirm clean gate passes
        self._git(["reset", "--hard", head], cwd=wt)
        res = self.run_bin("gate", jid, check=False)
        self.assertEqual(res.returncode, 0)
        self.assertIn("GATE: PASS", res.stdout)

    def test_gate_timeout_kills_process_group(self):
        cfg_path = self.repo / "factory" / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["gate_timeout_seconds"] = 1
        cfg_path.write_text(json.dumps(cfg, indent=2))
        (self.repo / "factory" / "checks.sh").write_text("#!/usr/bin/env bash\nsleep 10\n")

        jid = self.create_jira_job("PROJ-11", "Timeout test")
        job = self.advance_to_build(jid)
        res = self.run_bin("gate", jid, check=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn("timed out", res.stdout)
        checks_md = (self.repo / "factory" / "jobs" / jid / "round-1" / "checks.md").read_text()
        self.assertIn("TIMED OUT", checks_md)

    def test_cost_unknown_model_no_crash_and_cache(self):
        jid = self.create_jira_job("PROJ-12", "Cost test")
        proj_slug = re.sub(r"[^A-Za-z0-9]", "-", str(self.repo))
        sub_dir = self.claude_dir / "projects" / proj_slug / "sess-1" / "subagents"
        sub_dir.mkdir(parents=True)
        transcript = sub_dir / "agent-1.jsonl"
        job_folder = f"{self.repo}/factory/jobs/{jid}/"
        lines = [
            json.dumps({"type": "user", "message": {"content": f"Job: {jid}. Job folder: {job_folder} Test."}}),
            json.dumps({
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "model": "claude-haiku-4-5-20251001",
                    "usage": {"input_tokens": 1000000, "output_tokens": 500000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            }),
            json.dumps({
                "type": "assistant",
                "message": {
                    "id": "m2",
                    "model": "claude-future-unknown-9",
                    "usage": {"input_tokens": 1000, "output_tokens": 1000},
                },
            }),
        ]
        transcript.write_text("\n".join(lines) + "\n")

        res = self.run_bin("job", "sync", jid)
        self.assertIn("unpriced model(s)", res.stderr)
        job = json.loads((self.repo / "factory" / "jobs" / jid / "job.json").read_text())
        # claude-haiku-4 prefix: 1M * 0.80 + 0.5M * 4.0 = 2.80
        self.assertEqual(job["cost_usd"], 2.8)
        self.assertEqual(job["unknown_models"], ["claude-future-unknown-9"])
        self.assertIn("claude-haiku-4-5-20251001", job["cost_breakdown"]["by_model"])
        self.assertTrue((self.repo / "factory" / "jobs" / ".cost-cache.json").exists())

    def test_progress_events_jira_outbox_feedback_cancel_retry_gc(self):
        jid = self.create_jira_job("PROJ-20", "Lifecycle test")
        job = self.advance_to_build(jid)
        self.run_bin("job", "progress", jid, "chunk 1/3: add endpoint")
        job = json.loads((self.repo / "factory" / "jobs" / jid / "job.json").read_text())
        self.assertEqual(job["progress"]["label"], "chunk 1/3: add endpoint")

        # Complete build → gate → review → approve → needs-human (with CONFLICTING PR)
        wt = Path(job["worktree"])
        (wt / "app.txt").write_text("v2\n")
        self._git(["add", "app.txt"], cwd=wt)
        self._git(["commit", "-m", "v2"], cwd=wt)
        self._git(["push", "-u", "origin", job["branch"]], cwd=wt)
        head = self._git(["rev-parse", "HEAD"], cwd=wt)
        (self.repo / "factory" / "jobs" / jid / "build.md").write_text(
            f"STATUS: READY\nROUND: 1\nCOMMIT: {head}\n\n# Build\n"
        )
        self.run_bin("job", "advance", jid, "gate")
        self.run_bin("gate", jid)
        self.run_bin("job", "advance", jid, "review")
        for r in ("code", "security"):
            (self.repo / "factory" / "jobs" / jid / "round-1" / f"review-{r}.md").write_text(
                "VERDICT: PASS\n\n## Summary\n- good\n"
            )
        self.run_bin("job", "advance", jid, "approve")
        (self.repo / "factory" / "jobs" / jid / "decision.md").write_text("READY\n\n## Summary\n- ship it\n")

        st = json.loads(self.gh_state_file.read_text())
        st["mergeable"] = "CONFLICTING"
        self.gh_state_file.write_text(json.dumps(st))

        self.run_bin("job", "advance", jid, "needs-human")
        job = json.loads((self.repo / "factory" / "jobs" / jid / "job.json").read_text())
        self.assertEqual(job["mergeable"], "CONFLICTING")
        self.assertIsNotNone(job["pending_jira_comment"])
        st = json.loads(self.gh_state_file.read_text())
        self.assertTrue(any("merge conflicts" in " ".join(c) for c in st["comments"]))

        # Clear pending_jira_comment
        self.run_bin("job", "jira-commented", jid)
        job = json.loads((self.repo / "factory" / "jobs" / jid / "job.json").read_text())
        self.assertIsNone(job["pending_jira_comment"])

        # Feedback archives decision.md immediately (even within the same second)
        self.run_bin("job", "feedback", jid, stdin="Please rename the variable.")
        jdir = self.repo / "factory" / "jobs" / jid
        self.assertFalse((jdir / "decision.md").exists())
        self.assertTrue((jdir / "decision-1.md").exists())
        self.assertTrue((jdir / "feedback-1.md").exists())

        # Cancel an in-progress `build` job
        self.run_bin("job", "cancel", jid, stdin="No longer needed.")
        job = json.loads((jdir / "job.json").read_text())
        self.assertEqual(job["stage"], "rejected")
        self.assertFalse(wt.exists())

        # Events log recorded full lifecycle
        events = [json.loads(l)["event"] for l in (jdir / "events.jsonl").read_text().splitlines()]
        for expected in ("create", "route", "stage", "progress", "gate", "jira_commented", "feedback", "cancel"):
            self.assertIn(expected, events)

        # Retry archives the rejected job cleanly
        self.run_bin("job", "retry", jid)
        self.assertFalse(jdir.exists())
        self.assertTrue(any((self.repo / "factory" / "jobs" / ".archived").iterdir()))

        # gc prunes orphaned worktrees
        orphan = self.repo / ".worktrees" / "999-orphan"
        orphan.mkdir(parents=True)
        out = self.run_bin("job", "gc").stdout
        self.assertIn("999-orphan", out)
        self.assertFalse(orphan.exists())


if __name__ == "__main__":
    unittest.main()
