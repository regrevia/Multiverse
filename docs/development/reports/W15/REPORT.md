# W15: PostgreSQL storage checkpoint

日期：2026-10-07
依赖：W14、W02
状态：`blocked`，PostgreSQL 目标分类、单活 advisory lease、事务边界和 0001–0004 Ledger DDL 已通过真实 PG 17 验证；Ledger Runtime backend 尚未完成。

最终 checkpoint manifest：`final-tests/snapshot.sha256`
Manifest SHA256：`9983ec4504c6e62ccff22665c87f1990b6732b1aa83bf347ff774b035015dec5`
Implementation commit：`86bd7f8`。

## 已完成

- 新增 `multiverse_workflow.storage.database` 存储目标边界。
- 明确区分：
  - `Path` -> SQLite personal/local target；
  - `postgresql://` 或 `postgresql+psycopg://` -> PostgreSQL service target。
- PostgreSQL URL 目标仅用于分类；该解析函数本身不建立连接。
- 诊断位置脱敏：
  - URL userinfo 密码；
  - `password`、`api_key`、`access_token`、`token`、`secret` 等 query 参数；
  - 保留合法 IPv6 方括号格式。
- 畸形 IPv6、非法端口、不支持 scheme 和含糊的 SQLite 字符串均 fail-closed 为 `DatabaseTargetError`。
- 保留现有 SQLite Ledger/Runner 行为不变。
- 新增 `PostgresSingleActiveLease`，用专用 psycopg 连接持有 PostgreSQL session advisory lock。
- lock key 被另一个连接持有时拒绝 acquisition；连接丢失时 `assert_held()` 失败关闭；release 必须取得数据库 unlock=true 回执。
- 新增 SQLAlchemy 2 transaction boundary，接受标准 PostgreSQL DSN 和 `DATABASE_URL` 覆盖。
- 新增 `PostgresLedgerRepository` first slice：namespace-scoped Run/Scope/Event/Wait 查询、原子 queued Run 写入，以及 Invocation/Attempt 原子写入；当前仍未接入 Runner。
- 抽取 bounded `WaitStore` 调度契约；SQLite Ledger 通过原子 worker-owned complete/release/reschedule 实现，PostgreSQL Repository 提供对应适配器和真实 PG 契约测试；当前 PostgreSQL 适配器仍未接入完整 Runner/Worker。
- 抽取 bounded `CommandStore` 回执契约；PostgreSQL commands 支持 namespace/subject/operation 幂等、fingerprint 冲突回滚、accepted-only 原子 finish 和终态幂等；当前尚未接入 RuntimeApplication。
- PostgreSQL Run optimistic update 支持 `FOR UPDATE`、expected-version CAS、scope/invocation ownership、原子 `run.updated` Event 和节点切换时清空旧 invocation；当前尚未接入完整 Runner。
- HumanRequest/Decision PostgreSQL 契约支持 0005 namespace-scoped decision idempotency、Schema 校验、授权主体、版本、RFC3339 expiry、过期事件、progress intent 和 continuation wait；当前尚未接入 RuntimeApplication。
- PostgreSQL Artifact metadata/source 契约支持完整 W02 metadata 校验、终态观察、attempt/Run 锁、source-key 幂等和外部字节边界；当前不伪称中心 Artifact bytes 已存储。
- PostgreSQL Run control 契约支持 pause/resume/cancel、版本 CAS、active attempt stopping、无 active attempt 时级联取消实体及 `RUN_CANCELLED` 错误。
- Alembic `0001` storage metadata、`0002` 14 张核心 Ledger 表、`0003` inbox/host-session/FK/Outbox action-key 约束、`0004` ownership composite FK 约束。
- 四个 Alembic revisions 建立 14 张核心 Ledger 表、Inbox、host/session 和 ownership 关联；Ledger 业务模型到表的 Repository 映射尚未接入。
- 真实 schema parity 测试从当前 SQLite Ledger 初始化结构，与 PostgreSQL migration 逐表比较列覆盖；全部当前 Ledger 表列均被覆盖，PostgreSQL 扩展列和新增表单独声明。
- migration tests 使用每例临时 PostgreSQL schema，完成 upgrade/downgrade/re-upgrade 后清理 schema，不污染共享数据库。
- DATABASE_URL online/offline override、URL 编码密码、多动作 Outbox、Inbox 去重、关键 FK 拒绝均有真实 PostgreSQL 断言。
- Outbox 同一 Attempt 可有多个 action；Inbox 来源/revision 去重；Run current Scope/Invocation、Scope parent Invocation、Attempt host-session 外键均用非法写入负例验证。
- 若存在同 Attempt 多 Outbox action，0003 downgrade 会明确拒绝并保留当前 revision，不会在重建旧唯一约束时产生裸数据库冲突。

## 真实 PostgreSQL 17 验证

