# v1 发布支持矩阵

唯一行为规范为 [MULTIVERSE_SPEC.md](../spec/MULTIVERSE_SPEC.md#sec-0-7)。本文件记录目标与证据，不新增协议。目标软件为1.0.0；当前0.1.0仍是本地开发预览。盘点基线为 `4a4cf9225e22a2539f83afd3e9907bc14861a1bc`（W01）。W14静态测试验证契约一致性，不新增平台或真实集成通过声明。

`implemented` 表示存在限定实现；`verified` 必须注明实测范围和固定证据；`unsupported` 表示当前完整能力不可用。它们描述能力，不是ACCEPTANCE中的验收结论。`pending/failed/passed/blocked` 描述完整要求的验收状态。部分实现不会令完整ID自动passed。当前没有达到v1全部门槛的supported发行组合。

## 当前能力与证据

| 能力 | 当前状态 | 实现/测试线索与限定范围 | 尚缺证据/主负责 |
|---|---|---|---|
| 资源解析、Schema、确定性编译、六原语形状 | verified（本地开发） | protocol/models.py、compiler/compiler.py；tests/protocol、tests/compiler；W00/W01报告 | 完整安全归档导入/安装W24；编译不是导入 |
| 本地注册目录、配置Schema、只读预检 | verified（本地开发） | runtime/catalog.py、compiler/preflight.py；tests/runtime/test_catalog.py、tests/cli/test_catalog_cli.py；W01报告 | 目录证据是operator attestation，非实时健康/授权/沙箱证明 |
| SQLite台账、持久Run/人工请求、幂等回执 | implemented；开发回归已验证子集 | runtime/ledger.py、tests/runtime/test_ledger.py、tests/runtime/test_runner.py | PostgreSQL/单活W15、真实人工W04/W20 |
| workflow/parallel/repeat持久子scope与汇合 | implemented；完整语义pending | runtime/runner.py、tests/runtime/test_runner.py | W16完整调度、乱序/故障/取消传播；不得把图形或注释当保证 |
| Runtime暂停/取消/核对 | implemented；端到端取消pending | Runner.cancel保存ledger控制意图；tests/runtime/test_runner.py | 当前Runner取消没有调用HTTP Job cancel；W02服务端进程取消不等于W16 Runtime完整分发/竞争语义 |
| Local Process、HTTP Job客户端与运行适配 | implemented；受控测试子集 | runtime/executors.py、runtime/http_job.py；tests/runtime/test_http_job_runtime.py | 真实Bridge/进程树W02、恢复边界W16；当前HTTP产物字节导入未闭合 |
| API/CLI/Inspector命令、事件与人工入口 | implemented；本地开发子集 | api/app.py、cli/main.py、inspector/src/runtime；tests/api、tests/cli、Inspector单测 | 任意结构化表单/上传/嵌入SDK W20；客户端过期W25 |
| 本地默认身份与权限 | implemented（trusted-local） | api/dependencies.py的LocalPrincipal默认有本地全部scope；local.process.v1继承Worker权限 | 非默认最小授权证明；团队主体/namespace W17、策略W18 |
| PostgreSQL 17 / LangGraph持久后端 | unsupported | SQLite不能替代；W15/W16为待实现要求 | 真实事务、checkpoint、崩溃和单活恢复 |
| 实际沙箱、团队安全、Secret Provider | unsupported（完整要求） | trusted_local不是沙箱，目录permissionLevel不是执行证明 | W08/W17/W18/W26 |
| Codex/Claude/Pi、Session、Connector、飞书 | unsupported（完整集成） | W01可发现配置不表示已安装原生执行端 | W03/W05A/W05B/W06/W07/W09/W10A/W10B；原生版本区间未实测 |
| 真实离线、真实latent实验 | unsupported（完整验收） | Ollama适配代码/Mock测试不证明禁网真实执行；latent默认不加载 | W22/W23；可选安装仍强制项目验收 |
| Bundle、正式SDK、安装/升级/回滚/备份/GC | unsupported（完整交付） | 当前源码/包读取不能替代目标安装 | W20/W21/W24/W25 |

上述代码路径均相对 `src/multiverse_workflow/`（tests/inspector路径除外）。固定历史证据：[W00报告](../development/reports/W00/REPORT.md)、[W01报告](../development/reports/W01/REPORT.md)；报告涵盖的测试不能自动延伸到后续修改或新平台。

## 发行profile与平台

[profile Schema](../../schemas/deployment-profile.schema.json)仅校验目标声明；当前没有profile加载/部署命令。合法JSON不证明安装、身份、网络隔离或模型真实性。禁止给目标配置写假Secret/资源证明。

| profile | 必需目标 | 当前完整验收 |
|---|---|---|
| personal | SQLite、单用户、单活（原local）；显式选择trusted-local或enforced，不可信任务必须enforced；可按需接入外部执行器 | pending：本地预览不等于正式干净安装 |
| team | PostgreSQL17、同组织多主体/namespace、单活、实际隔离（原service） | pending：W15/W17/W18/W24 |
| offline | SQLite单用户单活；禁外网真实本地模型/程序/人工；资源manifest摘要 | pending：W22；本档不启用飞书/云CLI/远程Connector；latent仅显式实验安装 |

| 平台/依赖单元 | v1范围 | 当前实测事实 | 发布结论与必需后续 |
|---|---|---|---|
| Linux x86_64 服务与沙箱 | mandatory target | W00 Linux开发环境；没有发行物沙箱认证 | pending；W08/W24/W25实测发行物与隔离 |
| Linux x86_64 Connector | mandatory target | 尚无真实Connector | pending；W09/W25 |
| macOS arm64 Connector | mandatory target | 无目标机器证据 | pending；W09/W25；缺机器时blocked仍计分母 |
| Python3.12、3.13 | 两个版本均mandatory target | W00使用3.14.7；requires-python>=3.12不是支持证明 | pending；W25逐版本冻结patch及发行物测试 |
| PostgreSQL17 | team mandatory target | 只有SQLite开发回归 | pending；W15/W21/W25 |
| Node24、pnpm/frozen锁文件 | 保留规范§5.1构建目标 | inspector/.nvmrc=20.20.2，当前npm/package-lock；W00此开发组合通过 | pending；W24/W25需处理差异并冻结patch及pnpm锁；不得静默删目标 |
| 浏览器 | mandatory真实Console/宿主矩阵 | Vitest不是浏览器；无浏览器构建号实测证据 | pending；W20/W25在RC锁定浏览器精确构建号与宿主组合；未填写前不得发布 |
| 原生Codex/Claude/Pi版本 | mandatory真实执行；按需安装 | 没有实测支持区间 | pending；W03/W05A/W05B/W25逐版本固定，禁止latest |
| Python3.14.7、Node20.20.2/npm | 当前开发验证组合 | W00固定报告与锁文件 | verified仅指开发回归；不加入v1 supported分母替代必需目标 |
| Windows原生、敌对租户共享宿主、多活图调度 | excluded by spec | 不宣称支持 | unsupported；不用于缩减其他mandatory项 |

任何supported单元必须保存OS/架构、Python/Node/浏览器/数据库/CLI精确版本、产物digest、安装与真实运行报告、授权及测试快照。缺值不能写supported。W25按目标逐项补证据，不能删除失败行。浏览器/CLI未冻结精确实测版本是公开缺口，不是任意版本兼容承诺。

## 版本、弃用和后续兼容验收

版本规则统一见规范§0.7。软件SemVer、metadata.version及数据库CAS计数不能被当成线级版本。当前资源/计划/图投影为multiverse/v0.1，API为/api/v1，HTTP Job为/v1；事件版本继承API契约。SDK尚未正式发布；CLI仅现有preflight/注册文件有独立版本名，其余输出绑定安装版和命令Schema。HTTP Job响应保留未知可选字段，严格请求模型拒绝未知字段；不可混用。

正式v1弃用通知须至少90天且跨两个已发布minor；兼容期内保留既有含义。旧v0.1包导入须经只读安全校验、不可变快照、未激活部署和授权验收；当前compile测试只验证格式读取，不能称导入/迁移通过。

[ACCEPTANCE.json](ACCEPTANCE.json)保存222原ID与16个V1必需门槛。每项完整验收目前pending；test_paths是现有线索而非通过证据，evidence为空表示尚未签收。future_compatibility_scenarios列出W24/W25/W20需实现的固定setup/actions/assertions与目标测试文件；这些是可执行测试设计，当前静态校验设计的完整性，不创建skip/xfail冒充执行。

每条通过证据必须包括layer、path、snapshot、artifact_digest与结论。主owner最终签收，contributors须在owner依赖闭包内。W14只调整完整签收责任，不改变实现责任或验收范围；调整原因见规划附录。W29须检查全部238项及后续显式新增项，mandatory未通过不能发布；正式发行需另行授权。
