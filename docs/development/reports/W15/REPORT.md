# W15: PostgreSQL storage checkpoint

日期：2026-10-06
依赖：W14、W02
状态：`blocked`，PostgreSQL 目标分类、单活 advisory lease、事务边界和最小 Alembic migration 已通过真实 PG 17 验证；Ledger 后端迁移尚未完成。

最终 checkpoint manifest：`final-tests/snapshot.sha256`
Manifest SHA256：`53331b06212a175b26c1e05a4075373db2df7081c6d3ae30ab007b3c8f57bf8a`
Implementation commit：`d05718aad98c517c46b757716be49ab3b1705a35`。

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
- 新增 Alembic `0001_storage_meta` migration，验证 online upgrade/downgrade、重复 upgrade 和 URL 编码密码。

## 真实 PostgreSQL 17 验证

- 服务：Homebrew PostgreSQL `17.11`
- PostgreSQL DSN：本机 socket `postgresql+psycopg:///postgres`，未写入报告或仓库。
- 真实 lock integration：

```text
MULTIVERSE_POSTGRES_DSN='postgresql+psycopg:///postgres' \
uv run --python 3.12 --locked pytest -q tests/storage/test_postgres_lock.py
7 passed
```

其中 3 个测试连接真实 PostgreSQL，覆盖同 key lease 互斥、连接断开 fail-closed 和 context manager 异常退出释放；另 4 个 fixture 覆盖 unlock=false、unlock 空结果、acquisition 空结果时连接关闭及重复 release/close。

- 存储定向：`23 passed`（目标、lease、事务、migration）
- 完整 Python，设置 PostgreSQL DSN 后：`585 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- `uv lock --check --python 3.12`：通过
- 日志：`final-tests/storage.log`、`postgres-lock.log`、`python-full.log`、`ruff.log`、`mypy.log`、`diff-check.log`、`lock-check.log`
- 上一版 target-parser reviewer：`01a11195-a484-7c90-96ee-599fc32047b2`，其 approval 不覆盖 advisory lease。
- Lease reviewer：`01a11207-ccb1-7e21-bc1e-149f55727b31`，approved lease checkpoint。
- Transaction/migration reviewer：`01a11232-20f4-7013-86c3-d9eeeacb9fd9`，approved transaction+migration checkpoint。

## W15 尚未完成

本 checkpoint 不满足 W15 完整验收，仍未实现：

- SQLite 与 PostgreSQL 共同 Repository contract；
- PostgreSQL Ledger tables 和完整 SQLAlchemy backend；
- 幂等命令、版本竞争、等待领取、审批和 outbox 的真实 PostgreSQL 事务；
- 调度器持有 lease 的 Runtime 接线与失锁后停止派发；
- fencing token；
- SQLite fixture 到 PostgreSQL 的校验导入；
- 真实旧等待 Run/Artifact/Decision/Event 导入后继续运行的验收。

另外，`origin/dev` 推送继续受 GitHub SSH 名称解析 / 当前本机代理配置阻塞；因此 checkpoint commit 尚未远端核验，W15 仍保持 blocked，不解锁 W16。
