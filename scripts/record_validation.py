# Records run on system Python 3.10 as well as the project Python.
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description="Record a command and its source snapshot.")
parser.add_argument("--output", type=pathlib.Path, default=root / ".multiverse/validation")
parser.add_argument("name")
parser.add_argument("cwd", help="Absolute path or path relative to repository root")
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.command:
    parser.error("a command is required")
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
name, cwd, cmd = args.name, args.cwd, args.command
if pathlib.Path(name).name != name or name in {".", ".."}:
    parser.error("name must be a single filename component")
if any((out / f"{name}.{suffix}").exists() for suffix in ("json", "log")):
    raise SystemExit("Evidence name already exists; choose a new name.")
started = datetime.datetime.now(datetime.timezone.utc).isoformat()  # noqa: UP017
files = (
    subprocess.check_output(
        [
            "git",
            "ls-files",
            "-co",
            "--exclude-standard",
            "scripts",
            ".python-version",
            "src",
            "tests",
            "inspector",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=root,
    )
    .decode()
    .splitlines()
)
snapshot = {
    p: hashlib.sha256((root / p).read_bytes()).hexdigest()
    for p in sorted(set(files))
    if (root / p).is_file()
}
proc = subprocess.run(cmd, cwd=root / cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(out / f"{name}.log").write_bytes(proc.stdout)
data = (json.dumps(snapshot, sort_keys=True, indent=2) + "\n").encode()
digest = hashlib.sha256(data).hexdigest()
name_snapshot = f"source-snapshot-{digest[:12]}.json"
(out / name_snapshot).write_bytes(data)
record = {
    "command": cmd,
    "cwd": str(root / cwd),
    "started_at": started,
    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),  # noqa: UP017
    "exit_code": proc.returncode,
    "log": f"{name}.log",
    "snapshot_ref": name_snapshot,
    "snapshot_digest": "sha256:" + digest,
}
(out / f"{name}.json").write_text(json.dumps(record, indent=2) + "\n")
print(name, "exit", proc.returncode)
print(proc.stdout.decode(errors="replace")[-3500:])
sys.exit(proc.returncode)
