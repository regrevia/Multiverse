# W05A: Claude 执行端适配 checkpoint

日期：2026-09-30
当前实现基线：待 W05A checkpoint 提交
依赖：W03（已完成并已推送）
状态：`checkpoint_only`

## 已交付

- 新增 `runtime/claude.py`，使用 Claude Code `--print --output-format json`
  或 `stream-json` 的结构化单次新会话接口。
- 固定显式工作目录、workspaceRoot、homeDir、permissionMode、model、
  timeout 和 maxOutputBytes。
- Claude JSON/JSONL envelope、result JSON、事件分片、未知请求、拒绝结果、
  非零退出、超时、坏输出、输出上限、cooperative stop 均有明确异常分类。
- 新增 `execute_claude` 和通用 `execute_agent(adapter, ...)`，复用
  Runtime-owned Artifact 和统一 `ExecutionResult`，Runner 不按 provider 增加
  专用执行分支。
- 注册 `builtin.claude-deliverable.v1`、配置 Schema、协议 adapter 类型和
  `examples/bindings/content-claude.yaml`。
- W05A fixture 测试覆盖 JSON/stream-json 结构化结果、真实
  `delta.text` 分片、非零退出、超时、输出上限、坏 JSON、拒绝和未知请求；
  Executor → Runtime verifier → HumanRequest 的 fixture 也通过。
- 新增显式 live probe：
  `tests/integration/test_claude_live.py`。

## 验证

```text
uv run --python 3.12 --locked pytest -q \
  tests/runtime/test_claude.py \
  tests/runtime/test_executors.py \
  tests/runtime/test_catalog.py \
  tests/runtime/test_claude_runner.py \
  tests/compiler
118 passed

uv run --python 3.12 --locked ruff check src tests
passed

uv run --python 3.12 --locked mypy src
passed
```

Live probe command:

```text
MULTIVERSE_RUN_CLAUDE_LIVE=1 \
uv run --python 3.12 --locked pytest -q \
tests/integration/test_claude_live.py
```

本机 Claude Code 版本：`2.1.197`。直接结构化 probe 返回：
`Not logged in · Please run /login`。因此 live probe 当前准确记录为
blocked，未伪造真实 Claude 任务/产物证据。

## 边界

- 当前只实现新会话单次 print-json/stream-json 适配；resume/fork、跨 CLI handoff、
  原生 Claude 交互和多会话身份留给 W06/W07。
- 未登录/无配额时保持 blocked；不会换成 Anthropic API、Codex 或固定回显
  冒充 Claude live。
- 本机 Claude Code `2.1.197` 未登录，live probe 返回 `/login`，因此 W05A
  保持 blocked/pending；不会用 Codex、Anthropic API 或固定回显冒充 Claude live。

完整 Python 回归：`543 passed, 13 skipped`，日志在
`docs/development/reports/W05A/final-tests/python-full.log`。

## Independent review

Reviewer task：`01a0f198-0ab0-70c0-82e6-272a9e07c986`

Verdict：approved for this implementation checkpoint. Review covered the
current Claude bridge, stream events, safety flags, process-group stop,
deadline/version binding, generic Runtime adapter, and catalog/schema
consistency. Live authentication remains an external blocker.
