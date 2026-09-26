# W00 环境与基线验证证据

工作目录 `/home/aied/tanyicheng/multiverse`，开始 HEAD
`7fff55086c4a49209ec1cec839e209a9d758ea73`，dev 分支。
初始仓库无修改；[initial-versions.json](initial-versions.json) 记录初始工具与 Git 状态。
本目录由环境实现者生成，无业务代码或锁文件修改。

这些检查是 W00 实现期间的快照。pytest 当时收集 **209** 项，尚不包含另一实现者
新增的里程碑检查器测试。主 Agent 必须对最终合并快照补全门禁；不可把这些记录
用于声称新增测试已经通过。每个命令 `.json` 记录 cwd、完整 argv、UTC 起止、退出码、
日志索引和 `snapshot_ref`/`snapshot_digest`，对应源码清单覆盖 src、tests、inspector、
pyproject.toml、uv.lock 的 Git 已跟踪及未跟踪非忽略文件。快照不包含数据库或凭据。

## 实际结果

| 检查 | 退出码 | 原始记录/输出 | 结果 |
|---|---:|---|---|
| 隔离固定 uv 安装 | 0 | [bootstrap.json](bootstrap.json) / [log](bootstrap.log) | uv 0.12.19 |
| 重复安装 | 0 | [bootstrap-repeat.json](bootstrap-repeat.json) / [log](bootstrap-repeat.log) | 幂等安装通过 |
| uv 管理 Python | 0 | [python-install.json](python-install.json) / [log](python-install.log) | 3.14.7 |
| uv sync --locked | 0 | [uv-sync.json](uv-sync.json) / [log](uv-sync.log) | 锁文件恢复通过 |
| 固定 Python 后 sync | 0 | [uv-sync-pinned.json](uv-sync-pinned.json) / [log](uv-sync-pinned.log) | 通过 |
| pytest -q | 0 | [pytest.json](pytest.json) / [log](pytest.log) | 209 passed, 44.11s；0 failed/0 skipped |
| ruff check src tests | 0 | [ruff.json](ruff.json) / [log](ruff.log) | 通过 |
| mypy src | 0 | [mypy.json](mypy.json) / [log](mypy.log) | 29 源文件通过 |
| npm ci --engine-strict | 0 | [npm-ci.json](npm-ci.json) / [log](npm-ci.log) | 完整安装，engines 兼容 |
| npm run test:run | 0 | [npm-test.json](npm-test.json) / [log](npm-test.log) | 5 文件/27 tests passed；0 failed/0 skipped |
| npm run build | 0 | [npm-build.json](npm-build.json) / [log](npm-build.log) | tsc + Vite 8.3.0 通过 |
| 隔离 CLI 验收 | 0 | [cli-check.json](cli-check.json) / [log](cli-check.log) | 五个命令均符合预期 |
| 可复制 CLI 脚本复跑 | 0 | [cli-check-replay.json](cli-check-replay.json) / [log](cli-check-replay.log) | 与初次相同；各命令时间见最新 cli-results |
| 附加 npm audit | **1** | [npm-audit.json](npm-audit.json) / [log](npm-audit.log) | 2 moderate；未修复，不记通过 |

[effective-versions.json](effective-versions.json) 保存最终实际版本，
[node-engines.json](node-engines.json) 保存全部 113 个带 engines 的锁定依赖项。
Node 20.20.2 满足 Vite 8.3.0、rolldown 1.2.9 的 `^20.19.0 || >=22.12.0`；
安装与构建验证适用于本 Linux x86_64 环境，不是跨平台支持声明。

## CLI 验收边界

[cli-results.json](cli-results.json) 是最后一次复跑各命令的参数、时间、退出码和空目录
前后清单；[w00_cli_check.py](../../../../../scripts/w00_cli_check.py) 使用真实 CLI 子进程，断言退出码并保留输出。
capabilities、validate-local、validate-remote、preflight-local 都退出 0；preflight-remote
退出 2，诊断集合严格等于 `EXECUTOR_NOT_INSTALLED`、`EXECUTOR_UNAVAILABLE`、
`EXECUTOR_UNVERIFIED`。每条命令后隔离 cwd 仍为空，无运行数据库或执行产物。
另有现存 tests/cli/test_preflight.py 防止 Runner 构造、执行器派发或远端连接，包含于
本次全量 pytest。静态合法不代表远程就绪；不运行模型、远端或真人决策。

## 复现

先按 [ENVIRONMENT.md](../../../ENVIRONMENT.md) 建立 PATH 与解释器。在仓库根执行：

```bash
python3 scripts/w00_cli_check.py
python3 scripts/record_validation.py new-pytest . .multiverse/devtools/bin/uv run --locked pytest -q
```

`scripts/record_validation.py` 默认写入忽略目录 `.multiverse/validation`；
第一个参数是新证据名，拒绝覆盖已有记录；`--output` 可指定归档目录。
`scripts/w00_cli_check.py` 复跑将创建 `.multiverse/w00/cli-results-*` 新目录并打印路径，
保存新的 CLI 逐命令日志与 cli-results.json，不覆盖本目录的历史证据。
常规后续任务直接使用环境文档中的命令，无需重建 W00 报告。

## 已知风险

附加 audit 报告 Vitest 3.2.7 / @vitest/mocker 同一 GHSA-82fw-gwwq-j7x9，建议修复为
Vitest 4.1.11（主版本升级）。本包未修改锁文件或扩大测试框架升级范围。后续建议 owner
为 W24 供应链工作包，须独立 reviewer 明确同意后才能作为非阻塞后续项；这里不替代
reviewer 决定。没有其他环境/代码门禁失败。

可复用验收脚本已移至 `scripts/`，纳入产品快照；历史 JSON 中的原始执行路径保留，
不改写既有命令记录。迁移后复跑证据见 [relocated-cli](relocated-cli/cli-results.json)
和 [relocated-validation](relocated-validation/cli-relocated.json)。
