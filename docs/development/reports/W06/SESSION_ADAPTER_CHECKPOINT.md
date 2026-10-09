# W06 会话适配器第一子集

日期：2026-10-09
状态：`bounded_checkpoint`

## 本轮完成

- Claude adapter 支持显式持久会话模式：
  - `sessionPersistence`
  - `sessionId`
  - `resumeSessionId`
  - `forkSession`
- 默认行为仍是一次性调用并显式加入 `--no-session-persistence`。
- 只有明确打开 `sessionPersistence` 才允许 resume/fork/session ID，禁止隐式使用“最近会话”。
- Codex adapter 支持显式 `sessionMode=new|resume|fork` 与 `nativeSessionId`。
- 两种 adapter 都在 observation 中返回会话模式和原生会话关联。
- Executor config schema 与测试已同步。

## 真实环境核验

- Codex CLI：`codex-cli 0.156.1`，本机配置为 `gpt-6.1-sol`、`medium`。
- Claude Code：`2.1.197`，`claude auth status` 返回 `loggedIn=false`、`authMethod=none`。
- 因此 Claude 真实调用仍被本机认证阻塞，本轮没有把配置路由或一次性 fixture 当作真实会话证据。

## 验证

- `.venv/bin/python -m pytest -q tests/runtime/test_claude.py tests/runtime/test_executors.py tests/runtime/test_codex.py`：50 passed。
- `.venv/bin/python -m ruff check src tests`：通过。
- `git diff --check`：通过。
- Registry preflight 使用 `FormatChecker`，并在 Schema 阶段拒绝非法 UUID、隐式会话参数和非法 fork 组合。

## 尚未完成

- NativeSessionBinding/AgentSession 的 Ledger 持久化和查询 API。
- Codex/Claude resume/fork 的真实 live 证据。
- Inspector 原生会话列表、交互请求和会话继续操作面板。
- W06/W07 完整验收、跨 CLI handoff 与真人里程碑证据。

本 checkpoint 不修改 `docs/development/STATE.json` 的 W06 状态。
