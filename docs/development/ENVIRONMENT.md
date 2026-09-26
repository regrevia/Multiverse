# 可重复开发环境

W00 在 Linux x86_64 实测 Python **3.14.7**、uv **0.12.19**、Node
**20.20.2**、npm **10.8.2**。这是当前开发环境复现版本，不替代 W14/W25
未来的产品支持矩阵。项目声明 Python >=3.12；系统 Python 3.10.12 不满足，
只用于创建隔离工具环境。不要修改系统 Python 或删除锁文件。

## Python

在仓库根目录执行（宿主需有 `python3`、`venv`、pip 和包源网络）：

```bash
bash scripts/bootstrap-dev-tools.sh
export PATH="$PWD/.multiverse/devtools/bin:$PATH"
uv python install 3.14.7
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check src tests
uv run --locked mypy src
```

安装脚本固定 uv 0.12.19，安装到被忽略的 `.multiverse/devtools`；可重复运行。
`.python-version` 固定项目解释器 3.14.7，uv 管理解释器、`.venv` 与依赖。
工具不依赖 `/tmp`，不要求永久修改 shell 配置。当前宿主可直接使用
`/home/aied/tanyicheng/multiverse/.multiverse/devtools/bin/uv`。
系统用户工具目录中的解释器不是旧项目工作区，不需要搬动或复制。

## Inspector

`inspector/.nvmrc` 固定 Node 20.20.2（随附 npm 10.8.2）。已有 nvm 时：

```bash
cd inspector
nvm install
nvm use
node --version
npm --version
npm ci
npm run test:run
npm run build
```

无 nvm 时安装同版本 Node，再执行后三条命令即可。当前宿主的可用路径是
`/home/tanyicheng/.nvm/versions/node/v20.20.2/bin`，属于既有用户工具，
不是项目目录；必要时将此目录置于 PATH 首位。

锁文件中 Vite 8.3.0 与 rolldown 1.2.9 声明
`^20.19.0 || >=22.12.0`。W00 保存了全部 113 个锁定 `engines` 条目，并实际
执行 `npm ci --engine-strict`、27 项测试和构建。`.npmrc` 持续启用
`engine-strict=true`，后续锁变化必须重新核对并运行测试，不能只看 Node 主版本。

W00 的附加 `npm audit --json` 返回 1：Vitest/@vitest/mocker 有两条 moderate
受影响包记录，同一 GHSA-82fw-gwwq-j7x9。所建议修复跨 Vitest 主版本；W00
保留原锁，交里程碑 reviewer 判断是否可登记后续，不能将 audit 写成通过。

## 只读 CLI 验证

```bash
uv run --locked mverse capabilities --json
uv run --locked mverse validate presets/content-delivery --binding examples/bindings/content-local.yaml --json
uv run --locked mverse preflight presets/content-delivery --binding examples/bindings/content-local.yaml --json
uv run --locked mverse preflight presets/content-delivery --binding examples/bindings/content-remote.yaml --json
```

最后一条预期退出 **2**，声明的远程执行器未安装/不可用/未验证。
远程 Binding 的静态 `validate` 仍通过，这是声明合法与实际可运行的区别。
`capabilities` 没有远程模式。上述命令不执行业务，不能证明真实模型、远端、
权限或沙箱可用。W00 在空隔离 cwd 运行全部 CLI 并断言前后仍为空，且全量测试
覆盖不构造 Runner、不派发、不连接远端。

原始输出、命令、UTC 时间、退出码、测试输入逐文件 SHA256 和复现脚本见
[W00 环境证据](reports/W00/environment/README.md)。
