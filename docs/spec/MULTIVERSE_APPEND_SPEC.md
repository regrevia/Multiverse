# Multiverse V0.1 追加规范

**外部 Agent 原生编写 · 统一输入输出契约 · 人工与程序节点 · 可选 Latent Handoff**

| 项目 | 内容 |
|---|---|
| 文件名 | `MULTIVERSE_APPEND_SPEC.md` |
| 追加文档版本 | `1.0.0` |
| 适用主规范 | `MULTIVERSE_SPEC.md`，修订 `1.1.0` |
| 原协议版本 | `multiverse/v0.1`；本文件不自行改名或升级该协议 |
| 基准日期 | 2026-09-19 |
| 文档性质 | 主规范的追加章节与实施引导，不是另一套工作流协议 |
| 实现状态 | 本文规定待实现、待验收行为，不表示 Runtime、CLI、页面或真实 latent 后端已经完成 |
| 适用场景 | 通用工作流；不依赖任何特定宿主、行业、Agent 产品或业务平台 |

> **同一份契约，让外部 Agent 知道怎样编写流程，让程序知道怎样执行，让人知道怎样操作，让 Runtime 知道何时可以继续。**
>
> **内部实现自由，外部边界确定。**

---

## 导航

| 主题 | 位置 |
|---|---|
| 文档效力与追加范围 | [S0](#sup-00) |
| 外部 Agent 与 vibe coding | [S1](#sup-01) · [Authoring Kit](#sup-02) · [编写与验证闭环](#sup-03) |
| 统一输入输出范式 | [S4](#sup-04) · [契约版本与数据边界](#sup-05) |
| 人工工作与交互 | [S6](#sup-06) · [表单与页面](#sup-07) · [外部服务](#sup-08) · [产物提交](#sup-09) |
| 固定程序接入 | [S10](#sup-10) |
| 标准与 Latent 交接 | [S11](#sup-11) · [完整沿用条款](#append-latent) |
| 混合流程与工程落地 | [S12](#sup-12) · [接口缺口](#sup-13) · [实施顺序](#sup-14) |
| 验收与完成定义 | [S15](#sup-15) |
| 开发与编写材料 | [示例](#append-examples) · [外部 Agent 编写指引](#append-author) · [来源与追溯](#append-sources) |

---

<a id="sup-00"></a>

## S0. 文档效力、来源与追加边界

### S0.1 与主规范的关系

本文件与主规范 `1.1.0` 一起使用；不覆盖原文件，不重写主规范已经固定的生命周期、权限、事务、控制流和部署规则。主规范的章节号仍为 0—26，本文件使用 S0—S15，避免交叉引用混乱。

本文件整合两部分完整补充内容：

1. 已在主规范 `1.1.0` 固定的 Latent Handoff 开关、兼容性、真实消费、审计、安全、恢复和实验验收要求。
2. 随后讨论确认的外部 Agent 编写工作流、Authoring Kit、统一输入输出、人类操作页面、外部人工服务、程序 Wrapper、产物提交与补充验收要求。

本文不把最初草案中已经被主规范调整的技术选型、发布时间表或产品落点重新引入。旧草案保留的方向是统一黑盒节点、Specification/Binding 分离、Git-native、可移植 Package 和可解释交付；实际实现边界仍以主规范和本文为准。

### S0.2 三种内容标记

| 标记 | 含义 |
|---|---|
| **沿用** | 主规范已有明确规则；本文件重述或按原文收录，不产生另一种解释。 |
| **追加要求** | 来自本轮补充引导，开发时需要补齐的能力和验收结果。 |
| **尚未冻结的接口细节** | 上文只确定了能力，未确定完整字段、URL、参数或组件协议；不得把说明性示例当成当前已经支持的 API。 |

正文中的“必须”“禁止”为相应能力的验收约束；“建议”为工程实施指导；“可选”为明确可不采用的实现方式。新增字段、Schema、OpenAPI、CLI 参数及测试必须在同一实现变更中补齐，并登记为主规范的追加实现，不允许代码自行引入隐形规则。

主规范已有的不变量不得被本文放宽。发现实质冲突时应记录并修订，不得按“最近一段文字优先”静默覆盖。本文附录的 latent 原文是便于一起交付的受控摘录；维护时与主规范对应段落同步，不单独演进。

### S0.3 本次不新增的产品负担

不新建内置自主规划 Agent，不要求专有聊天界面，不把可视化拖拽作为主要创作入口，不强制接入 MCP，不增加第四种顶层声明资源，不要求安装向量数据库或 Semantic Blackboard，不改变主规范技术栈。

主规范中的 Specification、Runtime、Inspector/UI SDK 边界继续成立。作者 Agent 和执行节点都不以特定品牌为前提。

### S0.4 “方便”的验证含义

“原生支持 vibe coding”表示外部 Agent 能依据公开、版本匹配的编写材料和机器反馈完成流程创建与受控验证；不是保证一次提示生成就永远正确，也不是承诺未接入的任意外部服务会自动可用。

“Latent 可切换”表示支持组合上的实际通信方式可切换；不是让所有执行器自动获得模型内部接口。规范、样例解析、Mock 链路与真实业务验收必须分别报告。

---

<a id="sup-01"></a>

## S1. 外部 Agent 是原生工作流作者

### S1.1 产品入口

**追加要求：外部 Agent 编写应作为主要创建方式之一，而不是仅允许它偶然修改配置文件。**

用户能够表达自然语言目标，外部 Agent 随后完成：

```text
读取需求、约束与验收目标
          ↓
读取主规范、追加规范、Schema、样例和可见能力
          ↓
先设计节点输入输出，再设计依赖与分支
          ↓
生成或修改 Workflow Package 与 Binding 示例
          ↓
Validate → 修复 → 预检 → 受控试运行 / Eval
          ↓
输出 Diff、结果、风险和待绑定事项
          ↓
由有权限的人决定发布与部署
```

文件、CLI 和 API 必须足以完成主要操作，不要求作者通过浏览器点击图形节点，也不要求导入 LangGraph 内部类型。

### S1.2 作者与执行者分离

编写流程的 Agent 不必注册为流程中的 Executor，不必占用一个 `call` 节点，也不必具备 latent 导入/导出能力。它是在创建与修改声明，而不是替 Runtime 推进活动流程。

同一个 Agent 产品可以分别承担作者与执行者角色，但两者的身份、授权、输入和审计应分别确定。拥有编写权限不自动获得执行权限、人工审批权限或部署激活权限。

### S1.3 工作流是小型软件包，不限于一个大 JSON

**沿用主规范第 6、16 章：**流程主体使用 JSON/YAML；完整交付物还包含业务 Schema、必要的 Prompt/Skill/Policy、测试材料和 Binding 示例。

```text
workflow-package/
├── manifest.yaml
├── workflows/
├── schemas/
├── prompts/                 # 按需
├── skills/                  # 按需，须明确格式和版本
├── policies/                # 按需
├── evals/
└── bindings.example.yaml
```

对用户可以呈现“一句话生成一套流程”的体验，但生成结果必须是可解析、可验证、可版本化的小包。实际凭据、私有地址和环境授权不混入可移植包。

### S1.4 边界

作者不得直接写运行数据库、伪造外部执行引用或审批事实、修改活动 Run、自动合并发布、扩大权限。实际部署仍按主规范走 Package、Binding、预检、Eval、Diff 和有权主体的发布决定。

缺少执行器、凭据或人工入口时，应明确报告缺口；可生成未部署的包和待绑定清单，但不得声称已经可运行。

---

<a id="sup-02"></a>

## S2. Authoring Kit：面向外部 Agent 的编写能力

### S2.1 必须交付的材料

**追加要求：**提供一套与安装版本匹配、可离线读取的 Authoring Kit。它是规范的导航与操作材料，不是独立规则源。

| 材料 | 最低内容 |
|---|---|
| 简明编写指南 | 文件组织、节点契约、数据引用、常见流程、命令顺序、错误处理、发布边界。 |
| 协议与业务 Schema 示例 | 顶层资源、ValueExpr、Predicate、输入输出、人工请求结果、通信开关。 |
| 模板与最小包 | 标准交付、人工补充输入、人工产物提交、固定程序校验、外部服务调用。 |
| 正例与反例 | 合法输入、缺字段、非法引用、未绑定能力、错误人工输出、失效审批、无效 latent 路由。 |
| 能力发现材料 | 当前版本支持什么、当前授权范围能使用什么、哪些尚未验证。 |
| 机器可读操作结果 | Validate、预检、Eval、Diff 和状态查询的结构化结果。 |

可使用 `AUTHORING_GUIDE.md` 作为指南文件名；该名称是建议，不新增运行协议。指南中的每个行为指向主规范或本文件的明确章节。

### S2.2 能力发现

作者需要能够读取当前授权范围内的能力目录，至少获得：协议/功能版本、支持的节点与控制流子集、执行器 ID 与 Descriptor、输入输出契约、能力要求、人工入口支持情况、取消/幂等/查询保证，以及实验环境中已验证的通信 Profile。

必须区分以下状态：已声明、已安装、当前可用、已验证。它们不能互相代替。

能力目录不得包含 Secret 明文，不得因“给 Agent 看文档”泄露其他 namespace 的对象。读取目录不是授权，历史可见也不能覆盖授权撤销。离线快照可用于编写，但部署时必须重新检查。

标准模式的能力发现不应为了展示普通执行器，加载模型权重、访问 latent 凭据或探测 latent 推理服务。实验能力可由已登记的元数据说明；真实可用性在明确选择实验部署后检查。

主规范已有 ExecutorDescriptor 与注册表基础；面向作者的统一目录读取方式属于本次需要补齐的接口能力，具体端点和命令见 S13 的缺口登记。

### S2.3 不得猜测环境

没有查到某个 `executorRef` 时不能编造一个 ID 后宣称可运行；声明了某个 Capability 也不等于它已经实现。未知必需字段、未知必需功能和不支持的配置必须报错，而不是忽略。

作者不能将一个任意 Python 文件写入包后，就假设它会成为可信内建程序。程序接入遵守 S10 的注册与 Wrapper 边界。

### S2.4 结构化诊断

**沿用并落实主规范第 6.5、17.3、18 章：**诊断必须能定位文件、JSON Pointer、严重程度和稳定错误码，并给出可理解的期望、实际问题及建议操作。

建议外部 Agent 的修复流程只修改与问题相关的文件；诊断需能反查原始定义，不只暴露编译生成的内部节点名称。

CLI 的机器结果与运行日志分开，遵守主规范 stdout/stderr 约定；`--json` 输出中不能混入进度动画或无结构日志。不得另造一个与 API 状态不同的“CLI 成功”含义。

诊断的字段布局应随对应 Schema 固定；本文件不把说明性字段清单冒充已经发布的响应 Schema。

---

<a id="sup-03"></a>

## S3. Vibe coding 的创建、修复与验证闭环

### S3.1 先契约，后流程实现

作者应先明确最终交付、必需证据和验收，再划分节点。每个可调用节点明确输入、输出、能力、副作用和失败路径；之后才选择具体执行器与环境 Binding。

不得为了适配某个样例而要求修改核心 Runtime，除非确实需要新的通用功能，并明确提交规范与测试变更。业务专有字段优先留在业务 Schema 中。

### S3.2 必须区分的验证层次

| 层次 | 能确认的内容 | 不能据此宣称 |
|---|---|---|
| 静态 Validate | 语法、文件、引用、Schema 形状、控制流、已能判定的映射问题 | 外部服务真实可用、业务质量合格。 |
| Binding 预检 | 注册能力、权限、依赖、资源与契约匹配情况 | 预检未执行的业务或模型推理已经成功。 |
| Fixture / Mock 测试 | 确定性分支、契约、错误与状态处理 | 真 Agent 效果、真实 latent 消费、真实人工身份。 |
| 授权真实执行 | 实际 Adapter 和输入—执行—产物链路 | 所有样本、全部环境普遍可靠。 |
| Eval 与发布审阅 | 固定数据集、明确验收与变更影响 | 未测组合自动兼容、所有未知成本为零。 |

任何计划预览或模拟都必须标明是否调用执行器。不得让名为 validate、preview 或 test 的操作暗中触发写入副作用。

### S3.3 修复规则

作者可依据诊断迭代修复，但必须保留用户目标和验收基线。禁止通过删除必填字段、放宽门禁、跳过人工、伪造 Artifact、删除失败样本或改写测试期望，制造通过结果。

确实需要调整业务契约或验收时，应作为显式变更提交 Diff，说明原因及影响，而不是伪装为无语义变化的格式修正。

人工节点在自动测试中可用明确的测试身份与 fixture 驱动；测试批准不是生产批准，不得复制到正式 Run。

### S3.4 输出给人的交付说明

外部 Agent 完成编写后至少提供：包版本与修改文件、流程与契约说明、绑定缺口、权限和副作用变化、人工如何操作、测试层次与结果、标准/latent 模式及其验证状态、部署前仍需完成的事项。

用户不应被要求阅读整个配置包才能知道“这套流程做什么、会改动什么、哪里需要人、目前是否真的能运行”。

### S3.5 现有命令与新增接口分开

主规范已定义的 `mverse validate`、`package build/import`、`binding validate`、`deploy`、`run`、`inspect`、`events`、`eval`、`decide` 可作为实现目标使用；它们不是本文声称已安装可运行的工具。

能力目录、模板生成、任意结构化人工结果文件提交和产物上传的完整命令尚需补齐。不可在指南中加入未实现参数，然后把失败归因于用户配置。

---

<a id="sup-04"></a>

## S4. 不变的输入输出规范化范式

### S4.1 统一的是契约，不是所有业务字段

**沿用并强化：**所有执行方式共享输入输出的表达、校验、版本、生命周期、权限和证据规则；不同业务节点允许使用不同业务 Schema。

| 层次 | 必须保持稳定 | 可以替换 |
|---|---|---|
| 执行协议 | ExecutionRequest、ExecutionObservation、身份、终态、错误、取消、去重、核对 | 内部程序、模型、人、远程服务。 |
| 节点业务契约 | 当前契约版本的 inputSchema/outputSchema、能力、副作用、字段含义与验收 | 满足这些条件的执行实现。 |
| 工作上下文 | 来源、权限、版本、引用、快照和审计关联 | 标准交接或已配置的 latent 载荷。 |

不新增互不兼容的 AgentResult、HumanResult、ProgramResult。它们的实现均应通过 Adapter 映射到现有执行协议，业务结果置于规定的 output 中。

不把所有结果强制降为一个 `text` 字段，也不要求整个流程共享一份任意可变状态字典。

### S4.2 执行状态、业务结论、交接解释分离

执行状态表示调用是否完成；业务输出表示本次得到什么；Handoff 表示如何理解和承接这些结果。

例如校验器正常运行后输出 `valid=false`，属于成功完成一次校验但业务不合格；人工返回 `reject`，属于完成审阅但结论为拒绝。应走显式 switch/业务路径，不伪造为网络失败，也不触发隐式重派。

真正的执行错误按主规范 ErrorEnvelope 与 onError 处理。`reconciling` 是未知结果核对，不等于一个已确定错误，不能借错误分支绕过核对。

### S4.3 Schema 的内容要求

重要业务字段必须具有足够清晰的语义：含义、类型、必需性、允许值、缺失/null/空字符串区别；涉及数量、时间或版本时还要说明单位、格式和范围。

`title`、`description`、`examples` 可供作者和页面理解，但不能代替可执行约束或业务验证。仅定义 `score` 是 number，不能说明它是百分制、概率还是其他量。

输入输出验证仍使用主规范固定的 JSON 类型、JSON Schema 版本、路径解析和无隐式转换规则。静态检查不能证明的映射必须保留运行时验证，不把“不确定”显示成已证明兼容。

### S4.4 统一执行边界

```text
解析并冻结业务输入 + Context + 权限引用
                  ↓
校验 inputSchema、绑定与当前授权
                  ↓
Adapter 提交、观察、等待、取消或核对
                  ↓
校验 outputSchema、Artifact 与必要证据
                  ↓
提交持久事实后，按明确流程规则推进
```

对 Agent、程序、人和外部服务不能采用不同的宽松标准。“模型说完成”“程序退出 0”“HTTP 200”“有人点了按钮”都不足以单独通过该边界。

### S4.5 可替换性不等于可冒充身份

相同 Schema 只是必要条件之一。还必须满足语义、能力、权限、副作用和验收要求。

声明需要真人审批的节点，不能因某个 Agent 能生成同样的 `decision` JSON，就把它绑定为审批人。业务允许自动审核时，应明确变更能力和授权条件，而不是静默替换人工职责。

---

<a id="sup-05"></a>

## S5. 契约版本、输入快照与数据边界

### S5.1 “不变”的准确含义

同一契约版本的字段含义不能漂移。Schema、Prompt、Policy、Binding 或实现版本改变时，按主规范创建对应的新版本与部署，重新进行必要验证；活动 Run 不热替换。

新增字段并非天然兼容，尤其存在 `additionalProperties: false`、必填字段或含义变化时。不得凭“只是多了一个字段”省略兼容性检查。

### S5.2 每次调用固定实际材料

必须保存实际输入、Context 的摘要与引用、所用 Schema/Prompt/Skill/Binding 版本、权限主题和关联产物。幂等请求指纹覆盖业务 input 与实际 Context，不能只比较表面任务文本。

必要约束、动作权限、验收条件、产物版本与明确依赖必须显式传递；不能靠语义检索碰巧命中，也不能仅压入 latent。

### S5.3 结构化数据与大产物分离

可直接校验的小型业务值使用 JSON；文件、图像、视频、报告、模型载荷等大内容使用 ArtifactRef。可变 URL 和本地文件路径不能直接冒充可重现产物。

Artifact 需要真实可访问对象、版本或摘要及权限。审计摘要是解释，不取代产物本身，也不证明独立测试已经运行。

### S5.4 权威事实与投影分离

State、运行台账和不可采样的关键事件继续负责运行正确性；Checkpoint 保存后端推进进度，Inspector、缓存、Trace、检索索引和可读摘要不获得状态写入权。

如后续引入 Memory，仍遵守 State/Memory/Context 分离。它与本次 latent 开关独立，不是前置依赖。

---

<a id="sup-06"></a>

## S6. 人工节点：审批、审阅与实际工作

### S6.1 沿用三种 HumanRequest

人工执行沿用 `call` 节点与 Human Adapter，不新增一种绕过统一协议的“人类流程”。

| requestType | 典型工作 | 最终输出 |
|---|---|---|
| `approval` | 对明确对象版本和动作作许可决定 | `{decision, comment}`，choice 与 Schema 一致。 |
| `review` | 审阅特定版本的产物与证据 | `{decision, comment}`，按显式分支使用结论。 |
| `input` | 补充资料、分类标注、填写数据、修改文件、执行人工任务并交付产物 | 直接满足节点 outputSchema 的业务 JSON。 |

`input` 不限于“补一句话给 Agent”；它可以承担完整的人工生产环节。不得把复杂人工工作勉强塞进 `comment`，然后要求下游猜测文本含义。

### S6.2 输入与输出必须分别建模

`inputSchema` 约束交给人的任务材料；`decisionSchema` / `outputSchema` 约束人需要提交的结果。页面不能将冻结输入全部变成可编辑字段，再用编辑结果覆盖原任务。

任务目标变化时遵守主规范：需要新目标则创建新 Run；有界业务修订通过明确 repeat 输入传递，不修改旧输入和旧审批。

### S6.3 决策归一化

approval/review 的决定归一化为 `{decision: <choice>, comment: <string>}`，缺省 comment 为 `""`；必填评论规则仍由服务器实施。

input 的请求 choices 为空；API 请求中的 decision 值就是符合 outputSchema 的业务对象。附带的审计 comment 不注入业务输出。不能让页面和 CLI 各自采用不同的包裹层。

### S6.4 最低请求信息

HumanRequest 沿用主规范中的请求身份、namespace、run/scope/invocation、requestType、title、instructions、input/inputDigest、subjectRefs/subjectDigest、choices、decisionSchema、authorizedSubjects、createdAt、expiresAt、version、status。

指令、材料、证据和允许输出必须清晰。谁能处理属于环境授权；不能在可移植 Workflow 中硬编码某个公司的账户体系。

### S6.5 人工声明与独立验证分开

“人提交已完成”是一个有身份与版本的声明，不自动等于外部动作已被独立核验。需要核验时设计后续程序或服务节点读取明确证据。

任务是人工提交文件时，应验证文件存在和契约；任务涉及外部真实动作时，应明确证据要求与核验责任。不得用一个完成按钮替代必要事实。

---

<a id="sup-07"></a>

## S7. 人工页面与 Schema 驱动的交互

### S7.1 页面必须可真正完成任务

**追加要求：**人工节点不仅在图上显示 waiting，还必须有可用的操作入口。可采用内建页面、嵌入组件、自定义页面或合规接入的外部服务。

普通用户处理支持范围内的人工任务时，不应被要求手写 JSON。面向开发者的原始 JSON 查看/提交可保留，但不能代替最低可用表单。

### S7.2 页面分区

| 区域 | 必须表达的内容 |
|---|---|
| 任务信息 | 目标、说明、当前状态、处理期限、当前身份能做什么。 |
| 只读材料 | 冻结输入、待审阅产物、具体版本、验证结果、证据和明确约束。 |
| 结果填写 | 根据输出契约生成或配置的字段、选项、产物选择/提交。 |
| 提交与冲突 | 服务器校验结果、字段错误、版本过期、主题变化、已被处理或已取消。 |
| 操作记录 | 实际提交身份、时间、版本、决定及证据关联。 |

### S7.3 默认表单支持范围

必须发布支持矩阵，首版至少覆盖：布尔值、有限枚举、数字与整数、短文本与长文本、必填字段、对象分组、有限数组，以及受控 Artifact 选择或上传入口。

展示可使用 Schema 的说明信息；控件顺序、分组、布局和自定义呈现属于展示配置。数据规则以 Schema 和服务端验证为准。

不要求任意 JSON Schema 都自动得到完美表单。复杂组合、专用标注工具或领域编辑器可交给已注册页面/组件或外部服务。声明的任务超出所选入口支持范围时，预检应说明缺口；不能运行到一半才发现没有可用控件。

### S7.4 展示不拥有权限或事实

隐藏字段、禁用按钮、前端枚举和客户端校验不替代服务端验证。不得从客户端接收可自证身份或可自证授权的值。

默认值只可作为可见候选值；页面显示或初始化不得产生提交。审批不因默认选中 approve 而完成。任何最终决定都必须由受授权主体显式提交。

### S7.5 自定义呈现的边界

自定义页面只负责收集输入与展示事实，不能直接更新节点状态。必须使用同一请求、同一 subjectDigest、同一输出契约和同一命令入口。

包内不允许任意 JavaScript、HTML 或安装脚本因此获得服务端/页面执行权。自定义控件由受信任环境注册；页面采用安全呈现，不把业务字符串直接当作 HTML。

布局提示应通过明确 Schema 的展示扩展或 Adapter 配置承载。不得随意向 NodeDefinition 添加 `formUrl`、`uiSchema` 等未知核心字段。精确扩展键、字段和组件接口在实现时按 S13 登记，不由 Agent 自行发明。

### S7.6 持久等待与生命周期

人工等待不是一个必须保持连接的 HTTP 请求，也不占用持续工作的浏览器。关闭页面、CLI 断开或 Runtime 重启后，请求、版本和等待关系仍然存在。

重复提交去重；并发冲突不能覆盖先前有效决定。已过期或取消的请求不得因迟到提交重新激活；合法的重复幂等请求按原回执处理，不新增决定。

草稿不是最终输出，文件上传不是最终交付，页面打开不是已读授权，消息已读不是任务完成。是否提供草稿保存可作为界面增强，但不得与执行事实混淆。

人工可能已在外部执行真实动作时，取消请求不代表撤销动作；需要停止确认或结果核对时，沿用主规范安全边界。

---
<a id="sup-08"></a>

## S8. 内建页面、嵌入页面与外部人工服务

### S8.1 三种接入方式

| 方式 | 人在哪里操作 | 决定权威 | 接入要求 |
|---|---|---|---|
| 内建页面 | Inspector 的 Human Inbox / HumanRequestPanel | Multiverse Runtime | 读取并提交内建 HumanRequest。 |
| 嵌入或自定义页面 | 任意产品的受控页面 | Multiverse Runtime | 调用同一 HumanRequest API，不生成第二份审批。 |
| 外部工单/审批/人工服务 | 外部系统自己的入口 | 外部系统保存决定，Runtime 保存经验证的执行观察 | 通过 HTTP Job / Bridge 映射统一执行契约，保留身份、版本与证据。 |

前两种只改变界面，不改变权威。第三种明确由外部系统拥有决定，不能再创建一份能覆盖它的本地审批。一个请求只有一个最终决定权威。

### S8.2 外部入口不是完成信号

任务交给外部系统时，必须关联：本次调用、外部执行引用、请求版本、对象版本、允许操作、结果返回方式和状态核对方式。

通知、邮件、聊天卡片或页面链接只负责引导。不能把通知发送成功、页面打开、消息已读、重定向成功当作人工工作已完成。

外部地址与认证属于环境配置。链接不得携带长期凭据；外部回传需要认证、权限检查、幂等去重和版本匹配，不能信任浏览器随意提交的外部结果。

### S8.3 状态回传与恢复

外部系统可以主动回调，Runtime 也必须能按稳定引用查询/核对。不能把浏览器连接或一次 webhook 当作唯一恢复路径。

Bridge 负责将外部状态映射为原有 ExecutionObservation，保留外部 revision 或可核对版本，区分 accepted/running/waiting 与真实终态。请求结果未知时先查询，不重复创建工单或任务。

人工决定只在验证通过后作为节点输出提交。输出结构错误、证据缺失、身份不可验证或对象版本不一致时，不得为了推进而伪造 approve、completed 或 succeeded。

### S8.4 预检要求

部署前应检查该人工节点是否存在支持对应任务的入口，结果提交方式是否满足 Schema，以及授权、产物读写和查询/恢复条件是否满足环境要求。

这不要求所有部署都提供 Web：CLI、已验证的嵌入入口或外部人工服务可以满足相应使用场景。但面对普通用户的支持声明，不能把“有一个 JSON 接口”当作已经具备可用页面。

无法在无业务副作用预检中确认的项目保留 unverified；不能把发送一份真实工单隐藏为探测操作。

---

<a id="sup-09"></a>

## S9. 人工产物提交与结构化结果通道

### S9.1 必须补齐的交付闭环

**追加要求：**支持人工任务提交文件或登记外部不可变产物，而不只返回 approve/reject。

```text
选择本地文件 / 选择已有 Artifact / 提供待登记的外部版本
                          ↓
受授权的上传或登记通道
                          ↓
完成存储、摘要/版本、大小与权限等验证
                          ↓
获得本 namespace 可引用的有效 ArtifactRef
                          ↓
将 ArtifactRef 放入符合 outputSchema 的人工结果
                          ↓
以同一 HumanRequest 身份、版本和 subject 提交
                          ↓
服务器原子校验、记录决定、提交事件并唤醒流程
```

上传过程可以先于最终决定，但不能与最终决定混为同一事实。文件完成存储并通过规定验证后，才可作为输出引用。

### S9.2 生命周期与权限

临时上传、部分文件、浏览器本地路径、任意字符串或无法冻结版本的 URL 都不能登记为已完成交付。引用必须能解析到真实授权对象。

上传者、提交者和后续读取者的权限分别检查。成功上传不自动赋予下游读取权限，也不自动表明本次 HumanRequest 允许引用该对象。

取消/过期请求后完成的上传不应自动完成原任务。未被有效交付引用的临时数据按保留与回收策略处理；已登记历史产物不能被静默覆盖。

外部产物沿用主规范：优先内容摘要，否则使用可验证的外部不可变版本并标明验证方式；不能以可变 URL 代替版本事实。

### S9.3 提交操作的共同语义

内建 UI、嵌入页面、CLI 和 API 都提交符合相同 HumanRequest 契约的 decision，并带 expectedVersion、subjectDigest 和幂等身份。

对于 `input` 请求，提交的 decision 直接是业务对象。对于 approval/review，使用规定 choice/comment。不得额外添加只在某个前端生效的结果包裹层。

提交时重新验证请求仍可处理、身份有权、对象与版本一致、输出 Schema 合法、Artifact 可用。数据库事务不等待上传或模型推理；先完成对象，再在事务中核对引用与摘要。

### S9.4 API 与 CLI 缺口

主规范已有 Artifact 读取/下载与人工决定提交接口，但没有固定完整的上传/外部登记 API；CLI 示例也未给出任意 `input` 结果文件提交的完整参数。

本次明确把这两项列为需要补齐的能力。`--decision-file` 可作为结构化文件提交参数的设计建议，但尚未冻结，不得在当前支持矩阵中宣称可用。

上传端点、上传会话、外部登记字段和该 CLI 参数应在实现变更中一起补齐 Schema、错误语义、鉴权与测试。本文不擅自给未讨论的端点、大小默认值和保留期限命名；涉及限制继续遵守主规范或显式环境策略。

---

<a id="sup-10"></a>

## S10. 固定程序与通用 Wrapper

### S10.1 开发者编写业务函数，Adapter 管理执行边界

程序接入的目标体验是：实现“符合 inputSchema 的数据 → 符合 outputSchema 的业务结果”，而不要求每个函数自己实现 Run 台账、Outbox 或人工等待机制。

可采用可信 builtin、注册的 Local Process、HTTP Job 或现有服务的薄 Wrapper。统一生命周期仍由既有 Adapter Contract 表达。

### S10.2 沿用的最小规则

| 接入形态 | 必须遵守 |
|---|---|
| 可信内建程序 | 注册 ID 与固定入口；输入输出验证；包不能通过携带源码自动获得执行权。 |
| Local Process | JSON stdin；stdout 只输出一个 JSON result；日志写有上限的 stderr；不默认使用 shell。 |
| 同步/遗留程序 Wrapper | 显式映射输入输出和错误；说明实际查询、取消、幂等能力；不能凭包装伪造恢复保证。 |
| HTTP Job / 远程服务 | 使用稳定身份、提交回执、观察、取消和核对契约；一次 HTTP 成功不等于任务完成。 |

具体可执行文件、参数、凭据与环境权限来自受信任注册和 Binding，不来自工作流内任意命令字符串。

### S10.3 输出与错误

合法的业务“不通过”结论按业务分支处理；输出 Schema 不合法、必需 Artifact 缺失则不得成功；超时、崩溃与未知副作用按照主规范处理。

不得让固定程序返回一段日志后由下游猜测字段，也不能让 Adapter 把空输出自动修补成合格业务结果。

### S10.4 重试与副作用

Wrapper 不能将一个没有去重或查询能力的遗留脚本包装成“可安全无限重试”。执行器声明 retryOwner、submitDedup、reconcileByKey、cancelMode；本次调用只能有一个自动重试所有者。

未知写入结果先核对。恢复同一工作不创建新业务身份；确认安全的新执行尝试、业务返工与新 Run 重跑保持区分。

### S10.5 作者 Agent 与程序安装分开

作者可以生成待审阅的 Wrapper 或程序源码，但该源码必须走受授权的安装/注册流程。Workflow Package 的导入不能执行安装脚本，也不能借“vibe coding”跳过信任边界。

---

<a id="sup-11"></a>

## S11. 与可选 Latent Handoff 的统一设计

### S11.1 一个 Runtime、一个 Workflow、两种交接模式

**沿用主规范 1.1.0：**唯一开关为 `BindingSet.spec.communication.latentHandoff.enabled`，默认 false。首次配置 routes/profile 后，日常可开启或关闭；每次改变创建新部署，已有 Run 不热切换。

| 项目 | 标准模式 | Latent 实验模式 |
|---|---|---|
| 工作流作者 | 外部 Agent 或人编辑声明 | 相同；作者自身不需要 latent 能力。 |
| 业务输入输出 | 结构化 JSON、Schema、ArtifactRef | 相同，不能删掉必需业务材料。 |
| 机器工作上下文 | 必要文本与标准 Handoff | 选定兼容 route 使用真实 latent 载荷。 |
| 人与固定程序 | 按普通契约参与 | 非 route 的人和程序继续按普通契约参与。 |
| 状态、授权、审批 | 权威持久事实与受控操作 | 相同，不形成第二套状态同步。 |
| 审阅 | 摘要与证据 | 同样保留，另关联载荷、profile 与消费证据。 |
| 依赖 | 不因本功能增加 latent 推理依赖 | 可选安装已验证后端或实验执行服务。 |

该开关不是 Semantic Memory 开关；不要求先建设 Blackboard、向量数据库或检索系统。

### S11.2 实际生效，而不是只显示开关

必须区分请求开启、计划覆盖、载荷准备、接收端实际消费和本次未经过 route。只有真实消费证据满足要求才能计为已使用 latent。

不提供静默文本回退：不支持、模型/profile 不匹配、载荷损坏或未消费时明确阻止或按已确定错误处理；已提交执行结果未知时先核对，不因此重派。

向量检索、随机向量、张量字符串或仅注入审计摘要不能代替真实 latent 交接。一个黑盒内部使用 latent 也不能单独证明框架开关完成；首版验收需要两个逻辑调用间的一条真实 route。

### S11.3 范围与兼容性

沿用同 Workflow、同实际 scope、源先完成、两个 call 节点、每目标至多一个 latent 来源的限制。route 不改变控制流、依赖或权限。循环每轮形成独立身份；不同目标不能共享可变活动缓存。

CommunicationProfile 固定模型与执行器版本、表示格式、必要 Codec、上下文位置/前缀约束、资源与持久化要求、已验证兼容组合。不能仅凭维度或产品名称判断兼容。

Human Adapter 不是 latent 消费者；需要给人审阅的结论和证据必须以可读、可验证形式提供。后续程序也必须得到满足其 output/input Schema 的业务结果，不要求它从不透明张量猜测字段。

### S11.4 审计与实验隔离

两种模式共享同一业务验收。审计摘要绑定同一次交接、产物与载荷版本；事实来自运行记录，模型解释和假设明确标注。摘要不是对内部计算的完整解码证明。

选定 latent route 默认不把同一审计摘要再偷偷注入下游作为文本后备；必需约束、权限和业务输入仍显式保留，其他实际注入文本在 Context 快照与报告中披露。

不要求每个内部 latent step 都生成人类摘要；在交接和既有人工/风险边界提供即可。摘要生成失败时使用有来源的事实模板，不伪造解释。

### S11.5 可靠性与安全

载荷使用已完成持久存储、可校验摘要的 ArtifactRef；不使用裸 GPU 指针、短命 Session 或可变 URL 作为持久交接。恢复复用原载荷和原身份，不擅自生成新的语义状态。

导出、导入与消费回执沿用 submit/observe/lookup，不新建无台账的旁路通信。控制事件、日志、Checkpoint、SSE 和 OTel 只保留必要引用，不塞入原始张量。

载荷沿用来源敏感级别、namespace、权限与保留策略；不可读二进制不等于脱敏。采用受限格式与安全解码，不允许不可信 pickle 或任意解码脚本。

### S11.6 实验完成条件

至少一组锁定版本的真实兼容实现能在两个逻辑调用间完成导出与消费，同一包可关闭为标准模式对照。报告记录质量、端到端时间、文本量、latent 量、资源、存储/传输、摘要生成和失败核对成本。

实际消费为零的运行不能冒充 latent 效果样本，失败与未使用情况不能从报告中删除。没有成本来源保持未知，不预设 latent 必然优于标准方式。

为保证本文件可与上轮内容一起交付，完整第 14.6—14.12 节、开关 Schema 和 LH-01—LH-14 原文收录于[附录 B](#append-latent)。这些条款不是本次重新选型。

---

<a id="sup-12"></a>

## S12. 必须演示的混合流程

### S12.1 同一流程的两种通信方式

建议用下列通用场景验证本次补充，不将它变成核心业务模型：

```text
目标与约束
    ↓
draft：生成候选交付物
    ↓     ← draft → refine 可配置标准 / latent
refine：完善交付物
    ↓
verify：固定程序验证结构与必要材料
    ↓
switch：校验是否通过
    ├── 否 → 明确失败结束
    └── 是 → review：人工审阅当前版本和证据
                  ↓
                switch
                  ├── approve → 交付结果
                  └── reject  → 明确拒绝结束
```

该示例的拒绝与校验失败默认不隐式重试。不需要完整自主多 Agent 分工，也不引入自动发布。需要业务返工时另用主规范已有的有界 repeat 明确表达。

标准与 latent 的切换不修改图、不修改业务 Schema、不改变人工页面或验收。首次 latent 预检必须确认 draft/refine 是真实兼容的两个逻辑调用。

### S12.2 人工生产场景

另维护一个 `requestType=input` 的示例：人接收任务与材料，提交结构化结果或修订后的 ArtifactRef，程序验证输出，流程继续。

这个示例必须检验“人实际完成工作”，而不只是给 approve/reject 两个按钮。上传失败、必填缺失、输出错误、重复提交和请求过期都需覆盖。

### S12.3 页面与外部服务的替换

至少选择一个人工节点，验证内建页面与嵌入页面共享同一请求；另验证外部人工执行服务经统一 Adapter 提供相同业务输出。不得同时让两套权威相互覆盖。

协议自动化测试可以使用 fixture；“真实人操作”和“真实外部服务集成”分别保留证据，不把全部 Mock 当成真实可用声明。

### S12.4 不同执行者的互换示例

对一个不要求真人身份、语义和权限允许互换的生产节点，验证人、程序或 Agent 中至少两种实现能满足同一契约。身份必须为真人的审阅节点不参与这种自由替换。

这项演示证明接口边界和能力条件，不承诺不同执行者具有相同业务质量。

---

<a id="sup-13"></a>

## S13. 接口与配置缺口登记

本节区分“能力必须交付”和“接口尚未冻结”，避免把上一轮说明性建议当成当前可调用接口。

| 能力 | 主规范基础 | 本次追加要求 | 尚未冻结的细节 |
|---|---|---|---|
| Authoring Kit | 可解析文件、Schema、Validate/Eval/Diff | 外部 Agent 能找到版本匹配的指南、模板、正反例 | 指南具体目录和模板生成命令。 |
| 能力发现 | 注册表、ExecutorDescriptor、预检 | 授权范围内的机器可读能力清单与支持状态 | 聚合 API/CLI 的名称、分页与响应 Schema。 |
| 人工表单 | HumanRequest、HumanRequestPanel、decisionSchema | 输入展示与输出收集分离；支持基本字段和产物入口 | 展示扩展键、控件注册接口和完整支持矩阵。 |
| 自定义/外部入口 | UI SDK、Human API、HTTP Job | 入口可用、身份关联、单一权威、结果可核对 | 页面注册与导航元数据，不在节点中临时发明字段。 |
| Artifact 提交 | 元数据、摘要、存储、ACL、读取/下载 | 上传/外部登记至合法引用的完整闭环 | HTTP 方法/路径、上传会话与响应 Schema。 |
| 结构化人工 CLI | decide、权限/版本/幂等规则 | 以文件提交任意合规 input 结果，与页面一致 | `--decision-file` 为建议参数，需正式定义与实现。 |
| 程序 Wrapper | builtin/local_process/http_job | 入门模板、严格输入输出、真实能力声明 | 各示例的程序语言和包装工程形态。 |
| Latent 开关 | 主规范 14.6—14.12 与 A.9 已固定 | 按既有契约真实实现并验收 | 首个模型/Codec/后端的实际选型和锁定版本，不能预设已支持。 |

这些缺口应在对应实现开始前补齐，不要求重新讨论整个架构。接口补充不得改变已有三种顶层资源、call 模型、审批权威或活动 Run 冻结规则。

精确响应 Schema 未定义前，可以开发内部原型，但不能生成对外客户端或在 Authoring Kit 中宣称已支持。Schema、CLI/API、SDK、页面和测试更新必须同行。

---

<a id="sup-14"></a>

## S14. 实施顺序与职责

本节是在主规范 P0—P4、E1—E2 上追加工作，不重新排列已有可靠性优先级。

| 主阶段 | 本次追加工作 | 必须看到的结果 |
|---|---|---|
| P0 协议与骨架 | Authoring Kit、契约语义说明、正反例、能力发现与表单扩展接口定义 | 外部 Agent 能读到可验证依据；未知能力和错误字段精确失败。 |
| P1 单次交付 | 同一 call 的程序/Agent/人工适配；input 型人工任务；基本字段提交 | 真实输入—执行—人工结果—下游链路贯通，不靠手改状态。 |
| P2 恢复与控制 | 人工等待、重复/迟到提交、上传未完成、外部回传丢失/重复、未知结果 | 不丢决定、不重复工作、不把可能发生的动作当成未发生。 |
| P3 可交付与可嵌入 | 默认表单、Artifact 上传/登记、嵌入页面、可用外部入口、作者完整操作材料 | 同一包可部署，普通人能完成任务，外部 Agent 不需要点击页面创作。 |
| P4 组合与验收 | 混合场景、跨执行者契约测试、Authoring 闭环、补充验收 | 有明确实测材料，可分辨 Mock、真实 Adapter 与业务验收。 |
| E1 可选 Latent 原型 | 两个逻辑调用的真实导出/导入，同图开关对照 | 真实载荷进入模型计算，不用假向量或文本包装替代。 |
| E2 Latent 集成验收 | 不变 I/O、人工审阅、持久载荷、消费证据、恢复与权限 | 标准包独立可用；实验组合通过原 LH 验收与相关补充检查。 |

协议/Runtime 负责人维护不变的输入输出和生命周期；Adapter 负责人保证外部查询、取消、去重与证据真实；UI 负责人保证任务可操作且不越权；Authoring 负责人保证外部 Agent 可发现、可生成、可修复；发布负责人区分支持声明与实测范围。

不得为先展示漂亮表单、自动生成或 latent 动画而省略幂等、审批版本、Artifact 校验与取消核对。论文/模型原型可并行，但不得旁路接入真实有副作用业务。

---

<a id="sup-15"></a>

## S15. 补充验收与完成定义

### S15.1 新增验收

以下 `SUP-*` 为本次追加验收，不重编号或取代主规范 `AC-01—AC-49` 与 `LH-01—LH-14`。失败、未测和不支持分别记录；每项实测关联代码版本、依赖、环境与证据。

| ID | 场景 | 必须结果 |
|---|---|---|
| SUP-01 | 外部 Agent 从自然语言创建新流程 | 仅使用文档、Schema、能力信息与 CLI/API 完成包、测试和待绑定说明，不修改 Runtime、不自动化点击页面。 |
| SUP-02 | 作者读取不支持功能或不存在执行器 | 精确报告未实现/未绑定，不编造资源或忽略必需功能。 |
| SUP-03 | 语法、引用或业务字段错误 | 诊断可定位原文件和 JSON Pointer；修复后可重复校验。 |
| SUP-04 | 为获得通过而降低验收 | 必须形成显式规则变更与审阅，不能静默改测试、删除失败或绕过人工。 |
| SUP-05 | 机器可读命令输出 | CLI/API 状态一致，JSON 结果可解析，不混入日志；未实现参数不在支持声明中出现。 |
| SUP-06 | 静态、Mock、真实执行混合报告 | 每种证据分开，Mock 不冒充真 Agent、真人或 latent 消费。 |
| SUP-07 | 人、程序、Agent 执行同一可替换契约 | 保留输入输出语义、权限与版本；替换不依赖某种私有返回结构。 |
| SUP-08 | 要求真人的审批被 Agent 模拟 | 即使 JSON 合法也拒绝冒充；schema 兼容不授予身份与权限。 |
| SUP-09 | 程序成功返回 valid=false / 人拒绝 | 表示业务结论并走显式分支，不误判为传输失败或自动返工。 |
| SUP-10 | 退出 0 / HTTP 200 但结果不合规 | 输出或必需产物不合法时不得推进；原因关联本次调用。 |
| SUP-11 | 人工页面展示与提交 | 冻结任务材料只读；结果按 decisionSchema/outputSchema 收集，不要求普通用户手写 JSON。 |
| SUP-12 | 表单不支持某种契约 | 预检报告可操作入口缺口，不能运行后才显示无法填写或静默丢字段。 |
| SUP-13 | 默认值、页面打开或通知已读 | 不自动产生审批/输出；显式提交前仍等待。 |
| SUP-14 | input 型人工任务 | 成功提交结构化业务对象，审计 comment 不混入业务输出，结果被下游严格校验。 |
| SUP-15 | 人工文件上传并交付 | 先完成存储/登记/验证，再通过合法 ArtifactRef 提交；上传本身不完成节点。 |
| SUP-16 | 部分上传、任意路径或非法 ArtifactRef | 拒绝作为已交付结果，不伪造可读产物。 |
| SUP-17 | 上传与提交的跨权限引用 | 服务端逐项拒绝越权；UI 隐藏和客户端校验不能替代权限。 |
| SUP-18 | 人工等待时关闭浏览器或重启 | 请求、输入版本、期限和操作关系可恢复；不重新创建审批。 |
| SUP-19 | 并发/重复/过期/取消后提交 | 只有一份有效决定；返回原回执或明确冲突，不覆盖或重新激活。 |
| SUP-20 | 内建页与嵌入页处理同一请求 | 共用权威和 API；决定、Schema、版本和权限一致。 |
| SUP-21 | 外部人工服务回传或通知丢失 | 以稳定引用核对；回调认证去重；无重复外部工作、无双重决定权威。 |
| SUP-22 | 人声明外部工作已完成 | 展示声明与证据来源；需要独立验证时经后续节点确认，不夸大事实。 |
| SUP-23 | 页面与结构化 CLI 提交同一类结果 | 同一归一化对象、权限、subjectDigest、expectedVersion 和幂等语义。 |
| SUP-24 | Agent 生成程序源码 | 只形成待审阅实现，不因导入包自动安装、授权或执行。 |
| SUP-25 | 遗留程序副作用结果未知 | Wrapper 不假报安全重试，先查明原工作，不能用输入输出包装伪造恢复能力。 |
| SUP-26 | 切换标准/latent | Workflow 和业务 Schema 不变；只有选定机器交接变化，人工页面与验收不变。 |
| SUP-27 | latent 结果交给程序或人 | 必需结构化输出、约束、产物与可读证据仍存在，不要求读取不透明张量猜结果。 |
| SUP-28 | 全部能力的对外支持声明 | 原 AC/LH 与本 SUP 分别有证据；未实现、未验证、不支持如实公开，不以文档自证完成。 |

### S15.2 最低演示材料

交付一个由外部 Agent 依据需求编写的混合流程包，一份明确区分验证层次的编写记录，一个真实人工输入/文件交付记录，一组程序边界正反例，以及同图标准/latent 对照记录。

无法使用真实服务、身份或模型时继续其他开发，但对应验收保持未完成；不能将人工编辑 JSON 或返回 Mock consumed=true 当作能力成立。

### S15.3 完成定义

“能够生成 JSON”“图上出现人类节点”“页面有按钮”“开关能改变显示”“一次运行成功”均不单独构成完成。

完成意味着：外部 Agent 能在契约与反馈下生成可交付流程；程序和人按同一边界产出合规结果；人工具有真正可操作入口；失败、版本、权限和证据可解释；标准与 latent 的切换不破坏这些边界，并有相应真实验收记录。

---
<a id="append-examples"></a>

## 附录 A. 契约与人工节点示例

以下内容用于说明追加要求，不是一份完整可独立部署的 Workflow Package。`file` 路径是目标样例路径，`node fragment` / `binding fragment` 是合并位置；省略的 Workflow、其他 slots、注册对象、权限和文件须按主规范补齐。

示例业务字段不成为核心协议字段。样例中的 Artifact ID、执行器 ID 和身份是占位值，不代表已经存在或有权访问。真实运行必须解析与验证。

### A.1 统一的人工审阅节点

此节点沿用主规范 call 形状；只有 Binding 决定具体采用内建人工页面还是符合相同要求的外部人工服务。

<!-- node fragment: Workflow.spec.nodes.review -->
```yaml
review:
  type: call
  title: 人工审阅交付物
  description: 阅读当前版本和校验结果，提交明确审阅结论。
  slot: reviewer
  deadlineSeconds: 259200
  inputSchema: schemas/review-input.json
  outputSchema: schemas/review-output.json
  input:
    object:
      deliverable: {ref: "nodes.produce.output#"}
      verification: {ref: "nodes.verify.output#"}
  requires:
    capabilities: [human.review@1]
  effects:
    class: none
    actions: []
  next: review-route
```

`produce`、`verify` 和 `review-route` 必须在实际 Workflow 中存在，引用关系必须合法。`review-route` 根据结构化 decision 分支；不得根据 comment 中的自然语言猜测批准。

<!-- file: examples/supplement/schemas/review-output.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "审阅结论",
  "type": "object",
  "additionalProperties": false,
  "required": ["decision", "comment"],
  "properties": {
    "decision": {
      "title": "结论",
      "description": "对本次请求所绑定版本的审阅结论，不授权未说明的其他动作。",
      "type": "string",
      "enum": ["approve", "reject"]
    },
    "comment": {
      "title": "审阅说明",
      "type": "string",
      "maxLength": 8000
    }
  }
}
```

是否拒绝时必须填写说明，仍由既有 requireCommentFor 和服务端规则保证。Schema 结构合法不替代真人身份、主题版本或授权检查。

### A.2 人工完成工作并提交文件

以下是 `requestType=input` 的业务输入/输出样例，不引入新的 HumanRequest 类型。输入面板展示 objective 与源材料；结果区域收集已登记的交付物和变更说明。

<!-- file: examples/supplement/schemas/manual-work-input.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "人工修订任务",
  "type": "object",
  "additionalProperties": false,
  "required": ["objective", "source_artifact_refs", "constraints"],
  "properties": {
    "objective": {
      "type": "string",
      "minLength": 1,
      "description": "本次人工工作需要交付的目标。"
    },
    "source_artifact_refs": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {"type": "string", "minLength": 1},
      "description": "已登记且当前身份有权读取的源产物 ID。"
    },
    "constraints": {
      "type": "array",
      "maxItems": 30,
      "items": {"type": "string", "minLength": 1},
      "description": "必须遵守的明确约束，不能只置于隐式上下文。"
    }
  }
}
```

<!-- file: examples/supplement/schemas/manual-work-output.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "人工交付结果",
  "type": "object",
  "additionalProperties": false,
  "required": ["artifact_refs", "change_summary"],
  "properties": {
    "artifact_refs": {
      "title": "交付文件",
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {"type": "string", "minLength": 1},
      "description": "完成上传或登记后获得的合法 Artifact ID，不接受任意本地路径。"
    },
    "change_summary": {
      "title": "变更说明",
      "type": "string",
      "minLength": 1,
      "maxLength": 8000,
      "description": "本次人工修订的说明；不替代产物内容与独立校验。"
    }
  }
}
```

这些数组上限仅为本样例的业务约束，不是新增全局默认值。字符串形状通过 Schema 后，Runtime 仍必须检查引用实际存在、已完成存储、版本和 ACL。

<!-- binding fragment: BindingSet.spec.slots.manual-editor -->
```yaml
manual-editor:
  adapter: human
  executorRef: example.manual-editor.v1
  config:
    requestType: input
    choices: []
    authorizedSubjects: [example-editor]
    requireCommentFor: []
  secretRefs: {}
  grants: []
```

`example.manual-editor.v1` 与 `example-editor` 必须在示例环境中预注册并验证。这个片段使用主规范已有 Human config 字段；没有假设新增页面 URL 字段已经存在。人工任务是否涉及外部业务副作用，应在实际节点 effects 中按真实语义声明。

提交到既有 HumanRequest decision 接口时，业务结果位于 decision 中；expectedVersion、subjectDigest 和 Idempotency-Key 由客户端按真实请求获取并提交。下面只展示 decision 的值，不是完整 HTTP 请求：

<!-- example: manual-decision-value -->
```json
{
  "artifact_refs": ["example-artifact-id"],
  "change_summary": "修正术语，补充缺失章节，并更新引用。"
}
```

该样例可通过业务形状检查，但真实运行中占位 Artifact ID 不应通过存在性/授权校验。测试必须将这两个层次分开。

### A.3 固定程序输出的是业务结论

<!-- example: verification-business-output -->
```json
{
  "valid": false,
  "findings": ["交付物缺少必需章节"]
}
```

该对象符合主规范示例的 verification Schema。它表示校验已执行但交付物不满足业务要求，不意味着进程崩溃。Runtime 根据显式 switch 路由，而不是自动重试校验器或改写 valid。

### A.4 最小边界用例

| 输入/动作 | 期望 |
|---|---|
| review 的 decision 为 approve/reject，comment 为字符串 | 形状可通过；仍须检查请求、身份、版本与授权。 |
| decision 为其他值，或 comment 不是字符串 | Schema 拒绝。 |
| input 请求返回人工交付对象 | 按节点 outputSchema 校验，不能额外要求 `{decision, comment}` 业务包裹。 |
| artifact_refs 为空 | 本样例 Schema 拒绝。 |
| artifact_refs 非空但 ID 不存在或越权 | 形状可能通过，Runtime 必须拒绝。 |
| 只上传文件未提交请求 | HumanRequest 仍等待，不产生最终输出。 |
| 有效 review 输出但属于旧 subjectDigest | 提交冲突/拒绝，不应用到当前版本。 |

---

<a id="append-latent"></a>

## 附录 B. Latent Handoff 完整沿用条款

**以下内容直接收录自主规范修订 1.1.0，不是新协议。**其“第 9 章”“第 11—12 章”“第 14.3 节”等编号均指主规范。原文中的示例、待实现状态和支持范围保持不变。

B.1 收录主规范第 14.6—14.12 节，B.2 收录附录 A.9 的配置与结构 Schema，B.3 收录第 25.5 节的全部专项验收。它们与本文件 S11、S15 一起阅读，不删减原 AC/LH 门槛。

### B.1 通信开关、范围、兼容、传输、审计与后端

<!-- BEGIN VERBATIM: MULTIVERSE_SPEC.md@1.1.0 sections 14.6-14.12 -->
### 14.6 通信模式：一个可选开关

唯一用户开关为 `BindingSet.spec.communication.latentHandoff.enabled`，boolean，默认 `false`。它是部署配置，不是 Workflow 业务拓扑的一部分。

| 开关 | 机器交接方式 | 保持不变的内容 |
|---|---|---|
| `false` | 标准结构化输入输出、必要文本 Handoff、ArtifactRef | 权威状态、调度、重试/核对、权限、审批、审计、验收 |
| `true` | 配置 routes 上使用已验证兼容的 latent 导出/导入；其他节点仍按标准契约工作 | 同左；额外记录实际载荷、配置版本和消费回执 |

“关闭”不要求 GPU、模型隐藏态接口、latent 插件、向量服务或 latent 专用凭据；不得加载这些依赖后才发现开关关闭。标准路径不承诺属于所有外部工具的统一行业实现，只表示本项目的默认可互操作契约。

“开启”不是尽力优化提示：配置的交接必须使用真实 latent 载荷。V0.1 **不提供自动回退开关**；未安装、模型不兼容、载荷不可用或接收端未消费时明确阻止相关执行或按确定失败处理，不静默改用摘要重跑。已有外部工作结果未知时进入核对，继续遵守第 11—12 章。

首次为一个部署配置 routes 和 profile；此后用户只需切换 enabled 并完成预检。更新开关创建新的 BindingRevision/Deployment，只作用于新 Run。活动 Run 和已有 Attempt 不允许热切换，包括暂停后继续。要用另一模式比较或重跑，创建新 Run，并记录来源；不复制人工批准。

### 14.7 配置、适用范围与 route 校验

`communication` 仅允许 `latentHandoff`。其字段为：

| 字段 | 类型 / 默认 | 规则 |
|---|---|---|
| `enabled` | boolean，默认 false | 唯一模式选择；字符串 `"true"` 非法 |
| `routes` | array，默认 [] | 每项严格为 `{from, to, profile}`；from/to 为 `workflow_id/node_id`，profile 是环境注册 ID |

开启时 routes 非空；关闭时允许保留 routes 供下次实验，但只验证配置形状、节点引用和图关系，不解析模型、访问 latent 凭据或加载插件。编译后显式记录 enabled=false，不能仅凭 routes 非空擅自开启。

V0.1 的 route 只连接同一 Workflow 定义、同一实际 ExecutionScope 内的两个 `call` 节点。源必须在所有能够到达目标的正常路径上先完成，校验遵守第 7.9 节；route 不创建新调度依赖、不跳过节点、不改变分支。该 Workflow 被嵌套或 repeat 调用时，每个 scope 形成独立交接，禁止跨轮次混用。跨 scope、隐式广播和动态通信拓扑不属于本次能力。

同一目标最多一个 latent 来源，禁止默认拼接多个 KV 或隐藏状态。一个源可交付给多个目标，但分别创建交接身份和消费记录；载荷不可变，分支不能共同修改同一活动缓存。多个来源需先通过明确的聚合节点产生一个符合 profile 的载荷。

源与目标都必须支持选定 profile；Human Adapter 不作为 latent 消费者。程序节点、审批节点和未配置的交接继续使用标准数据。预检和 Inspector 显示明确的覆盖范围，不能将一个局部 latent route 显示为整个 Workflow 所有节点都采用 latent。

如果本次分支未经过任何配置的 route，记录“已开启，但本次未执行 latent 交接”，不计作真实 latent 实验样本。

### 14.8 CommunicationProfile 与兼容预检

CommunicationProfile 由环境管理员在注册表中安装并固定版本，不作为包导入时可执行的新资源。至少记录：profile ID/version/digest、导出和导入 Adapter/执行器版本、源与目标模型修订及相关权重/配置标识、表示格式、序列化版本、Codec/对齐版本（如有）、形状与精度约束、上下文位置/前缀绑定规则、资源上限、持久化方式，以及经过验证的兼容组合。

框架不规定所有模型使用同一种 latent 格式，不要求所有 profile 只能同模型；但每个允许组合必须逐项验证。不能只因为向量维度相同、模型名称相近或双方都能调用 HTTP，就判断兼容。首个实验后端至少锁定一组真实可运行的导出/导入组合，不声称支持任意闭源接口或跨模型转换。

开启前必须验证：插件可用；routes 有效；双方 Descriptor 声明相同 profile digest 的导出/导入；版本与配置匹配；数据访问与权限域允许；载荷存储和恢复方式满足本规范；资源上限足够。预检不借机执行付费模型推理或业务动作；真实端到端消费的验证结果来自单独授权的 LH-02 测试。

声明兼容而尚未完成真实验证时显示 unverified，并阻止激活 latent 部署。运行前再次检测版本漂移；历史兼容证明不能覆盖变更后的模型。标准模式不执行这些 latent 专属探测。

### 14.9 传输契约、持久化与真实消费

首版将 latent 当作受保护的 **Handoff 载荷**，不当作 State。沿用原 Adapter 的 submit/observe/lookup 生命周期，不再创建另一套无持久身份的点对点聊天通道。

参与通信的 ExecutionRequest 可带以下字段；标识和摘要由 Runtime 生成，此处为字段契约：

- `context.communication.version` 固定为 `multiverse.handoff/v0.1`。
- `exports` 为 `{routeId, profileDigest}` 数组，通知源执行器为成功结果产生哪些不可变载荷。
- `imports` 为 `{handoffId, routeId, profileDigest, payloadRef, payloadDigest}` 数组；V0.1 每次调用最多一项。

routeId 来自冻结计划，exports/imports 缺省空数组。无 latent 工作的标准调用省略整个 context.communication。完整 Context 摘要覆盖模式、路由、所有 profile/载荷摘要、必需显式材料及实际注入文本；请求指纹必须覆盖 input 与 context，不能只对业务 input 做幂等比较。

源的终态观察可带 `handoffExports`，每项包含 `{routeId, profileDigest, payloadRef, auditHandoff}`。payloadRef 必须为已完成存储、可校验内容摘要的 ArtifactRef，不能只是裸 GPU 指针、短命 Session 名或可变 URL。auditHandoff 满足第 14.3 节；实际生成方式与来源另行记录。Runtime 关联该源 Attempt、输出版本和载荷摘要，创建具体目标调用的 HandoffRecord。目标尚未激活时可先建立 planned invocation 身份以登记交接，但不得因此转为 ready 或提前派发；若目标随后因分支未选中而 skipped，交接保留为未消费，不构成运行失败。

只有原输出契约、必需导出载荷及其审计 Handoff 均验证通过，源 invocation 才可成功并释放下游。外部执行器已成功但漏载荷，不等于 Runtime 可以重复执行上游：先查询相同 execution，确认最终缺失后记录 `LATENT_PAYLOAD_UNAVAILABLE` 并按既有错误规则处理，不另造一份源执行。更新外部 revision 也不得篡改已固定终态。

目标的观察包含 `handoffReceipts`，每项为 `{handoffId, payloadDigest, profileDigest, consumerVersion, consumed}`。只有接收执行器确认该载荷确实进入模型计算后才可填 consumed=true；仅收到 URL、下载完文件、将张量转成字符串或把摘要放入 Prompt 都不构成 latent 消费。目标 invocation 成功前，Runtime 必须核对与请求完全一致的 consumed=true 回执。中间观察的 consumed=false 可以在更高 revision 变为 true；同一 revision 的冲突内容违反执行器协议。最终消费记录不可覆盖，所有原始观察保留在 Inbox/事件记录中。

消费回执是执行器提供的证据，并不是 Runtime 能直接洞察神经网络计算的证明。真实后端验收还需确认载荷进入隐藏表示/KV/约定模型输入接口；Inspector 标明证据来源和可观测范围。Mock 回执只验证协议，不证明实验能力成立。

HandoffRecord 至少持久化：handoff_id、namespace/run/scope、源 invocation/attempt、目标 invocation、route_id、mode、profile_digest、payload_ref/digest、源输出与输入快照摘要、audit_ref/digest、created_at、交付/消费状态和逐 Attempt 接收证据。源成功提交、必要交接登记及下游唤醒保持事务一致；目标输入快照与 submit outbox 同事务冻结。二进制对象沿用第 14.2 节的先完成存储再登记流程。

恢复重用同一份已固定载荷及原 dispatchKey；已确认安全的重试使用同一 invocation 的输入快照，不重新生成语义载荷。目标执行结果未知时先 lookup/reconcile，不因缺少消费回执新建执行。载荷丢失或模型版本改变时 blocked，报告具体原因；不得退回文本、重新生成不同 latent 或自动从头执行业务。

### 14.10 可读审计、显式边界与安全

两种模式都提供可读交接和证据。审阅卡至少显示：当前产物和版本、已确认完成项、尚未完成项、风险/不确定性、关联事件/产物、实际通信模式，以及 latent 模式下的 profile 和载荷摘要。审计摘要与同一 HandoffRecord 绑定，禁止显示另一轮或另一模式的旧摘要。

已观察到的状态、校验结论与审批来自权威记录；模型生成的原因、假设和建议标为解释。摘要是审计入口，不是对 latent 内部推理的完整或忠实解码保证。没有证据的解释不能升级为事实。人工 Request 的 subjectDigest 覆盖实际需要审阅的版本和相关交接证据；摘要或审批主题变更遵守第 13 章。

latent route 默认不把该 route 的自然语言审计摘要再交给目标作为备用上下文；必需业务输入、约束、权限和结构化输出始终显式。用户可以查看摘要，但实验报告必须披露其他实际注入的文本，不能宣称“纯 latent”而暗中发送完整原始上下文。

不要求每个内部 latent step 都生成摘要，只在交接边界和已有人工/风险边界生成。摘要生成失败时使用有来源的结构化事实模板；不得伪造模型解释。实际模型推理、存储、传输及摘要生成成本全部纳入测量。

latent 载荷按来源上下文的敏感级别和权限处理；人看不懂二进制不构成脱敏。不得绕过 namespace、授权与保留策略，也不得把潜在秘密通过载荷转交给更低权限执行器。首个实验后端只验证明确授权的同一数据访问域，不声称提供跨域自动净化。

使用限额、格式白名单及无可执行反序列化的载荷格式；禁止不可信 pickle 或任意安装/解码脚本。解压/解码后的大小和形状也必须受限。原始张量/KV 不放入 JSON 状态、LangGraph Checkpoint、SSE、普通日志或 OTel；这些位置只放受控引用、摘要和状态。

### 14.11 实现模块与首个实验后端

建立 `communication/` 边界，包含标准 Handoff、模式解析、route 预检、HandoffRecord 与可选 profile 注册接口。推理库、模型权重和具体 Codec 位于可选插件或独立实验执行服务，不进入核心启动依赖。开关关闭时基础 Runtime、CLI、Inspector 和既有 Adapter 独立工作。

第一版必须交付至少一个真实的 latent 导出/导入适配示例及配套可选安装方式，锁定模型/Codec/推理环境版本。可以复用成熟研究实现，但本规范不将任何未核验的研究仓库、模型或假定包名标为已支持；实现时将实际选型、许可证、依赖锁和通过的 profile 记录到注册表及测试报告。

不能只把若干模型角色封装成一个黑盒执行器，就宣称框架级开关已完成。该黑盒可以作为底层实现，但 LH-02 必须证明至少一条规范 route 在两个逻辑调用之间完成真实 latent 交接，并可在同一 Workflow/同组已兼容执行器下关闭为标准交接进行对照。

### 14.12 开关决策表

| 条件 | 必须行为 |
|---|---|
| 未配置 / enabled=false | 标准交接；不加载、不探测 latent 依赖 |
| enabled=true，未配置有效 routes | 422 `INVALID_SPEC`；不创建业务执行 |
| enabled=true，未安装支持实现 | `LATENT_HANDOFF_UNSUPPORTED`；不得静默按标准模式运行 |
| profile、模型或 Codec 不匹配 / 未验证 | `LATENT_PROFILE_MISMATCH` 或未验证报告；阻止激活/派发 |
| 载荷缺失、损坏或接收端未消费 | 阻止成功/推进，分别记录载荷或消费错误；依据真实执行状态核对 |
| 运行中修改开关 | 不改变原 Run；通过新部署发起新 Run |
| 流程包含程序、人或其他非 route 节点 | 保持标准契约；明确展示覆盖范围 |
| 分支未经过 latent route | 记录本次未使用；不以开关值替代真实实验结果 |
<!-- END VERBATIM: sections 14.6-14.12 -->

### B.2 开关配置与结构 Schema

<!-- BEGIN VERBATIM: MULTIVERSE_SPEC.md@1.1.0 appendix A.9 -->
### A.9 Latent 开关配置与结构 Schema

以下是插入同一份 BindingSet.spec 的配置片段，不是独立声明资源。`analysis/draft` 与 `analysis/refine` 是示意引用；使用时替换为包内真实且满足第 14.7 节的 call 节点。`lab-latent-v1` 是需由实验实现注册和验证的 profile，不是现成可下载服务。

关闭（默认；也可以完全省略 communication）：

```yaml
communication:
  latentHandoff:
    enabled: false
```

开启（首次完成 routes/profile 配置后，以后只改 enabled）：

```yaml
communication:
  latentHandoff:
    enabled: true
    routes:
      - from: analysis/draft
        to: analysis/refine
        profile: lab-latent-v1
```

关闭时可保留上述 routes，但不访问 latent 环境。两种配置都必须与原 BindingSet 的 slots 等字段合并，经过 validate 与新部署激活，不能作为活动 Run PATCH。

下面的 Schema 校验 communication 对象形状；节点依赖、profile 真实性、已验证兼容性和权限由语义预检另行检查。BindingSet Schema 的可选 communication 属性引用此文件。默认值由编译器显式补齐；JSON Schema 的 default 不负责修改输入。

<!-- file: schemas/communication.schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Multiverse Communication v0.1",
  "type": "object",
  "properties": {
    "latentHandoff": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": false},
        "routes": {
          "type": "array",
          "default": [],
          "uniqueItems": true,
          "items": {
            "type": "object",
            "required": ["from", "to", "profile"],
            "properties": {
              "from": {"type": "string", "pattern": "^[^/\\s]+/[^/\\s]+$"},
              "to": {"type": "string", "pattern": "^[^/\\s]+/[^/\\s]+$"},
              "profile": {"type": "string", "minLength": 1}
            },
            "additionalProperties": false
          }
        }
      },
      "allOf": [
        {
          "if": {"required": ["enabled"], "properties": {"enabled": {"const": true}}},
          "then": {"required": ["routes"], "properties": {"routes": {"minItems": 1}}}
        }
      ],
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```
<!-- END VERBATIM: appendix A.9 -->

### B.3 原专项验收 LH-01—LH-14

<!-- BEGIN VERBATIM: MULTIVERSE_SPEC.md@1.1.0 section 25.5 -->
### 25.5 可选 Latent 能力验收

以下测试针对实际声明支持的模型/profile/环境组合；测试值必须区分协议 Mock 与真实推理。未通过时可以发布明确的开发预览，但不能宣称 V0.1 的 Latent 开关已经可用。

| ID | 场景 | 必须得到的结果 |
|---|---|---|
| LH-01 | 同一包同一组兼容执行器切换 enabled | Workflow 摘要不变；创建不同部署；关闭时标准、开启时指定 route 使用 latent |
| LH-02 | 两个逻辑调用间真实交接 | 导出真实模型表示，目标在模型计算中消费；保存载荷摘要、消费回执、模型/Codec/依赖版本和实测证据 |
| LH-03 | 假向量、转成字符串、仅注入审计摘要 | 不得通过真实后端验收，不得据此标为 latent 已支持 |
| LH-04 | 模型/profile/Codec 版本不一致或漂移 | 激活或后续派发受阻；不自动换模型/回退文本 |
| LH-05 | 开启但路由不满足同 scope/依赖/单源限制 | 预检定位到配置字段并拒绝；不修改 Workflow 拓扑“修好”它 |
| LH-06 | 载荷损坏、过大或使用危险序列化 | 校验拒绝；无不可信代码执行、无隐式截断 |
| LH-07 | 导出后重启、接收端提交响应丢失 | 重用原载荷、交接身份和 dispatchKey；核对同一执行，不重新生成/重复派发 |
| LH-08 | 实际消费回执缺失、摘要不匹配或 consumed=false | 目标不得标成功；已提交的执行先查明状态，不盲目重派 |
| LH-09 | 活动 Run 期间关掉/打开开关 | 原 Run 模式与 profile 不变；新模式通过新部署/新 Run 生效 |
| LH-10 | 人工/程序混合节点、分支未经过 route | 非 route 标准执行；本次零 latent 消费显示未使用，不冒充成功实验 |
| LH-11 | 重复、并行和有界循环中的交接 | scope/轮次/目标隔离；不可变载荷不被并发修改；无错配消费 |
| LH-12 | 审计摘要、证据和审批关联 | 关联同一交接/产物版本；事实与模型解释区分；无旧批准复用、无伪造内部推理解释 |
| LH-13 | 跨 namespace/更低权限读取、载荷备份恢复 | 权限拒绝；日志/OTel 不泄露原始载荷；备份完整，丢失时明确阻塞 |
| LH-14 | 开关对照与真实成本报告 | 同数据/验收与披露配置；含传输/摘要/资源/失败成本；零消费与失败样本不隐去，不要求 latent 必然更优 |
<!-- END VERBATIM: section 25.5 -->

---

<a id="append-author"></a>

## 附录 C. 给外部 Agent 的完整编写指引

以下可直接作为 Authoring Kit 的任务引导。它只指导作者使用公开契约，不授予执行、审批或发布权限。具体用户目标、环境能力和预算由实际任务提供。

```text
你是 Multiverse 工作流作者，不是 Runtime，也不自动拥有任何人工审批身份。

依据：
- 读取 MULTIVERSE_SPEC.md，确认修订版本。
- 读取 MULTIVERSE_APPEND_SPEC.md。
- 读取安装版本提供的 JSON Schema、正反例、CLI/API 操作说明。
- 读取授权范围内的执行器、能力、人工入口和通信 Profile 信息。

第一步：理解交付。
明确用户目标、必需产物、输入、约束、验收、人工参与点、外部副作用。
缺少关键能力或环境信息时列出待绑定项；不要编造已经可用的资源。

第二步：先设计契约。
给每个 call 节点定义明确的 inputSchema、outputSchema、Capability 和 effects。
区分执行状态、业务输出和自然语言解释。
为重要字段说明含义、单位、范围、空值和版本，不把一切变成自由文本。
需要真人的节点不能用 Agent 返回相同 JSON 来替代身份。

第三步：生成包。
生成 WorkflowPackage、Workflow、业务 Schema、必要资源、Eval 和 Binding 示例。
只使用支持的顺序、switch、parallel、nested workflow、显式有界 repeat 等结构。
使用规定的 ValueExpr 和 Predicate，不写任意脚本表达式或隐式共享状态。
真实凭据、执行器地址和个人/企业环境配置留在部署 Binding 中。
不要创建第四种未支持的顶层资源或未知必需字段。

第四步：设计人怎样完成工作。
区分只读输入材料与待提交输出。
approval/review 按既有 choice/comment 契约；input 提交 outputSchema 规定的业务对象。
选择已有的内建表单、嵌入页面或外部人工服务；决定权威只能有一个。
提交文件时走上传/登记、校验、ArtifactRef、请求提交闭环。
没有实现的页面/上传接口不能假装存在；界面扩展须遵守已注册配置。

第五步：处理固定程序。
复用可信 builtin、Local Process、HTTP Job 或薄 Wrapper。
只生成待审阅的程序代码，不因写进 Workflow Package 就获得执行权限。
输出必须可校验；stdout、stderr、退出状态与错误遵守 Adapter 契约。
未知副作用先核对，不用重试掩盖缺失的恢复能力。

第六步：选择通信。
默认 latentHandoff.enabled=false。
只有用户明确选择实验且 route/profile 已实际支持并验证，才提出开启的部署配置。
开启只改变选定 route 的机器上下文，不改变业务 Schema、必需约束和人工审阅。
不以向量检索、随机向量、字符串包装或审计摘要冒充真实 latent。
不静默回退文本，不在活动 Run 中切换。
作者自身不需要模型隐藏状态接口。

第七步：验证和修复。
按 Validate、预检、Fixture、授权真实执行/Eval、Diff 的顺序给出证据。
使用结构化诊断修复错误，不删除必填条件、弱化验收或伪造产物以获得通过。
静态、Mock、真实执行与业务质量结论分别报告。
测试中的人工决定不得转成生产批准。
任何会产生真实外部写入或费用的测试必须符合授权和预算。

第八步：交付变更。
说明包版本、修改文件、节点契约、权限/副作用变化、人工入口、通信模式、
已验证结果、未测项、待绑定项、后续部署步骤。
只调用已经定义并实现的命令；缺失参数或能力明确说明。
不得修改活动 Run、运行数据库、真实审批或未知执行事实。
部署激活、合并和生产发布交由具有对应权限的主体决定。
```

---

<a id="append-sources"></a>

## 附录 D. 来源、追溯与尚未决定的事项

### D.1 来源范围

本文依据主规范修订 `1.1.0` 与本次对话已经给出的两轮补充引导整理，不以外部市场研究、框架宣传或模型能力推测补全缺失实现。

初始架构的“统一黑盒节点”“AI/Git 编辑”“可移植 Package”“State/Memory/Context 分离”和“内部实现自由，外部边界确定”继续保留；主规范已经确定的技术与行为不因早期草案而回退。

| 主题 | 主规范定位 | 本文件处理 |
|---|---|---|
| 顶层资源、Schema、引用与诊断 | §6 | 沿用；增加外部作者使用指引，不重新定义语法。 |
| 统一 call 与控制流 | §7 | 沿用；强化业务状态与执行状态区分。 |
| 注册表、能力、Binding | §8 | 沿用；追加面向作者的能力发现闭环。 |
| 执行请求、观察与程序适配 | §9 | 沿用；补充 Wrapper 与作者安装边界。 |
| 权限与持久恢复 | §10—12 | 沿用；应用于人工页面、上传与外部服务。 |
| HumanRequest 与单一决定权威 | §13 | 沿用；完善 input 型工作、表单、外部入口。 |
| State、Artifact、Context、审计 | §14.1—14.5、§15 | 沿用；明确上传与交付、事实与解释的区别。 |
| Latent Handoff | §14.6—14.12、附录 A.9 | 原规则沿用；附录 B 收录完整条款与结构 Schema。 |
| Package 与部署 | §16 | 沿用；生成的是小型包而非不可验证的大段文本。 |
| HTTP API、CLI | §17—18 | 沿用已定义部分；能力发现、上传和结构化人工 CLI 的缺口显式登记。 |
| Inspector 与嵌入 UI | §19 | 沿用；增加任务可操作性、表单支持矩阵与单一提交语义。 |
| 外部 AI 编辑与 Eval | §20.4 | 从最低文件支持细化为 Authoring Kit 与完整创建闭环。 |
| 实施与验收 | §24—25 | 不改原阶段；增加 SUP-01—SUP-28，保留全部 AC/LH。 |

上轮提到的 JSON Forms 可作为表单实现参考，但不是本次固定的新依赖；其他表单实现只要满足同一契约和支持矩阵也可以采用。本文件不新增对其当前版本或能力的研究结论。

### D.2 已决定与尚未决定

已决定：外部 Agent 原生编写；统一 call 与 I/O；人、程序、Agent 按同一执行边界参与；人工有实际可操作入口；Artifact 提交闭环；默认标准交接与可选真实 latent；权限、版本、恢复与证据不因模式改变。

尚未决定：S13 列出的新接口具体字段与路径、UI 展示扩展键、自定义控件注册协议、上传会话形态，以及首个真实 latent 模型/Codec 的实际选型。这些不得静默填成既有功能，也不得被开发者跳过；在对应接口实现前通过带 Schema 和测试的变更固定。

### D.3 文件维护规则

主规范不因本文件生成而修改。将本文件与主规范放在同一目录，引用章节时注明文件名及修订。Authoring Guide、生成类型和测试是两份文档的可执行表达，不再产生第三套行为规则。

后续维护时，新增行为和接口在同一变更中更新相关章节、Schema、SDK、CLI/API、示例及测试。附录 B 的原文摘录须与适用主规范一致；变更主规范版本时重新检查摘录，不保留两份冲突规则。

### D.4 交付性质

这是一份规范性 Markdown 文档，不包含已实现的 Runtime、上传服务、表单组件或模型后端。示例和 Schema 可做静态检查，但不能因此宣称任何真实执行、权限隔离、恢复、人工业务操作或 latent 效果已经通过验收。

**最终目标：同一份契约，支持自由实现、可验证交付和可解释协作；作者工具、执行者类型、交互页面及机器通信方式都可以替换，而边界语义不被替换。**
