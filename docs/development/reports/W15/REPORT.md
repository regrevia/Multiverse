# W15: PostgreSQL 持久化边界 checkpoint

日期：2026-10-06
依赖：W14、W02
状态：`blocked`，当前完成存储目标边界，真实 PostgreSQL 服务条件缺失。

## 本 checkpoint 已完成

- 新增 `multiverse_workflow.storage.database` 存储目标边界。
- 明确区分：
  - `Path` -> SQLite personal/local target；
  - `postgresql://` 或 `postgresql+psycopg://` -> PostgreSQL service target。
- PostgreSQL URL 仅做校验和分类，不建立连接，不宣称真实 PostgreSQL 已支持。
- 诊断位置脱敏：
  - URL userinfo 密码；
  - `password`、`api_key`、`access_token`、`token`、`secret` 等 query 参数；
  - 保留合法 IPv6 方括号格式。
- 畸形 IPv6、非法端口、不支持 scheme 和含糊的 SQLite 字符串均 fail-closed 为 `DatabaseTargetError`。
- 保留现有 SQLite Ledger/Runner 行为不变。

## 验证

- 定向存储测试：`10 passed`
- 完整 Python：`571 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- 独立 reviewer：`01a11195-a484-7c90-96ee-599fc32047b2`
- reviewer verdict：`approved`

## 外部阻塞

本机当前没有可用 PostgreSQL 工具或服务：

- `psql` / `pg_isready` 不可用；
- Docker CLI 存在，但 Docker daemon 不可连接；
- 因此尚未实现或验收：
  - SQLAlchemy/Alembic PostgreSQL backend；
  - PostgreSQL 真实事务和唯一约束；
  - advisory lock/fencing；
  - 迁移与 SQLite 导入；
  - 双 Worker、断线和恢复真实集成。

本 checkpoint 不满足 W15 完整验收，不解锁 W16。
