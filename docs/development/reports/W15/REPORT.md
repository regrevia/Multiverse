# W15: PostgreSQL storage checkpoint

日期：2026-10-06
依赖：W14、W02
状态：`blocked`，PostgreSQL 目标分类、单活 advisory lease、事务边界和 0001–0004 Ledger DDL 已通过真实 PG 17 验证；Ledger Runtime backend 尚未完成。

最终 checkpoint manifest：`final-tests/snapshot.sha256`
Manifest SHA256：`c6e745341f6fcb0f6233fdc27449892158c1dcc14f0448f5cffc52f95373f8ef`
Implementation commit：待当前 Repository Invocation/Attempt 快照提交。

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
- 真实 PostgreSQL storage suite：`32 passed`
- Migration schema suite：`7 passed`
- Transaction 子集：`3 passed`
- Lock suite：`7 passed`，其中 3 个真实 PG case、4 个 fixture case。

- 完整 Python，设置 PostgreSQL DSN 后：`594 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- `uv lock --check --python 3.12`：通过
- 日志：`final-tests/storage.log`、`postgres-lock.log`、`python-full.log`、`ruff.log`、`mypy.log`、`diff-check.log`、`lock-check.log`
- Lease reviewer：`01a11207-ccb1-7e21-bc1e-149f55727b31`，approved lease checkpoint。
- Transaction/migration reviewer：`01a11232-20f4-7013-86c3-d9eeeacb9fd9`，approved transaction/migration checkpoint (0001)。
- Final 0004 schema reviewer：`01a112fe-4e35-7793-ac7c-d4aa73ed989e`，approved 当前 manifest checkpoint；不代表 W15 完成。
- Repository first-slice reviewer：`01a1135b-fe5e-7cc0-8b16-cacfde7b5d31`，approved namespace/transaction/Invocation/Attempt slice。

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