- 服务：Homebrew PostgreSQL `17.11`
- 每个 migration 集成用例使用临时 schema 并在退出时清理。
- PostgreSQL DSN：本机 socket `postgresql+psycopg:///postgres`，未写入测试日志或提交内容。
- 真实 PostgreSQL storage suite：`58 passed`
- Repository Wait/Worker/Command/Run update/Human/Artifact/Runtime read/Run control slice：`31 passed`
- Migration schema suite：`7 passed`
- Transaction 子集：`3 passed`
- Lock suite：`7 passed`，其中 3 个真实 PG case、4 个 fixture case。

- 完整 Python，设置 PostgreSQL DSN 后：`624 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- `uv lock --check --python 3.12`：通过
- 日志：`final-tests/storage.log`、`postgres-lock.log`、`python-full.log`、`ruff.log`、`mypy.log`、`diff-check.log`、`lock-check.log`
- Lease reviewer：`01a11207-ccb1-7e21-bc1e-149f55727b31`，approved lease checkpoint。
- Transaction/migration reviewer：`01a11232-20f4-7013-86c3-d9eeeacb9fd9`，approved transaction/migration checkpoint (0001)。
- Final 0004 schema reviewer：`01a112fe-4e35-7793-ac7c-d4aa73ed989e`，approved 当前 manifest checkpoint；不代表 W15 完成。
- Repository first-slice reviewer：`01a1135b-fe5e-7cc0-8b16-cacfde7b5d31`，approved namespace/transaction/Invocation/Attempt slice。
- Repository Outbox first slice：`01a1138b-b9eb-7b23-9228-fea12f747317`，首次发现两个 P1，修复后最终复审 approved；复审覆盖原子 Outbox、Run 行锁事件序号、cancelled wait 重激活和新增并发/回滚测试。
- Repository Wait/Worker slice：`01a113a0-b8d0-7540-b899-4c9f5d059c8b`，首次发现完成竞态和 stale Worker ownership 两个 P1；修复后最终复审 approved。新增条件完成/释放、worker ownership、stale reclaim、并发唯一领取和 namespace 重排测试。
- Scheduler WaitStore bounded checkpoint：`01a114d7-8d2a-7ad1-a013-1c7645ab4331`，初审指出 SQLite TOCTOU、external reschedule 绕过和 namespace/接线边界；修复后按 bounded checkpoint 复审 approved。完整 PostgreSQL Runner/Worker 接线作为 W15 scope limitation 保留。
- Command Receipt bounded checkpoint：`01a11502-45ea-75a3-abce-a7de63b743d6`，初审发现 finish 终态覆盖 P1；修复为 `FOR UPDATE` + accepted-only + 相同终态幂等后复审 approved。异常类型统一和 RuntimeApplication 接入保留为后续范围。
- Run optimistic update bounded checkpoint：`01a11527-5673-78a3-b1dd-e4f4689549ed`，初审 P2 测试未建立旧 invocation；补充真实 Invocation 绑定、节点切换清空断言后复审 approved。
- HumanRequest/Decision bounded checkpoint：`01a11557-c252-7b72-a396-456bfdfdf3b3`，初审发现 Schema、expiry、namespace idempotency 和并发/回滚证据缺口；补齐 0005、RFC3339 expiry、授权/Schema/幂等/并发/回滚后最终 approved。
- Artifact metadata bounded checkpoint：`01a1158d-acfc-7733-a26c-6bdf37eaa39c`，初审发现 stale observation、终态、完整 metadata 校验和并发证据缺口；补齐事务内重核验、W02 validator、Run lock 和非法 digest 负例后最终 approved。
- Runtime entity read bounded checkpoint：`01a115bf-b32f-7550-866e-5eed40eaa6e5`，覆盖 namespace-scoped Scope/Invocation/Attempt/Event 读取与 Artifact metadata；最终 approved。
- Run control bounded checkpoint：`01a115d8-a3c4-7363-ba1d-3f5ac1d942a3`，初审发现 cancel 级联状态缺口；补齐 waiting entity 取消与 RUN_CANCELLED 错误后最终 approved。

## W15 尚未完成

本 checkpoint 不满足 W15 完整验收，仍未实现：

- SQLite 与 PostgreSQL 共同 Repository contract；
- Ledger DDL 已建立 14 张核心表及 inbox/host-session 关联；Repository 已完成 queued Run 与 Invocation/Attempt first slice，完整 PostgreSQL Ledger runtime backend 未实现；
- 幂等命令、版本竞争、等待领取、审批和 outbox 的真实 PostgreSQL 事务；
- 调度器持有 lease 的 Runtime 接线与失锁后停止派发；
- fencing token；
- SQLite fixture 到 PostgreSQL 的校验导入；
- 真实旧等待 Run/Artifact/Decision/Event 导入后继续运行的验收。

另外，`origin/dev` 推送继续受 GitHub SSH 名称解析 / 当前本机代理配置阻塞；因此 checkpoint commit 尚未远端核验，W15 仍保持 blocked，不解锁 W16。
