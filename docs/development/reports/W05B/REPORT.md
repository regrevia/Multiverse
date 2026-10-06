# W05B: Pi 执行端适配

日期：2026-10-06
依赖：W03（已推送）
状态：`blocked`，代码和 fixture 已完成，真实 provider 认证缺失。

## 交付范围

- 安装并锁定 Pi CLI `1.0.1`。
- JSONL RPC prompt 生命周期适配。
- 严格校验 prompt response、`disposition`、`agent_settled` 和版本。
- 支持 Pi 1.0.1 的 message、tool、queue、compaction、retry 事件集合。
- `message_end` 作为最终 assistant 消息权威来源。
- 未知记录/未知嵌套事件 fail-closed。
- deadline 覆盖输入背压、输出上限、cooperative stop、stderr 和进程组清理。
- 通过统一 `execute_agent("pi", ...)`、Artifact 和 Runner 路由接入。

## 环境与真实检查

- `pi --version`：`1.0.1`
- `pi auth check --provider anthropic --no-refresh --json`：

```json
{"status":"not_ready","provider":"anthropic","reason":"credentials_not_configured"}
```

因此真实 Pi 模型 delivery 保持 blocked，没有用 fixture 或 skip 冒充 live 通过。

## 验证

- Pi 定向测试已纳入当前适配器回归。
- 当前定向适配器测试：`136 passed`
- 完整 Python：`562 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- 实现快照清单复用 W05A：`docs/development/reports/W05A/final-tests/implementation-snapshot.sha256`
- 实现快照清单 SHA256：`641abda8556e0ff67854496d73860953e3c3f14be8f249c8d3633cace1aee4b9`
- 完整测试日志复用 W05A：`docs/development/reports/W05A/final-tests/python-full.log`

## 限制

- 当前只验证 Pi CLI RPC 协议和 fixture；没有已认证 provider，因此没有真实模型产物证据。
- Pi session resume/fork、身份绑定、跨 CLI handoff 留给 W06/W07。
- Pi 不会读取或复制其他 CLI 的原生 session 文件。

## 独立审阅

最终 reviewer：`01a1114e-ad50-7131-bfb5-dff81ff76060`
状态：代码问题已关闭；本包因外部 provider 认证保持 blocked，最终状态回执将在远端核对后补入。
