#!/usr/bin/env bash
# Install a pinned uv in a repository-local, ignored tool environment.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
tool_dir="$repo_root/.multiverse/devtools"
uv_version=0.12.19
if [[ ! -x "$tool_dir/bin/python" ]]; then
  python3 -m venv "$tool_dir"
fi
"$tool_dir/bin/python" -m pip --disable-pip-version-check install "uv==$uv_version"
"$tool_dir/bin/uv" --version
printf 'Use: export PATH="%s/bin:$PATH"\n' "$tool_dir"
