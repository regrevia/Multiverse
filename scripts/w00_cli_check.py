# Runs on system Python 3.10 as well as the project Python.
import argparse
import datetime
import json
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
scratch = root / ".multiverse/w00"
scratch.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser(description="Exercise W00 read-only CLI acceptance cases.")
parser.add_argument("--output", type=pathlib.Path, help="New directory for evidence")
args = parser.parse_args()
if args.output is None:
    out = pathlib.Path(tempfile.mkdtemp(prefix="cli-results-", dir=scratch))
else:
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
print(f"CLI evidence directory: {out}")
uv = root / ".multiverse/devtools/bin/uv"
with tempfile.TemporaryDirectory(prefix="cli-", dir=root / ".multiverse/w00") as temp:
    cwd = pathlib.Path(temp)
    cases = [
        ("capabilities", ["capabilities", "--json"], 0),
        (
            "validate-local",
            [
                "validate",
                str(root / "presets/content-delivery"),
                "--binding",
                str(root / "examples/bindings/content-local.yaml"),
                "--json",
            ],
            0,
        ),
        (
            "validate-remote",
            [
                "validate",
                str(root / "presets/content-delivery"),
                "--binding",
                str(root / "examples/bindings/content-remote.yaml"),
                "--json",
            ],
            0,
        ),
        (
            "preflight-local",
            [
                "preflight",
                str(root / "presets/content-delivery"),
                "--binding",
                str(root / "examples/bindings/content-local.yaml"),
                "--json",
            ],
            0,
        ),
        (
            "preflight-remote",
            [
                "preflight",
                str(root / "presets/content-delivery"),
                "--binding",
                str(root / "examples/bindings/content-remote.yaml"),
                "--json",
            ],
            2,
        ),
    ]
    records = []
    for name, args, expected in cases:
        command = [str(uv), "run", "--project", str(root), "--locked", "mverse", *args]
        before = sorted(str(p.relative_to(cwd)) for p in cwd.rglob("*"))
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()  # noqa: UP017
        r = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        after = sorted(str(p.relative_to(cwd)) for p in cwd.rglob("*"))
        (out / f"{name}.log").write_text(r.stdout + r.stderr)
        payload = json.loads(r.stdout)
        record = {
            "name": name,
            "command": command,
            "cwd": str(cwd),
            "started_at": started,
            "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),  # noqa: UP017
            "exit_code": r.returncode,
            "expected_exit_code": expected,
            "files_before": before,
            "files_after": after,
            "log": f"{name}.log",
        }
        records.append(record)
        assert r.returncode == expected, (name, r.returncode)
        assert before == after == [], (name, before, after)
        if name == "preflight-remote":
            assert payload["ok"] is False
            assert {d["code"] for d in payload["diagnostics"]} == {
                "EXECUTOR_NOT_INSTALLED",
                "EXECUTOR_UNAVAILABLE",
                "EXECUTOR_UNVERIFIED",
            }
        print(name, "exit", r.returncode, "workspace remains empty")
    (out / "cli-results.json").write_text(json.dumps(records, indent=2) + "\n")
