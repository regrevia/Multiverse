# W15: PostgreSQL storage checkpoint

日期：2026-10-06
依赖：W14、W02
状态：`blocked`，PostgreSQL 目标分类和单活 advisory lease 已通过真实 PG 17 验证；Ledger 后端迁移尚未完成。

最终 checkpoint manifest：`final-tests/snapshot.sha256`
Manifest SHA256：`271acc450b5b980d0839f266ba1a5614bef668b960a7fab84017cfcd1da6e4ff`
Implementation commit：`dc6fca9400e2a455376702280b7926e37d744bb4`。

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

- 存储定向：`17 passed`（目标解析、真实 advisory lock、释放/连接清理负例）
- 完整 Python，设置 PostgreSQL DSN 后：`579 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- `uv lock --check --python 3.12`：通过
- 日志：`final-tests/storage.log`、`postgres-lock.log`、`python-full.log`、`ruff.log`、`mypy.log`、`diff-check.log`、`lock-check.log`
- 上一版 target-parser reviewer：`01a11195-a484-7c90-96ee-599fc32047b2`，其 approval 不覆盖 advisory lease。
- 最终 lease reviewer：`01a11207-ccb1-7e21-bc1e-149f55727b31`
- Reviewer verdict：`approved` for this manifest-bound checkpoint only；not W15 completion。

## W15 尚未完成

本 checkpoint 不满足 W15 完整验收，仍未实现：

- SQLite 与 PostgreSQL 共同 Repository/transaction contract；
- PostgreSQL Ledger tables、SQLAlchemy backend 与 Alembic migrations；
- 幂等命令、版本竞争、等待领取、审批和 outbox 的真实 PostgreSQL 事务；
- 调度器持有 lease 的 Runtime 接线与失锁后停止派发；
- fencing token；
- SQLite fixture 到 PostgreSQL 的校验导入；
- 真实旧等待 Run/Artifact/Decision/Event 导入后继续运行的验收。

另外，`origin/dev` 推送继续受 GitHub SSH 名称解析 / 当前本机代理配置阻塞；因此 checkpoint commit 尚未远端核验，W15 仍保持 blocked，不解锁 W16。
