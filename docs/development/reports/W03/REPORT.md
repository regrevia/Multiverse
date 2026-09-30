# W03: 首个真实 Coding Agent：Codex

日期：2026-09-30
当前验收快照：`c32581efd71cb16778b52671a25dc3783f1585f1`
实现提交：`541d181067aef11bd3582a9859f419b56d9199d3`
依赖：W02（已完成且已推送）

## 范围

本包交付 Codex App Server 结构化 Bridge、Runtime-owned Artifact、原生交互持久化和受控回复，以及 deadline、输出上限、协作停止、取消和 unknown 语义。交互回复使用持久 `interactionId`、授权主体、expectedVersion、期限、actor-scoped idempotency key 和正文摘要；原生工具许可与业务 HumanRequest 分开记录。

## 当前实现证据

- Codex 使用结构化 JSON-RPC `initialize`、`thread/start`、`turn/start` 和事件消费，记录 `threadId`/`turnId`。
- 启动、turn 创建和执行共用一个 deadline；超时请求 `turn/interrupt`，只有收到 `turn/completed.status=interrupted` 才确认停止。
- Run cancel 接入活动 Codex turn；确认停止进入 `RUN_CANCELLED`，停止未确认进入 unknown/reconciliation wait，Run 保持 blocked。
- delta 和 completed item 全文均受 `maxOutputBytes` 限制。
- handshake/响应管道断开、原生请求拒绝/取消、交互过期、响应乱序、已知 failed 终态和未知传输均有明确分类。
- 原生回复先落 Ledger，再通过同一 App Server 连接投递；重复同回复返回原回执，正文变化产生冲突；连接/投递不明不会自动重发旧批准。

## 测试与门禁

当前快照验证记录：

```text
uv run --python 3.12 --locked pytest -q
523 passed, 10 skipped

uv run --python 3.12 --locked pytest -q \
  tests/runtime/test_codex.py \
  tests/runtime/test_codex_interactions.py \
  tests/runtime/test_executors.py \
  tests/runtime/test_runner.py \
  tests/runtime/test_ledger.py
99 passed

uv run --python 3.12 --locked ruff check src tests
All checks passed

uv run --python 3.12 --locked mypy src
Success: no issues found in 37 source files
```

10 个 skip 是平台或需显式 live 开关的条件项；Linux-only `prctl` crash recovery 已显式标记，不冒充 macOS 证据。Execution Host 在当前快照为 `44 passed, 3 skipped`。

## 当前快照真实 live 证据

Codex 版本：`codex-cli 0.156.1`。

1. `MULTIVERSE_RUN_CODEX_INTERACTION_LIVE=1 uv run --python 3.12 --locked pytest -q -s tests/e2e/test_coding_delivery.py::test_real_codex_native_approval_is_persisted_replied_and_resumed`
   - 结果：`1 passed in 9.25s`
   - Run：`run_41eff0a1f48742d0b2583b111b43db48`
   - Interaction：`interaction_4505b060370843d4beaae47cc9063009`
   - 证据：真实 command approval 持久化、授权回复、`deliveryStatus=sent`、文件效果和独立业务 HumanRequest approve。

2. `MULTIVERSE_RUN_CODEX_LIVE=1 uv run --python 3.12 --locked pytest -q -s tests/e2e/test_coding_delivery.py::test_real_coding_delivery_completes_runtime_human_loop`
   - 结果：`1 passed in 33.02s`
   - 证据：真实 Codex producer、Runtime verifier、授权主体 `example-reviewer` approve 和 succeeded terminal Run。

3. `MULTIVERSE_RUN_CODEX_LIVE=1 uv run --python 3.12 --locked pytest -q -s tests/e2e/test_coding_delivery.py::test_real_coding_delivery_survives_runtime_restart_before_approval`
   - 结果：`1 passed`
   - Run：`run_a442eebfe9e34d3bbfe30feee9841304`

4. `MULTIVERSE_RUN_CODEX_LIVE=1 uv run --python 3.12 --locked pytest -q -s tests/e2e/test_coding_delivery.py::test_real_coding_delivery_survives_worker_restart_before_approval`
   - 结果：`1 passed`
   - Run：`run_01f08cd0a6404890afff4755cd0c153b`

## 独立审阅

- W03 Codex Bridge/interaction/cancellation 最终代码快照由独立 reviewer `01a0ef40-8b0b-7c60-add0-ddd49ffeecce` 复审并批准；审阅覆盖 deadline、停止确认、失败/完成竞态、幂等回复和 unknown 路由。
- 当前依赖的 Execution Host 跨平台 checkpoint 由独立 reviewer `01a0ef8f-bd12-74e3-ac3c-f77ca5482f97` 复审并批准后形成 `c32581e`。

## 边界

- 本包只支持已验证的本地 trusted-local Codex 配置，不宣称通用多租户认证或隔离沙箱。
- Codex 模型是否主动触发工具请求具有模型行为不确定性；确定性失败矩阵和至少一条当前快照真实 approval round-trip 已覆盖。
- W04 的 Inspector reopen 现场证据、完整 UI 关闭/重开演示和 W04 独立状态回执仍作为后续工作包处理。

本报告证明 W03 当前代码和验收范围已达到可进入稳定预览的工作包完成门槛；不把 W04 或后续可移植能力标记为完成。
