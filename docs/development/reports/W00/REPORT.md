# W00：保全基线与建立可重复验证

执行日期：2026-09-26；基线 HEAD：7fff55086c4a49209ec1cec839e209a9d758ea73；分支 dev。
开始时工作树干净且远端同步；初始清单见 BASELINE.json。主 Agent 负责监工、整合、验收和推送。

## 范围与实现

- `/root/w00_gate_impl`：只读里程碑检查器与临时 Git 仓库集成测试、机器证据格式。
- `/root/w00_environment`：持久 uv 安装、锁定开发版本、环境复现文档与真实基线验证。
- 两名实现者均显式使用 gpt-6-sol / medium，不自行提交或推送。
- 主 Agent 更新仓库执行委托与 STATE，调派独立 reviewer；同包按文件范围并发，没有跳过后续包依赖。

检查器提供 next、check-plan、snapshot、check ID 的 JSON 接口，拒绝缺失/陈旧测试或审阅记录、未推送依赖和回执；后台等待只能解锁独立就绪工作。检查器不执行测试或 Git 网络操作，不声称 JSON 能证明真人或子 Agent 的实际行为。

快照包含产品文件及未跟踪文件，仅固定排除 STATE 与报告目录以避免循环；实现、测试、配置和可复用验收脚本均放在受快照保护的位置。主 Agent 曾退回环境子 Agent，将报告目录中的验收脚本移入 scripts 并复测，避免脚本逃出快照。

## 验收矩阵

| W00 要求 | 证据 | 结论 |
|---|---|---|
| 保留前序 preflight、规范、研究成果 | 干净基线、Git diff、全量回归 | 保留，无业务改动 |
| 持久工具路径、锁文件复现 | environment/README.md 与原始日志 | uv不再依赖/tmp，Python/Node版本明确 |
| Python 与前端全量门禁 | final-tests-r2/results.json | 237 Python、27前端及全部适用门禁通过 |
| CLI 本地正例/远程负例，无执行副作用 | environment/CLI 原始记录、scripts/w00_cli_check.py | remote preflight预期退出2，隔离cwd为空 |
| 恢复/依赖/测试/审阅/推送/等待状态门禁 | tests/development/test_milestone_gate.py | 实际 Git 集成负例覆盖 |
| 独立审阅与返工复审 | REVIEW.md | 独立复审approved，见REVIEW.md |

环境实现期间先跑通 209 项原有 Python 测试、27 项前端测试、构建、Ruff 和 mypy；此历史基线不能替代包含新检查器的最终测试。最终测试命令、版本、UTC 时间、退出码、计数和日志见 final-tests-r2；绑定的产品摘要见 EVIDENCE.json。

## 审阅与限制

最终 reviewer 为 /root/w00_independent_review，各轮发现、修复/复测/复审保存在 REVIEW.md；最终复审已返回 approved，原阻塞项关闭。首轮P2发现额外测试记录绕过证据校验，已退回原实现者修复并新增7项Git回归，检查器定向测试增至28项。
当前验证为 Linux x86_64、Python3.14.7、Node20.20.2 开发环境，不能冒充未来 W14/W25 的产品支持矩阵。
附加 npm audit 返回1，报告 Vitest/@vitest/mocker 同一公告 GHSA-82fw-gwwq-j7x9 的 moderate 问题；未将该审计计为通过，独立 reviewer 明确同意在当前受控本地 Node 批处理测试边界内交 W24 修复；若提前引入浏览器mock、对外测试服务或交付运行时则须提前修复，详见 REVIEW.md。

不涉及真实 Coding CLI、飞书、跨机、付费模型或真人业务决策。W01 及以后包没有因 W00 通过而自动完成。

## 提交交接

代码、上述报告及脱敏证据随实现提交C推送；核对远端后，STATE填completed与C，单独推送回执R。实现/回执ID和远端核验追加到独立 PUSH_RECEIPT 文件，不回写已绑定报告或 EVIDENCE，避免循环引用。
下一步为 W01；必须先确认 W00 实现与状态回执都已在origin/dev，再解锁它。

日志封装说明：三个前端测试日志保留原始输出的全部字节，并追加明确结束标记，避免原输出末尾空行触发 Git staged whitespace 检查；测试结果/时间/命令均未改变。暂存后另跑 git diff --cached --check。
