# W02：最小执行宿主与持久 HTTP Job Bridge

基线4a4cf9225e22a2539f83afd3e9907bc14861a1bc；W01实现及完成回执均远端核对。独立工作树/home/aied/tanyicheng/multiverse/.multiverse/worktrees/w02，分支work/w02-host；w02_execution_host（gpt-6-sol/medium）独占实现，主Agent管理STATE、串行整合、最终验收、独立审阅、推送。未完成实现/门禁前不标完成。

并发细分：/root/w02_execution_host独占execution_host、tests/execution_host及host文档/示例/spec；/root/w02_runtime_artifacts（gpt-6-sol/medium）独占runtime/http_job.py、ledger.py、runner.py及tests/runtime新增产物测试。共同独立worktree，接口先冻结，同包双方都冻结后才能整合/测试/审阅。主Agent不提交半成品。

## 最终整合候选

W14实现与回执已远端核对后，主从冻结w02树整合Host与Runtime，spec三方合并干净。主补README入口、支持矩阵W02实际边界和Linux限定；未改已完成W14报告/证据。最终快照与整合后测试另记录。

Host独立SQLite+flock单活；dispatchKey/完整请求摘要持久绑定，同key不同内容409。launching之前持久发布effectState=possible；真实SIGKILL窗口不知结果时unknown，不重发、不凭PID消失断言无副作用。终态与产物可跨服务重启查询；不支持重启后自动接管活动原生进程。

固定操作者命令，隔离任务cwd/HOME与精选环境，stdout单一有限JSON、stderr单独有界，事件最近32项。取消只针对当前宿主持有身份的进程组，best_effort，不能撤回外部副作用或保证逃逸进程停止。Host/Origin/JSON/大小/绝对读取时限限制，不是公网身份认证或沙箱。

产物经Host冻结普通文件字节、同源固定content端点、不跟重定向，限制件数/大小/总量并比对namespace/execution/metadata/SHA256；Runtime整批验证后按(attempt,execution,artifact,version)来源幂等登记并保留原始observe。事务失败不能留下可见部分batch；字节落盘后事务失败最多产生待清理孤儿文件。坏产物/Schema有持久脱敏协议错误并blocked，不盲重试；暂时传输失败仍保留恢复等待。

最小控制修复：成功Attempt保留external_ref以持久来源关联；下载期间取消时已cancelled wait幂等不复活，迟到成功不能派下游。此处不声称W16完整Runtime取消分发已完成。

实现者测试历史：Host定向88通过，但最后effectState修复发生其测试运行期间，完整88不冒充精确最终快照，最终窗口/store另5通过；Runtime定向62通过、末次submit重定向unknown补3通过。Ruff/mypy定向与Host全src均通过。主必须在整合后独立全量测试、绑定最终摘要并实际委托独立reviewer，才可交付。

证据层：本包要求真实本地确定性子进程、TCP、故障kill和Artifact登记；不涉及真实模型或真人验收。最终Python全套记录包含这些必需真实测试，JUnit逐case索引辅助核对，不能把fixture/纯契约测试冒充外部模型或人工通过。

主首次整合全量：2 failed、460 passed（无skip），其余27前端/ruff/mypy/build等门禁通过；失败原始日志/JUnit保留final-tests。两项失败是W14 HTTP兼容测试mock已移除urlopen私有符号，退回Runtime实现者换真实TCP fixture，保留公共兼容断言。另主真实进程实证重复请求过期后被提前拒绝（MAIN_DEADLINE_FINDING.json），退回Host实现者修复幂等/过期顺序，要求真实TCP重复仍200同ref且只启动一次，新过期请求无intent，冲突仍409。尚未调用首次W02独立review，须完整复测通过。

作者文档主验收发现复制样例目录会继承permissionLevel=enforced，而Host是trusted_local。已退回实现者修正登记声明并说明非授权/隔离证明；CLI平台描述也精确为Linux。过期幂等修复已在原树89项通过后同步3文件；W14兼容测试换真实TCP后69项通过。主开始新的整合全量r2。

整合r2全量463 Python/27前端及其余门禁通过且快照不变，但主按作者文档实际CLI演练在preflight失败：交付Binding含非法secretRefs.authorization值。失败真实命令/退出码/诊断保留AUTHOR_CLI_DEMO-failed-r2.json。没有因全部单测绿而通过验收；退回Host实现者修成无secret引用的可信本地示例，并将真实文件链测试改为直接使用交付示例以防漂移。

主r3 CLI演练首次已通过preflight；验收脚本错误地期望异步run首次返回4（waiting），实际正常返回0/running并已持久提交意图，因此脚本停止且未派发。该次真实记录保留AUTHOR_CLI_DEMO-failed-final-tests-r3.json；纠正仅本地验收脚本退出码预期，不改产品或业务断言，使用新的独立临时工作区重跑。

最终候选r3：Python463 passed、前端27 passed及其余全部门禁0，无skip，快照d3d296a2ea23f8ed0780da53c6c57fff9787507f27ffa58d4847cfcf32112205（221文件）前后不变。JUnit中Host/产物接线84个case全通过，索引REAL_EXECUTION_CASES.json按真实范围说明。作者CLI演练实际通过：启动宿主→capabilities确认trusted_local→preflight→run/worker→两个真实进程产物读取并验SHA256→一个pending人工待办；未提交任何人工决定，未调用模型。见AUTHOR_CLI_DEMO.json，绑定同一快照。进入首次实际独立review。

首次实际独立审阅 changes_requested：104 项定向通过且快照不变，但真实 TCP 复现旧 executionRef `job:123` 在 submit 后无法 observe/cancel。新产物 ID 正则误用于通用 executionRef，属于 P2 兼容回归。见 REVIEW-r1.json，已退回 Host 实现者，仅在主目录 http_job.py 与专用测试修复；修复后重新全量测试及实际复审，未推送此候选。

W02-R1 已由原实现者修复：通用 executionRef 独立安全编码，恢复冒号/长引用并支持 Unicode；blob ID 保持严格边界。真实 TCP 生命周期与危险输入回归补齐，指定三组 82 passed（38.94s），Ruff/Mypy/diff 通过。主继续最终 r4 全量复测与 CLI 演练。

最终候选 r4：488 Python / 27 前端通过、其余门禁均 0、无 skip；完整快照 9e016ee83e5dcc1f83b859bde615733f5aa1d1589337a9eca8b2fcf3da0f0fbd（221 文件）前后不变。新 CLI 演练生成两个真实产物且 SHA256 验证通过，进入一个人工待办，0 人工决定；见 AUTHOR_CLI_DEMO-final-tests-r4.json。HTTP 兼容与 Host/产物逐项索引 REAL_EXECUTION_CASES-r4.json 包含 111 项。请求原独立 reviewer 复审最终快照。

最终实际独立复审 approved：129 项定向通过（72.57 秒、无 skip），前后快照一致；W02-R1 关闭，无未解决 P0/P1/P2。审阅者核对完整 488/27 门禁及新 CLI 证据，批准范围仅 Linux 可信 loopback。见 REVIEW-r2.json。主验收通过，进入正常提交推送及远端回执；此处不声称完整模型/真人或 W16 取消链路通过。
