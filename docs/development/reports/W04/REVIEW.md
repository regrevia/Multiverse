# W04 Independent Review Record

## Initial Review

独立 reviewer task：`01a0efd2-1140-7462-b4ab-aacfac9c4e73`

Verdict: `changes_requested`

阻断项：

- 初始 W04 EVIDENCE 为空且未绑定当前快照；
- Inspector reopen 报告引用旧 Run/旧端口；
- 缺少真实 reject 终态证据；
- Worker stop/restart exactly-once 证据不足；
- 测试日志、主体、subjectDigest、expectedVersion 和幂等回执未完整记录。

## Current Candidate Status

上述实现/证据缺口已补入当前候选：

- 新增真实 reject e2e；
- 新增 Worker 明确 stop → restart → durable continuation e2e；
- 当前 Inspector Runtime reopen 记录、截图和 SHA256；
- 当前 Python/前端/Ruff/mypy/npm 门禁日志；
- 当前 Run、HumanRequest、Decision、Artifact 和版本/主体关联。

尚未请求最终复审，因为 W04 仍缺一次由获授权真人在 Inspector 中提交的实际 approve/reject。当前候选不得标记为 completed。

## Limitations

- 仅支持当前 trusted-local 单主体预览。
- 真实 Codex 原生 approval 的触发受模型行为影响；确定性协议测试覆盖失败路径。
- 当前 review 是 changes-requested，不是完成批准。
