#!/usr/bin/env python3
"""Read-only milestone record consistency gate; never fetches or pushes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

STATUSES = {
    "pending",
    "in_progress",
    "testing",
    "waiting_external",
    "reviewing",
    "blocked",
    "ready_to_push",
    "push_pending",
    "completed",
}
ACTIVE = {"in_progress", "testing", "reviewing", "ready_to_push"}
BACKGROUND = {
    "source_commit",
    "artifact_digests",
    "isolated_environment",
    "task_id",
    "log_ref",
    "checkpoint",
    "next_check_at",
    "resume_command",
}


class Invalid(ValueError):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise Invalid("timestamp must include timezone")
    return parsed


class Gate:
    def __init__(self, repo, state="docs/development/STATE.json", report=None, now=None):
        self.repo = Path(repo).resolve()
        self.state_path = self.path(state)
        self.state_rel = self.state_path.relative_to(self.repo).as_posix()
        self.state = json.loads(self.state_path.read_text())
        self.packages = self.state["work_packages"]
        self.by_id = {p["id"]: p for p in self.packages}
        self.report_override = report
        self.now = now or datetime.now(UTC)
        policy = self.state.get("push_policy", {})
        self.remote = f"refs/remotes/{policy.get('remote', 'origin')}/{policy.get('branch', 'dev')}"

    def path(self, value):
        path = (self.repo / value).resolve()
        if not path.is_relative_to(self.repo):
            raise Invalid("path outside repository")
        return path

    def git(self, *args, required=True):
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            check=False,
        )
        if required and result.returncode:
            raise Invalid(f"git {args[0]} failed")
        return result

    def excluded(self, path):
        return path == self.state_rel or path.startswith("docs/development/reports/")

    def snapshot(self, revision=None):
        files = {}
        if revision:
            entries = self.git("ls-tree", "-rz", "--full-tree", revision).stdout.split(b"\0")
            for entry in filter(None, entries):
                metadata, name = entry.split(b"\t", 1)
                mode, kind, oid = metadata.decode().split()
                path = os.fsdecode(name)
                if self.excluded(path):
                    continue
                if kind != "blob":
                    raise Invalid("submodules are not supported in snapshots")
                content = self.git("cat-file", "blob", oid).stdout
                files[path] = {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
        else:
            names = self.git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
            for name in sorted(set(filter(None, names.stdout.split(b"\0")))):
                path = os.fsdecode(name)
                if self.excluded(path):
                    continue
                target = self.repo / path
                if not target.exists() and not target.is_symlink():
                    continue  # Deletions are represented by absence, matching the committed tree.
                if target.is_symlink():
                    content, mode = os.fsencode(os.readlink(target)), "120000"
                elif target.is_file():
                    content = target.read_bytes()
                    mode = "100755" if target.stat().st_mode & 0o111 else "100644"
                else:
                    raise Invalid(f"unsupported snapshot entry: {path}")
                files[path] = {"sha256": hashlib.sha256(content).hexdigest(), "mode": mode}
        return {"files": files, "digest": digest(files)}

    def plan_errors(self):
        errors = []
        if len(self.by_id) != len(self.packages):
            errors.append("duplicate package IDs")
        for p in self.packages:
            if p.get("status") not in STATUSES:
                errors.append(f"{p['id']}: invalid status")
            deps = p.get("depends_on")
            if not isinstance(deps, list) or any(d not in self.by_id for d in deps):
                errors.append(f"{p['id']}: invalid dependencies")
        visiting, visited = set(), set()

        def visit(pid):
            if pid in visiting:
                errors.append(f"dependency cycle: {pid}")
                return
            if pid in visited:
                return
            visiting.add(pid)
            for dep in self.by_id[pid].get("depends_on", []):
                if dep in self.by_id:
                    visit(dep)
            visiting.remove(pid)
            visited.add(pid)

        for pid in self.by_id:
            visit(pid)
        return errors

    def background_errors(self, p):
        bg = p.get("background_validation", {})
        errors = [
            f"{p['id']}: missing background {key}" for key in sorted(BACKGROUND) if not bg.get(key)
        ]
        env = bg.get("isolated_environment")
        if not isinstance(env, dict) or not all(
            env.get(k) for k in ("workspace", "database", "ports")
        ):
            errors.append(f"{p['id']}: isolated workspace/database/ports required")
        elif Path(env["workspace"]).resolve() == self.repo:
            errors.append(f"{p['id']}: background workspace is active repository")
        try:
            timestamp(bg.get("next_check_at", ""))
        except (ValueError, TypeError, AttributeError):
            errors.append(f"{p['id']}: invalid next_check_at")
        source = bg.get("source_commit", "")
        if (
            not source
            or self.git("cat-file", "-e", f"{source}^{{commit}}", required=False).returncode
        ):
            errors.append(f"{p['id']}: missing source commit")
        return errors

    def report_paths(self, p):
        report = self.path(self.state_path.parent / p["report"])
        evidence = self.path(
            self.report_override
            or (self.state_path.parent / p["evidence"] if p.get("evidence") else None)
            or str(report.with_name("EVIDENCE.json"))
        )
        return report, evidence

    def reference_errors(self, reference, revision=None):
        """References are nonempty repository files; fragments identify receipt/log sections."""
        try:
            path = self.path(reference.split("#", 1)[0])
            if not path.is_file() or not path.read_bytes():
                return ["missing evidence reference file"]
            if revision:
                relative = path.relative_to(self.repo).as_posix()
                for ref in (revision, self.remote):
                    result = self.git("show", f"{ref}:{relative}", required=False)
                    if result.returncode or result.stdout != path.read_bytes():
                        return ["evidence reference not preserved in implementation and remote"]
        except (OSError, ValueError, TypeError, AttributeError):
            return ["invalid evidence reference"]
        return []

    def evidence_errors(self, p, revision=None):
        errors = []
        try:
            report, evidence_path = self.report_paths(p)
            if not report.is_file() or not report.read_text().strip():
                return ["missing report"]
            evidence = json.loads(evidence_path.read_text())
        except (OSError, KeyError, TypeError, ValueError):
            return ["missing or invalid report/evidence"]
        if evidence.get("package_id") != p["id"]:
            errors.append("evidence package mismatch")
        snapshot = self.snapshot(revision)
        if evidence.get("snapshot") != snapshot:
            errors.append("stale or incomplete snapshot (includes untracked files)")
        expected = snapshot["digest"]
        tests = evidence.get("tests", [])
        required = evidence.get("required_tests", [])
        if not required or len(set(required)) != len(required):
            errors.append("required_tests must be nonempty and unique")
        indexed = {t.get("id"): t for t in tests}
        if len(indexed) != len(tests):
            errors.append("duplicate test IDs")
        for test_id in required:
            if test_id not in indexed:
                errors.append(f"{test_id}: required test record missing")
        for test in tests:
            test_id = test.get("id")
            fields = ("id", "command", "cwd", "tool_versions", "started_at", "log_ref")
            if not all(test.get(k) for k in fields):
                errors.append(f"{test_id}: incomplete test record")
            errors += self.reference_errors(test.get("log_ref"), revision)
            counts = [test.get(k) for k in ("passed", "failed", "skipped")]
            if any(type(n) is not int or n < 0 for n in counts):
                errors.append(f"{test_id}: invalid result counts")
            if test.get("exit_code") != 0 or test.get("failed") != 0:
                errors.append(f"{test_id}: test failed")
            if (
                test_id in required
                and test.get("live")
                and (test.get("skipped") != 0 or not test.get("passed"))
            ):
                errors.append(f"{test_id}: required live acceptance not passed")
            if test.get("snapshot_digest") != expected:
                errors.append(f"{test_id}: stale test snapshot")
        acceptance = evidence.get("acceptance", [])
        if not acceptance or any(
            a.get("status") != "passed" or not a.get("evidence_ref") for a in acceptance
        ):
            errors.append("acceptance missing or not passed")
        for item in acceptance:
            errors += self.reference_errors(item.get("evidence_ref"), revision)
        reviews = evidence.get("reviews", [])
        if not reviews:
            errors.append("missing independent review record")
        for review in reviews:
            errors += self.reference_errors(review.get("record_ref"), revision)
            if not all(review.get(k) for k in ("task_id", "tool", "record_ref", "scope")):
                errors.append("review missing actual tool record reference")
            if "limitations" not in review or review.get("verdict") != "approved":
                errors.append("review not approved or limitations missing")
            if review.get("snapshot_digest") != expected:
                errors.append("stale review snapshot")
            if review.get("blocking_findings", []) or review.get("reviewer_role") != "independent":
                errors.append("review unresolved or not independent")
        return errors

    def remote_errors(self, p):
        if p.get("status") != "completed":
            return ["not completed"]
        commit = p.get("implementation_commit")
        if (
            not commit
            or self.git(
                "merge-base",
                "--is-ancestor",
                commit,
                self.remote,
                required=False,
            ).returncode
        ):
            return ["implementation commit not in remote history"]
        remote_state = self.git("show", f"{self.remote}:{self.state_rel}", required=False)
        try:
            packages = json.loads(remote_state.stdout)["work_packages"]
            receipt = next(q for q in packages if q["id"] == p["id"])
        except (ValueError, KeyError, StopIteration):
            return ["remote state receipt missing"]
        if any(
            receipt.get(k) != p.get(k)
            for k in (
                "status",
                "implementation_commit",
                "report",
                "evidence",
                "depends_on",
            )
        ):
            return ["state receipt pending push or inconsistent"]
        errors = self.evidence_errors(p, commit)
        try:
            for path in self.report_paths(p):
                relative = path.relative_to(self.repo).as_posix()
                for ref in (commit, self.remote):
                    result = self.git("show", f"{ref}:{relative}", required=False)
                    if result.returncode or result.stdout != path.read_bytes():
                        errors.append("report/evidence not preserved in implementation and remote")
        except (OSError, KeyError, TypeError, ValueError):
            errors.append("missing committed report")
        return errors

    def check(self, pid, phase=None):
        p = self.by_id[pid]
        errors = self.plan_errors()
        for dep in p["depends_on"]:
            errors += [f"dependency {dep}: {e}" for e in self.remote_errors(self.by_id[dep])]
        phase = phase or ("remote" if p["status"] == "completed" else "pre-push")
        if phase == "remote":
            errors += self.remote_errors(p)
        else:
            if p["status"] not in {"reviewing", "ready_to_push", "push_pending"}:
                errors.append("pre-push requires reviewing/ready_to_push/push_pending")
            if p.get("blockers"):
                errors.append("unresolved blockers")
            errors += self.evidence_errors(p)
        return {"ok": not errors, "package_id": pid, "phase": phase, "errors": errors}

    def next(self):
        errors = self.plan_errors()
        if errors:
            return {"ok": False, "errors": errors}
        for p in self.packages:
            if p["status"] == "push_pending":
                return {"ok": True, "package_id": p["id"], "action": "retry_implementation_push"}
            if p["status"] == "completed":
                problems = self.remote_errors(p)
                if problems:
                    return {
                        "ok": True,
                        "package_id": p["id"],
                        "action": "reconcile_remote_receipt",
                        "reasons": problems,
                    }
        waiting = [p for p in self.packages if p["status"] == "waiting_external"]
        for p in waiting:
            errors += self.background_errors(p)
        if errors:
            return {"ok": False, "errors": errors}
        due = [
            p for p in waiting if timestamp(p["background_validation"]["next_check_at"]) <= self.now
        ]
        if due:
            return {"ok": True, "package_id": due[0]["id"], "action": "resume_external"}
        active = [p for p in self.packages if p["status"] in ACTIVE]
        if len(active) > 1:
            return {
                "ok": False,
                "errors": ["multiple foreground active packages require coordination"],
            }
        if active:
            p = active[0]
            deps = [d for d in p["depends_on"] if self.remote_errors(self.by_id[d])]
            if deps:
                return {"ok": False, "errors": [f"active package dependencies not remote: {deps}"]}
            return {"ok": True, "package_id": p["id"], "action": "resume"}
        for p in self.packages:
            if p["status"] == "pending" and not any(
                self.remote_errors(self.by_id[d]) for d in p["depends_on"]
            ):
                return {"ok": True, "package_id": p["id"], "action": "start"}
        return {"ok": False, "errors": ["no ready package"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--state", default="docs/development/STATE.json")
    parser.add_argument("--report", help="override evidence JSON path (for selected package)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("next")
    sub.add_parser("check-plan")
    sub.add_parser("snapshot")
    check = sub.add_parser("check")
    check.add_argument("id")
    check.add_argument("--phase", choices=["pre-push", "remote"])
    args = parser.parse_args(argv)
    try:
        gate = Gate(args.repo, args.state, args.report)
        if args.command == "next":
            result = gate.next()
        elif args.command == "check-plan":
            errors = gate.plan_errors()
            if not errors:
                for package in gate.packages:
                    if package["status"] == "completed":
                        errors += gate.remote_errors(package)
                    elif package["status"] == "waiting_external":
                        errors += gate.background_errors(package)
            result = {"ok": not errors, "errors": errors}
        elif args.command == "snapshot":
            result = {"ok": True, "snapshot": gate.snapshot()}
        else:
            result = gate.check(args.id, args.phase)
        result["remote_freshness"] = (
            "caller must fetch remote refs; this command never uses network"
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["ok"] else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid input: {exc}"]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
