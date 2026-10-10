# W06 会话台账与 Inspector 关联子里程碑

日期：2026-10-10
状态：`approved_bounded_checkpoint`

## 完成内容

- Ledger 持久化 `AgentSession`：
  - namespace、agent、主体、scope、profile revision；
  - 可选 Run/Scope/Invocation 关联；
  - 版本、幂等键和请求指纹；
  - 创建事件。
- Ledger 持久化 `NativeSessionBinding`：
  - provider、安装实例、存储身份、原生 session ID、版本；
  - capabilities、来源、workspace/policy revision；
  - active/superseded 历史；
  - provider + installation + storage + native ID 复合唯一性。
- API：
  - `GET /agent-sessions`
  - `GET /agent-sessions/{id}`
  - `POST /agent-sessions`
  - `POST /agent-sessions/{id}/native-bindings`
  - 新增 `session:manage` 权限；
  - 列表支持 `runId` 过滤。
- Inspector：
  - 智能体编辑面板显示当前 Run 关联的原生会话；
  - 显示 provider、原生 ID、状态、版本；
  - 显示待处理 Codex 原生交互；
  - 不伪造 resume/fork 操作，当前为只读审阅面板。
- Provider 扩展边界仍是注册式的；Hermes、Pi、DeepSeek Harness 等可通过同一 NativeSessionBinding/Adapter Contract 接入，不需要修改 Ledger 事实模型。

## 真实验证边界

- 已核对 Codex `0.156.1` 的公开 App Server schema，存在 `thread/start`、`thread/resume`、`thread/fork`。
- 全新空 thread 的实际 `thread/resume` 返回 `no rollout found`，因为尚未产生可恢复 rollout；因此没有把空会话探针当作 resume 成功。
- 真实恢复验证需要先完成一个实际 turn，再在新 App Server 进程中 resume/fork；本轮未启动模型 turn，也未产生计费调用。
- Claude 使用 CC Switch 第三方供应商配置，不以 `claude auth status` 的 first-party 登录状态作为唯一判断；真实 Claude 持久会话仍待在不产生错误认证假设的条件下执行。

## 验证

- Python 完整测试：`644 passed, 59 skipped`
- Python 定向会话/API测试：`27 passed`
- Inspector：`48 passed`
- TypeScript/Vite build：通过
- Ruff：通过
- `git diff --check`：通过
- 独立 reviewer：`01a123ea-358a-7b30-947d-1d64e9a94c2f`
- 最终结论：`approved`

## 限制

本 checkpoint 不代表 W06/W07 全部完成，尚未实现：

- Attempt 与 AgentSession/NativeSessionBinding 的自动关联写入；
- Inspector 中真正发起 resume/fork 的命令操作；
- Codex 完成真实 turn 后的 resume/fork live 证据；
- Codex → Claude 的 handoff envelope、工作区快照和授权消费回执；
- Hermes/Pi/DeepSeek Harness 的真实 Adapter 验证。
