# W01：Agent 可发现配置与可注入注册表

基线：125d4e3ee6225bfd0e754eadf2d84805c6ebbf17，dev；W00 实现与回执已推送且remote gate通过，开始时工作树干净。主Agent负责监工/验收/推送。

## 并发范围

- `/root/w01_catalog`：受信任目录、配置Schema、registry/preflight、配置诊断、安全负例、规范和作者文档。
- `/root/w01_integration`：CLI、RuntimeApplication、ServiceSettings、LocalWorker一致注入与端到端测试。
- 实现者均显式gpt-6-sol/medium，按文件范围独占；不提交或推送，最终由另一独立reviewer审阅。

## 交付行为

显式 `--registry DIRECTORY` 读取固定版本的 executor-registration.json，完整替换默认集合；没有参数时保留默认。目录仅允许已实现adapter及已知builtin/human实现，无动态Python导入/下载。capabilities --executor提供有效配置Schema、源文件摘要与有效Schema摘要。目录必须由可信操作者选择，Binding不能把verified或任意配置透传成管理权限。

配置同时满足后端字段白名单和操作者追加Schema。目录文件越界/符号链接逃逸、摘要错误、未知字段/版本、unsupported adapter/保证、伪造验证状态无证据均拒绝。Schema不支持$ref/$dynamicRef/$id，包括#片段，不会为验证Schema而联网。错误给出准确config字段和安全expected/脱敏actual，不回显Secret内容。

CLI validate/preflight/run/serve/worker/sweep/resume/rerun/decide共用注入；pause/cancel仅访问Ledger无需加载目录。ServiceSettings只加载一次描述快照，create_application/create_worker共享。目录撤销/修改后下一次执行前注册预检拒绝新Run，不冒充取消在途执行或热撤销授权。

修复运行时公开导出的循环导入，并以独立进程测试导入顺序，避免pytest缓存掩盖。已有loader本来就拒绝非有限数字；主Agent核实后保留既有实现，增加9个CLI回归，未重复实现数字校验。

## 验收与证据

| 要求 | 证据 | 边界 |
|---|---|---|
| 发现Schema并修复配置 | capabilities/preflight测试、作者修复演练 | 不编辑Python登记常量 |
| 严格配置、版本、引用/摘要和权限声明 | tests/runtime/test_catalog.py | 仅可信显式目录；非插件安装ABI |
| 入口注入与目录一致 | tests/cli/test_catalog_cli.py | CLI服务配置→API→Worker→loopback HTTP Job |
| 旧Binding兼容、撤销后拒绝新Run | 目录/CLI集成测试 | 固定描述快照不静默切换 |
| 无网络预检及Secret脱敏 | catalog/preflight负例和既有无dispatch测试 | 不探测实际凭据/授权/沙箱 |
| 全量门禁及独立review | 本包EVIDENCE.json、测试/REVIEW记录 | 未approved前不完成 |

HTTP Job协议测试使用真实本机TCP服务；服务入口测试拦截uvicorn启动并通过真实FastAPI ASGITransport请求API，没有宣称已做公网部署或第三方服务验收。终态Attempt既有逻辑清空external_ref，测试由持久observation的executionRef、dispatchKey、输出和状态验证关联，未为测试更改业务语义。

`verificationEvidence`为操作者的版本化声明，加载器校验描述一致性，不证明声明中的测试实际发生。安装目录的身份权限管理、持续热撤销、沙箱与真实CLI接入仍属于后续工作包。

最终原始命令/版本/时间/退出码/计数/日志、产品快照和审阅引用由EVIDENCE关联。既有W00审计风险及适用边界保持，未更改依赖锁或借W01声称修复。

## 交付

主Agent在最终测试与独立review通过后提交实现C，正常推送核对远端，再提交STATE completed与C的回执R并推送。推送证据追加独立文件，不改写已绑定报告或日志。
W01完成并远端核验后，W14与W02可按依赖合理并发。

## 主Agent验收返工

首次最终全量pytest收集失败（退出2）：CLI与runtime目录的test_catalog.py同名，在现有pytest导入模式下冲突。定向分组通过没有覆盖这一收集组合。已退回集成实现者，把CLI文件改名test_catalog_cli.py，规划中的建议路径及可复制定向命令同步；没有修改全局pytest模式或靠删缓存掩盖问题。失败原始记录保留final-tests/python.log，修复后整套重新验收。

作者路径已实际演练：capabilities查询有效Schema→timeoutSeconds=0预检精确报错→仅改Binding为合法值→预检通过，见AUTHOR_REPAIR.json。此演练没有模型调用或执行节点。

第二次全量结果为3 failed、286 passed：新增严格human-input配置Schema漏了既有Binding字段，打断manual-input兼容。失败日志保留final-tests-r2/python.log；已退回核心实现者依据现有真实行为补Schema/兼容字段说明及回归，禁止修改旧测试或删除原配置求通过。

最终第三轮全量验收：Python 296 passed、前端 27 passed，无失败或跳过；Ruff、Mypy、前端构建、计划检查、CLI只读检查、diff检查全部通过。产品快照 a639deecf827950b1f415e2e6527d32d15426dd2d2247d19ace2bb4de8cb5813 测试前后不变。最新作者修复演练 AUTHOR_REPAIR-r3.json 绑定同一快照。已实际委托 /root/w01_independent_review（gpt-6-sol/medium）独立审阅，结论待回传。

独立第一轮审阅changes_requested，4项实际发现与回执见REVIEW.md。已返工：JSON parse_float拒绝正负溢出；command argv保留既有非空字符串语义；registry/preflight显式记录配置检查完成状态，撤销/解析失败不误称checked；登记标识/版本/能力/摘要采用严格EOF并同步发布Schema。定向93项通过，主Agent重新全量验收final-tests-r4；旧r3批准不存在，不能沿用。

返工后final-tests-r4：Python315 passed、前端27 passed，其余全部门禁退出0，无skip；产品快照557ec1121fd73a7f9fc1dce31ccb0de5f1938f945a994c17e0572c5e8cd49dfa（199文件）前后不变，作者修复演练重跑通过。以本轮为最终候选，原reviewer复审。

原独立reviewer复审approved：四项全部关闭；额外实际复跑127项通过。主验收以r4最终快照/315 Python/27前端及作者演练为准。完整结论和限制见REVIEW.md最终批准。满足实现推送门禁，完成回执须在实现提交C远端核对后单独追加。
