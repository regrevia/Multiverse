# Multiverse V0.1 唯一开发规范

**修订 2.2.0 · v1 发布契约与证据门槛 · 保留 multiverse/v0.1**

| 项目 | 固定值 |
|---|---|
| 权威文件 | `MULTIVERSE_SPEC.md` |
| 文档修订 | `2.2.0` |
| 核心协议 | `multiverse/v0.1` |
| 基准日期 | `2026-09-26` |
| CLI / Python | `mverse` / `multiverse_workflow` |
| 文档状态 | 待实现与待验收的统一开发依据，不是现有源码完成声明 |
| 合并范围 | 主规范 1.1.0＋两份既有补充 1.0.0＋本轮引导 Spec 3 |
| 核心目标 | 任意受支持数量的 Agent、人、程序、外部服务共享契约；标准通信自动处理；独立、混合、离线与目标嵌入分别验证 |

> **内部实现自由，外部边界确定。固定契约，不固定角色数量。**
>
> Workflow 定义工作，Binding 选择实现，Execution Host/外部平台执行，Runtime 保存与推进事实，Inspector/宿主显示并控制，交付包将完整能力带到目标环境。

## 导航

- [0. 文档效力、阅读方法与命名边界](#s00)
- [1. 定位与产品目标](#s01)
- [2. 不可破坏的原则](#s02)
- [3. V0.1 范围与明确不做的事](#s03)
- [4. 领域模型与身份](#s04)
- [5. 技术栈与架构决策](#s05)
- [6. 文档格式、通用类型与校验](#s06)
- [7. Workflow Contract 与控制流](#s07)
- [8. Capability、Binding 与部署解析](#s08)
- [9. Executor Adapter Contract](#s09)
- [10. 权限、Policy 与安全边界](#s10)
- [11. 生命周期、失败与人为控制](#s11)
- [12. 持久执行、一致性与 LangGraph 集成](#s12)
- [13. Human Request 与受控审阅](#s13)
- [14. State、Artifact、Handoff、Context 与 Memory](#s14)
- [15. 运行事件、Trace 与可解释性](#s15)
- [16. Workflow Package、Preset 与部署生命周期](#s16)
- [17. Runtime HTTP API](#s17)
- [18. CLI 与无界面工作流](#s18)
- [19. Inspector 与可嵌入 UI SDK](#s19)
- [20. Evaluation 与 AI 编辑闭环](#s20)
- [21. 部署、运维与资源边界](#s21)
- [22. 持久数据模型与事务要求](#s22)
- [23. 仓库、模块与开发约束](#s23)
- [24. 实施阶段、职责与进入条件](#s24)
- [25. 验收清单与完成定义](#s25)
- [26. 后续演进边界](#s26)
- [27. 受管执行配置、Execution Host 与工作区](#s27)
- [28. 远程 Connector：配对、派发与恢复](#s28)
- [29. 通用组合与协作标准库](#s29)
- [30. Agent 优先开发与跨环境连续性](#s30)

附录：[A 基础样例](#appendix-a) · [B 一致性施工](#appendix-b) · [C 来源](#appendix-c) · [D 人工/程序样例](#appendix-d) · [E 通用组合样例](#appendix-e) · [F 作者指引](#appendix-f) · [G 合并映射](#appendix-g)

---

<a id="s00"></a>

## 0. 文档效力、阅读方法与命名边界

<a id="sec-0-1"></a>

### 0.1 唯一基准与版本

本文修订 **2.2.0** 增加 v1.0 稳定试用的发布契约、profile、兼容策略与验收证据门槛；2.1.0 在 2.0.0 合并基线上增加第 30 章，并强化第 20.5 节的 Agent 第一开发者定位。2.0.0 合并并替代主规范 1.1.0、第一追加 1.0.0、运行接入交付补充 1.0.0 与本轮引导 Spec 3。日常开发、验收和集成只引用本文件及由它生成的 Schema/类型/测试；旧文件归档用于追溯，不再提供并行规则源。

核心协议继续为 `multiverse/v0.1`。文档大版本变化表示产品要求的统一与扩展，不等于对外线级协议已发布 2.0，也不声称现有源码已经支持全部要求。新增标准库描述使用自己的版本标识，不新增 Workflow 顶层 kind。

MUST/必须为验收要求，MUST NOT/禁止为禁用行为，SHOULD/建议为偏离需记录理由的实施方向，MAY/可选不是可以冒充已支持的能力。正文 0—30 和规范性附录定义要求；历史来源只说明来源，不重新引入旧约束。

<a id="sec-0-2"></a>

### 0.2 使用方法

产品负责人先读 1—5、24—26、29；框架开发读 6—18、22、27—29；前端读 11、13、15、17、19；交付/接入开发读 8—10、16—17、21、27—28。所有人使用第 25 章的完整验收集合。

本文规定待实现行为，不是市场宣传或源码完成报告。当前支持性由固定代码版本、安装配置和实际测试证据声明。没有实现某能力时要在预检中拒绝，不能让声明走到业务写入后才发现不支持。

<a id="sec-0-3"></a>

### 0.3 项目命名与不变量

项目工作名 Multiverse；产品描述 Multiverse Workflow；Python 导入名 `multiverse_workflow`；CLI 为 `mverse`，不使用系统命令 `mv`。本文件不确认商标、域名和公开包名可用性，不为任何第三方改变许可。

任何行业、模型品牌、特定宿主、Agent 产品或公司数据表只能作为适配/示例，不能成为核心契约前提。内部可托管不等于绑定内建实现；外部可接入不等于接管全平台；交付不等于迁移活动运行。

<a id="sec-0-4"></a>

### 0.4 本次明确解决的范围变化

| 历史表述/潜在歧义 | 本版统一决定 |
|---|---|
| 多 Agent 样例似乎固定为开发者、审阅者和一人 | 人数和角色不固定。保留六种原语，业务结构自由组合；标准模板只是可拆解参考。 |
| 只有循环与分支便覆盖一切 | 两者不替代执行调用、数据、等待、并行汇合、身份与恢复；不承诺无限场景/规模。 |
| 标准库还是让作者重写交接 | Runtime 自动完成可靠交接；作者只声明业务输入、依赖、条件与策略，Adapter 封装外部差异。 |
| 有 builtin/local_process 即完成内建 Agent | 必须有真实可配置受管执行宿主、真实 Agent/程序、工作区与事件。 |
| 不建设已有平台的设备/IAM，因此不能独立运行 | 保留不重造完整业务平台的边界；提供自身最小身份、执行接入和配置能力。 |
| 只读 Inspector 不能启动/停止 | 图不是事实权威；界面仍是 Runtime Console，经同一命令层运行、人工处理和停止。 |
| 只保留五类一级页面 | 五类职责保留，允许且应提供紧凑“执行能力”入口；不强制再建组织管理产品。 |
| 包导入禁止任意源码，因此不能交付程序 | 导入仍不执行源码；程序通过独立受控安装资产随 Runnable Bundle 交付。 |
| 交付补充把试运行放在创建 Deployment 之前 | 先创建不可变、未对普通入口激活的部署；经授权验证后再激活业务入口。测试须绑定同一快照，不能测试完才生成另一份配置。 |
| 可移植只是复制 JSON | 交付依赖、身份/资源绑定、人工入口、目标 Runtime 与验收必须闭合。 |
| 模型、平台或软件没内部事件就算没有内部操作 | 标注观测范围和新鲜度，不能伪造步骤。 |
| 作者可修改流程就可修改实时 status | 草稿、演示和执行观察分离；修改活动运行事实禁止。 |
| 实验用 latent 所以全体默认开启 | 产品默认关闭；实验部署可开启并冻结；无静默文本回退、无跨轮隐式 KV。 |

以前文档中已经被覆盖的阶段优先级、GUI 只读字样、动态默认值不再生效；第 24 章是唯一实施路线。安全、版本、幂等、审批和未知副作用规则没有放宽。

<a id="sec-0-5"></a>

### 0.5 单一接口冻结登记

设计目标已确定不表示线级细节已冻结。以下接口在对应实现进入公共 SDK/配置前，必须补齐 Schema、类型、错误、授权、幂等、版本和正反例，并作为本文的同一修订合入。不得从说明性名称猜造 JSON/API。

| ID | 已确定的能力 | 尚未确定的具体接口 | 进入条件 |
|---|---|---|---|
| G-01 | 注册式 Adapter，按平台复用。 | 插件发现/安装接口、版本共存、注册清单格式与卸载约束。 | 新增第三方 Adapter 前。 |
| G-02 | 执行管理归属与实际位置分开。 | Descriptor 的扩展字段、枚举及兼容规则。 | 输出公共能力目录前。 |
| G-03 | AgentProfile / 程序配置版本化。 | 完整配置 Schema、引用、默认项、创建更新和导出接口。 | 受管配置页面/SDK 开发前。 |
| G-04 | Managed Execution Host 执行与恢复。 | 宿主命令、工具调用台账、实例引用及事件协议。 | 接入真实工具副作用前。 |
| G-05 | 隔离与资源限制要实际实施。 | 首个沙箱/进程实现、支持平台、限额及停止策略。 | 开放多人或不可信代码执行前。 |
| G-06 | Connector 配对与可撤销身份。 | 端点、认证形式、凭据周期与批准流程。 | 对外提供接入安装包前。 |
| G-07 | 出站接入、持久领取及断线恢复。 | 领取/确认/回传协议、游标、配额与过期处理。 | 声称跨电脑可靠接入前。 |
| G-08 | Agent/工具内部步骤可观察。 | 事件字段、父子关系、顺序/去重、截断及成本覆盖。 | 声称完整内部轨迹前。 |
| G-09 | 人工表单与外部查看入口。 | 展示扩展键、控件支持矩阵、页面/链接注册及授权。 | 安装需要自定义页面的流程前。 |
| G-10 | 飞书等渠道与 Runtime 关联。 | 通道配置、消息/请求映射、认证、待送达与失败回执。 | 真实通道接入前。 |
| G-11 | 运行中可选交互，不改原始输入。 | 交互请求/提交接口、身份、Schema、期限与恢复语义。 | 统一投递任意 Agent 中途消息前。 |
| G-12 | Artifact 上传/外部登记完整闭环。 | 上传会话、登记端点、完成验证与关联请求的响应。 | 发布远程文件提交入口前。 |
| G-13 | Runnable Bundle 与依赖闭合检查。 | 交付清单、依赖分类、摘要锁、资源分包和兼容报告格式。 | 输出正式可运行交付物前。 |
| G-14 | 安装/激活/更新/卸载可验证。 | 安装 API/CLI、重复安装语义、权限、模板及保留策略。 | 自动化目标部署前。 |
| G-15 | 宿主一次接入、多流程复用。 | 认证委托和映射方式、客户端生成入口、UI 承载及回调契约。 | 声称即插即用宿主兼容前。 |
| G-16 | 完全本地真实 Agent。 | 本地推理后端、模型/工具兼容矩阵、资源与离线交付方式。 | 声称完全离线可用前。 |
| G-17 | 多会话身份、原生绑定与安全切换。 | 关联/租约/版本模型、迁移/分叉命令、幂等、错误、授权与恢复证据。 | 发布会话管理与迁移 API 前。 |
| G-18 | 权限变化与执行策略映射。 | 策略 Schema、原生后端能力、权限请求、失效/撤销和实施证据。 | 发布跨后端权限管理前。 |
| G-19 | Agent 优先编辑与语义变更审阅。 | 配置 Schema 发现、语义 Diff、并发编辑、安装版本匹配的作者契约。 | 发布统一作者 SDK/编辑器前；第 30.3 节仅冻结本地预检子集。 |

补充登记：能力目录的公开 API/CLI、结构化诊断响应与模板生成命令仍须精确定义；它们对应第一追加的 Authoring Kit/能力发现缺口。`--decision-file`、Artifact 上传/外部登记与展示扩展在同一实现变更中固定，不能用某个 CLI 原型局部存在代替端到端契约。

本轮已新定义第 29 章标准库组件描述、参考业务 Schema 与纯辅助组件语义；这只冻结相应标准库设计，不声称插件安装 ABI、远程配对、完整 AgentProfile、Bundle manifest 等 G 项因此完成。首版工程负责人按阶段逐项关闭 G 项；未关闭部分不得生成正式公共客户端或宣传可用。

<a id="sec-0-6"></a>

### 0.6 变更、追溯与来源保全

Schema、OpenAPI、客户端类型、迁移和测试是本规范的可执行表达，不是另一套自行演进的依据。新的必需能力必须用 requiredFeatures 声明；不认识时拒绝。发现冲突必须显式修订，不能选择更宽松解释。

附录 G 给出全部来源章节的迁移映射；原 AC/LH/SUP/RDI 编号全部保留，新增 CMP。旧文档复制的 Latent 条款只保留一次，旧“与其他文件一起使用”的行政条款由本节替代。初始技术与架构草案仅核对意图，不恢复旧发布时间表或未经当前测试的第三方支持声明。

<a id="sec-0-7"></a>

### 0.7 软件发行与公开兼容策略

目标软件版本为 `1.0.0`，当前源码仍为 `0.1.0` 开发预览。文档修订、软件 SemVer、资源 metadata.version、资源 CAS version 和线级版本互不替代；不得仅升级软件号声明稳定。v1 软件继续读取 `multiverse/v0.1` 的 WorkflowPackage、Workflow、BindingSet；不改写活动 Run 的已冻结版本。未知 apiVersion、未知必需功能和声明中的未知字段在执行前拒绝。业务 input/output 的扩展性由其业务 Schema 决定。

| 公开面 | v1 冻结的兼容单位 | 未知字段与版本行为 |
|---|---|---|
| 包、Workflow、Binding、ExecutionPlan | `multiverse/v0.1`；metadata.version 为独立 SemVer | 声明模型拒绝未知字段/版本；新增必需能力必须声明 requiredFeatures；旧 v0.1 包先只读校验，导入不执行源码。 |
| HTTP Job | `/v1` 路径与 Descriptor.contractVersion=`multiverse/v0.1` | 不兼容 Descriptor 阻止新派发；接收方校验必需请求字段；客户端可以忽略未知可选响应字段，不能忽略必需结果/终态/完整性错误。 |
| Runtime HTTP API | `/api/v1` 与安装版本的 OpenAPI | 请求未知字段拒绝；响应允许客户端忽略未知可选字段；未知路径版本拒绝，不静默降级。 |
| CLI JSON | 安装软件版本及命令对应 Schema；preflight=`multiverse.preflight/v0.1`，注册文件=`multiverse.executor-catalog/v0.1` | 输出消费者允许未知可选字段；缺失必需字段/未知报告版本拒绝。现有其他命令没有统一 envelope，不虚构全局 JSON 版本字段；破坏性形状变更须显式新契约。 |
| 事件与图投影 | `/api/v1` 事件流；投影 protocolVersion=`multiverse/v0.1` | 事件 seq/type/payload 保留；未知可选事件可保留/忽略展示，但不得推进业务；不兼容投影拒绝渲染并提示升级，不能猜测状态。 |
| SDK/嵌入组件 | 正式 SDK 的软件 SemVer + 支持的 API/投影版本集合 | 发布前按 G-15/G-19 固定 Schema 与兼容测试；现有 Inspector 源码不是已发布稳定 SDK。 |

同一兼容单位内只允许保持既有含义的向后兼容变化；新增必需字段、删除字段、改变状态或错误语义均需新线级契约或显式 major。正式 v1 发布后，弃用至少提前 90 天且跨两个已发布 minor 通知（两条件都满足），保留旧契约读取与诊断路径；安全紧急撤销可以提前拒绝执行，但须记录公告、影响与迁移指引，不能静默改变已确认事实。开发预览尚未建立正式服务期限，不能把此策略说成当前已实现客户端协商。

v0.1 导入路径固定为：读取原声明 → 校验版本/必需能力/摘要与安全限制 → 生成不可变包和 Binding 快照 → 创建未激活部署 → 授权验收 → 激活。未知旧版本不进行猜测转换；活动 Run 沿用旧快照。完整导入/升级/回滚由 W24 验收；当前 compile/validate 的旧格式兼容测试仅证明前两步。过期客户端拒绝、SDK/事件兼容由 W25/W20 验收，不能将 404 或 Schema 测试替代端到端协商。

追踪文件 `docs/release/ACCEPTANCE.json` 是本规范的证据索引，`SUPPORT_MATRIX.md` 是限定快照的支持说明，两者不独立定义产品行为。所有必需 ID 持续计入分母；可选安装、未实现、未实测、缺硬件均不能取消项目验收。

---

<a id="s01"></a>

## 1. 定位与产品目标

<a id="sec-1-1"></a>

### 1.1 项目是什么

Multiverse 是三个相互独立、协同工作的产品层：

| 产品层 | 责任 | 不承担的责任 |
|---|---|---|
| Specification | 工作流、节点边界、能力、Binding、包与运行语义 | 定义 Agent 内部思维、固定业务领域 |
| Runtime | 解析、验证、部署、调用、等待、恢复、记录与受控操作 | 重造已有执行系统的设备和账户管理 |
| Inspector / UI SDK | 展示结构、状态、原因、证据、结果、评测和可执行操作 | 成为工作流定义的唯一存储或权限裁决者 |

工作流说明“什么需要发生”；Binding 说明“本环境由什么实现”；Runtime 决定“何时可以推进”；执行环境决定“实际允许做什么”。

<a id="sec-1-2"></a>

### 1.2 第一版需要交付的用户价值

用户能够在本框架受管执行宿主中独立运行 Agent、程序与人工流程，也能通过 Binding 接入远程平台/机器；运行、异常、循环与交接在实际承载该 Run 的 Runtime 中可追踪；整套流程能交付到兼容目标环境。角色和数量不由框架固定，具体支持受功能、权限与资源限制。

同一个 Runtime 可安装多个包，不要求每个 Workflow 配套部署一套独立平台。没有 Inspector，CLI/API 仍能完成全部核心操作；没有外部观测平台，仍能运行、查询、审阅和恢复。

<a id="sec-1-3"></a>

### 1.3 不是本项目的默认形态

本项目不是聊天应用、Agent 市场、组织管理系统、模型路由网关、连接器市场、完整业务项目管理平台，也不是以拖拽搭建为主要入口的可视化编辑器。

这些能力可以出现在第三方产品或 Preset 中，但不得反向成为 Workflow Protocol 的必需字段。

<a id="sec-1-4"></a>

### 1.4 产品定义

> **Multiverse 是自带可用执行环境的可移植工作流系统：快速组织 Agent、程序、人与外部服务，在统一 Runtime 中推进和追踪，并将完整流程作为业务能力交付到目标环境。**

项目不是只转发外部 API 的薄路由，也不是只在本机运行 Agent 的孤立平台。统一节点契约必须同时支持内部独立运行、外部替换和完整交付。

<a id="sec-1-5"></a>

### 1.5 四种使用形态

| 形态 | 用户应能完成的事情 | 关键要求 |
|---|---|---|
| 全内建 | 在一套 Multiverse 安装中配置真实 Agent、程序与人工操作，运行流程并获取产物。 | 不以第三方 Agent 平台为前置条件。 |
| 混合执行 | 将部分节点绑定到外部平台或远程电脑上的能力。 | 流程结构和业务契约不因部署位置而重写。 |
| 独立交付 | 将完整流程交付到另一套干净环境。 | 原开发平台、账号、数据库与网络服务不是隐含依赖。 |
| 宿主嵌入 | 在已有内部平台里启动、观察、控制和人工处理交付流程。 | 一次接通宿主后，新流程主要通过安装、绑定和授权使用。 |

<a id="sec-1-6"></a>

### 1.6 “快速”的验收含义

快速意味着：平台级适配一次；同平台 Agent 级主要配置；节点级通过 Binding 复用；相同操作使用统一 API/CLI；外部作者能通过结构化反馈完成创建与修复。

不规定未经实测的分钟数、代码行数或零成本承诺。不承诺没有稳定接口的服务与标准执行器具有相同接入成本。

<a id="sec-1-7"></a>

### 1.7 整体产品边界

平台可以承载完整运行，但不是 Workflow 的永久所有者。原开发站点可以关闭，目标实例仍应运行；运行所在环境中的 Runtime 对该 Run 负责。其他控制台和飞书等渠道可同步或转发操作，不共同抢写状态。

---

<a id="s02"></a>

## 2. 不可破坏的原则

| 编号 | 约束 |
|---|---|
| INV-01 | Workflow 定义不得包含具体凭据、固定设备地址、私有目录或强制模型品牌；这些内容属于 Binding 或 Secret Provider。 |
| INV-02 | Agent 是 Executor 的一种实现，不是所有节点的父类型。 |
| INV-03 | Capability 匹配不等于授权，不等于质量合格。 |
| INV-04 | 执行器不能自行授予权限、通过自己的审批或修改已发布流程。 |
| INV-05 | Graph 是定义与运行事实的投影；前端坐标、颜色、展开状态不决定执行。 |
| INV-06 | 定义的权威是版本化包；执行事实的权威是 Runtime 持久记录；两者不可混为一个“Source of Truth”。 |
| INV-07 | State、Memory、Context 分离；检索结果不能证明节点已完成。 |
| INV-08 | 网络请求重试、执行重试、业务返工、恢复、重跑是不同操作。 |
| INV-09 | 未知结果不能自动解释成失败，也不能解释成未发生副作用。 |
| INV-10 | 每次实际调用必须具有持久身份、输入快照、版本、权限上下文和结果关联。 |
| INV-11 | 人工批准必须绑定具体对象与版本；内容改变后不得沿用旧批准。 |
| INV-12 | 已开始的 Run 固定包、Binding、策略、Adapter 与执行计划版本；不热替换。 |
| INV-13 | 基础审计事件不能采样；详细 Trace 可以采样或关闭。 |
| INV-14 | 不依赖任何特定宿主、业务对象命名或第三方数据库表。 |
| INV-15 | 未实现的扩展必须报错或明确禁用，不能忽略后继续运行。 |
| INV-16 | AI 可以提交修改，但不能绕过验证、评测、授权和发布。 |
| INV-17 | Latent 开关只改变选定交接的机器通信表示；不改变状态权威、输入输出契约、权限、审批或副作用安全。开启后不得静默回退为文本并宣称 latent 已使用。 |

---

<a id="s03"></a>

## 3. V0.1 范围与明确不做的事

<a id="sec-3-1"></a>

### 3.1 发布必需能力

| 领域 | V0.1 必须实现 |
|---|---|
| 定义 | YAML/JSON 文档、独立 JSON Schema、确定性引用和条件表达式、静态检查 |
| 控制流 | 顺序、互斥条件分支、静态并行且全部汇合、受限嵌套 Workflow、显式有界循环 |
| 执行 | 统一调用契约；真实受管 Agent/程序、Execution Host、Local Process、HTTP Job、内建 Human Adapter 与注册式接入 |
| 生命周期 | 持久运行状态、截止时间、受限重试、暂停调度、继续、取消请求、结果核对 |
| 数据 | 结构化输入输出、不可变 Artifact 引用、可读审计 Handoff、输入快照 |
| 通信 | 默认标准交接；可选启用 Latent Handoff；模式冻结、兼容预检、实际使用回执；至少一个可独立安装并实测的实验后端 |
| 交付 | Workflow Package、Runnable Bundle、依赖完整性、宿主接入、目标独立运行、版本/安装/回滚边界 |
| UI | 独立 Inspector 与可嵌入 React 组件；状态、原因、证据和下一步同屏关联 |
| 评测 | 本地确定性 Evaluator、数据集执行、基线比较、机器可读报告 |
| 接入 | 独立 CLI/API、注册表/Bridge SDK、远程 Connector、人工通道与宿主集成 |
| 观测 | 不可采样的运行事件；可选 OTel 导出 |
| 部署 | 本地单进程开发模式；PostgreSQL 支撑的单活 Worker 服务模式 |

“V0.1 必须实现”指发布门槛，不指第一天全部完成。按第 24 章分阶段交付，未完成阶段只能标记开发预览。标准发行包不安装或加载 latent 推理依赖也必须可用；项目的 V0.1 完成门槛同时包含一个通过第 25.5 节的实验可选安装产物。未具备真实实现时开关必须禁用或拒绝开启，不能以 Mock 冒充已支持。

<a id="sec-3-2"></a>

### 3.2 不进入 V0.1 发布阻塞项

不实现动态拓扑改写、任意图环、递归 Workflow、运行中换引擎、跨引擎迁移 Checkpoint、分布式多活调度、自动扩缩容、通用分布式事务、自动业务补偿、完整拖拽编辑器、公共包市场、内置 Agent 公司、完整 IAM、向量数据库、任意跨模型 latent 自动对齐。

MCP、A2A、Langfuse、其他观测后端、LLM Judge、自动优化器和其他执行后端作为扩展方向；不要求第一版提供生产级集成。扩展接口可以预留，但不能用空实现通过支持性检查。

<a id="sec-3-3"></a>

### 3.3 可移植性分级

| 级别 | 定义 | V0.1 承诺 |
|---|---|---|
| P1 包可交付 | 无私有环境信息的包可以复制、解析、校验 | 必须 |
| P2 环境可部署 | 同一包在本地与服务环境通过不同 Binding 运行 | 必须，使用声明支持的组合 |
| P3 执行器可替换 | 不改 Workflow，只替换兼容 Binding，并重新验收 | 必须至少验证两种实现 |
| P4 引擎语义兼容 | 不同后端实现同一协议子集并通过一致性测试 | 设计边界；V0.1 只实现 LangGraph 后端 |
| P5 进行中的跨引擎迁移 | 一个后端的活动实例转到另一个后端继续 | 不支持 |

P3 不保证模型输出相同、成本相同或质量相同。兼容性、授权、可运行性和评测结果必须分别报告。

<a id="sec-3-4"></a>

### 3.4 本版完整产品与阶段预览

标准发行必须包含可验证的通用组合标准库、全内建真实执行与人工入口、可选择的外部/跨电脑接入及完整交付路径；离线档位按第 21 章的已验证模型与环境组合验收。并非每个使用者都必须安装所有可选连接或模型资源。

小型可用预览可以先行交付，但要逐项标明未支持能力。完整产品门槛包含第 25 章 AC、LH、SUP、RDI、CMP；不能把不固定人数理解为取消既有真实示例验收，也不能把样例人数解释为协议限制。

---

<a id="s04"></a>

## 4. 领域模型与身份

<a id="sec-4-1"></a>

### 4.1 核心对象

| 对象 | 定义 | 标识与版本规则 |
|---|---|---|
| WorkflowDefinition | 一个可执行流程定义 | 包内 `workflow_id`；内容由包摘要固定 |
| NodeDefinition | 一个节点的类型、契约和流转规则 | 所属定义内唯一 `node_id` |
| WorkflowPackage | 定义、Schema、Prompt、Policy、Eval 等可交付文件集合 | `name`、SemVer、`package_digest` |
| BindingRevision | 一组逻辑 slot 到真实实现的映射 | 不可变 `binding_revision_id` 与摘要 |
| Deployment | 一个包版本加一个 BindingRevision 和环境策略 | 不可变 `deployment_id`；停用只阻止新 Run |
| CommunicationProfile | 本环境已注册、版本化的 latent 导出/导入兼容配置；不是第四种 YAML 资源 | profile ID + 不可变内容摘要 |
| HandoffRecord | 一次源到目标交接的模式、载荷、审计说明和接收证据 | `handoff_id`，关联具体 scope/invocation/attempt 与摘要 |
| WorkflowRun | 一次顶层工作流运行 | `run_id`，输入、快照和结果不可变引用 |
| ExecutionScope | 顶层或嵌套工作流的一次激活 | `scope_id`，包含父节点与迭代/分支路径 |
| NodeInvocation | 一个节点在特定 scope 中的一次逻辑调用 | `invocation_id`；不同循环轮次不是同一调用 |
| Attempt | 同一调用的一次执行尝试 | `attempt_id` 与从 1 开始的 `attempt_no` |
| ExternalExecutionRef | 外部系统返回的稳定工作引用 | Adapter ID + 外部 ID；可关联多个外部子尝试 |
| HumanRequest | 一个等待人的请求 | 请求 ID、subject digest、决策版本与截止时间 |
| Artifact | 一份输出内容或可验证外部资源 | 内容摘要/稳定版本 + 存储引用 + ACL |
| EvalRun | 一次固定数据集与版本组合的评测 | 独立 ID，关联生产式 Run，不覆盖原运行 |

运行时 ID 使用随机 UUID；身份连续性依赖持久映射和唯一约束，不依赖重新计算出同一个随机数。业务关联使用 `external_refs`，内容为命名空间化的 opaque 引用，不要求存在 Project、Task、Agent、Computer 等固定业务表。

<a id="sec-4-2"></a>

### 4.2 必须区分的关系

```text
PackageVersion + BindingRevision + EnvironmentPolicy
                         ↓
                    Deployment
                         ↓
                    WorkflowRun
                         ↓
                 ExecutionScope(s)
                         ↓
                 NodeInvocation(s)
                         ↓
                     Attempt(s)
                         ↓
              ExternalExecutionRef(s)
```

一个节点不等于一个 Agent；一个节点调用不等于一个操作系统进程；一个外部执行可能包含多次内部尝试。外部系统拥有其内部生命周期，Runtime 只解释 Adapter 对外承诺的状态。

<a id="sec-4-3"></a>

### 4.3 核心身份字段

所有运行实体必须携带 `namespace_id`。API 中的 namespace 必须经过身份权限校验；不得信任客户端在正文里任意填写的租户字段。

执行关联最少包含：`run_id`、`scope_id`、`node_id`、`invocation_id`、`attempt_id`、`deployment_id`、`package_digest`、`binding_digest`。可选 `trace_id` 不得代替上述任何身份。

<a id="sec-4-4"></a>

### 4.4 内部 / 外部是执行属性，不是新的节点类型体系

用户界面可以显示“内建执行”“外部执行”“远程受管执行”。核心继续使用本规范的 `call`、子 Workflow 和既有控制节点，不新增品牌或部署位置专用的 Workflow 节点。

| 类别 | 执行生命周期的管理者 | 实际位置 |
|---|---|---|
| 内建执行 | Multiverse 的 Managed Execution Host。 | 当前安装所在机器或其受管执行环境。 |
| 外部执行 | 外部平台 / 服务；Multiverse 提交、观察及请求控制。 | 外部平台或服务。 |
| 远程受管执行 | Multiverse 通过 Connector 管理本次执行。 | 接入的另一台电脑或服务器。 |

底层应分别记录“管理归属”和“执行位置”，而不是仅一个含糊的 internal/external 布尔值。确切字段名与枚举属于 第 0.5 节 的待冻结接口，不得由本文表格直接推导新的公共 JSON。

<a id="sec-4-5"></a>

### 4.5 不变的四条边界

**输入输出：**每个可调用节点使用明确的 inputSchema / outputSchema，程序、人和 Agent 都不例外。

**生命周期：**所有实现映射回 ExecutionRequest / ExecutionObservation；不得各自发明 AgentResult、HumanResult 与 ProgramResult 三套互不兼容的状态语义。

**权限：**能力匹配和 Schema 匹配不授予执行或真人审批权限；内建实现也不能通过自己的审批。

**证据：**成功必须同时满足有效输出、所需产物与实际终态；文字“完成”、HTTP 200、退出码 0 均不足以证明成功。

<a id="sec-4-6"></a>

### 4.6 分离状态、业务结果与解释

执行成功可以产生业务“不通过”的结果，例如校验输出 `valid=false`；人工审阅成功完成也可以输出 `decision=reject`。这些值进入显式分支，不伪装成网络故障来触发重试。

自然语言摘要解释工作，不能更新权威状态。大型内容和二进制通过 Artifact 引用传递；标准输出不替换成不透明 latent 向量。

<a id="sec-4-7"></a>

### 4.7 内外替换条件

同一 slot 从内建切换到外部，必须满足契约、能力、授权、资源、版本及声明的执行保证。结构不变不代表质量相同，需重新预检和验收。

替换创建新 BindingRevision / Deployment；活动 Run 继续使用原快照。不能在原写入结果未知时切换执行器并重派同一业务动作。

<a id="sec-4-8"></a>

### 4.8 与 Agent 选择相关的动态性

不同任务改变输入；不同环境改变 Binding；分情况执行可先使用显式 switch 和预先配置的 slot。首版不默认实现运行中的自动模型竞价、任意候选池或跨机器故障转移。

同一逻辑 slot 的实现由部署固定，执行身份、Session 与实际 Attempt 的关联仍逐次记录。将来新增动态选择时，需要新的明确选择契约及审计，不通过任意配置透传实现。

---

<a id="s05"></a>

## 5. 技术栈与架构决策

<a id="sec-5-1"></a>

### 5.1 冻结的主要选型

| 层 | 决定 | 约束 |
|---|---|---|
| 后端语言 | Python 3.12 作为首版验证基线 | 这是目标环境，不宣称是最新版本 |
| API / 数据模型 | FastAPI + Pydantic 2 | Pydantic 是实现工具，不是协议定义 |
| 执行后端 | LangGraph 开源库 | 不要求 LangGraph 托管平台；协议不暴露其对象 |
| 协议载体 | YAML 1.2 的 JSON 兼容子集 / JSON | 以统一 JSON 数据模型校验 |
| Schema | JSON Schema Draft 2020-12 | 控制本地引用，禁止运行时任意远程取 Schema [E3] |
| 数据库 | PostgreSQL 17 基线；SQLite 本地单进程模式 | 不声称两个模式提供相同并发和部署保证 |
| 持久层 | SQLAlchemy 2 + Alembic；LangGraph saver 独立封装 | 不在业务层散布第三方 Checkpoint SQL |
| 前端 | React 19 + TypeScript + Vite | Inspector 为客户端；不引入 Next.js/SSR 前提 |
| 图 | `@xyflow/react` + ELK.js | React Flow 展示；ELK 做布局；图不是协议 [E4] |
| 组件 | shadcn/ui + Tailwind，生成独立作用域样式 | 不污染宿主全局样式；主题通过 tokens 注入 |
| 服务端状态 | TanStack Query | 运行数据不复制为另一份全局可变事实 |
| 界面局部状态 | Zustand，仅用于选择、视图和面板 | 无复杂状态时允许普通组件 state |
| 网络 | HTTP JSON + SSE | 控制走命令 API，不依赖 SSE 触发执行 |
| 观测 | OpenTelemetry 可选导出 | 基础事件与审计独立存储 [E5] |
| 评测 | 内部 Eval 接口 + 本地确定性实现 | Langfuse Adapter 非强制服务 |
| 包管理 | Python 使用 uv；前端使用 pnpm | 提交锁文件，CI 使用 frozen/locked 模式 |
| 测试 | pytest、Vitest、Playwright | 包括协议、故障注入和真实边界集成测试 |
| 发布 | OCI 镜像 + Compose 基线 | 镜像引用固定版本/摘要，不使用 `latest` |

Node.js 24 为前端构建验证目标。依赖的精确版本在 M0 阶段通过安装、构建和最小恢复测试锁入 `uv.lock`、`pnpm-lock.yaml`；这不允许重新开放上述技术路线。未测试组合必须标记为未验证，而不是自动继承支持声明。

<a id="sec-5-2"></a>

### 5.2 必须保留的模块边界

```text
CLI / API / Inspector / Embedded UI
                  │
          Application Commands
                  │
        Policy / Authorization
                  │
  Package → Validator → Normalized Plan
                  │
      Runtime Facade + Durable Ledger
                  │
       LangGraph Backend Adapter
                  │
        Executor Adapter Contract
       ┌──────────┼────────────┐
       ↓          ↓            ↓
   Program     External       Human
               Executor
```

Package、Binding、State、Artifact、Eval、Policy 和 UI 领域类型不得导入 LangGraph、React Flow 或 Langfuse 的内部类型。对第三方类型的依赖只能出现在对应 backend/adapter/view-mapper 中。

<a id="sec-5-3"></a>

### 5.3 LangGraph 使用边界

LangGraph 提供持久 Checkpoint 与中断/恢复能力；内存 saver 在进程重启后不保留状态；生产式模式必须使用持久 saver。[E1]

LangGraph 中断后的节点可能从函数开头重新执行，因此节点重入必须安全；不能将创建外部工作与等待人工写成一段无幂等保护的代码。[E2]

本项目使用它执行规范化流程及其控制结构，不自建另一个竞争的通用图解释器。自身必须实现的部分是跨系统调用台账、幂等命令、输入输出契约、权限、部署与恢复核对。详细一致性规则见第 12 章。

<a id="sec-5-4"></a>

### 5.4 不引入的基础设施

V0.1 默认部署不要求 Redis、Celery、Kafka、Temporal、ClickHouse、向量数据库、对象存储集群或外部 Trace 后端。可使用本地 Artifact volume；备份时必须一并备份。

Langfuse 官方自托管架构包含多个应用与存储组件，因此作为可选集成，而非轻量启动依赖。[E6] 重新评估 Temporal 的条件是执行基础设施负担和可靠性需求，不是“用户多了再说”；更换后端必须走 ADR、兼容测试和版本变更。

<a id="sec-5-5"></a>

### 5.5 架构

```text
作者工具 / Inspector / 嵌入 UI / CLI / 宿主业务接口
                         │
                Application Commands
                         │
          Policy + Package/Binding/Deployment
                         │
              Workflow Runtime + 持久台账
                         │
                统一 Executor Contract
          ┌──────────────┼─────────────────┐
          ▼              ▼                 ▼
  Managed Execution   External Adapter   HumanRequest
       Host            / Bridge         权威请求与结果
    ├── Agent              │                 │
    ├── Program         外部平台          内建/宿主页
    └── Workspace       原生执行          /飞书等通道
          │
          └── 可由 Connector 放置在远程机器

状态、事件、产物、人工结果 → 目标 Runtime → 各类查看界面
```

这是职责图，不是要求启动同等数量的微服务。可以先在一个发行产物中提供 API、单活 Worker、执行宿主及可选连接模块。

<a id="sec-5-6"></a>

### 5.6 Workflow Runtime

负责解析后的流程推进、依赖、分支、Workflow 层循环、人工门禁、整体控制意图、结果验收、持久状态与恢复核对。继续通过既定 backend 执行规范化计划；不得因增加 Execution Host 再隐式构建第二套竞争的图执行引擎。

<a id="sec-5-7"></a>

### 5.7 Managed Execution Host

负责一次受管调用的创建、隔离、配置与工作区装配、执行监督、内部步骤记录、资源限制、取消以及输出与产物登记。

它不是另一个自主调度整个 Workflow 的 Agent；不能创建未授权上游任务、修改下一条边、扩大权限或直接写审批表。它通过同一 Adapter 语义报告执行事实。

<a id="sec-5-8"></a>

### 5.8 外部与本地状态权威

外部平台确认其实际执行事实；Adapter 不得因 Runtime 期望某状态就伪造它。Runtime 将经过校验的观察、输出与权限门禁转换为 Multiverse 的节点状态及推进决定。

Inspector、飞书、宿主列表和 Trace 是投影。只有目标 Runtime 的受控命令入口可以改变该 Run 的 Multiverse 状态；外部事实仍需保留来源和更新时间。

<a id="sec-5-9"></a>

### 5.9 单活调度与多执行端

V0.1 单活调度 Worker 规则不变。多个 Connector 或多个 Execution Host 仅承载执行，不因此声称支持多活图调度。

API/页面请求不应承载必须持续存在的内存后台任务。持久意图与结果决定进度，连接和唤醒只促使 Worker 检查状态。

---

<a id="s06"></a>

## 6. 文档格式、通用类型与校验

<a id="sec-6-1"></a>

### 6.1 顶层资源

V0.1 识别 `WorkflowPackage`、`Workflow`、`BindingSet` 三种声明文档。运行资源由 API 创建，不由 YAML 直接导入。

通用顶层字段：`apiVersion`、`kind`、`metadata`、`spec`，均必填。`metadata` 允许 `name`、`version`、`description`、`labels`；name 使用小写字母、数字、点、中划线，长度 1—64，首字符必须是字母。version 为 SemVer 字符串。

除明确列出的字段外拒绝未知字段。扩展只能位于 `extensions`，扩展键使用所属方命名空间。影响执行语义的扩展必须在包内 `requiredFeatures` 声明；不认识的必需扩展必须拒绝。UI 装饰类扩展可以忽略。

<a id="sec-6-2"></a>

### 6.2 解析要求

仅允许 JSON 类型：object、array、string、number、boolean、null。禁止重复键、自定义 YAML tag、锚点/别名、合并键、隐式日期对象、NaN、Infinity、超出安全范围的整数和依赖语言对象的反序列化。

数字限制为有限 IEEE-754 可表达值；整数必须在 `[-(2^53-1), 2^53-1]`。业务中需要更高精度的数量使用带格式说明的字符串，禁止依靠客户端浮点四舍五入完成精确验收。

Workflow 中的 Schema/资源路径统一相对包根；JSON Schema 文件内部的 `$ref` 相对该 Schema 文件所在位置解析。JSON Schema 使用 Draft 2020-12。本地 `$ref` 必须归属当前包；仅允许相对文件路径与文件内 fragment。禁止安装/执行时下载远程 Schema。协议对象默认 `additionalProperties: false`，业务 payload 是否允许额外字段由其 Schema 明确决定。

<a id="sec-6-3"></a>

### 6.3 ValueExpr：唯一的数据映射语法

每个 ValueExpr 只能是下列四种对象之一，不允许字符串插值、Python 表达式、JavaScript、模板函数或任意代码。

| 形式 | 意义 |
|---|---|
| `{literal: <JSON>}` | 常量，内容不再作为表达式解释 |
| `{ref: "input#/objective"}` | 读取当前 scope 输入的 JSON Pointer |
| `{object: {key: <ValueExpr>, ...}}` | 构造对象 |
| `{array: [<ValueExpr>, ...]}` | 构造数组 |

有效引用根：`input`、`nodes.<node_id>.output`；`repeat` 的 `until` 和 `feedback` 中额外允许 `iteration.output`、`iteration.index`。`iteration.index#` 从 1 开始。Pointer 空字符串使用尾部 `#` 表示整个对象；路径转义遵循 JSON Pointer。[E7]

引用不存在字段报 `DATA_REFERENCE_MISSING`；`null` 是真实值，不等于缺失。不进行隐式类型转换。禁止读取未完成节点、被跳过节点、其他分支内部状态、父级私有状态和任意数据库字段。

<a id="sec-6-4"></a>

### 6.4 Predicate：唯一条件语法

比较形式为 `{op, left, right}`；op 允许 `eq`、`ne`、`lt`、`lte`、`gt`、`gte`、`in`。组合形式为 `{all: [Predicate...]}`、`{any: [...]}`、`{not: Predicate}`。每个 Predicate 只使用一种形式；all/any 的数组必须非空。

`eq/ne` 按 JSON 类型和值比较，对象键顺序无关；数值比较仅接受 number；`in` 的右值必须为 array。所有引用必须存在，条件失败不得吞掉引用错误。禁止读时钟、随机数、网络和 Memory 做隐式路由。需要这些信息时，先通过显式节点生成持久输出，再进行条件判断。

<a id="sec-6-5"></a>

### 6.5 验证顺序

解析 → 顶层 Schema → 文件/引用解析 → 节点和控制流校验 → Schema/数据映射检查 → Capability/Binding 匹配 → 权限和依赖预检 → 生成规范化计划。

静态检查不能证明任意 Schema 的完全包含关系。V0.1 必须验证明显冲突、必需引用及注册契约的 Schema 摘要；无法静态证明的映射标记 `runtime_validation_required`，实际调用前后仍严格校验，禁止报告为“已证明兼容”。

错误必须返回稳定 code、文件、JSON Pointer、中文/英文可本地化 message、严重程度和建议操作。

<a id="sec-6-6"></a>

### 6.6 统一的是契约，不是所有业务字段

**沿用并强化：**所有执行方式共享输入输出的表达、校验、版本、生命周期、权限和证据规则；不同业务节点允许使用不同业务 Schema。

| 层次 | 必须保持稳定 | 可以替换 |
|---|---|---|
| 执行协议 | ExecutionRequest、ExecutionObservation、身份、终态、错误、取消、去重、核对 | 内部程序、模型、人、远程服务。 |
| 节点业务契约 | 当前契约版本的 inputSchema/outputSchema、能力、副作用、字段含义与验收 | 满足这些条件的执行实现。 |
| 工作上下文 | 来源、权限、版本、引用、快照和审计关联 | 标准交接或已配置的 latent 载荷。 |

不新增互不兼容的 AgentResult、HumanResult、ProgramResult。它们的实现均应通过 Adapter 映射到现有执行协议，业务结果置于规定的 output 中。

不把所有结果强制降为一个 `text` 字段，也不要求整个流程共享一份任意可变状态字典。

<a id="sec-6-7"></a>

### 6.7 执行状态、业务结论、交接解释分离

执行状态表示调用是否完成；业务输出表示本次得到什么；Handoff 表示如何理解和承接这些结果。

例如校验器正常运行后输出 `valid=false`，属于成功完成一次校验但业务不合格；人工返回 `reject`，属于完成审阅但结论为拒绝。应走显式 switch/业务路径，不伪造为网络失败，也不触发隐式重派。

真正的执行错误按本规范 ErrorEnvelope 与 onError 处理。`reconciling` 是未知结果核对，不等于一个已确定错误，不能借错误分支绕过核对。

<a id="sec-6-8"></a>

### 6.8 Schema 的内容要求

重要业务字段必须具有足够清晰的语义：含义、类型、必需性、允许值、缺失/null/空字符串区别；涉及数量、时间或版本时还要说明单位、格式和范围。

`title`、`description`、`examples` 可供作者和页面理解，但不能代替可执行约束或业务验证。仅定义 `score` 是 number，不能说明它是百分制、概率还是其他量。

输入输出验证仍使用本规范固定的 JSON 类型、JSON Schema 版本、路径解析和无隐式转换规则。静态检查不能证明的映射必须保留运行时验证，不把“不确定”显示成已证明兼容。

<a id="sec-6-9"></a>

### 6.9 统一执行边界

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

<a id="sec-6-10"></a>

### 6.10 可替换性不等于可冒充身份

相同 Schema 只是必要条件之一。还必须满足语义、能力、权限、副作用和验收要求。

声明需要真人审批的节点，不能因某个 Agent 能生成同样的 `decision` JSON，就把它绑定为审批人。业务允许自动审核时，应明确变更能力和授权条件，而不是静默替换人工职责。

---

<a id="s07"></a>

## 7. Workflow Contract 与控制流

<a id="sec-7-1"></a>

### 7.1 Workflow.spec 必需字段

| 字段 | 类型 | 规则 |
|---|---|---|
| `inputSchema` | 相对 `.json` 路径 | 当前流程输入 Schema |
| `outputSchema` | 相对 `.json` 路径 | 成功结束时的输出 Schema |
| `entry` | node_id | 唯一入口 |
| `nodes` | node_id → NodeDefinition | 1—200 个静态节点 |
| `defaults` | object，可选 | 本章给出的有限默认值 |
| `extensions` | object，可选 | 按第 6 章处理 |

默认值：`runDeadlineSeconds=604800`、`callDeadlineSeconds=3600`、`maxAttempts=1`、`maxConcurrency=4`。这些值在编译后显式写入计划，不能依赖后端隐式默认值。

每个同级 Workflow 的显式 next/case 边必须无环；循环只能通过 `repeat` 表达。除了互斥 switch 分支重新汇合，不允许隐式 fan-out 或隐式并发；并发只由 `parallel` 产生。节点被同一 scope 激活一次；多轮执行通过新的子 scope 表达。

<a id="sec-7-2"></a>

### 7.2 所有节点的公共字段

必填 `type`。可选 `title`、`description`、`extensions`。可调用/组合节点可以设置 `deadlineSeconds` 和 `onError`。除 `switch` 与 `end` 外，必须有 `next`。

`onError` 为目标 node_id，表示在错误已经确定、相关活动执行已经结束后走错误分支；没有它则当前 scope 失败。错误路径中可引用失败节点的 `.output`，其值固定为 `{error: ErrorEnvelope}`，并必须使用对应 Schema。`reconciling` 不是确定错误，不触发 `onError`。

<a id="sec-7-3"></a>

### 7.3 call：统一执行节点

`type: call` 必填：`slot`、`inputSchema`、`outputSchema`、`input`、`requires`、`effects`、`next`。

`requires` 包含 `capabilities: string[]`，能力 ID 采用 `domain.action@major`。`effects` 包含 `class: none|read|write` 和 `actions: string[]`；它描述可能发生的外部业务影响，不包含 Runtime 自己记录状态的写入。

可选 `retry`：`maxAttempts`（1—3）、`initialDelaySeconds`（默认 2）、`backoffMultiplier`（默认 2）、`maxDelaySeconds`（默认 30）、`retryableCodes`（默认空数组）。是否实际允许重试同时受第 11 章约束。

不设置 `agent_type`、`model`、`machine` 等字段。执行器是人还是程序，不改变该节点的对外数据契约；特殊行为由 Adapter 能力声明，并受通用生命周期约束。

<a id="sec-7-4"></a>

### 7.4 switch：互斥条件

必填 `cases` 和 `default`。cases 是非空有序数组，每项为 `{id, when, next}`；按顺序评估，首个为 true 的分支胜出。没有命中则走 default。选择及其输入摘要必须持久记录。

未选择分支不创建执行尝试。前端将其显示为未选中/跳过，而不是失败。两个分支可指向同一后继，但只有当前控制 token 到达的路径生效。

<a id="sec-7-5"></a>

### 7.5 workflow：嵌套调用

必填 `workflow`（包内 workflow_id）、`input`、`next`。以独立 ExecutionScope 执行被引用流程，输入输出遵守被调用流程的 Schema。子流程成功后的输出为当前节点输出。

V0.1 禁止直接与间接递归，嵌套深度不超过 8，子流程不具有独立提升权限的能力。父级取消必须传递给子级；子级结果未知时父级不得成功结束。

<a id="sec-7-6"></a>

### 7.6 parallel：静态并行且全部汇合

必填 `branches`、`join: all`、`next`；branches 是分支 ID 到 `{workflow, input}` 的映射。支持 2—16 个静态分支，`maxConcurrency` 可选且不得超过环境上限。

输出固定为 `{branches: {branch_id: child_output}}`。按照分支 ID 形成稳定结果映射，不使用完成时间决定数组位置。禁止并行分支隐式修改同一共享可变状态。

默认失败策略为 `stop_on_failure`：一个分支确定失败后，停止新分支、向已启动兄弟分支请求取消；所有活动分支已停止后才确定失败。无法确认停止则进入 `blocked`，不伪造全部终止。不支持 first-success、quorum、动态 map 或忽略失败自动汇合。

<a id="sec-7-7"></a>

### 7.7 repeat：显式有界循环

必填 `workflow`、`input`、`until`、`feedback`、`maxIterations`、`next`。maxIterations 为 1—20。

第一轮输入来自 `input`；子流程成功后，用 `iteration.output` 和 `iteration.index` 判断 until。为 true 则输出最后一轮子流程输出并走 next；为 false 且未达到上限，则由 feedback 生成下一轮输入；达到上限仍未满足则报 `LOOP_LIMIT_EXCEEDED`。

每轮是新 scope、新 NodeInvocation、新审批主题；不得覆盖前一轮记录。一个子流程若确定失败，默认不当作“继续循环”，按 onError/失败规则处理。业务修订请求应通过成功输出中的显式业务值表达，而不是制造基础设施失败。

<a id="sec-7-8"></a>

### 7.8 end：结束当前 scope

必填 `outcome: succeeded|failed`。成功结束必须提供 `output: ValueExpr` 并通过 Workflow.outputSchema；失败结束必须提供 `error: {code, message}`。不允许 next。

“外部执行返回 0”“HTTP 200”“模型说完成”均不自动等于工作流成功。只有选中成功 end、输出通过校验且无未核对活动执行，才可成功结束。

<a id="sec-7-9"></a>

### 7.9 静态图与数据流限制

所有节点必须从 entry 可达，所有正常可选路径必须到达 end；悬空节点和边直接报错。数据引用必须支配当前读取点，或位于已经选中的同一分支；不能从互斥分支中任意读取一个“可能存在”的结果。

分支汇合需要统一输出时，将每条分支封装为子流程，统一其输出 Schema，或者在各分支中显式构造相同结果。禁止用后写覆盖前写的共享字典规避类型与路径检查。

---

<a id="s08"></a>

## 8. Capability、Binding 与部署解析

<a id="sec-8-1"></a>

### 8.1 逻辑 slot

Workflow 只引用稳定的逻辑 slot，如 `producer`、`verifier`、`reviewer`。slot 不是特定产品名。一个 BindingSet 中每个被使用 slot 必须恰好解析到一个实现。

V0.1 不做自动模型竞价、质量路由或运行中故障切换到另一个提供者。可以给出候选匹配报告，但最终发布的 Deployment 必须固定选择。

<a id="sec-8-2"></a>

### 8.2 BindingSet.spec

必填 `slots` 映射；可选 `limits`、`communication`、`extensions`。`communication` 的唯一首版配置是第 14.6 节的 `latentHandoff`，未声明时默认关闭。每个 slot 包含：

| 字段 | 意义 |
|---|---|
| `adapter` | 已安装的 Adapter 类型：`builtin`、`local_process`、`http_job`、`human` |
| `executorRef` | 本环境已注册执行器 ID；不得由包安装阶段自动授权 |
| `config` | 该 Adapter 的非敏感配置，按 Adapter Schema 校验 |
| `secretRefs` | 字段名到 Secret Provider 引用；不包含 secret 值 |
| `grants` | 允许的 action/resource 范围，不得超过发起方权限 |

`capabilities` 不允许由 Binding 文件自行伪造后即被信任。解析器必须取得受信任的 ExecutorDescriptor 并校验 required capabilities。远程 descriptor 也是执行器声明，不是运行质量证明。

<a id="sec-8-3"></a>

### 8.3 ExecutorDescriptor

必须提供 ID、adapterVersion、executorVersion、contractVersion、capabilities、输入输出契约支持、取消能力、幂等能力、可恢复查询能力、观测等级及权限实施等级。

固定枚举：

- `cancelMode`: `confirmed` / `best_effort` / `unsupported`。
- `submitDedup`: `durable` / `none`。
- `reconcileByKey`: `strong` / `eventual` / `unsupported`。
- `retryOwner`: `runtime` / `executor`，一个调用只能有一个自动重试所有者。
- `observability`: `boundary` / `internal`。
- `enforcement`: `enforced` / `trusted_local` / `advisory`。

返回不支持不等于无法接入；它决定可提供的保证。环境要求达不到时，预检必须拒绝，而不是隐藏降级。

可选 `communication` 描述为 `{latentExports: [profileDigest...], latentImports: [profileDigest...]}`；缺省两者均为空。摘要必须对应环境注册的 CommunicationProfile。只写 capability 名称、拥有文本 API 或能够返回任意向量，不构成真实 latent 导出/导入支持。具体核查见第 14.8 节。

<a id="sec-8-4"></a>

### 8.4 预检输出

预检必须逐项返回 `pass`、`warn`、`fail`、`unverified`。至少检查 Schema、功能子集、Adapter 安装与版本、Capability、权限交集、凭据可解析性、资源可达性、Artifact 可读写性、取消/恢复保证、质量基线是否存在。

凭据只验证引用及必要的最小探测，不写入日志。外部成本操作不得借“预检”名义执行。`unverified` 不能计作 pass；由环境策略决定是否阻止激活。

Deployment 固定包摘要、Binding 摘要、Descriptor 快照、解析计划摘要、策略版本与验证报告；同时固定通信开关、目标 routes 和 CommunicationProfile 摘要。真正调用前再次检查凭据有效性、授权撤销和资源可用性；冻结快照不赋予已撤销权限继续使用的权利。

<a id="sec-8-5"></a>

### 8.5 适配一次，配置复用

Adapter 解决“这种外部接口怎样调用”；执行配置解决“具体调用谁”；Binding 解决“本流程哪个 slot 使用它”。不得为同一平台的每个 Agent 编写重复 Adapter。

| 需求变化 | 处理位置 |
|---|---|
| 同一 Agent 新任务 | 本次输入。 |
| 同平台另一个 Agent、工作区或配置版本 | 新的执行配置与 Binding。 |
| 同协议参数或字段变化 | Adapter Schema 允许的显式配置与映射。 |
| 新专有协议 | 安装新 Adapter / 薄 Bridge，并验证。 |
| 正在执行的调用更换实现 | 不直接覆盖；按新部署、新 Run 或明确后续调用处理。 |

<a id="sec-8-6"></a>

### 8.6 注册式实现

Compiler 不得维护不断扩大的业务执行器 if/else；Runner 不得按厂商品牌分支。公共接口依赖注册表描述和 Adapter Contract。

注册最少关联：实现标识与版本、配置 Schema、支持契约、能力、权限实施方式、取消/去重/查询保证、观测范围、对应测试证据，以及可读取的配置修订。

安装新插件不必强求进程热加载；受控重启可接受。已经启动的 Run 不能悄悄改用插件最新版本。原版本不可用或发生语义漂移时，明确阻止并说明。

#### 8.6.1 W01 显式本地执行器目录（当前实现）

`load_executor_registry(path=None)` 保留随 Runtime 提供的默认目录；显式目录读取
`executor-registration.json`，**完整替换**默认集合。所需 builtin/human 引用也必须列入。
格式由 `schemas/executor-registration.schema.json` 冻结：`catalogVersion` 固定为
`multiverse.executor-catalog/v0.1`，每项包含 `executorRef`、三段数字 `executorVersion`、
`contractVersion=multiverse/v0.1`、adapter、capabilities、取消/幂等/查询保证、观测与权限等级、
installed/available/verified，以及 `configSchemaRef`、`configSchemaDigest`。
目录只支持已实现的 builtin/local_process/http_job/human；builtin/human 只能使用已知实现 ID，
不能增加实现未支持的能力或保证。local_process 只能声明 trusted_local，不能声明取消、幂等或恢复查询。
不扫描包目录，不动态导入 Python，不自动下载或安装插件。

`configSchemaRef` 必须解析为目录内的普通文件（含符号链接解析），摘要是该文件原始字节的
`sha256:<hex>`。JSON 不得有重复键或非有限数字，包括指数溢出（如 `1e999`）及任意嵌套位置。配置 Schema 使用 Draft 2020-12；W01
只支持自包含 Schema，拒绝 `$ref`、`$dynamicRef`、`$id`，包括本地 `#` 引用。
执行配置必须同时满足已实现后端的字段白名单和目录的附加 Schema，附加 Schema 无法放宽后端。
目录输出 `configSchema` 是实际校验的有效 Schema；`effectiveConfigSchemaDigest` 是该对象
按键排序、无空白的 UTF-8 JSON 的 SHA256。默认目录无引用文件时，`configSchemaRef=null`，
`configSchemaDigest` 等于有效 Schema 摘要。所有导出对象均为新副本，不能修改内部快照。

`verified=true` 必须同时 installed/available 并带 `verificationEvidence`：
`kind=operator-attestation`、reference、environment、与登记一致的 executorVersion 和非空 cases。
这只是可信操作者提供的版本化验证证据描述，不代表加载器实际运行了用例、认证了证明内容或探测了服务。
Binding 无权提供登记证据；在 config 内伪造 verified/能力/未知字段将失败。目录必须由操作者明确
选择并保护写入权限，普通包作者不能通过提供目录得到管理权限。W01 未实现团队管理身份与远程认证。

应用、Worker 共享构造时的不可变描述快照；新加载目录取得新配置。显式目录文件删除、字节修改
或 Schema 摘要变化会在下一次 registry preflight 返回 `EXECUTOR_CATALOG_REVOKED`，阻止新 Run
使用原快照，必须显式重载。此校验不终止在途执行，也不构成持续授权/热撤销保证；后续权限生命周期
仍由 W18 实现。已经执行的任务不会悄悄改用新 Schema 或新执行器。

预检及 Runner 执行前共用配置校验。诊断 `EXECUTOR_CONFIG_INVALID` 定位到
`/spec/slots/<escaped-slot>/config/<field>`，details 提供 expected 约束与脱敏的 actual 类型，
不回显配置内容。只有所有调用节点的配置校验实际完成后 checked 才增加 executor-config；静态编译失败、目录撤销或 slot/执行器未解析而跳过配置校验时仍列入 notChecked。
这不检查 live-connectivity、credentials、authorization、sandbox-enforcement 或人工通道送达。
`builtin.human-input.v1` 保留旧 Binding 的 `requestType: input`、`choices: []`；
拒绝其他 requestType 与非空 choices。`requireCommentFor` 字符串数组仅作为 deprecated
兼容字段接受，在 input 模式不生效，不引入审批语义。
既有可信本地 Binding 的 command/cwd 形状保持兼容：command 每个参数是非空字符串，允许纯空白参数；cwd 仍必须含非空白字符。目录文件引用的防越界约束不等于进程文件系统沙箱。

<a id="sec-8-7"></a>

### 8.7 安全与支持状态

“已声明”“已安装”“当前可用”“已验证”分开展示。Descriptor 是执行器声明，不是独立安全证明；verified 必须说明用例、环境和版本，不能只是一个手写常量。

作者或模型不得通过输出代码、伪造 capability 名称、指定 URL 或添加配置字段自动安装实现。环境管理员安装的实现仍需通过对应授权与版本检查。

<a id="sec-8-8"></a>

### 8.8 接入成本分级

原生符合契约的服务主要配置即可；稳定 API 服务提供少量映射；SDK/CLI 通过 Wrapper；只有人工网页、缺乏稳定调用接口的系统，需要不同级别的人工桥接或定制，不保证完全自动化。

相同接入协议下，用户创建更多执行配置不应需要改核心代码。复杂恢复能力不能由简单字段映射凭空生成。

---

<a id="s09"></a>

## 9. Executor Adapter Contract

<a id="sec-9-1"></a>

### 9.1 最小方法集

所有 Adapter 提供以下逻辑方法。方法可以通过 Python 接口或 HTTP 实现，但语义必须一致。

| 方法 | 输入 | 输出 / 要求 |
|---|---|---|
| `describe` | 注册上下文 | ExecutorDescriptor |
| `validate_binding` | Binding、节点契约、环境策略 | 结构化预检报告，无业务副作用 |
| `submit` | ExecutionRequest | 持久 ExecutionRef 或带明确状态的错误 |
| `lookup` | dispatch_key | 原提交对应的引用、强一致未创建证明，或 unknown |
| `observe` | ExecutionRef、可选 cursor | 权威状态、结果和后续观察位置 |
| `cancel` | ExecutionRef、取消命令 ID | 请求回执；不等同于已经停止 |
| `fetch_artifacts` | ExecutionRef、授权上下文 | 有版本的 Artifact 描述，不返回无权限数据 |

HTTP Job 的 observe 可通过轮询工作。Webhook 或事件订阅仅作为降低延迟的可选方式，不是唯一恢复路径。

<a id="sec-9-2"></a>

### 9.2 ExecutionRequest

提交请求必须包含以下字段：

```json
{
  "protocolVersion": "multiverse/v0.1",
  "dispatchKey": "opaque-stable-dispatch-key",
  "effectKey": "opaque-stable-invocation-key",
  "runId": "opaque-run-id",
  "scopeId": "opaque-scope-id",
  "invocationId": "opaque-invocation-id",
  "attemptId": "opaque-attempt-id",
  "attemptNo": 1,
  "executorRef": "registered-executor",
  "input": {},
  "inputDigest": "sha256:64-lowercase-hex-characters",
  "inputSchemaDigest": "sha256:64-lowercase-hex-characters",
  "outputSchemaDigest": "sha256:64-lowercase-hex-characters",
  "deadlineAt": "2026-09-20T12:00:00Z",
  "authorizationRef": "short-lived-scoped-grant-reference",
  "context": {
    "artifactRefs": [],
    "handoff": null,
    "promptRefs": [],
    "skillRefs": []
  },
  "traceContext": null
}
```

以上 ID、摘要与时间仅展示字段形状，不是有效凭据或可直接发往线上系统的请求。实际 ID 由系统产生；摘要必须是有效 SHA-256。

`dispatchKey` 表示同一 Attempt 的提交身份，网络重发不改变。`effectKey` 表示同一 NodeInvocation 的业务操作身份，在安全执行重试之间保持不变。新的业务返工轮次创建新 invocation，因此使用新 effectKey。

authorizationRef 不是可自证权限的任意字符串。Adapter 必须通过配置的授权验证器或受信任 Bridge 将其关联到可验证的受限授权；只有传递此字段而没有验证机制不能标记 enforced。

输入或权限主题变化不能继续复用旧 dispatchKey。相同 key 携带不同请求摘要必须返回冲突，禁止覆盖原请求。

通信关闭时，上述标准请求形状不变。通信开启且当前调用涉及配置的 route 时，`context.communication` 增加第 14.9 节的导出计划或导入引用。未参与 latent route 的程序、人工和外部节点不接收 latent 载荷。

<a id="sec-9-3"></a>

### 9.3 ExecutionObservation

observe 结果必须包含：`executionRef`、`revision`、`status`、`observedAt`、`executionFinal`、`effectState`；可包含 `output`、`error`、`artifacts`、`usage`、`waitReason`、`externalRefs`；仅参与 latent route 的调用可以包含 `handoffExports`、`handoffReceipts`，语义见第 14.9 节。

- status 为 `accepted`、`running`、`waiting`、`succeeded`、`failed`、`cancelled`、`unknown`。
- revision 是同一 execution 的单调递增序号；重复版本不得改变内容。
- executionFinal 只有执行器确认不会再继续当前执行时才为 true。
- effectState 为 `none`、`possible`、`confirmed`、`not_applicable`。它用于安全判断，不能仅因 HTTP 请求失败而填 none。
- succeeded 必须 executionFinal=true，并提供可校验输出；failed/cancelled 如 executionFinal=false，Runtime 仍需等待或核对，不视为安全终止。
- usage 缺失应显示 unknown，不得以 0 冒充无成本。

外部终态必须单调。相互冲突的终态或相同 revision 不同内容触发 `EXECUTOR_PROTOCOL_VIOLATION`，保留证据并阻止自动推进。

<a id="sec-9-4"></a>

### 9.4 HTTP Job 标准映射

V0.1 通用 HTTP Adapter 使用以下端点；第三方不具备这些接口时，通过薄 Bridge 转换，不要求修改第三方内部协议。

| 方法与相对路径 | 行为 |
|---|---|
| `GET /v1/descriptor` | 获取 Descriptor |
| `POST /v1/executions` | 提交 ExecutionRequest；新建返回 201，重复同请求返回 200 |
| `GET /v1/executions/lookup?dispatchKey=...` | 根据提交身份查找；无法可靠判断时明确返回 unknown |
| `GET /v1/executions/{id}` | 获取最新 ExecutionObservation |
| `POST /v1/executions/{id}/cancel` | 取消请求，接收成功返回 202 |
| `GET /v1/executions/{id}/artifacts` | 获取 Artifact 元数据 |

W02 的可信 loopback 宿主在既有元数据端点上返回
`{executionRef, namespace, artifacts}`；每件元数据固定为
`{artifactId, version: 1, executionRef, namespace, name, mediaType, sizeBytes, digest}`。
有产物的终态观察包含同一 `artifacts` 列表；`output.artifact_refs` 留空，由 Runtime 导入后填写。
字节读取补充端点为 `GET /v1/executions/{id}/artifacts/{artifactId}/content`。
它返回原始字节，不返回文件路径。Runtime 仅构造同源固定端点、拒绝重定向，核对执行身份、
本机配置 namespace、版本、SHA-256、实际字节数后进入既有受控 Artifact 存储和 ACL。
本机宿主 namespace 由操作者配置（默认 `local`），不是调用者提供的权限证明。
每件最多 1 MiB、最多 8 件、合计最多 4 MiB；元数据总响应最多 200 KB。
按 `(attemptId, executionRef, artifactId, version)` 幂等登记，来源元数据变化必须拒绝；
登记后 Runtime 崩溃重放不得重复创建引用。旧执行器未声明产物时保留原有观察行为。

宿主只有标准执行事实权威，不拥有 Workflow 路由。SQLite 单活锁与提交意图先于原生启动；
启动窗口或重启后缺权威终态证据时保留 `unknown / executionFinal=false / effectState=possible`，
同 dispatchKey 不再启动。PID 缺失不能证明副作用为 none。Linux 可信本地实现的取消声明
`best_effort`，仅操作当前宿主持有且尚未回收进程身份的任务专属进程组；不承诺杀死主动逃逸的进程。
Runtime 完整取消分发与竞争闭合仍由 W16 负责；支持宿主 cancel 端点不代表 Runtime 已完成接线。

lookup 的普通 404 不能自动解释为“可以安全重做”。只有 Descriptor 声明 strong，且响应明确为 `not_created`，才构成该提交没有创建工作的证明。业务系统的最终一致列表缺少某项不构成证明。

请求认证使用部署配置的受限凭据。必须验证 TLS；禁止以禁用证书验证解决连接问题。允许对明确配置的开发地址使用 HTTP，但不可作为公共服务默认设置。

<a id="sec-9-5"></a>

### 9.5 各类 Adapter 的首版边界

| Adapter | 实现要求 | 明确限制 |
|---|---|---|
| `builtin` | 只调用随 Runtime 或经运营者安装的可信函数；输入输出校验；注册表固定 ID | 工作流包不能上传 Python 源码即获得服务端执行权 |
| `local_process` | 从执行器注册表取得可执行文件与参数规则；JSON stdin、stdout 只输出一个 JSON result；stderr 为有上限日志 | 不默认使用 shell；不承诺任意第三方 CLI 崩溃后可续接 |
| `http_job` | 标准方法、稳定 ID、可恢复查询；支持轮询 | 普通同步 API 必须适配；未知写入结果不自动重发 |
| `human` | 持久 HumanRequest、授权决策、截止时间、审批证据 | 不以浏览器内存或聊天文本作为审批事实 |

Local Process 的 `config` 只包含注册表允许的参数值；包不提供可执行路径。Wrapper 的 JSON 协议与现有 CLI 的交互由适配实现负责。

本地执行记录 host boot identity、PID、启动时间、工作目录引用和日志位置。进程重启后无法可靠核实是否仍在执行时进入 reconciling；不能靠 PID 相同、进程不存在或终端断线单独推断所有子进程与外部副作用已经停止。

`trusted_local` 模式只用于明确授权的可信执行器；它不是沙箱，不得宣传为不可信代码隔离。服务模式默认禁用任意本地执行器注册，只有具备环境管理权限的人能安装它。

<a id="sec-9-6"></a>

### 9.6 通用宿主集成

宿主是任何通过 API 调用或承载界面的系统，不是特殊必需角色。集成层只负责身份映射、执行器注册、外部引用、动作转发与结果映射。

如外部系统已经拥有执行排队、内部重试、交付验收或人工决定，Adapter 必须声明清楚其责任边界。不能同时让 Runtime 和外部系统自动创建同一类重试或返工。`retryOwner=executor` 时，Runtime 只跟踪外部生命周期，不创建新的自动 Attempt。

接入不得直接读写第三方业务数据库，亦不得要求第三方采用本项目的 Task、Project 或 Agent 模型。NodeInvocation 与外部对象通过持久映射关联，不预设一对一关系。

<a id="sec-9-7"></a>

### 9.7 开发者编写业务函数，Adapter 管理执行边界

程序接入的目标体验是：实现“符合 inputSchema 的数据 → 符合 outputSchema 的业务结果”，而不要求每个函数自己实现 Run 台账、Outbox 或人工等待机制。

可采用可信 builtin、注册的 Local Process、HTTP Job 或现有服务的薄 Wrapper。统一生命周期仍由既有 Adapter Contract 表达。

<a id="sec-9-8"></a>

### 9.8 沿用的最小规则

| 接入形态 | 必须遵守 |
|---|---|
| 可信内建程序 | 注册 ID 与固定入口；输入输出验证；包不能通过携带源码自动获得执行权。 |
| Local Process | JSON stdin；stdout 只输出一个 JSON result；日志写有上限的 stderr；不默认使用 shell。 |
| 同步/遗留程序 Wrapper | 显式映射输入输出和错误；说明实际查询、取消、幂等能力；不能凭包装伪造恢复保证。 |
| HTTP Job / 远程服务 | 使用稳定身份、提交回执、观察、取消和核对契约；一次 HTTP 成功不等于任务完成。 |

具体可执行文件、参数、凭据与环境权限来自受信任注册和 Binding，不来自工作流内任意命令字符串。

<a id="sec-9-9"></a>

### 9.9 输出与错误

合法的业务“不通过”结论按业务分支处理；输出 Schema 不合法、必需 Artifact 缺失则不得成功；超时、崩溃与未知副作用按照本规范处理。

不得让固定程序返回一段日志后由下游猜测字段，也不能让 Adapter 把空输出自动修补成合格业务结果。

<a id="sec-9-10"></a>

### 9.10 重试与副作用

Wrapper 不能将一个没有去重或查询能力的遗留脚本包装成“可安全无限重试”。执行器声明 retryOwner、submitDedup、reconcileByKey、cancelMode；本次调用只能有一个自动重试所有者。

未知写入结果先核对。恢复同一工作不创建新业务身份；确认安全的新执行尝试、业务返工与新 Run 重跑保持区分。

<a id="sec-9-11"></a>

### 9.11 作者 Agent 与程序安装分开

作者可以生成待审阅的 Wrapper 或程序源码，但该源码必须走受授权的安装/注册流程。Workflow Package 的导入不能执行安装脚本，也不能借“vibe coding”跳过信任边界。

<a id="sec-9-12"></a>

### 9.12 接入方向

```text
Workflow call / 逻辑 slot
           ↓ Binding
已注册的执行配置
           ↓
通用 Adapter / Platform Bridge
           ↓
外部 Agent、工作区、配置、原生工具及执行记录
```

外部系统保留自己的知识库、Prompt、工具连接、Workspace 和 Session 管理。Multiverse 不要求它开放业务数据库或采用特定 Task/Project 模型。

<a id="sec-9-13"></a>

### 9.13 平台适配一次

有标准执行接口时直接接入；字段不同则用薄 Bridge 翻译；SDK/CLI 使用 Wrapper。新增同平台另一个 Agent、配置或工作区，主要通过注册记录与 Binding 完成。

适配器可以部署在中心，也可以放在能够访问外部平台的网络中。无须为每个节点单独部署一套桥接服务。

<a id="sec-9-14"></a>

### 9.14 必须复用的调用语义

| 方法 | 适配责任 |
|---|---|
| `describe` | 声明契约、能力、版本、取消/去重/查询/观测/权限保证。 |
| `validate_binding` | 验证对象、配置、资源与授权，不执行业务。 |
| `submit` | 映射任务输入，取得可持久关联的执行引用。 |
| `lookup` | 按原提交身份核对已创建、可证明未创建或未知。 |
| `observe` | 映射执行状态、单调 revision、终态、输出与副作用信息。 |
| `cancel` | 请求停止，报告真实支持范围和后续观察。 |
| `fetch_artifacts` | 返回有版本、可核验且授权可读取的产物。 |

标准 HTTP Job 路径继续以本规范第 9 章为准。本规范不增加另一套外部任务生命周期。

<a id="sec-9-15"></a>

### 9.15 保证不足时的行为

无取消能力不等于完全不能接入，但不能声称取消可确认。无可靠 lookup 时不能把普通 404 当作未创建证明。已写入但响应丢失时，Bridge 即使保存了本地请求，也不能自行证明远端没有执行。

远端拥有重试、返工或审批时明确责任边界；Multiverse 不重复自动创建同一类工作。目标选择和版本变化必须重新预检。

<a id="sec-9-16"></a>

### 9.16 既有标准与未知服务

MCP、A2A 或其他协议按本规范保留扩展方向；本规范不宣称当前已集成它们，也不重新核验其版本特性。真实目标已使用某标准时，可实现标准 Adapter，但要逐项映射该服务实际支持的保证。

不能要求外部 Agent 将它内部的所有工具连接也迁入 Multiverse。调用整个 Agent 与接管全部工具是不同接入范围。

<a id="sec-9-17"></a>

### 9.17 框架承担公共复杂度

接入者不应重复实现任务数据库、身份关联、事件去重、回调、轮询、输出验证和产物封装。Integration Kit 应提供统一类型、配置验证、认证引用、关联记录、观察模板、错误封装与契约测试。

平台开发者主要提供请求映射、状态映射、结果映射及原生控制方式。公共实现不能掩盖远端实际能力不足。

<a id="sec-9-18"></a>

### 9.18 四项交付

| 交付项 | 必须解决的问题 |
|---|---|
| 注册表与能力目录 | 找到、配置、验证执行对象，不改 Compiler/Runner。 |
| Bridge SDK | 复用标准调用与持久关联边界，专有逻辑最小化。 |
| Connector | 接入其他电脑的允许执行能力。 |
| 事件与 Artifact SDK | 将真实步骤、错误和交付物接入同一运行视图。 |

这些是模块/安装产物，不要求全部独立进程。插件安装、语言包装和通信具体参数在 第 0.5 节 冻结。

<a id="sec-9-19"></a>

### 9.19 用户路径

**接入能力 → 选择执行配置 → 完成工作流 Binding → 预检 → 受控试运行 → 在 Multiverse 查看与处理。**

接入页不能只显示“连接成功”。要说明可见对象、可用能力、实际保证、缺失资源和未验证项。网络通、对象存在、契约兼容、授权充分、质量合格是不同结论。

<a id="sec-9-20"></a>

### 9.20 Authoring Kit

沿用本文已合并的人工/作者要求的原生外部 Agent 编写能力。机器可读目录应包含当前授权范围的 slot 候选、契约、配置 Schema、交互方式和已验证组合。不能泄露其他租户资源或凭据。

作者先定义交付与 Schema，再生成 Workflow 和 Binding；调用 validate、预检与测试，根据精确诊断修复。不得为了通过而删除验收、降低权限要求或绕过真人。

开发流程作者不必是运行节点；内建受限作者模板只是可选工作方式，不得扩大成自动发布系统。

---

<a id="s10"></a>

## 10. 权限、Policy 与安全边界

<a id="sec-10-1"></a>

### 10.1 权限计算

一次实际执行的有效授权必须是以下范围的交集：节点声明的动作范围、Deployment 允许范围、当前发起人/服务身份权限、执行环境可以实施的范围。

声明 Capability 只是“支持某操作”；声明 Policy 只是“要求某限制”；只有网关、受限凭据、执行环境或可验证执行器实际实施，才能标记 `enforced`。

不能因为 Agent 在 Prompt 中被要求遵守，就显示网络、文件和命令权限已经隔离。

<a id="sec-10-2"></a>

### 10.2 身份模式

首版提供本地受限 token 与集成用服务 token，不重造完整账户系统。每个身份具有 subject、namespace 和 scope；最低 scopes 为 `read`、`run:start`、`run:control`、`human:decide`、`deploy:write`、`executor:manage`、`reconcile:write`。

独立本地模式首次生成高强度随机 token，写入仅当前用户可读的凭据文件。默认监听 loopback。服务模式禁止匿名启动/部署/审批；反向代理认证必须通过受信任集成适配，不接受任意客户端 `X-User` 头。

外部服务转发人的操作时，必须有可验证的委托身份或限定范围的操作授权。服务 token 不能仅通过正文填写某人的名字就获得该人的权限。所有决定记录实际执行主体和经验证的代表主体。

<a id="sec-10-3"></a>

### 10.3 审批的权限边界

人批准某项动作不扩大该 Deployment 的权限上限。审批对象必须含动作、资源、输入/产物摘要、包和 Binding 版本、必要的有效期。

有效凭据在调用时解析，只注入该次执行需要的最小集合。持久记录保存 secret reference 与可用时的版本标识，不保存 secret 明文。凭据轮换允许，但权限变更或语义相关配置变更必须重新预检；撤销立即阻止后续派发。

<a id="sec-10-4"></a>

### 10.4 外部输入与导入安全

默认拒绝包内安装钩子、任意执行脚本、路径穿越、绝对路径、符号链接和解压炸弹。HTTP 连接地址来自运营者授权注册表，不能由模型输出直接变成允许访问的内部地址。重定向与 DNS 解析仍需按网络策略检查。

Artifact 默认不主动执行 HTML、JavaScript、宏或下载来的程序。纯文本与 JSON 预览必须转义。外部网页、模型输出、Memory 与 Artifact 中的指令均为不可信数据，不能取得系统权限。

<a id="sec-10-5"></a>

### 10.5 命令与查询使用同一授权源

前端隐藏按钮不是授权控制。所有 API、CLI、自动化调用和宿主转发必须经过同一命令权限入口。若某个节点是发布或验收的强制门槛，不能通过另一个 API 直接绕过。

<a id="sec-10-6"></a>

### 10.6 有效权限取交集

实际执行权限受节点声明、部署上限、当前主体权限与执行环境实施能力共同限制。配置文件、Prompt 或 Descriptor 自报不能代替实施。

目标平台和飞书等转发操作时，要验证实际主体及合法委托；不能通过自报姓名或 userId 获取真人权限。共享服务 token 不得成为所有审批人的替代身份。

<a id="sec-10-7"></a>

### 10.7 凭据与注册

导出包不含密钥、个人账号授权、机器凭据和原平台会话。运行时按 Secret Provider 或受控本地存储引用注入最小集合，撤销后阻止新派发。

Connector 配对只授权相应接入范围；新增本地程序与工作目录需明确选择。程序不能通过读取上级目录获得 Runtime 数据库或宿主凭据。

<a id="sec-10-8"></a>

### 10.8 执行资产安装

编辑/生成代码、构建资产、登记依赖、安装、授权与调用是不同步骤。导入 Workflow 不执行任意脚本，也不因包声明能力就自动注册可信代码。

构建和安装应由受信任工具在明确权限下完成，保留内容摘要、版本和依赖记录。格式、镜像/压缩包校验和安装入口需在 第 0.5 节 冻结，不设计任意代码安装钩子。

<a id="sec-10-9"></a>

### 10.9 外部与页面内容

模型输出、文件、网页、外部回调及聊天正文均按不可信数据处理。不得将其中命令自动升级为环境管理指令。

外部链接、下载、重定向和文件路径受策略检查。页面安全渲染，HTML/脚本/宏不因成为 Artifact 被自动执行。大型或二进制内容受大小、解码与保留约束。

<a id="sec-10-10"></a>

### 10.10 跨环境与同步

开发环境默认不读取交付环境的数据。需要远程支持或集中监控时，单独配置授权、范围和审计，不强制数据回传。

模型、Workspace、Artifact 与 latent 载荷的访问范围分别验证；能看到一个 Run 不自动能读取其全部敏感内容。摘要脱敏不意味着原始载荷已脱敏。

---

<a id="s11"></a>

## 11. 生命周期、失败与人为控制

<a id="sec-11-1"></a>

### 11.1 NodeInvocation 状态

| 状态 | 意义 | 允许的后续 |
|---|---|---|
| `planned` | 已知定义、尚未激活 | ready / skipped |
| `ready` | 条件满足、等待容量与派发 | running / waiting / cancelled / failed |
| `running` | 派发中或正在执行，可能尚未收到外部确认 | waiting / retry_wait / cancel_requested / reconciling / succeeded / failed / cancelled |
| `waiting` | 等待人工、外部事件或子流程 | running / ready / cancel_requested / reconciling / succeeded / failed / cancelled |
| `retry_wait` | 已证明允许重试，等待持久定时器 | ready / cancelled |
| `cancel_requested` | 已发起停止，尚未确认 | cancelled / succeeded / failed / reconciling |
| `reconciling` | 是否创建/完成/停止尚不确定 | ready / retry_wait / running / waiting / succeeded / failed / cancelled |
| `succeeded` | 输出有效、执行已结束 | 无；终态不可覆盖 |
| `failed` | 确定失败、无当前执行继续运行 | 无；新的业务尝试通过关联的新 Run，不改写当前终态 |
| `cancelled` | 确认未启动或已停止 | 无 |
| `skipped` | 非选中路径 | 无 |

自动重试是在 invocation 最终 failed 之前决定；每个失败 Attempt 保持不可变。V0.1 不提供任意“将一个终态 invocation 改回 ready”的接口。用户要重新尝试已终结流程，创建关联的新 Run；结果未知则先完成核对。

Attempt 状态为 `created`、`submitted`、`running`、`waiting`、`cancel_requested`、`unknown`、`succeeded`、`failed`、`cancelled`。具体调用的原始观察始终保留，不能只保留最后一张状态快照。

<a id="sec-11-2"></a>

### 11.2 WorkflowRun 状态

`queued`、`running`、`waiting`、`paused`、`stopping`、`blocked`、`succeeded`、`failed`、`cancelled`。

Runtime 单独保存 `control_mode=run|pause|cancel|fail` 与 `status`，避免用状态字符串同时表达意图和事实。

确定规则：有未解决 execution unknown，或必需的已固定交接载荷/兼容版本无法恢复时 status=blocked；已要求 cancel/fail 且仍有活动执行时为 stopping；已暂停派发时为 paused；存在可推进或执行中的工作时为 running；全部剩余活动都在已知等待时为 waiting；所有必要结果和结束条件满足后才进入终态。

终态必须没有未核对活动执行。已经成功/失败的 Run 不因迟到事件复活；事件作为异常证据保留。外部事实若与已记录终态冲突，标记完整性事故，禁止静默重写历史。

<a id="sec-11-3"></a>

### 11.3 重试规则

重试需要同时满足：错误码在允许列表；retryOwner=runtime；尚未达到次数；旧 Attempt 已最终结束；输入/授权主题不变；副作用安全条件成立。

副作用安全条件是以下之一：操作无外部写入；已经可靠证明未产生写入且不会继续执行；执行器实施 effectKey 级别的重复保护，重复调用不会产生额外业务动作。单纯支持 dispatchKey 去重不等于支持跨 Attempt 的业务幂等。

Schema 校验失败、权限拒绝、用户拒绝、输出缺失、结果未知默认不自动重试。禁止仅凭 HTTP 500、客户端超时或进程退出码认定写入未发生。

延迟按固定指数退避计算，实际 next_attempt_at 必须持久化。服务重启不重置次数或重新随机选择延迟。内建默认不加随机抖动；未来增加时也必须保存实际值。

<a id="sec-11-4"></a>

### 11.4 超时

所有截止时间使用 UTC 并在开始时固定。调用 deadline 从首次创建 Attempt 开始计算，包含外部排队与等待；节点可显式设较长时限。Run 总 deadline 始终优先。

超时后先停止新派发并请求取消活动执行。确认停止后，以 `DEADLINE_EXCEEDED` 失败；不能确认则 blocked。人工请求到期不会默认批准。暂停调度不冻结 deadline，界面必须说明这一点。

<a id="sec-11-5"></a>

### 11.5 暂停与继续

pause 表示“停止产生新的业务执行意图”，不表示冻结操作系统进程。已有执行可以继续上报结果；日志、状态核对、取消和审计仍工作。尚未真正派发的 outbox 项必须在发送前再次检查 control_mode。

resume 只解除调度暂停，不能代替人的决定、解决未知副作用、修改输入或替换 Binding。对 blocked 使用 resume 必须拒绝并返回所需核对动作。

<a id="sec-11-6"></a>

### 11.6 取消与竞争

取消命令提交后先设置控制意图，再请求取消当前执行。若结果先完成，保留节点成功事实，但不得因迟到结果启动取消后的下游；Run 在确认所有活动结束后可 cancelled，并保留已发生副作用摘要。

若完成事务已经先将 Run 置为 succeeded，之后的取消返回 `ALREADY_TERMINAL`。以命令/状态事务的持久顺序决定控制竞争，不按浏览器到达顺序或不可靠外部时间判断。

V0.1 没有“强制取消即当作什么都没发生”的按钮。必要的人工处置必须提交可审计的核对证据，不能清空未知状态。

<a id="sec-11-7"></a>

### 11.7 结果核对

允许的核对结论：`confirmed_succeeded`、`confirmed_failed`、`confirmed_cancelled`、`confirmed_not_started`。必须提供证据引用、对象版本、处理人和 reason。成功结论仍需输出 Schema 通过，且不能自动补齐业务审批。

confirmed_not_started 只有能确认旧提交不会稍后执行时才成立。核对后按原控制意图继续/失败/取消；如原重试策略仍允许剩余尝试，创建明确的新 Attempt，保留旧 Attempt 的“未创建”结论；次数不足则原调用结束，另行创建 Run，不因人工核对无限扩充 maxAttempts。无法确认就维持 blocked。

<a id="sec-11-8"></a>

### 11.8 区分三个操作对象

Workflow/Deployment 是定义与部署，WorkflowRun 是一次执行，执行宿主/模型服务是运行环境。它们不得共用一个无范围说明的“开关”。

| 界面操作 | 对象 | 命令含义 |
|---|---|---|
| 运行 | 已激活的部署入口。 | 提交业务输入，创建新的持久 Run。 |
| 暂停派发 | 活动 Run。 | 停止安排新的业务执行；当前执行可继续上报。 |
| 继续派发 | 已暂停 Run。 | 解除调度暂停，不代替人的决定和未知结果核对。 |
| 停止本次运行 | 活动 Run。 | 持久记录取消意图，请求停止当前执行并禁止下游。 |
| 重新运行 | 历史 Run。 | 创建关联新 Run，不改旧终态、不拷贝批准。 |
| 停用部署 | Deployment。 | 禁止新 Run，不自动取消活动实例。 |
| 排空/关闭执行环境 | Execution Host / Connector / 模型服务。 | 管理操作，单独权限与影响说明；精确接口待定。 |

按钮可使用熟悉名称，但必须有准确解释。V0.1 暂停派发不等于冻结 OS 进程；若后续提供 Agent 安全步骤暂停，应作为独立可协商能力。

<a id="sec-11-9"></a>

### 11.9 停止流程

```text
验证身份、对象版本和可操作状态
              ↓
提交取消意图、事件与必要控制 Outbox
              ↓
禁止新的下游派发
              ↓
向本次拥有的活动执行请求取消
              ↓
保存终态观察、已发生副作用与产物
              ↓
全部确认结束则取消；未知执行仍需核对
```

受管进程可按经过验证的退出策略处理；终止进程不撤销已发生的文件修改或外部请求。不能只在 UI 将状态变灰。

取消与完成按持久提交顺序处理，沿用本规范。取消后到达的成功结果可以保留节点事实，但不能重新派发被取消的下游。

已经领取、处于网络提交途中的请求可能在控制命令之后才被外部接受，仍需继续核对并按需取消；暂停/停止不能承诺瞬间阻断全部在途动作。待处理人工请求和子流程按相同控制意图处理，迟到表单不能复活已终止请求。

<a id="sec-11-10"></a>

### 11.10 共享资源与操作范围

停止 Run 只影响该 Run 拥有的执行实例和明确关联的子执行。不得关闭其他 Run 使用的共享模型服务、长期 Agent 配置或工作区。

执行器不支持可确认取消时显示实际能力，不能提供一个看似保证立即停止的按钮。结果未知时不能“强制标成功/标取消”绕过证据核对。

<a id="sec-11-11"></a>

### 11.11 节点级操作

首版不提供绕过依赖的任意节点播放键。允许的“调试试运行”创建隔离测试执行或关联新 Run，使用显式输入、沙箱 Binding，不修改生产实例，不自动满足下游依赖。

已终态的 invocation 不改回 ready。更复杂的从中间节点重跑、局部取消或内部工具级控制须单独定义数据、副作用和兄弟分支影响，不能仅靠前端按钮加入。

<a id="sec-11-12"></a>

### 11.12 页面与命令一致

服务端决定允许动作，前端展示并仍接受服务端重新验证。202/请求回执只说明已持久接收；界面显示“已请求/待确认”，直到事实更新。

暂停不冻结既定 deadline；blocked 不能用普通 resume 当作已经解决。关闭页面或 CLI 不取消持久 Run。

---

<a id="s12"></a>

## 12. 持久执行、一致性与 LangGraph 集成

<a id="sec-12-1"></a>

### 12.1 权威与投影

Runtime 的业务状态表、调用台账和运行事件是 Multiverse 语义的权威记录；LangGraph Checkpoint 保存后端控制进度，不能覆盖外部执行事实。Inspector、缓存和 OTel 均为投影。

不要求实现可以从事件日志重建一切的通用 Event Sourcing 系统。要求关键状态变更、事件和必要 outbox 在同一数据库事务提交；快照与事件之间必须可核对。

<a id="sec-12-2"></a>

### 12.2 四种幂等身份

| 身份 | 用途 | 生命周期 |
|---|---|---|
| API `Idempotency-Key` | 同一用户命令的重复提交 | 命令回执保留期内 |
| `transition_key` | 后端重入同一次语义状态变更 | Run 保留期内 |
| `dispatch_key` | 同一 Attempt 的外部提交去重 | 不短于 Run 与外部执行的保留期 |
| `effect_key` | 同一 invocation 的业务副作用去重 | 由执行器声明，必须覆盖配置重试与核对窗口 |

用户命令去重键的作用域是 namespace、subject、operation 和 key；相同 key 不同正文返回 409。不能因为客户端重试就另生成一份 Run。

<a id="sec-12-3"></a>

### 12.3 外部执行的提交过程

```text
1. 数据库事务：创建 invocation/attempt，冻结输入与权限引用，写 submit intent/outbox。
2. 提交事务。此时尚不能对用户声称外部已开始。
3. Dispatcher 在短事务中复核 control_mode、授权与 deadline，记录 dispatch_started 后，以固定 dispatch_key 提交。
4. 外部执行器先持久去重身份，再创建实际工作，返回 execution reference。
5. Runtime 事务：保存 reference、追加事件、安排 observe/reconcile。
6. 输出进入终态观察并校验后，提交本地事实，再允许图的下游推进。
```

dispatch_started 的事务提交是派发的本地线性化边界。暂停/取消先提交时，不得再领取新派发；已经领取但网络调用尚未返回的执行属于在途工作，可能在控制命令之后才被外部接受，必须继续核对并按需取消。界面不能承诺暂停会瞬间阻断已经在途的请求。

步骤 3—5 之间崩溃不能通过“重新创建业务工作”解决。先 lookup 或用同 key 重发由外部执行器去重；无法核实时进入 reconciling。

本规范不承诺跨系统 exactly-once。提供的是持久意图、至少一次传输、稳定身份、条件性的副作用去重、终态校验和结果核对。

<a id="sec-12-4"></a>

### 12.4 Graph 节点的实现形状

编译后的外部调用至少区分“确保提交意图存在”“读取/等待持久结果”“验证并推进”。每一段重入前先检查对应持久记录；已有成功结果直接复用，不能重新调用外部模型或程序。

LangGraph 节点只在相关权威记录提交后返回完成。Checkpoint 保存失败时，下一次恢复允许重入，但 transition_key、dispatch_key 和既有结果确保不产生新的业务执行。Checkpoint 已保存但客户端未收到完成响应，也由同一逻辑识别。

不得假设 LangGraph saver 与应用表天然共享同一个原子事务。不能为了省事，将“保存 Checkpoint”与“外部创建工作”当成原子提交。[E1][E2]

<a id="sec-12-5"></a>

### 12.5 单活 Worker

服务模式 V0.1 仅支持一个活跃调度 Worker；可以并发等待多个外部执行，但同一 Run 的图推进必须串行。

PostgreSQL 模式使用专用连接持有集群唯一调度 advisory lock；失去该连接即停止新的推进与发送。待执行意图存数据库，不存进程任务队列。PostgreSQL 提供应用可用的 advisory lock，但业务去重和未知结果处理仍由本项目负责。[E8]

SQLite 模式使用进程排他锁，只允许一个本地 Runtime，禁止共享数据库文件运行多个实例或置于网络文件系统上做生产服务。

HTTP/API 进程与 Worker 可分开启动，默认一个镜像提供不同命令。不使用 FastAPI 请求内 BackgroundTasks 作为持久工作流调度器。

<a id="sec-12-6"></a>

### 12.6 Inbox、Outbox 与唤醒

外部回调先认证、限流、持久化 inbox，再应答；Worker 去重并应用。poll 取得的观察也走同一入站处理逻辑。每个执行器的 revision 单调，旧事件保留但不回退状态。

Outbox 项包含 ID、关联身份、动作、payload digest、not_before、处理状态、尝试次数和最后错误。重发需要稳定业务 key。不同动作使用不同 key；取消重试不创建新的执行。

图等待使用持久 wait record 和定期扫描作为兜底。唤醒只是提示；Worker 每次从数据库确认当前条件。事件早于 wait record 到达时，已有结果仍能被读取，不能永久漏唤醒。

<a id="sec-12-7"></a>

### 12.7 Checkpoint 恢复与历史回放

日常恢复使用相同后端版本及持久 Checkpoint。若 Checkpoint 无法读取，默认 blocked 并报告 `BACKEND_RECOVERY_REQUIRED`，不得自动从头运行真实外部动作。

只读历史回放根据事件和快照还原过程，不调用执行器。调试重跑创建新 Run，默认使用录制结果或沙箱 Binding；生产副作用重跑需要新的显式授权。

V0.1 不支持不同 LangGraph 版本之间未经迁移测试的活动实例恢复。升级门禁必须包含真实旧 Checkpoint 兼容测试；无法兼容时先完成/停止旧实例或保留旧版本 Worker。

<a id="sec-12-8"></a>

### 12.8 固定内容，而不只是保存摘要

开始 Run 时固定 Package、Binding、策略、解析计划、配置/Adapter/执行器版本及必要 Context。继续执行不得重新读取当前可变目录并沿新定义推进旧运行。

只存摘要但没有原内容或可取回版本，不足以恢复。原依赖无法读取或版本漂移时明确 blocked；不能悄悄选最新模型、Profile 或 Schema。

<a id="sec-12-9"></a>

### 12.9 命令去重

API Idempotency-Key、transition_key、dispatch_key、effect_key 的作用沿用本规范。相同身份和 key 的重复请求需要比较完整语义指纹，不仅检查“属于同一个请求”。

指纹应覆盖影响行为的输入、Context、动作、对象主题和经验证主体；敏感凭据不进入普通日志。相同 key 不同正文返回冲突，不能伪装成原命令成功。

只支持提交去重不意味着跨 Attempt 副作用幂等。取消重试不创建新执行。

<a id="sec-12-10"></a>

### 12.10 人工决定与推进

人工决定、请求版本、审计事件和必要的持久推进意图必须原子提交。Worker 按持久状态完成 Attempt/Invocation 和后续推进。

进程在决定落库后退出，重复回调不能只返回一个仍等待的 Run 而永远不补做推进。等待扫描与已存在决定需要可核对；重复命令不重复业务动作。

<a id="sec-12-11"></a>

### 12.11 支持性门禁

“协议可解析”“静态合法”“当前后端可执行”“真实验证通过”分别报告。开始运行前检查整个可达流程需要的特性与绑定，不允许前面已产生副作用，执行到中间才发现某节点或后端根本不支持。

未实现的运行类型、未知必需扩展、缺失人工入口、未验证 latent 组合必须在对应预检/激活阶段拒绝。

<a id="sec-12-12"></a>

### 12.12 外部提交与观察

沿用持久 intent/outbox、稳定提交身份、inbox 去重、输出验证后推进。提交成功但回执丢失时先 lookup/reconcile；普通 HTTP 失败不证明副作用不存在。

执行成功后输出格式错误、缺产物或缺 latent 载荷时，不能重新运行已完成的业务动作来补齐。保存证据，查询同一执行，并按真实副作用状态处理。

<a id="sec-12-13"></a>

### 12.13 恢复边界

框架级 Checkpoint 与外部动作、宿主台账不被假设为一个原子事务。恢复按原身份和固定版本进行；未知执行保持待核对，不能从头重跑。

备份覆盖 Runtime 记录、Checkpoint、包、执行资产引用、Artifact、必要的 Connector 关联及交接载荷。恢复后先核对活动外部工作；不能把“服务启动成功”当作所有执行已安全恢复。

本节是对前述设计及历史审阅暴露风险的回归要求，不是对某个最新仓库提交的重新缺陷判定。

---

<a id="s13"></a>

## 13. Human Request 与受控审阅

<a id="sec-13-1"></a>

### 13.1 人工请求模型

HumanRequest 必须包含：id、namespace、run/scope/invocation 关联、requestType、title、instructions、input、inputDigest、subjectRefs、subjectDigest、choices、decisionSchema、authorizedSubjects、createdAt、expiresAt、version、status。

requestType 为 `approval`、`review`、`input`。approval/review 的 choices 非空，决策归一化输出为 `{decision: <choice>, comment: <string>}`，缺省 comment 为 `""`；input 的 choices 为空，提交的 decision 必须是直接符合节点 outputSchema 的 JSON 对象，comment 只记审计、不注入业务输出。decisionSchema 必须与上述归一化输出契约一致。status 为 `pending`、`decided`、`expired`、`cancelled`。V0.1 每个请求只接受一次有效最终决定，不实现多人会签与投票。

subjectDigest 至少覆盖包、Binding、请求输入、被审阅 Artifact 版本和动作目标。需要重新审阅的内容变化必须创建新请求。

<a id="sec-13-2"></a>

### 13.2 决策提交

提交包含 `decision`、必要 `comment`、`expectedVersion`、`subjectDigest` 和 Idempotency-Key。服务端在同一事务校验权限、请求未终止、未过期、版本匹配、主题匹配，再记录不可变决定并安排继续。

重复相同命令返回原回执。第二份冲突决定返回 409。读取页面不自动延长审批期限。

review 返回 approve/reject 并不直接改变整个 WorkflowRun 状态，而是作为节点输出供显式 switch 使用。request 的有效完成可对应业务拒绝；只有流程定义决定拒绝后是失败、修改循环还是其他处理。

<a id="sec-13-3"></a>

### 13.3 两种人工来源

内建 human 由 Runtime 保存并验证决定。第三方审批系统可以作为 HTTP Job 执行器完成相同输出契约，其 Bridge 必须保留决策人的证据与对象版本。一个请求只能有一个最终决定权威，不能同时让两个界面互相覆盖。

<a id="sec-13-4"></a>

### 13.4 人工输入不是任意状态编辑器

允许提交 Schema 规定的补充材料，不允许直接改 `node.status`、执行结果、Graph 或已经冻结的输入。需要修改工作目标时新建 Run，关联原 Run 并说明原因；有界业务返工通过 repeat 的显式输入传递完成。

<a id="sec-13-5"></a>

### 13.5 沿用三种 HumanRequest

人工执行沿用 `call` 节点与 Human Adapter，不新增一种绕过统一协议的“人类流程”。

| requestType | 典型工作 | 最终输出 |
|---|---|---|
| `approval` | 对明确对象版本和动作作许可决定 | `{decision, comment}`，choice 与 Schema 一致。 |
| `review` | 审阅特定版本的产物与证据 | `{decision, comment}`，按显式分支使用结论。 |
| `input` | 补充资料、分类标注、填写数据、修改文件、执行人工任务并交付产物 | 直接满足节点 outputSchema 的业务 JSON。 |

`input` 不限于“补一句话给 Agent”；它可以承担完整的人工生产环节。不得把复杂人工工作勉强塞进 `comment`，然后要求下游猜测文本含义。

<a id="sec-13-6"></a>

### 13.6 输入与输出必须分别建模

`inputSchema` 约束交给人的任务材料；`decisionSchema` / `outputSchema` 约束人需要提交的结果。页面不能将冻结输入全部变成可编辑字段，再用编辑结果覆盖原任务。

任务目标变化时遵守本规范：需要新目标则创建新 Run；有界业务修订通过明确 repeat 输入传递，不修改旧输入和旧审批。

<a id="sec-13-7"></a>

### 13.7 决策归一化

approval/review 的决定归一化为 `{decision: <choice>, comment: <string>}`，缺省 comment 为 `""`；必填评论规则仍由服务器实施。

input 的请求 choices 为空；API 请求中的 decision 值就是符合 outputSchema 的业务对象。附带的审计 comment 不注入业务输出。不能让页面和 CLI 各自采用不同的包裹层。

<a id="sec-13-8"></a>

### 13.8 最低请求信息

HumanRequest 沿用本规范中的请求身份、namespace、run/scope/invocation、requestType、title、instructions、input/inputDigest、subjectRefs/subjectDigest、choices、decisionSchema、authorizedSubjects、createdAt、expiresAt、version、status。

指令、材料、证据和允许输出必须清晰。谁能处理属于环境授权；不能在可移植 Workflow 中硬编码某个公司的账户体系。

<a id="sec-13-9"></a>

### 13.9 人工声明与独立验证分开

“人提交已完成”是一个有身份与版本的声明，不自动等于外部动作已被独立核验。需要核验时设计后续程序或服务节点读取明确证据。

任务是人工提交文件时，应验证文件存在和契约；任务涉及外部真实动作时，应明确证据要求与核验责任。不得用一个完成按钮替代必要事实。

<a id="sec-13-10"></a>

### 13.10 页面必须可真正完成任务

**追加要求：**人工节点不仅在图上显示 waiting，还必须有可用的操作入口。可采用内建页面、嵌入组件、自定义页面或合规接入的外部服务。

普通用户处理支持范围内的人工任务时，不应被要求手写 JSON。面向开发者的原始 JSON 查看/提交可保留，但不能代替最低可用表单。

<a id="sec-13-11"></a>

### 13.11 页面分区

| 区域 | 必须表达的内容 |
|---|---|
| 任务信息 | 目标、说明、当前状态、处理期限、当前身份能做什么。 |
| 只读材料 | 冻结输入、待审阅产物、具体版本、验证结果、证据和明确约束。 |
| 结果填写 | 根据输出契约生成或配置的字段、选项、产物选择/提交。 |
| 提交与冲突 | 服务器校验结果、字段错误、版本过期、主题变化、已被处理或已取消。 |
| 操作记录 | 实际提交身份、时间、版本、决定及证据关联。 |

<a id="sec-13-12"></a>

### 13.12 默认表单支持范围

必须发布支持矩阵，首版至少覆盖：布尔值、有限枚举、数字与整数、短文本与长文本、必填字段、对象分组、有限数组，以及受控 Artifact 选择或上传入口。

展示可使用 Schema 的说明信息；控件顺序、分组、布局和自定义呈现属于展示配置。数据规则以 Schema 和服务端验证为准。

不要求任意 JSON Schema 都自动得到完美表单。复杂组合、专用标注工具或领域编辑器可交给已注册页面/组件或外部服务。声明的任务超出所选入口支持范围时，预检应说明缺口；不能运行到一半才发现没有可用控件。

<a id="sec-13-13"></a>

### 13.13 展示不拥有权限或事实

隐藏字段、禁用按钮、前端枚举和客户端校验不替代服务端验证。不得从客户端接收可自证身份或可自证授权的值。

默认值只可作为可见候选值；页面显示或初始化不得产生提交。审批不因默认选中 approve 而完成。任何最终决定都必须由受授权主体显式提交。

<a id="sec-13-14"></a>

### 13.14 自定义呈现的边界

自定义页面只负责收集输入与展示事实，不能直接更新节点状态。必须使用同一请求、同一 subjectDigest、同一输出契约和同一命令入口。

包内不允许任意 JavaScript、HTML 或安装脚本因此获得服务端/页面执行权。自定义控件由受信任环境注册；页面采用安全呈现，不把业务字符串直接当作 HTML。

布局提示应通过明确 Schema 的展示扩展或 Adapter 配置承载。不得随意向 NodeDefinition 添加 `formUrl`、`uiSchema` 等未知核心字段。精确扩展键、字段和组件接口在实现时按 第 0.5 节 登记，不由 Agent 自行发明。

<a id="sec-13-15"></a>

### 13.15 持久等待与生命周期

人工等待不是一个必须保持连接的 HTTP 请求，也不占用持续工作的浏览器。关闭页面、CLI 断开或 Runtime 重启后，请求、版本和等待关系仍然存在。

重复提交去重；并发冲突不能覆盖先前有效决定。已过期或取消的请求不得因迟到提交重新激活；合法的重复幂等请求按原回执处理，不新增决定。

草稿不是最终输出，文件上传不是最终交付，页面打开不是已读授权，消息已读不是任务完成。是否提供草稿保存可作为界面增强，但不得与执行事实混淆。

人工可能已在外部执行真实动作时，取消请求不代表撤销动作；需要停止确认或结果核对时，沿用本规范安全边界。

<a id="sec-13-16"></a>

### 13.16 三种接入方式

| 方式 | 人在哪里操作 | 决定权威 | 接入要求 |
|---|---|---|---|
| 内建页面 | Inspector 的 Human Inbox / HumanRequestPanel | Multiverse Runtime | 读取并提交内建 HumanRequest。 |
| 嵌入或自定义页面 | 任意产品的受控页面 | Multiverse Runtime | 调用同一 HumanRequest API，不生成第二份审批。 |
| 外部工单/审批/人工服务 | 外部系统自己的入口 | 外部系统保存决定，Runtime 保存经验证的执行观察 | 通过 HTTP Job / Bridge 映射统一执行契约，保留身份、版本与证据。 |

前两种只改变界面，不改变权威。第三种明确由外部系统拥有决定，不能再创建一份能覆盖它的本地审批。一个请求只有一个最终决定权威。

<a id="sec-13-17"></a>

### 13.17 外部入口不是完成信号

任务交给外部系统时，必须关联：本次调用、外部执行引用、请求版本、对象版本、允许操作、结果返回方式和状态核对方式。

通知、邮件、聊天卡片或页面链接只负责引导。不能把通知发送成功、页面打开、消息已读、重定向成功当作人工工作已完成。

外部地址与认证属于环境配置。链接不得携带长期凭据；外部回传需要认证、权限检查、幂等去重和版本匹配，不能信任浏览器随意提交的外部结果。

<a id="sec-13-18"></a>

### 13.18 状态回传与恢复

外部系统可以主动回调，Runtime 也必须能按稳定引用查询/核对。不能把浏览器连接或一次 webhook 当作唯一恢复路径。

Bridge 负责将外部状态映射为原有 ExecutionObservation，保留外部 revision 或可核对版本，区分 accepted/running/waiting 与真实终态。请求结果未知时先查询，不重复创建工单或任务。

人工决定只在验证通过后作为节点输出提交。输出结构错误、证据缺失、身份不可验证或对象版本不一致时，不得为了推进而伪造 approve、completed 或 succeeded。

<a id="sec-13-19"></a>

### 13.19 预检要求

部署前应检查该人工节点是否存在支持对应任务的入口，结果提交方式是否满足 Schema，以及授权、产物读写和查询/恢复条件是否满足环境要求。

这不要求所有部署都提供 Web：CLI、已验证的嵌入入口或外部人工服务可以满足相应使用场景。但面对普通用户的支持声明，不能把“有一个 JSON 接口”当作已经具备可用页面。

无法在无业务副作用预检中确认的项目保留 unverified；不能把发送一份真实工单隐藏为探测操作。

<a id="sec-13-20"></a>

### 13.20 必须补齐的交付闭环

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

<a id="sec-13-21"></a>

### 13.21 生命周期与权限

临时上传、部分文件、浏览器本地路径、任意字符串或无法冻结版本的 URL 都不能登记为已完成交付。引用必须能解析到真实授权对象。

上传者、提交者和后续读取者的权限分别检查。成功上传不自动赋予下游读取权限，也不自动表明本次 HumanRequest 允许引用该对象。

取消/过期请求后完成的上传不应自动完成原任务。未被有效交付引用的临时数据按保留与回收策略处理；已登记历史产物不能被静默覆盖。

外部产物沿用本规范：优先内容摘要，否则使用可验证的外部不可变版本并标明验证方式；不能以可变 URL 代替版本事实。

<a id="sec-13-22"></a>

### 13.22 提交操作的共同语义

内建 UI、嵌入页面、CLI 和 API 都提交符合相同 HumanRequest 契约的 decision，并带 expectedVersion、subjectDigest 和幂等身份。

对于 `input` 请求，提交的 decision 直接是业务对象。对于 approval/review，使用规定 choice/comment。不得额外添加只在某个前端生效的结果包裹层。

提交时重新验证请求仍可处理、身份有权、对象与版本一致、输出 Schema 合法、Artifact 可用。数据库事务不等待上传或模型推理；先完成对象，再在事务中核对引用与摘要。

<a id="sec-13-23"></a>

### 13.23 API 与 CLI 缺口

本规范已有 Artifact 读取/下载与人工决定提交接口，但没有固定完整的上传/外部登记 API；CLI 示例也未给出任意 `input` 结果文件提交的完整参数。

本次明确把这两项列为需要补齐的能力。`--decision-file` 可作为结构化文件提交参数的设计建议，但尚未冻结，不得在当前支持矩阵中宣称可用。

上传端点、上传会话、外部登记字段和该 CLI 参数应在实现变更中一起补齐 Schema、错误语义、鉴权与测试。本文不擅自给未讨论的端点、大小默认值和保留期限命名；涉及限制继续遵守本规范或显式环境策略。

<a id="sec-13-24"></a>

### 13.24 人工是统一执行参与者

沿用 approval / review / input 三类 HumanRequest。人工 input 可以提交结构化资料、分类、标注、修改后的文件或完整人工产物，不限于一句补充文本。

任务材料按 inputSchema 展示，冻结输入只读；结果区按 decisionSchema / outputSchema 收集。审批按钮、文件上传与表单校验不能各自拥有不同完成语义。

<a id="sec-13-25"></a>

### 13.25 三种入口与单一决定权威

| 入口 | 权威 |
|---|---|
| 内建 Inspector 页面 | Runtime 验证并保存同一 HumanRequest 决定。 |
| 宿主页面、嵌入组件或飞书卡片 | 调用同一受控人工命令；仍为 Runtime 权威。 |
| 外部审批 / 工单系统 | 外部系统保存决定；Adapter 返回可核验结果和版本证据。 |

前两种可以同时展示同一请求，但只接受一次有效最终决定。第三种不能额外创建一份可与原决定互相覆盖的审批。

<a id="sec-13-26"></a>

### 13.26 飞书不是新的节点协议

飞书可作为通知渠道、人工入口、启动/查询流程的外部入口，或执行器内部会话渠道。通知投影与必需业务发消息节点要分开；普通通知失败不自动推翻业务成功，必需消息送达则需要自己的执行与验收语义。

接入由通用 Gateway 处理事件校验、身份映射、请求关联、入站持久去重、出站状态和格式转换。具体 SDK 及 API 版本本轮不重新选定，不将官方 SDK 的存在当成本项目已接通。

<a id="sec-13-27"></a>

### 13.27 消息与身份关联

持久关联租户/应用/会话或消息与 Run、Scope、Invocation、HumanRequest 及主题版本。群里有多个流程时不能用“最近一个 Agent”猜测目标。

操作身份来自可信通道与身份映射，不来自昵称、消息正文、卡片自报 actor 或未验证 userId。显示的动作仍由服务端检查权限。

回调必须在必要认证和持久接收后应答，不等待整条 Agent 推理结束。收到消息不等于命令生效，更不等于后续流程已推进。

<a id="sec-13-28"></a>

### 13.28 产物与入口可用性

飞书文件或外部页面上传结果必须转为已登记且授权的 ArtifactRef。向群聊发出文件可能改变可见范围，不能因为是通知就忽略产物权限。

入口未配置、通知未送达、等待用户和请求过期必须有不同说明。页面打开、消息已读、默认选项及超时均不能自动批准。

含人工节点的交付流程必须提供内建页面、嵌入页面或已验证的外部入口之一；缺少可用入口应在激活前报告。

<a id="sec-13-29"></a>

### 13.29 Agent 内部多轮对话

固定交互点优先拆成显式 Human 节点或有界子流程。外部 Agent 内部自由对话可由执行器管理，前提是能关联本次执行、持久等待并返回可观察状态。

需要 Multiverse 统一投递中途消息时，须先定义可选交互契约：交互 ID、所属执行、输入/结果 Schema、主体、期限和回执。当前 submit/observe 并不自动包含“向任意运行 Agent 追加消息”能力。

追加交互形成新事件或后续输入，不改写原冻结 ExecutionRequest。等待输入不赋予 Agent 自批权限。

---

<a id="s14"></a>

## 14. State、Artifact、Handoff、Context 与 Memory

<a id="sec-14-1"></a>

### 14.1 State

State 只记录可确认事实：流程路径、输入输出摘要、尝试、外部引用、审批、版本、定时器和控制意图。禁止将模型生成的“已完成”文字直接转换为事实。

节点输出一旦成功固定，不被后续节点覆盖。需要累积结果时通过显式输入映射或受限循环 feedback 构造下一份输出。

<a id="sec-14-2"></a>

### 14.2 Artifact

Artifact 元数据最少包含 `artifact_id`、namespace、所属运行/调用、name、media_type、size_bytes、digest、storage_ref、created_at、sensitivity、retention_policy、origin。

本地内容使用 SHA-256 标识；外部资源优先有内容摘要，否则必须有外部不可变版本，并标记 `verification=external_version_only`。可变 URL 不构成完整的可重现交付证据。

输出 JSON 只携带 ArtifactRef，不把大型文件或二进制写入 Graph Checkpoint。服务读取和下载必须检查 ACL，签名地址短期有效，不能把存储路径当公共下载链接。

文件系统存储先写临时对象并计算摘要，再原子归位；数据库事务只登记已经完成的对象。崩溃产生的未引用临时对象由垃圾回收清理，不能把部分文件登记为完成产物。

<a id="sec-14-3"></a>

### 14.3 Handoff

V0.1 的可读审计 Handoff 包含：`summary`、`completed`、`remaining`、`constraints`、`evidence_refs`、`artifact_refs`、`warnings`。其中 summary 为字符串，completed/remaining/constraints/warnings 为字符串数组，evidence_refs/artifact_refs 为有权限与版本的引用数组。它与交接身份、实际机器载荷及输入快照关联持久化。

标准模式以结构化 JSON、必要文本和 ArtifactRef 进行机器交接；latent 模式只替换选定 route 的机器工作上下文载荷，可读摘要与证据仍供人审阅。两种模式都保留业务输入输出、必需约束和授权事实，见第 14.6—14.12 节。

摘要是解释，不是事实替代物。下游可以读取必要产物，不能仅依据上游自然语言声称测试通过。

<a id="sec-14-4"></a>

### 14.4 Working Context

Context 由当前任务输入、允许读取的 State、授权 Artifact、固定 Prompt/Skill，以及所选通信模式的机器交接内容组装；可选 Memory 是独立能力。标准模式读取显式 Handoff；latent route 读取经校验的 latent 引用，不自动将同一路由的审计摘要作为隐藏的文本后备输入。组装结果保存摘要、引用、裁剪记录和策略版本；敏感正文按保留策略存储或脱敏。

必需业务输入、验收标准、明确约束和权限仍须显式提供，不得仅压入 latent 载荷。规范不承诺两种模式的模型输出或行为等价；禁止通过删掉必要约束来制造 latent 性能优势。实际仍映射给模型的上游文本必须计入 Context 快照和评测披露。

Prompt/Skill 引用必须解析到包内内容摘要或环境已验证版本，不能假装一个目录存在即已经加载。执行器不支持某种 Skill 格式时预检失败或显示明确的非必需降级。

<a id="sec-14-5"></a>

### 14.5 Semantic Memory

V0.1 默认关闭语义检索，仅定义 `put/search/get` Provider 接口及 provenance、namespace、权限、时间和来源引用字段。Memory 无权更新 State、审批或路由事实。

后续启用检索时，命中的记录 ID、版本和实际注入内容必须进入 Context 快照。嵌入向量、相似度和自动摘要均不能成为执行完成的依据。

Semantic Blackboard 与跨 Run 自学习仍为后续独立研究扩展。Latent Handoff 则按以下小节进入 V0.1 的可选实验能力；它不以开启 Semantic Memory、安装向量数据库或实现共享 Blackboard 为前置条件。


<a id="sec-14-6"></a>

### 14.6 通信模式：一个可选开关

唯一用户开关为 `BindingSet.spec.communication.latentHandoff.enabled`，boolean，默认 `false`。它是部署配置，不是 Workflow 业务拓扑的一部分。

| 开关 | 机器交接方式 | 保持不变的内容 |
|---|---|---|
| `false` | 标准结构化输入输出、必要文本 Handoff、ArtifactRef | 权威状态、调度、重试/核对、权限、审批、审计、验收 |
| `true` | 配置 routes 上使用已验证兼容的 latent 导出/导入；其他节点仍按标准契约工作 | 同左；额外记录实际载荷、配置版本和消费回执 |

“关闭”不要求 GPU、模型隐藏态接口、latent 插件、向量服务或 latent 专用凭据；不得加载这些依赖后才发现开关关闭。标准路径不承诺属于所有外部工具的统一行业实现，只表示本项目的默认可互操作契约。

“开启”不是尽力优化提示：配置的交接必须使用真实 latent 载荷。V0.1 **不提供自动回退开关**；未安装、模型不兼容、载荷不可用或接收端未消费时明确阻止相关执行或按确定失败处理，不静默改用摘要重跑。已有外部工作结果未知时进入核对，继续遵守第 11—12 章。

首次为一个部署配置 routes 和 profile；此后用户只需切换 enabled 并完成预检。更新开关创建新的 BindingRevision/Deployment，只作用于新 Run。活动 Run 和已有 Attempt 不允许热切换，包括暂停后继续。要用另一模式比较或重跑，创建新 Run，并记录来源；不复制人工批准。

<a id="sec-14-7"></a>

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

<a id="sec-14-8"></a>

### 14.8 CommunicationProfile 与兼容预检

CommunicationProfile 由环境管理员在注册表中安装并固定版本，不作为包导入时可执行的新资源。至少记录：profile ID/version/digest、导出和导入 Adapter/执行器版本、源与目标模型修订及相关权重/配置标识、表示格式、序列化版本、Codec/对齐版本（如有）、形状与精度约束、上下文位置/前缀绑定规则、资源上限、持久化方式，以及经过验证的兼容组合。

框架不规定所有模型使用同一种 latent 格式，不要求所有 profile 只能同模型；但每个允许组合必须逐项验证。不能只因为向量维度相同、模型名称相近或双方都能调用 HTTP，就判断兼容。首个实验后端至少锁定一组真实可运行的导出/导入组合，不声称支持任意闭源接口或跨模型转换。

开启前必须验证：插件可用；routes 有效；双方 Descriptor 声明相同 profile digest 的导出/导入；版本与配置匹配；数据访问与权限域允许；载荷存储和恢复方式满足本规范；资源上限足够。预检不借机执行付费模型推理或业务动作；真实端到端消费的验证结果来自单独授权的 LH-02 测试。

声明兼容而尚未完成真实验证时显示 unverified，并阻止激活 latent 部署。运行前再次检测版本漂移；历史兼容证明不能覆盖变更后的模型。标准模式不执行这些 latent 专属探测。

<a id="sec-14-9"></a>

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

<a id="sec-14-10"></a>

### 14.10 可读审计、显式边界与安全

两种模式都提供可读交接和证据。审阅卡至少显示：当前产物和版本、已确认完成项、尚未完成项、风险/不确定性、关联事件/产物、实际通信模式，以及 latent 模式下的 profile 和载荷摘要。审计摘要与同一 HandoffRecord 绑定，禁止显示另一轮或另一模式的旧摘要。

已观察到的状态、校验结论与审批来自权威记录；模型生成的原因、假设和建议标为解释。摘要是审计入口，不是对 latent 内部推理的完整或忠实解码保证。没有证据的解释不能升级为事实。人工 Request 的 subjectDigest 覆盖实际需要审阅的版本和相关交接证据；摘要或审批主题变更遵守第 13 章。

latent route 默认不把该 route 的自然语言审计摘要再交给目标作为备用上下文；必需业务输入、约束、权限和结构化输出始终显式。用户可以查看摘要，但实验报告必须披露其他实际注入的文本，不能宣称“纯 latent”而暗中发送完整原始上下文。

不要求每个内部 latent step 都生成摘要，只在交接边界和已有人工/风险边界生成。摘要生成失败时使用有来源的结构化事实模板；不得伪造模型解释。实际模型推理、存储、传输及摘要生成成本全部纳入测量。

latent 载荷按来源上下文的敏感级别和权限处理；人看不懂二进制不构成脱敏。不得绕过 namespace、授权与保留策略，也不得把潜在秘密通过载荷转交给更低权限执行器。首个实验后端只验证明确授权的同一数据访问域，不声称提供跨域自动净化。

使用限额、格式白名单及无可执行反序列化的载荷格式；禁止不可信 pickle 或任意安装/解码脚本。解压/解码后的大小和形状也必须受限。原始张量/KV 不放入 JSON 状态、LangGraph Checkpoint、SSE、普通日志或 OTel；这些位置只放受控引用、摘要和状态。

<a id="sec-14-11"></a>

### 14.11 实现模块与首个实验后端

建立 `communication/` 边界，包含标准 Handoff、模式解析、route 预检、HandoffRecord 与可选 profile 注册接口。推理库、模型权重和具体 Codec 位于可选插件或独立实验执行服务，不进入核心启动依赖。开关关闭时基础 Runtime、CLI、Inspector 和既有 Adapter 独立工作。

第一版必须交付至少一个真实的 latent 导出/导入适配示例及配套可选安装方式，锁定模型/Codec/推理环境版本。可以复用成熟研究实现，但本规范不将任何未核验的研究仓库、模型或假定包名标为已支持；实现时将实际选型、许可证、依赖锁和通过的 profile 记录到注册表及测试报告。

不能只把若干模型角色封装成一个黑盒执行器，就宣称框架级开关已完成。该黑盒可以作为底层实现，但 LH-02 必须证明至少一条规范 route 在两个逻辑调用之间完成真实 latent 交接，并可在同一 Workflow/同组已兼容执行器下关闭为标准交接进行对照。

<a id="sec-14-12"></a>

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

<a id="sec-14-13"></a>

### 14.13 “不变”的准确含义

同一契约版本的字段含义不能漂移。Schema、Prompt、Policy、Binding 或实现版本改变时，按本规范创建对应的新版本与部署，重新进行必要验证；活动 Run 不热替换。

新增字段并非天然兼容，尤其存在 `additionalProperties: false`、必填字段或含义变化时。不得凭“只是多了一个字段”省略兼容性检查。

<a id="sec-14-14"></a>

### 14.14 每次调用固定实际材料

必须保存实际输入、Context 的摘要与引用、所用 Schema/Prompt/Skill/Binding 版本、权限主题和关联产物。幂等请求指纹覆盖业务 input 与实际 Context，不能只比较表面任务文本。

必要约束、动作权限、验收条件、产物版本与明确依赖必须显式传递；不能靠语义检索碰巧命中，也不能仅压入 latent。

<a id="sec-14-15"></a>

### 14.15 结构化数据与大产物分离

可直接校验的小型业务值使用 JSON；文件、图像、视频、报告、模型载荷等大内容使用 ArtifactRef。可变 URL 和本地文件路径不能直接冒充可重现产物。

Artifact 需要真实可访问对象、版本或摘要及权限。审计摘要是解释，不取代产物本身，也不证明独立测试已经运行。

<a id="sec-14-16"></a>

### 14.16 权威事实与投影分离

State、运行台账和不可采样的关键事件继续负责运行正确性；Checkpoint 保存后端推进进度，Inspector、缓存、Trace、检索索引和可读摘要不获得状态写入权。

如后续引入 Memory，仍遵守 State/Memory/Context 分离。它与本次 latent 开关独立，不是前置依赖。

<a id="sec-14-17"></a>

### 14.17 受管、交付与标准库中的通信约束

受管 Agent 不自动具有 latent 能力；Connector、外部平台或本地模型的适用组合必须通过同一 profile 验证。标准库、模板和人工表单不以 latent 或向量检索为依赖。

Runnable Bundle 可以携带配置和依赖要求，不默认导出开发 Run 的敏感载荷。目标环境重新检查版本和权限。循环新 Scope 不复用上一轮 KV；跨 Scope/多源隐式融合仍不支持。第 29 章描述模板与路由的组合限制。

---

<a id="s15"></a>

## 15. 运行事件、Trace 与可解释性

<a id="sec-15-1"></a>

### 15.1 必须持久化的事件

事件类型至少覆盖：包导入/部署/停用、Run 创建和控制、节点激活、Attempt 创建、外部提交确认、等待、取消请求、外部终态观察、输出校验、分支选择、并行分支创建/汇合、循环轮次、审批决定、结果核对、运行终结和安全拒绝。通信相关事件另含 `communication.mode_resolved`、`handoff.prepared`、`handoff.consumed`、`handoff.rejected`；内容只包含版本化引用、摘要、证据来源与原因，不包含原始 latent 载荷。

运行事件字段：`event_id`、namespace、run/scope/invocation/attempt 引用、`seq`、`type`、`occurred_at`、`recorded_at`、actor、causation_id、correlation_id、payload、payload_schema_version。seq 在同一 Run 内严格递增；外部时钟仅作说明，记录顺序使用 seq。

状态快照返回 `last_event_seq`。前端从该位置继续订阅；断线重连不需要猜测漏掉哪些事件。

<a id="sec-15-2"></a>

### 15.2 观测等级

`boundary` 至少能展示提交、等待、结果、版本、公开错误、外部引用和交付物；`internal` 可以进一步展示工具调用、模型调用和资源使用。不能观察到的内部操作应显示“执行器未提供”，不能显示“未发生”。

OTel 映射：Run 对应 trace 或根关联；NodeInvocation/Attempt 对应 span；工具/模型调用为可选子 span；异步与嵌套关系可用 link。敏感数据按 Policy 脱敏后导出。[E5]

长时间运行不要求把全部历史放进一个永不结束的内存 span。允许分段 span 并通过稳定运行身份关联。无 Trace 后端时，基础事件和 Inspector 仍必须完整工作。

<a id="sec-15-3"></a>

### 15.3 错误解释模型

UI/API 的失败说明必须分别提供：

`reason_code`（机器判断）、`summary`（给人的一句话原因）、`evidence_refs`（日志/事件/输出/外部引用）、`next_actions`（当前身份可申请的操作）、`uncertainty`（已知/待确认）、`retry_safety`（安全/不安全/未知）。

禁止只显示“Failed”“Error occurred”或一段没有关联实体的堆栈。底层异常不得直接泄露凭据、完整请求头或敏感目录。

<a id="sec-15-4"></a>

### 15.4 一个 Run 的权威与多处查看

Workflow 定义来自版本化包；运行事实来自实际承载该 Run 的 Runtime；底层执行事实来自执行宿主或外部平台的观察。界面、通知、缓存与 Trace 是投影。

关键事件、状态变化与必要 Outbox 按本规范同事务持久化。按 Run 序列与游标恢复，不依赖外部时间排序、不依赖浏览器保持连接。

<a id="sec-15-5"></a>

### 15.5 三种信息不能合并

分别展示：连接是否在线、执行处于何种状态、最近确认发生在什么时候。离线不等于失败，在线不等于任务正常，未上报成本不等于零成本。

原始外部观察保留来源与 revision。旧事件不回退状态，相互冲突的终态触发完整性问题而非静默改写。

<a id="sec-15-6"></a>

### 15.6 三层循环与尝试

| 层级 | 负责方 | 需要显示 |
|---|---|---|
| Workflow 业务循环 | Runtime 的 repeat / 子 Scope。 | 第几轮、输入反馈、每轮结果、继续/结束原因、轮数上限。 |
| Node Attempt | Runtime 或明确的执行器 retryOwner。 | 第几次尝试、原因、输入主题、真实执行引用和安全性。 |
| Agent 内部工作循环 | 受管 Agent 或外部执行器。 | 实际阶段、工具/模型调用、内部步数、阶段产物、等待。 |

禁止把它们统一成一个“重试次数”。repeat 沿用本规范有限轮数和新 Scope 规则；历史轮次不得覆盖。

<a id="sec-15-7"></a>

### 15.7 基础与增强观测

基础 boundary 接入至少显示提交、等待、版本、错误、外部引用、产物与结果。internal 接入可以显示真实步骤、工具调用和资源使用。

内建真实 Agent 应提供相应内部事件；外部未暴露内部过程时明确显示“执行器未提供”。不得用模型生成的推理说明冒充日志或声称揭示不可见的内部计算。

可见的内部步骤不自动获得独立重跑、暂停或调度能力。需要独立门禁和恢复的阶段应建成 Workflow 节点。

<a id="sec-15-8"></a>

### 15.8 事件接入的语义要求

内部事件应能关联所属 Run/Scope/Invocation/Attempt、父子步骤、发生与记录时间、事件身份、结果引用和可观测来源。字段名、顺序协议及事件 Schema 尚待冻结，不通过 OTel 私有对象定义公共协议。

事件及日志需限额、分页、脱敏和截断标记。控制事件不能采样；详细遥测可按策略裁剪。缺失或中断的详细 Trace 不得让控制面丢失运行状态。

<a id="sec-15-9"></a>

### 15.9 审计摘要

摘要与同一次交接、产物版本、载荷摘要关联。已验证状态与模型解释分开展示；摘要失败可用有来源的事实模板，不伪造内部原因。

---

<a id="s16"></a>

## 16. Workflow Package、Preset 与部署生命周期

<a id="sec-16-1"></a>

### 16.1 包的最小结构

```text
content-delivery/
├── manifest.yaml
├── workflows/
│   └── delivery.yaml
├── schemas/
│   ├── request.json
│   ├── deliverable.json
│   ├── verification.json
│   ├── review-input.json
│   └── review-output.json
├── prompts/                 # 可选、纯内容
├── skills/                  # 可选、带格式和版本描述
├── policies/                # 可选、声明式策略
├── evals/
│   ├── cases.jsonl
│   └── suite.yaml
└── bindings.example.yaml    # 仅占位示例，不含真实环境配置
```

Preset 是同一个包中若干可运行入口、配置说明和评测材料的组合，不引入另一套运行引擎或独立生命周期。

<a id="sec-16-2"></a>

### 16.2 WorkflowPackage.spec

必填 `workflows`、`entrypoints`、`requiredFeatures`；可选 `assets`、`evalSuites`、`extensions`。

- workflows：workflow_id → 包内定义相对路径。
- entrypoints：可供用户直接运行的 workflow_id 数组，至少一个。
- requiredFeatures：显式功能 ID，如 `core.call`、`core.switch`、`core.human`、`core.parallel`、`core.repeat`、`core.nested`。
- assets：资源 ID → `{path, kind, format, version}`；kind 为 prompt/skill/policy。
- evalSuites：相对路径数组。

所有依赖的子 Workflow 必须随包一起存在；V0.1 不在执行时从公共注册表动态下载依赖。外部能力通过 Binding，不作为可执行源码自动安装。

<a id="sec-16-3"></a>

### 16.3 内容摘要与可重现构建

单文件 digest 为实际字节的 SHA-256。构建生成按 UTF-8 路径顺序排列的文件清单，每项为 `{path, size, sha256}`；对清单使用 JCS 规范化 JSON，再计算 package_digest。[E9]

`package.lock.json` 保存清单与根摘要，但不参与自身的根摘要；签名/归档文件也不参与。打包只包含清单内文件，不包含 `.git`、本地 Binding、凭据、缓存和构建输出。检查解包后实际文件与清单完全一致。

同名同 version 但不同 digest 的包默认拒绝发布。编辑内容必须递增包版本。JSON/YAML 注释变化可能改变包字节摘要，这是有意保留来源差异；语义 Diff 可以另外说明“运行语义未变”。

<a id="sec-16-4"></a>

### 16.4 安装与部署分离

```text
导入归档 → 安全检查 → Schema/文件校验 → 注册不可变 PackageVersion
                                              ↓
                 选择 Binding → 预检 → 创建 Deployment → 激活
                                              ↓
                               指定入口与输入 → 创建 Run
```

导入包不等于部署成功；部署激活不等于第三方服务永远可用。预检报告保留检查时点和有效期。

Deployment 的内容不可变，但可 active/inactive。停用阻止新 Run，不杀掉已有 Run。要停止既有执行必须明确提交取消命令。

<a id="sec-16-5"></a>

### 16.5 更新与回滚

发布更新创建新 Deployment。旧 Run 继续使用旧解析计划和 Adapter/执行器版本要求；版本漂移导致无法安全调用时阻塞并说明，不偷偷跟随注册表的最新版本。

回滚表示将后续入口指向一个旧 Deployment，不撤销已经发生的代码修改、消息发送、文件写入或外部动作。V0.1 不提供隐式业务补偿。

<a id="sec-16-6"></a>

### 16.6 外部平台嵌入的安装体验

任意宿主可以通过同一 API 实现“导入包—绑定执行能力—预检—激活—运行”。它不需要开放数据库，也不需要改成 Python。

Python 可以使用薄 SDK 调用相同 Application Commands；Go、Java、Node 等通过 HTTP Client、Sidecar 或 Service 接入。V0.1 不承诺这些语言都有进程内原生 Runtime。

一套共享服务默认承载多个 Deployment。只有明确的隔离或资源策略需要时，才使用独立实例；不是“一份工作流一套平台”。

<a id="sec-16-7"></a>

### 16.7 两种交付形态

| 形态 | 目标环境 | 内容与目的 |
|---|---|---|
| Workflow Package | 已有兼容 Multiverse Runtime。 | 流程、Schema、Prompt/Policy/Eval、依赖描述与 Binding 示例。 |
| Runnable Bundle | 没有现成 Runtime，或需要固定运行组合。 | Workflow Package，加必要运行组件/锁定执行资产、部署模板、宿主接入材料与可选 UI。 |

两者执行语义一致，不是两种工作流引擎。Runnable Bundle 是部署输出形态，不自动新增第四种顶层 Workflow 资源。

<a id="sec-16-8"></a>

### 16.8 可移植业务模块

整套流程对外暴露入口、输入、输出、错误、人工交互、运行控制和产物访问。宿主不需要知道内部有几个 Agent，也不应复制内部状态机。

若将交付流程作为更大流程的一个节点，默认由其 Runtime 按原协议执行，外层通过异步任务契约观察。不能让两个 Runtime 同时成为同一个 Run 的权威。

<a id="sec-16-9"></a>

### 16.9 必须交付的材料

| 材料 | 必须说明什么 |
|---|---|
| Workflow 与业务 Schema | 所有入口、节点和最终输出的契约。 |
| 执行资产与模板 | 受管 Agent 配置、程序实现/不可变引用、必要工具及初始化规则。 |
| 依赖与兼容性清单 | Runtime、Adapter、模型、程序、系统/存储等所需版本与环境。 |
| Binding 模板 | 目标模型、资源、身份、工作区和外部服务需要填什么。 |
| 宿主接入材料 | 启动、查询、订阅、控制、人工结果、产物与错误处理。 |
| 交互资产 | 必需人工入口和可选运行查看组件。 |
| 验证维护材料 | 预检、授权试运行、支持矩阵、升级/备份/卸载说明。 |

<a id="sec-16-10"></a>

### 16.10 轻量包与执行资产分层

本规范当前资产类型只定义了 prompt/skill/policy 等，不得直接塞入未定义的 executable kind。可移植 Agent 模板和程序依赖须在扩展清单/交付层先明确设计，再同步 Schema。

大模型、容器镜像或系统依赖可以单独资源包分发；离线交付要求它们在目标环境可用，不要求全部装入一个轻量归档。沿用主包文件摘要和锁定原则，不直接套用其小体积上限去声称已经支持大模型包。

<a id="sec-16-11"></a>

### 16.11 不导出的内容

默认不包含真实密钥、个人授权、机器私有路径、生产数据、在线 Session、活动 Run、Checkpoint 或运行中的 latent 载荷。开发资料确实作为可交付资源时，需要明确纳入清单与权限审阅，不通过隐含目录带走。

一个源环境 executorRef 不能作为交付能力的唯一凭证。需提供可安装实现/模板，或明确要求目标环境绑定等价能力。

<a id="sec-16-12"></a>

### 16.12 即插即用定义

> 在声明支持的环境中，一次完成宿主接入后，新流程通过安装、配置、授权和验证使用，无需修改宿主核心代码或 Multiverse 核心代码。

不表示无条件绕过依赖、模型、硬件、授权和网络配置；也不表示任意第三方引擎可原生解释 Multiverse Workflow。

<a id="sec-16-13"></a>

### 16.13 依赖归类

每项依赖必须明确属于：随交付物提供、由目标环境提供、明确保留的外部依赖或尚未解决。每项应有身份/版本或摘要、用途、目标绑定方式与验证结论。

激活前不允许存在未解决的必需依赖；“有一个在线地址”“开发机器已安装”“原平台数据库有记录”不等于目标可用。

<a id="sec-16-14"></a>

### 16.14 完整性检查

检查流程与子 Workflow、Schema 引用、Prompt/Skill、Agent/程序实现、Adapter、模型资源、UI 静态资源、身份映射、存储、人工入口与外部连接。

不可移植路径、原站点 URL、只能在源环境解析的 ID、未打包脚本及隐含 Session 都必须报告。明确的外部依赖可以保留，但不能把它们包装成完全独立或离线能力。

<a id="sec-16-15"></a>

### 16.15 安装步骤

```text
导入交付物
    ↓
检查内容、版本、依赖和兼容性
    ↓
显示缺失资源与权限要求
    ↓
绑定目标环境身份、模型、工作区、存储和外部能力
    ↓
由受信任工具准备运行组件和批准的执行资产
    ↓
检查后生成不可变、尚未对普通入口激活的 Deployment
    ↓
基于固定快照进行就绪检查与经授权的试运行
    ↓
验证报告满足门禁后激活业务入口
```

导入不是部署，容器/进程启动不是业务就绪，预检不执行业务写入或付费推理。必须单独授权试运行，不能用检查之名访问生产资源。未激活部署只能通过明确的评测/预检身份执行受控验证；普通 POST /runs 不得绕过激活门禁。测试必须固定同一包、Binding 与权限，变更后重新验证。具体安装命令在第 0.5 节 G-14 冻结。

<a id="sec-16-16"></a>

### 16.16 安装与重复执行

重复安装相同内容应可识别并返回既有结果或明确冲突；同版本不同内容不得静默覆盖。精确安装幂等 API 和包签验格式未在讨论中冻结，见 第 0.5 节。

安装失败应保留可解释检查结果，不留下对用户显示为可用的半部署。修复依赖后重新检查，不自动篡改包中的验收标准。

<a id="sec-16-17"></a>

### 16.17 首个部署形式

按此前建议，第一版默认服务式 / Sidecar 交付，并提供部署模板；可采用 Compose 等成熟载体，不自造通用部署系统。此处只是实施方向，文件格式、模板和支持环境必须在实现中锁定并测试。

目标已有兼容 Runtime 时复用它，不要求每安装一个流程都启动一整套新平台。需要隔离时才使用独立实例。

<a id="sec-16-18"></a>

### 16.18 两档嵌入界面

业务层可仅显示开始处理、进度、待办和结果下载；需要排错时打开完整图、节点详情、时间线和证据。

完整 Multiverse 后台不是强制嵌入项。人工流程至少提供一个真实可用入口；开始/停止可以由宿主按钮触发，但必须调用同一命令层。

<a id="sec-16-19"></a>

### 16.19 目标环境独立性

运行模型和 UI 能力可以来自 Multiverse，而界面位置在目标平台中。不能把“在 Multiverse 查看”解释成强制返回原开发站点。

目标日志、产物、数据和审批留在目标环境。需要跨环境查询时单独授权、记录来源，不形成第二个调度权威。

<a id="sec-16-20"></a>

### 16.20 升级与回滚

新包、新执行配置或通信模式创建新部署；旧 Run 沿用原版本。保留原依赖或明确阻塞，不能悄悄迁移不兼容 Checkpoint 或 Session。

回滚切换后续入口，不撤销已发生的外部操作。数据库与执行后端迁移必须经过恢复测试，不将产品版本回退等同于所有状态自动兼容。

<a id="sec-16-21"></a>

### 16.21 停用与卸载

先禁止新 Run，再处理活动执行与等待；之后按授权策略卸载业务资产。共享 Runtime、模型、执行宿主和工作区不能随单个流程被删除。

历史产物和审计按保留策略处理；运行未结束或结果未知时不删除恢复关联。卸载动作、影响与保留结果需要可见。

<a id="sec-16-22"></a>

### 16.22 备份与恢复

备份覆盖运行台账、后端 Checkpoint、包与执行资产、Artifact 和必要接入映射。凭据按各自安全机制管理，不进入普通交付包。

恢复先核对活动执行。备份恢复不是将同一 Run 复制成两个并发权威；跨环境活动迁移需独立设计，不随“一键交付”提供。

---

<a id="s17"></a>

## 17. Runtime HTTP API

<a id="sec-17-1"></a>

### 17.1 基本约定

API 前缀 `/api/v1/namespaces/{namespace}`。除健康检查与首次本地认证交换外，均要求授权。所有公开时间为 RFC 3339 UTC；所有身份使用 opaque 字符串，客户端不得解析其内部含义。

所有产生状态变化的 POST 必须带 `Idempotency-Key`。需要乐观并发控制的操作还必须带 `expectedVersion`。返回 `request_id` 便于关联，不向浏览器暴露内部数据库 ID 以外的敏感信息。

命令接收返回 202 与 CommandReceipt；仅在已完成纯本地事务时可返回 200/201。202 只代表已持久接收，不代表执行成功。

<a id="sec-17-2"></a>

### 17.2 首版端点

| 方法与相对路径 | 请求概要 | 返回 / 语义 |
|---|---|---|
| `POST /packages:import` | multipart 归档文件 | 导入回执与 package digest；不运行安装脚本 |
| `GET /packages` | cursor、limit | 已授权可见包 |
| `GET /packages/{digest}` | — | 包清单、入口和验证结果 |
| `GET /packages/{digest}/workflows/{id}` | — | 定义及中立 Graph 表示 |
| `POST /bindings:validate` | BindingSet、packageDigest | 匹配/权限/可达性报告 |
| `POST /deployments` | packageDigest、BindingSet、policyRef | 不可变部署与预检报告，默认 inactive |
| `POST /deployments/{id}:activate` | expectedVersion、reportDigest | 复核权限与预检时效，激活 |
| `POST /deployments/{id}:deactivate` | expectedVersion、reason | 仅禁止新 Run |
| `GET /deployments` | cursor、limit | 部署列表 |
| `GET /deployments/{id}` | — | 部署内容、状态和报告 |
| `POST /runs` | deploymentId、workflowId、input、externalRefs? | 持久 Run/命令引用 |
| `GET /runs` | status、deploymentId、cursor、limit | 按 namespace 过滤 |
| `GET /runs/{id}` | — | 状态、控制意图、版本、问题摘要、lastEventSeq、通信开关和本次实际使用计数 |
| `GET /runs/{id}/graph` | scopeId? | 规范图与运行投影，不返回 React Flow 私有模型 |
| `GET /runs/{id}/invocations` | scopeId?、cursor | 调用与 Attempt 摘要 |
| `GET /invocations/{id}` | — | 输入、输出、Attempt、原因、证据与允许动作；关联 HandoffRecord、实际模式及消费证据摘要 |
| `GET /runs/{id}/events` | after、limit | 可分页事件 |
| `GET /runs/{id}/stream` | after / Last-Event-ID | SSE；只读投影 |
| `POST /runs/{id}:pause` | expectedVersion、reason | 暂停新派发 |
| `POST /runs/{id}:resume` | expectedVersion、reason | 仅恢复已暂停调度 |
| `POST /runs/{id}:cancel` | expectedVersion、reason | 持久取消意图 |
| `POST /runs/{id}:rerun` | input?、deploymentId?、reason | 创建新 Run；默认复制原输入/部署，不拷贝审批 |
| `GET /human-requests` | status、cursor | 当前身份可见请求 |
| `GET /human-requests/{id}` | — | 主题、证据、截止时间、版本、允许决定 |
| `POST /human-requests/{id}/decisions` | decision、comment?、expectedVersion、subjectDigest | 原子决策回执 |
| `POST /attempts/{id}:reconcile` | conclusion、evidenceRefs、output?、expectedVersion、reason | 受限核对，不是任意状态 PATCH |
| `GET /artifacts/{id}` | — | 授权元数据 |
| `GET /artifacts/{id}/content` | — | 受限下载/流式内容 |
| `POST /eval-runs` | deploymentId、suite、baselineRef? | 新评测任务 |
| `GET /eval-runs/{id}` | — | 状态、样本和比较报告 |
| `GET /commands/{id}` | — | 命令处理回执 |

执行器注册以管理员配置/CLI 管理为首版实现，不必先开发完整管理 CRUD 页面。已注册对象必须可通过预检报告定位。

<a id="sec-17-3"></a>

### 17.3 错误封装

```json
{
  "error": {
    "code": "STATE_CONFLICT",
    "message": "请求对象的版本已变化，请重新读取后提交。",
    "retryable": false,
    "details": {
      "resourceId": "opaque-id",
      "expectedVersion": 3,
      "actualVersion": 4
    },
    "evidenceRefs": [],
    "nextActions": ["refresh"]
  },
  "requestId": "opaque-request-id"
}
```

稳定错误码至少包括：`INVALID_SPEC`、`UNSUPPORTED_FEATURE`、`DATA_REFERENCE_MISSING`、`SCHEMA_VALIDATION_FAILED`、`BINDING_UNRESOLVED`、`CAPABILITY_MISMATCH`、`DEPENDENCY_UNAVAILABLE`、`SECURITY_REQUIREMENT_UNSUPPORTED`、`PERMISSION_DENIED`、`STATE_CONFLICT`、`IDEMPOTENCY_CONFLICT`、`ALREADY_TERMINAL`、`APPROVAL_EXPIRED`、`APPROVAL_SUBJECT_CHANGED`、`EXECUTION_UNKNOWN`、`EXECUTOR_PROTOCOL_VIOLATION`、`DEADLINE_EXCEEDED`、`LOOP_LIMIT_EXCEEDED`、`BUDGET_EXCEEDED`、`BACKEND_RECOVERY_REQUIRED`、`LATENT_HANDOFF_UNSUPPORTED`、`LATENT_PROFILE_MISMATCH`、`LATENT_PAYLOAD_UNAVAILABLE`、`LATENT_PAYLOAD_INVALID`、`LATENT_NOT_CONSUMED`。

HTTP 映射：语法/参数 400、未认证 401、无权限 403、资源不可见 404、状态或幂等冲突 409、合法结构但语义不成立 422、限流 429、暂时服务不可用 503。未知副作用必须在错误语义中显式表达，不能让 SDK 将任意 503 自动转为新业务提交。

<a id="sec-17-4"></a>

### 17.4 SSE 与重连

每个 SSE 事件使用对应 Run 的 seq 作为 event ID，并包含 event type 和 JSON payload。服务端先回放 after 之后的保留事件，再连续输出，避免“先读再订阅”的空隙。SDK 按 seq 去重并处理乱序。

游标过期返回 `CURSOR_EXPIRED` 与最新快照位置；客户端重新读取快照再继续。无权限或 token 失效立即停止流。

带 Bearer Token 的 UI 使用支持认证头的 fetch 流式客户端，不把 token 放在 URL、日志或浏览器持久存储中。以同源 BFF 接入时可使用其受保护的会话方案，但仍必须执行服务端授权。

<a id="sec-17-5"></a>

### 17.5 两个不同方向的契约

**Executor Adapter Contract：**Multiverse 怎样调用一个执行者。

**Host Integration Contract：**另一个平台怎样使用交付的完整流程。

宿主接入复用既有 Application Commands / Runtime API，不重新发明第二套状态与审批接口。下列契约是对已有能力的宿主视角整理。

<a id="sec-17-6"></a>

### 17.6 角色与权威

开发环境负责创建、验证和打包。目标环境中的 Runtime 负责当地执行、状态、等待、产物和审计。目标内部平台提供业务入口、用户身份和资源绑定。

原开发环境关闭、断网或被删除后，交付实例仍应工作。原环境不默认遥控目标运行，也不接收敏感数据；集中运维需要另行授权。

<a id="sec-17-7"></a>

### 17.7 宿主最小操作

以下路径沿用本规范 API 前缀 `/api/v1/namespaces/{namespace}`，是既有契约引用，不表示所有端点已经实现。

| 宿主动作 | 既有方法与相对路径 | 语义 |
|---|---|---|
| 创建运行 | `POST /runs` | deploymentId、workflowId、input、可选 externalRefs；取得持久 Run/回执。 |
| 查运行 / 节点 | `GET /runs/{id}`、`GET /runs/{id}/invocations`、`GET /invocations/{id}` | 读取当前事实、版本、原因和允许动作。 |
| 查图与事件 | `GET /runs/{id}/graph`、`GET /runs/{id}/events`、`GET /runs/{id}/stream` | 规范图、分页事件和可恢复订阅。 |
| 控制 | `POST /runs/{id}:pause`、`:resume`、`:cancel`、`:rerun` | 按既有身份、版本和控制语义执行。 |
| 人工待办 | `GET /human-requests`、`GET /human-requests/{id}` | 当前主体可见请求。 |
| 人工结果 | `POST /human-requests/{id}/decisions` | 结构化结果、expectedVersion、subjectDigest 和幂等键。 |
| 产物 | `GET /artifacts/{id}`、`GET /artifacts/{id}/content` | 授权元数据和下载；上传/登记沿用待补接口。 |
| 命令回执 | `GET /commands/{id}` | 检查持久接收与实际处理结果。 |

所有修改命令遵守本规范的 Idempotency-Key 与必要 expectedVersion。回调不能成为唯一恢复通道；宿主随时可按 Run 引用查询。

<a id="sec-17-8"></a>

### 17.8 异步业务能力

启动后返回持久引用，不要求宿主保持一个 HTTP 请求直到整个流程完成。可关联宿主业务任务号，但不能把宿主重新打开页面或重试查询当作新启动。

人拒绝、验收失败、依赖阻塞与技术失败分别反映。宿主不自行判断“HTTP 200 就已完成”，而读取 Runtime 的真实结果。

<a id="sec-17-9"></a>

### 17.9 身份与权限

宿主可以保留自己的登录体系，经受信任后端完成主体映射和受限授权。浏览器不持有通用管理员凭据，任意 userId 不构成可信身份。

相同一套宿主身份、客户端和 UI 承载可以供多个交付流程复用。新增业务流程仍需明确相应资源范围与真人处理主体。

<a id="sec-17-10"></a>

### 17.10 嵌入形态

默认：目标环境部署 Runtime 服务或 Sidecar，宿主通过 HTTP 使用；需要界面则嵌入 UI SDK 或受控独立页。Python Embedded 保留，但必须显式管理存储、Worker 和执行生命周期。

不要求 Go/Java/Node 把 Python 引擎加载进同一进程。也不承诺第三方工作流引擎能够直接读取 JSON 执行；原生跨引擎解释需要额外 backend 与一致性验证，不属于简单交付。

---

<a id="s18"></a>

## 18. CLI 与无界面工作流

以下是需要实现的 CLI 契约，不表示已有可安装的公开命令。所有命令支持 `--json` 供其他程序和 AI 工具消费；错误输出到 stderr，机器结果到 stdout。

```bash
# 检查定义、引用、Schema 与控制流；不调用业务执行器
mverse validate ./presets/content-delivery

# 确定性构建；不包含本地真实 Binding
mverse package build ./presets/content-delivery --out ./dist/content-delivery.mverse.tgz

# 启动本地模式：SQLite、受限本地身份、单进程
mverse dev --data-dir ./.multiverse

# 导入、预检、创建部署；绑定配置可以包含本环境资源引用
mverse package import ./dist/content-delivery.mverse.tgz
mverse binding validate --package <digest> --file ./bindings/local.yaml
mverse deploy --package <digest> --binding ./bindings/local.yaml --activate

# 一次运行与状态观察
mverse run --deployment <id> --workflow delivery --input ./request.json --wait
mverse inspect <run-id>
mverse events <run-id> --follow

# 经权限与版本校验的控制
mverse pause <run-id> --reason "暂停后续派发"
mverse resume <run-id> --reason "继续"
mverse cancel <run-id> --reason "用户终止"
mverse decide <request-id> --choice approve --subject-digest <digest>

# 不修改旧 Run 的重跑与评测
mverse rerun <run-id> --reason "新的验收尝试"
mverse eval --deployment <id> --suite evals/suite.yaml --baseline <report-id>

# 服务部署进程入口
mverse db migrate
mverse serve --host 0.0.0.0 --port 8080
mverse worker
```

需要 expectedVersion 的 CLI 命令先读取当前版本和对象主题，再提交；若读取后对象变化，显示冲突，不自动无限刷新后覆盖。人工审批必须展示主题与产物摘要后提交，`--json` 模式也不能绕过权限。

Latent 开关沿用 Binding 文件和 `mverse binding validate` / `mverse deploy`，不增加绕过部署预检的 Run 热切换参数。修改 enabled 后创建新部署，再使用原 `mverse run`；相同 Workflow 包无需改写。`mverse inspect --json` 必须返回 requested 模式、计划 routes、实际消费次数和未使用原因。

退出码：0=操作成功或等待后 Run 成功；1=运行确定失败；2=参数/Spec 无效；3=权限或状态冲突；4=需要人工/结果核对且命令选择不继续等待；5=网络/服务暂不可用。`--wait` 不因断开终端而取消 Run。

---

<a id="s19"></a>

## 19. Inspector 与可嵌入 UI SDK

<a id="sec-19-1"></a>

### 19.1 第一屏必须回答的问题

Run Detail 首屏必须同时显示：本次目标、当前状态、正在等待什么或卡在哪里、原因和证据入口、当前身份可执行的下一步、已完成交付物、运行所用版本。

Graph 是解释这些信息的手段，不是要求用户逐个点完才能知道流程失败原因的入口。状态不能只靠颜色，必须有文字和图标；waiting、blocked、paused、stopping 必须有不同说明。

<a id="sec-19-2"></a>

### 19.2 首版页面

保留 Packages、Deployments、Runs、Human Inbox、Evals 五类核心页面职责，并提供紧凑的“执行能力”入口。Workflow Graph 与版本信息放在包/部署详情，Graph、Timeline、State、Artifact、Trace 放在 Run Detail 内。

高级 Graph Diff、复杂仪表盘、Memory 浏览器不阻塞首版。最低版本比较必须展示包摘要、Binding/权限变化、文本 Diff 与 Eval 变化；不能把“未测”显示成“没有退步”。

<a id="sec-19-3"></a>

### 19.3 必须交付的组件

`WorkflowCanvas`、`RunSummary`、`NodeInspector`、`RunTimeline`、`ArtifactList`、`HumanRequestPanel`、`EvalSummary`。HandoffCard 可以作为 NodeInspector 的子组件，不需要另建一级页面。

UI SDK 接收框架领域模型、data client 和 action callbacks。它不自行创建账号、不决定权限、不强制宿主路由、不依赖唯一 QueryClient、不向 window 注册不可控全局状态。

React、ReactDOM 使用 peerDependency；首版明确验证 React 19。非 React 宿主可以使用独立 Inspector、iframe 隔离部署或 HTTP 自建界面，不要求迁移前端框架。iframe 必须配置明确来源与认证边界，不传递长期 token 到 URL。

<a id="sec-19-4"></a>

### 19.4 图与布局规则

Graph DTO 使用 `nodes`、`edges`、`groups` 与稳定 domain IDs，不直接返回 React Flow 的内部持久对象。前端映射后展示。

ELK 在 Web Worker 中计算布局，结果按 package digest、scope 和布局版本缓存。运行状态变化不重新排列节点；用户选中、缩放、平移后不被增量事件强制重置。

默认折叠嵌套 Workflow；展开后保留父子路径。循环显示定义和当前轮次，而不是无限复制整张图。并行显示各分支状态与等待汇合条件。

节点卡片必须区分定义、invocation 与 attempt。点击失败的第三次尝试，不能只显示第一次日志。Artifact 边只表示明确的数据引用，不推断隐式共享文件。

<a id="sec-19-5"></a>

### 19.5 视觉与交互要求

独立 Inspector 默认浅色中性背景、单一强调色、明确文字层级。宿主可覆盖主题 tokens。禁止向宿主注入全局 CSS reset；Tailwind utilities 与组件变量使用限定作用域，弹层挂载容器可配置。

每个页面实现 loading、empty、partial、stale、error、unauthorized 状态。控制命令显示“已请求/待确认”，直到事实状态变化；不能点击取消就立即将流程涂成已停止。

危险操作需要展示影响范围。审批显示产物版本和证据；subject 已变化时阻止旧表单提交。Trace/日志必须虚拟化和分页，不能一次加载全部 Token 历史。

部署创建/克隆界面提供一个 `Latent Handoff（实验）` 开关，默认关闭；先展示配置的 routes 与兼容性，再允许激活。没有可用插件/profile 时显示不可用原因，不保留一个看似可生效的空开关。切换生成新 BindingRevision/Deployment，不修改活动 Run。

Run 和节点详情必须区分“请求开启”“已规划覆盖”“载荷已准备”“接收端已确认消费”“本次未经过 route”，并展示 profile 版本、来源与目标调用、载荷摘要、审计摘要和证据。禁止仅凭 enabled=true 为所有节点标上 latent；原始张量默认不展示，下载需单独检查 Artifact 读取权限。

<a id="sec-19-6"></a>

### 19.6 SDK 数据接口

最小接口定义：`getRun`、`getGraph`、`listInvocations`、`getInvocation`、`listEvents`、`subscribeRun`、`listArtifacts`、`getHumanRequest`、`submitCommand`。

接口使用 AbortSignal/取消订阅；组件卸载后清理流。UI 必须显示服务端允许的 action，并在操作时仍接受服务端重新校验。服务端返回的业务值不能直接作为 HTML 插入。

<a id="sec-19-7"></a>

### 19.7 主查看位置

流程在实际 Runtime 的控制台中统一可见。可以使用独立 Inspector，也可以把相同组件嵌入目标平台。不能为了了解整体进展，强迫用户逐一访问多个外部平台。

不改“Graph 是投影”的原则；文件与 API 仍是主要创作入口。控制台必须能运行、处理人工和异常，不只是静态日志查看器。

<a id="sec-19-8"></a>

### 19.8 页面信息架构

保留 Packages、Deployments、Runs、Human Inbox、Evals 的原有职责。根据此前补充，建议增加一个紧凑的“执行能力”入口，集中管理受管配置、外部连接、远程接入端与支持性检查；具体导航名称待 UI 定稿，不建设完整组织或设备管理产品。

<a id="sec-19-9"></a>

### 19.9 点击规则

| 操作 | 行为 |
|---|---|
| 单击普通节点 | 选中，右侧显示该节点或调用的摘要。 |
| 双击 / 显式“查看详情” | 打开完整节点详情。 |
| 双击子 Workflow | 进入内部图，保留父级路径导航。 |
| 切换轮次 / Attempt | 显示选定历史身份的数据，不默认错用最新结果。 |
| 键盘或触屏入口 | 提供等价的可聚焦按钮或明确操作，不依赖双击。 |

需要避免节点双击与画布双击缩放同时触发。自动布局不随状态变化重新排列；选中节点、视角和打开详情不因事件刷新被重置。

<a id="sec-19-10"></a>

### 19.10 定义视图与运行视图

未选定 Run 时显示定义、契约、逻辑 slot 与可选部署信息，不显示假实时状态。进入某个 Run 后显示其冻结版本、实际执行者与具体 Invocation/Attempt。

节点卡片建议显示标题、执行类别、状态、所在循环、最近活动及信息新鲜度。执行位置与管理归属分别表达；不能只靠颜色区分。

<a id="sec-19-11"></a>

### 19.11 统一详情结构

| 区域 | 必需内容 |
|---|---|
| 概览与操作 | 当前状态、原因、等待事项、观察时间、允许动作及风险。 |
| 输入与输出 | 冻结输入、Schema、输出校验、产物与版本。 |
| 执行过程 | Attempt、业务轮次、内部步骤、时间线、日志与外部状态。 |
| 执行环境 | 受管/外部、实际位置、执行配置修订、工作区和依赖。 |
| 审计与证据 | Artifact、Handoff、真人决定、模式及来源；解释与事实区分。 |

人工调用在详情中提供实际表单或操作入口。外部执行器至少显示已确认的边界事实；缺失内部轨迹不应空白冒充“没有内部操作”。

<a id="sec-19-12"></a>

### 19.12 外部原生页面

可提供“打开外部执行记录”“查看外部工作区”“前往外部人工入口”。链接来自受信任连接和对象映射，调用前检查权限；不默认嵌入不可信 HTML，不将模型返回的任意 URL 当管理入口，不传长期凭据到 URL。

外部链接是补充，不能成为节点唯一详情。受限日志或产物无法读取时应说明权限，而不是由前端绕过。

<a id="sec-19-13"></a>

### 19.13 嵌入一致性

继续复用 WorkflowCanvas、RunSummary、NodeInspector、RunTimeline、ArtifactList、HumanRequestPanel 等领域组件，客户端与组件不决定权限、不强制宿主路由或账号、不注入全局样式。

只嵌入业务摘要也必须保留更深的授权排错入口；完整 Inspector 非强制。样式、认证、资源路径与订阅释放在宿主环境测试。

---

<a id="s20"></a>

## 20. Evaluation 与 AI 编辑闭环

<a id="sec-20-1"></a>

### 20.1 首版 Eval 数据模型

Dataset 是版本化 JSONL；每行包含 case_id、input、expected（可选）、tags（可选）。Suite 声明 workflow、dataset、evaluators、gate。Evaluator 通过已注册 ID 调用可信实现，禁止执行数据集内任意源码。

EvalRun 固定 package/binding/deployment、dataset digest、evaluator version、重复次数、种子（适用时）、预算、开始时间和运行环境；同时固定通信开关、routes/profile/模型/Codec 版本及实际 Context 策略。每个样本产生独立 Run 及结果，失败与超时也必须计入，不删除不利样本。

<a id="sec-20-2"></a>

### 20.2 第一版 Evaluator

必须提供输出 Schema 检查、必需 Artifact 检查、结构化字段断言和运行成功率汇总。可增加可信业务校验程序。LLM Judge 保留接口，不作为唯一发布门槛。

最低指标：case pass、workflow status、latency、attempt count、unknown count、人工决定耗时、已知成本、成本覆盖率。无费用来源时 cost=null，coverage 标记 unavailable。

读取某份测试报告不能被标记为独立执行测试；Evaluator 必须声明证据来源和是否实际执行验证。

<a id="sec-20-3"></a>

### 20.3 基线与门禁

发布比较必须使用同一数据集版本、明确的预算和次数。报告同时列出通过、失败、未知、跳过和样本数；小样本不宣称统计显著或普遍优越。

门禁是显式规则，例如 `requiredPassRate=1.0`、`maxUnknown=0`、`allowMissingCost=true`。质量门禁失败不允许把包自动升级为生产默认入口。

评测默认使用沙箱/只读 Binding。带写入副作用的生产评测必须单独授权，不得因为命令名叫 eval 就绕过 Policy。

Latent 对照使用同一 Workflow 包、同一数据集、相同输入输出和验收、同组可支持两种模式的执行器及模型配置，主要只改变通信开关。不可避免的模型/Prompt/Codec 差异必须披露，不能将所有收益归因于 latent。记录任务质量、端到端耗时、文本 Token、latent 大小/步数、存储/传输量、峰值内存、摘要生成与全部可计量费用，以及失败/核对/人工处理成本。未知指标保持 null，不把 latent 步数直接等同于免费 Token。

实际消费次数为零的 Run 不计入“已执行 latent”的效果样本；预检失败、缺载荷、消费失败与模式未使用必须在覆盖/失败报告中保留，禁止筛掉后只展示成功样本。协议验收不要求 latent 必然优于标准模式，结果应如实报告。

<a id="sec-20-4"></a>

### 20.4 AI 编辑的最小支持

V0.1 不内置自主优化 Agent。提供可解析文件、validate、eval、diff 和结构化诊断，让外部 AI 工具编辑。

变更路径固定为：创建新包版本 → Validate → 预检 → Eval → Diff → 人工发布决定。Diff 必须标出执行器能力、权限、依赖、流程结构和验收门槛的变化，不能只显示 Prompt 文本。

AI 提案没有修改活动 Run 的权力。自动 Merge、自动发布和自主扩权均不属于首版。

<a id="sec-20-5"></a>

### 20.5 产品入口

**Agent 是框架的第一开发者，外部 Agent 编写是首要创建和修改路径；图形界面的人类编辑是辅助路径。**

主开发接口为版本化文件、Schema、能力发现、CLI/API、结构化诊断与可验证变更。图形界面主要用于理解、审阅、人工处理与辅助编辑，保存时仍经过同一编译和版本检查。效率与准确性要求见第 30.1—30.3 节。

用户能够表达自然语言目标，外部 Agent 随后完成：

```text
读取需求、约束与验收目标
          ↓
读取本规范、Schema、样例和可见能力
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

<a id="sec-20-6"></a>

### 20.6 作者与执行者分离

编写流程的 Agent 不必注册为流程中的 Executor，不必占用一个 `call` 节点，也不必具备 latent 导入/导出能力。它是在创建与修改声明，而不是替 Runtime 推进活动流程。

同一个 Agent 产品可以分别承担作者与执行者角色，但两者的身份、授权、输入和审计应分别确定。拥有编写权限不自动获得执行权限、人工审批权限或部署激活权限。

<a id="sec-20-7"></a>

### 20.7 工作流是小型软件包，不限于一个大 JSON

**沿用本规范第 6、16 章：**流程主体使用 JSON/YAML；完整交付物还包含业务 Schema、必要的 Prompt/Skill/Policy、测试材料和 Binding 示例。

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

<a id="sec-20-8"></a>

### 20.8 边界

作者不得直接写运行数据库、伪造外部执行引用或审批事实、修改活动 Run、自动合并发布、扩大权限。实际部署仍按本规范走 Package、Binding、预检、Eval、Diff 和有权主体的发布决定。

缺少执行器、凭据或人工入口时，应明确报告缺口；可生成未部署的包和待绑定清单，但不得声称已经可运行。

<a id="sec-20-9"></a>

### 20.9 必须交付的材料

**追加要求：**提供一套与安装版本匹配、可离线读取的 Authoring Kit。它是规范的导航与操作材料，不是独立规则源。

| 材料 | 最低内容 |
|---|---|
| 简明编写指南 | 文件组织、节点契约、数据引用、常见流程、命令顺序、错误处理、发布边界。 |
| 协议与业务 Schema 示例 | 顶层资源、ValueExpr、Predicate、输入输出、人工请求结果、通信开关。 |
| 模板与最小包 | 标准交付、人工补充输入、人工产物提交、固定程序校验、外部服务调用。 |
| 正例与反例 | 合法输入、缺字段、非法引用、未绑定能力、错误人工输出、失效审批、无效 latent 路由。 |
| 能力发现材料 | 当前版本支持什么、当前授权范围能使用什么、哪些尚未验证。 |
| 机器可读操作结果 | Validate、预检、Eval、Diff 和状态查询的结构化结果。 |

可使用 `AUTHORING_GUIDE.md` 作为指南文件名；该名称是建议，不新增运行协议。指南中的每个行为指向本规范的明确章节。

<a id="sec-20-10"></a>

### 20.10 能力发现

作者需要能够读取当前授权范围内的能力目录，至少获得：协议/功能版本、支持的节点与控制流子集、执行器 ID 与 Descriptor、输入输出契约、能力要求、人工入口支持情况、取消/幂等/查询保证，以及实验环境中已验证的通信 Profile。

必须区分以下状态：已声明、已安装、当前可用、已验证。它们不能互相代替。

能力目录不得包含 Secret 明文，不得因“给 Agent 看文档”泄露其他 namespace 的对象。读取目录不是授权，历史可见也不能覆盖授权撤销。离线快照可用于编写，但部署时必须重新检查。

标准模式的能力发现不应为了展示普通执行器，加载模型权重、访问 latent 凭据或探测 latent 推理服务。实验能力可由已登记的元数据说明；真实可用性在明确选择实验部署后检查。

本规范已有 ExecutorDescriptor 与注册表基础；面向作者的统一目录读取方式属于本次需要补齐的接口能力，具体端点和命令见 第 0.5 节 的缺口登记。

<a id="sec-20-11"></a>

### 20.11 不得猜测环境

没有查到某个 `executorRef` 时不能编造一个 ID 后宣称可运行；声明了某个 Capability 也不等于它已经实现。未知必需字段、未知必需功能和不支持的配置必须报错，而不是忽略。

作者不能将一个任意 Python 文件写入包后，就假设它会成为可信内建程序。程序接入遵守 第 9.7 节 的注册与 Wrapper 边界。

<a id="sec-20-12"></a>

### 20.12 结构化诊断

**沿用并落实本规范第 6.5、17.3、18 章：**诊断必须能定位文件、JSON Pointer、严重程度和稳定错误码，并给出可理解的期望、实际问题及建议操作。

建议外部 Agent 的修复流程只修改与问题相关的文件；诊断需能反查原始定义，不只暴露编译生成的内部节点名称。

CLI 的机器结果与运行日志分开，遵守本规范 stdout/stderr 约定；`--json` 输出中不能混入进度动画或无结构日志。不得另造一个与 API 状态不同的“CLI 成功”含义。

诊断的字段布局应随对应 Schema 固定；本规范不把说明性字段清单冒充已经发布的响应 Schema。

<a id="sec-20-13"></a>

### 20.13 先契约，后流程实现

作者应先明确最终交付、必需证据和验收，再划分节点。每个可调用节点明确输入、输出、能力、副作用和失败路径；之后才选择具体执行器与环境 Binding。

不得为了适配某个样例而要求修改核心 Runtime，除非确实需要新的通用功能，并明确提交规范与测试变更。业务专有字段优先留在业务 Schema 中。

<a id="sec-20-14"></a>

### 20.14 必须区分的验证层次

| 层次 | 能确认的内容 | 不能据此宣称 |
|---|---|---|
| 静态 Validate | 语法、文件、引用、Schema 形状、控制流、已能判定的映射问题 | 外部服务真实可用、业务质量合格。 |
| Binding 预检 | 注册能力、权限、依赖、资源与契约匹配情况 | 预检未执行的业务或模型推理已经成功。 |
| Fixture / Mock 测试 | 确定性分支、契约、错误与状态处理 | 真 Agent 效果、真实 latent 消费、真实人工身份。 |
| 授权真实执行 | 实际 Adapter 和输入—执行—产物链路 | 所有样本、全部环境普遍可靠。 |
| Eval 与发布审阅 | 固定数据集、明确验收与变更影响 | 未测组合自动兼容、所有未知成本为零。 |

任何计划预览或模拟都必须标明是否调用执行器。不得让名为 validate、preview 或 test 的操作暗中触发写入副作用。

<a id="sec-20-15"></a>

### 20.15 修复规则

作者可依据诊断迭代修复，但必须保留用户目标和验收基线。禁止通过删除必填字段、放宽门禁、跳过人工、伪造 Artifact、删除失败样本或改写测试期望，制造通过结果。

确实需要调整业务契约或验收时，应作为显式变更提交 Diff，说明原因及影响，而不是伪装为无语义变化的格式修正。

人工节点在自动测试中可用明确的测试身份与 fixture 驱动；测试批准不是生产批准，不得复制到正式 Run。

<a id="sec-20-16"></a>

### 20.16 输出给人的交付说明

外部 Agent 完成编写后至少提供：包版本与修改文件、流程与契约说明、绑定缺口、权限和副作用变化、人工如何操作、测试层次与结果、标准/latent 模式及其验证状态、部署前仍需完成的事项。

用户不应被要求阅读整个配置包才能知道“这套流程做什么、会改动什么、哪里需要人、目前是否真的能运行”。

<a id="sec-20-17"></a>

### 20.17 现有命令与新增接口分开

本规范已定义的 `mverse validate`、`package build/import`、`binding validate`、`deploy`、`run`、`inspect`、`events`、`eval`、`decide` 可作为实现目标使用；它们不是本文声称已安装可运行的工具。

能力目录、模板生成、任意结构化人工结果文件提交和产物上传的完整命令尚需补齐。不可在指南中加入未实现参数，然后把失败归因于用户配置。

---

<a id="s21"></a>

## 21. 部署、运维与资源边界

<a id="sec-21-1"></a>

### 21.1 两个受支持的运行档位

| 档位 | 组成 | 保证和限制 |
|---|---|---|
| `local` | 一个本地进程、SQLite、文件 Artifact、内建 Inspector 可选 | 单用户/可信开发；持久文件恢复；不提供集群与不可信代码隔离 |
| `service` | API 进程、单活 Worker、PostgreSQL、Artifact volume、反向代理可选 | 多身份隔离、持久命令和等待；执行器须满足部署声明的恢复要求 |

Sidecar 是 service 或 local 档位的一种放置方式，不产生第三套执行语义。Python Embedded 必须显式提供存储、调度生命周期与身份上下文；随请求创建临时 Runtime 然后丢弃不属于持久模式。

<a id="sec-21-2"></a>

### 21.2 服务配置

需要提供 `DATABASE_URL`、`ARTIFACT_ROOT`、`AUTH_CONFIG_REF`、`EXECUTOR_REGISTRY_REF`、`PUBLIC_BASE_PATH`、`LOG_LEVEL`。可选 `OTEL_EXPORTER_OTLP_ENDPOINT`、`SECRET_PROVIDER_CONFIG_REF`、`LATENT_PROFILE_REGISTRY_REF`。后者仅在安装并启用实验能力的环境需要；标准启动不加载模型权重或 latent 推理库。敏感值通过环境注入/挂载机密配置，不提交仓库。

启动顺序：迁移检查 → 数据库迁移任务 → API readiness → Worker 取得单活锁 → 扫描未完成工作。迁移失败时禁止启动调度。

健康检查区分 `/health/live`、`/health/ready` 和 Worker heartbeat。ready 检查数据库、迁移版本、Artifact 存储；外部执行器不可达不必令整个 API 下线，但必须阻止对应的新调用并展示局部不可用。

<a id="sec-21-3"></a>

### 21.3 默认资源限制

以下是首版必须可配置并可测试的保护阈值，不是已测得的性能能力：

| 项目 | 默认限制 |
|---|---|
| 单个声明文件 | 1 MiB |
| 单包压缩归档 / 解压总量 | 32 MiB / 128 MiB |
| 包内文件数量 | 2,000 |
| 单 Workflow 静态节点 | 200 |
| 最大嵌套深度 | 8 |
| 单 parallel 分支数 | 16 |
| 单 repeat 最大轮次 | 20 |
| 顶层 Run 累计 invocation 数 | 2,000，含嵌套与循环 |
| 调用并发 | 每 Run 默认 4；单 Worker 外部调用默认 32 |
| 单输入 / 输出 JSON | 1 MiB，超出内容应转 Artifact |
| 单 Artifact | 256 MiB，超大文件使用明确配置的外部存储 |
| Latent 载荷 | 默认同 Artifact 上限；profile 必须声明解码后大小、形状及内存上限，超过环境限额拒绝而不隐式截断 |
| 单调用 stdout/stderr 保留 | 各 10 MiB，超出标记截断，不影响事实状态 |
| 默认 Run 总截止时间 / 环境上限 | 7 天 / 30 天 |
| 取消确认宽限 | 30 秒；超出后进入核对，不伪造停止 |
| 正常观察轮询 / 失败后最大退避 | 2 秒 / 30 秒 |
| 控制事件与命令回执保留 | 至少关联 Run 保留期；默认终态后 90 天 |

并发预算按未终结的真实外部执行计数，包括外部排队；纯控制节点和空闲 HumanRequest 不占外部执行槽位。parallel 的 maxConcurrency 则限制未终结的子分支数量，等待中的分支仍占自己的分支名额，不能将两个计数混用。

限制达到时返回具体 code 和范围。不得因为日志截断而删除运行事实；不得因为遥测服务缓慢阻塞业务状态提交。

<a id="sec-21-4"></a>

### 21.4 成本与预算

Run 可以设置 maxAttempts、maxInvocations、deadline 和可计量的费用预算。未知费用不能用 0 代替。硬费用上限只有在执行器支持可靠的预算实施/预留时才能保证；否则只能做已知消耗的软限制，预检报告必须区分。

并行派发前需要原子检查本地并发/调用额度。外部服务真正计费若滞后，不能宣传严格费用封顶。

<a id="sec-21-5"></a>

### 21.5 备份与保留

备份必须覆盖应用数据库、LangGraph Checkpoint、包内容及 Artifact；开启 latent 的环境还需覆盖活动交接载荷和对应不可变 profile/Codec 版本引用。不能将易失 GPU 缓存当作唯一恢复依据。恢复后先进入只读核对模式，检查活动外部执行，不能不加判断地重新派发。

不得自动删除活动 Run 的回执、输出、审批或恢复关联。删除/归档终态数据时保留说明性 tombstone，避免历史引用看似从未存在。Secret 明文从始至终不进入备份。

<a id="sec-21-6"></a>

### 21.6 支持性声明

首版正式验收以 Linux 服务部署和项目声明的本地环境为准。其他操作系统、数据库版本、存储后端和执行器必须分别列出 verified/unverified 状态，不把“Python 理论上能运行”当成已经验证。

<a id="sec-21-7"></a>

### 21.7 两个承诺分别验收

| 档位 | 允许的依赖 | 必须具备 |
|---|---|---|
| 独立运行 | 不依赖第三方 Agent / 工作流平台；可显式选用远程模型 API。 | Runtime、受管执行、人类入口、存储、产物、查看与控制完整闭环。 |
| 完全本地 / 离线运行 | 安装和资源准备完成后，不依赖外部在线服务。 | 本地模型、程序依赖、资料、前端资源、身份和所需运行组件已准备齐。 |

“0 外部依赖”不等于零系统依赖、零模型文件或零硬件要求。必须在交付说明中写清安装前准备与运行期依赖。

<a id="sec-21-8"></a>

### 21.8 离线验收

至少使用真实本地模型完成两份不同 Agent 配置、一个程序节点和一个人工节点的协作，并产出真实文件。验证时禁止外网访问，不能偷偷调用云模型、下载前端资源或依赖原开发平台。

在线搜索、飞书等依赖网络的功能不得在离线档位显示为可用。模型的具体格式、推理后端、工具调用支持、硬件组合及分发条件须按 第 0.5 节 选择和验证，不由本规范推测支持。

<a id="sec-21-9"></a>

### 21.9 创建与启动

模板、文件编辑、Schema 和本地 validate 必须足以创建流程；不要求必须先连接外部编写 Agent。可以提供受限作者模板，但它与其他受管 Agent 服从相同权限。

离线运行所需依赖不能仅写一个在线下载 URL。可通过单独资源包交付大模型与镜像，不要求放入轻量 Workflow 归档。

<a id="sec-21-10"></a>

### 21.10 标准与实验发行

默认标准发行不加载 latent 插件、推理专属依赖或向量服务。普通内建 Agent 不因“由 Multiverse 管理”自动具有 latent 能力。实验环境显式安装并验证相应组合后才开启。

<a id="sec-21-11"></a>

### 21.11 v1 发行 profile 与平台范围

`schemas/deployment-profile.schema.json` 定义目标部署声明，不是当前 Runtime 已实现的启动配置或自动授权。三个 profile 复用同一事实权威：personal 对应 local，SQLite、单用户、单活本地调度，isolation须显式选择trusted-local或enforced（不可信任务必须enforced）；team 对应 service，PostgreSQL 17、同组织多主体/namespace、单活调度；offline 使用 SQLite 单用户单活 topology，真实本地模型/程序/人工与完整资源闭包，运行期禁止外网。offline 不是 Mock 档位，也不自动证明实验 latent 支持。

v1 必需平台基线为 Linux x86_64 服务与实际沙箱，Linux x86_64 和 macOS arm64 本地 Connector，Python 3.12/3.13。Windows 原生、敌对租户共享宿主、多活图调度不进入 v1 承诺。远程 Connector、飞书、原生 CLI 后端和 latent 按需安装；每项真实验收仍是项目发布必需项。原生 CLI 支持区间必须以固定实际版本逐项测试，不跟随 latest。

保留 §5.1 Node.js 24、pnpm、浏览器实测与锁文件目标。当前 npm/package-lock、Node 20.20.2、Python 3.14.7 是开发验证事实，不自动满足目标。目标平台的精确 patch、浏览器构建号、CLI 区间、产物 digest 和运行证据须在支持矩阵补齐并经过 W25；缺精确版本/硬件/真实证据的单元保持 pending/blocked，不得写 supported。平台范围不因当前无机器而自动缩减。

<a id="sec-21-12"></a>

### 21.12 v1 稳定性基准

team 基准为 4vCPU、8GiB 内存、SSD 与独立受控执行端，冻结数据库/网络/模型位置、版本和数据量。保留 100 静态节点、20 等待 Run、10,000 分页事件的基础负载：首屏可交互≤2秒，已提交控制事件至本地 UI 可见≤1秒；报告冷启动/稳态、P50/P95/P99、内存/FD/进程/磁盘、队列年龄和错误率。100 活动 Run/20 外部执行任务/200 SSE 订阅为额外容量目标，未达到不宣传该容量，也不降低基础要求。

先运行6小时预检，再持续72小时 soak，混合提交、等待、决定、取消、重连和完成；确定性执行器控制成本，另有真实模型链抽样。非注入合成控制面成功率≥99.9%；计划故障单列且不能隐藏失败。注入 Worker/Bridge/Connector 崩溃、网络分区、数据库中断、令牌撤销、磁盘压力与积压，要求零未经授权推进、零未知写入盲目重发、零已确认控制事实丢失。停止/缩时不算通过，影响主要不变量或资源泄漏的修复须重启完整72小时。

备份恢复 RPO 为最近一次确认备份，目标 RTO≤30分钟；未确认外部动作不能为达标而强行推进。负载中演练排空、升级、备份和恢复，记录数据量与实际耗时。模型等待和人工等待分开统计，不能伪装 Runtime 延迟；模型费用另设预算。

---

<a id="s22"></a>

## 22. 持久数据模型与事务要求

<a id="sec-22-1"></a>

### 22.1 最小表族

| 表族 | 关键内容 | 关键约束 |
|---|---|---|
| `packages` / `package_files` | 包身份、清单、内容地址 | digest 唯一；同 namespace/name/version 不覆盖不同内容 |
| `binding_revisions` | 脱敏配置、Descriptor 快照、摘要 | 不可变 revision |
| `deployments` | 包、Binding、Policy、执行计划、active 状态 | 内容不可变；乐观版本控制 |
| `runs` | 输入引用、status、control_mode、deadline、version、冻结通信计划和实际使用计数 | namespace 过滤；终态单调 |
| `scopes` | 父 invocation、workflow、分支/轮次 | 父引用 + 激活路径唯一 |
| `invocations` | node、scope、状态、输入输出、错误 | scope + node_id 唯一 |
| `attempts` | invocation、attempt_no、dispatch/effect key、外部引用 | invocation + attempt_no 唯一；dispatch_key 唯一 |
| `decisions` | switch 选择、循环判断、计划中的控制决定 | transition_key 唯一 |
| `human_requests` / `human_decisions` | 主题、版本、截止时间、授权决定 | 每请求最多一个最终决定 |
| `artifacts` / `artifact_links` | 内容、版本、敏感级别和关联 | 内容存储完成后才登记可读 |
| `handoffs` / `handoff_receipts` | mode、route、profile/载荷/审计摘要、源/目标调用、逐 Attempt 消费证据 | source_attempt + target_invocation + route_id 唯一；handoff + target_attempt 回执幂等；源记录不可变 |
| `run_events` | seq、type、actor、payload | run_id + seq 唯一 |
| `command_receipts` | Idempotency-Key、请求摘要、结果 | namespace + subject + operation + key 唯一 |
| `inbox` | 认证后的外部观察 | executor + external_id + revision 去重 |
| `outbox` / `waits` | 待发送意图、等待、定时器 | 语义 action key 唯一 |
| `eval_runs` / `eval_cases` | 数据集、版本、结果和门禁 | 样本不因失败而被移除 |
| 后端 Checkpoint 表 | LangGraph saver 的存储 | 由 backend 模块管理，非公共查询 API |

scope + node_id 唯一依赖第 7 章的同级无环约束；循环创建子 scope，不复用同一 scope 中的节点调用。

<a id="sec-22-2"></a>

### 22.2 必须原子提交的组合

Run 创建 + 命令回执 + 初始事件 + 唤醒；Attempt 创建 + 输入快照 + submit outbox；外部终态记录 + 输出校验结论 + 节点事件 + 下游唤醒；人工决定 + 版本推进 + 事件 + 唤醒；控制意图 + 命令回执 + 取消/暂停派生意图；源输出完成 + 必需 Handoff 登记 + 下游唤醒；目标输入快照/交接引用 + submit outbox；消费回执核对 + 对应结果/节点事件。

输出校验如果依赖大型 Artifact，可先验证并保存验证报告，再在事务中检查相关摘要没有变化。禁止在数据库长事务中执行模型调用或等待人工。

<a id="sec-22-3"></a>

### 22.3 查询与并发

所有查询经 namespace 和资源级权限过滤，不允许“先查全量再在浏览器隐藏”。列表必须游标分页，默认 50、最大 200。事件与大日志使用独立分页，不塞进 Run 列表。

状态更新使用 expected version 或行级锁；外部事件处理、用户取消和 Worker 推进发生竞争时必须有确定的提交顺序。不依赖前端刷新速度保证一致性。

<a id="sec-22-4"></a>

### 22.4 受管、接入、组件与交付记录

在既有表族上增补执行配置/安装资产修订、受管执行与工作区关联、Connector 身份/执行映射/待回传观察、内部步骤/工具调用关联、通道消息/HumanRequest 映射、组件描述/展开来源、Bundle 依赖/目标安装记录。

表名和 DDL 随对应 G 项冻结；相同语义优先复用 attempts/inbox/outbox/events/artifacts/receipts，不建设第二套竞争台账。namespace、外部来源和关联键必须纳入唯一性与授权检查。远端本地 journal 与中心数据库不假定存在分布式事务。

---

<a id="s23"></a>

## 23. 仓库、模块与开发约束

<a id="sec-23-1"></a>

### 23.1 初始 Monorepo

```text
multiverse-workflow/
├── MULTIVERSE_SPEC.md
├── pyproject.toml
├── uv.lock
├── package.json
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
├── apps/
│   └── inspector/                  # 独立 Web 壳
├── src/multiverse_workflow/
│   ├── protocol/                   # 资源模型、Schema、ValueExpr
│   ├── compiler/                   # 验证与规范化计划
│   ├── application/                # 同一命令/查询入口
│   ├── runtime/                    # 台账、状态、等待、控制
│   ├── backends/langgraph/         # 唯一第三方图执行适配
│   ├── binding/                    # 注册表、预检、解析
│   ├── adapters/                   # builtin/process/http_job/human
│   ├── communication/              # 标准交接、模式解析、route/profile 接口与台账
│   ├── policy/                     # 身份、授权、动作范围
│   ├── storage/                    # 应用事务与 Repository
│   ├── artifacts/
│   ├── packaging/
│   ├── evaluation/
│   ├── observability/
│   ├── api/
│   └── cli/
├── packages/
│   ├── protocol-ts/                # 从协议生成的类型
│   ├── client/                     # HTTP/SSE TypeScript Client
│   └── ui/                         # 领域组件，不拥有宿主应用
├── schemas/                        # 可执行 JSON Schema，与本文同步
├── migrations/
├── presets/
│   ├── content-delivery/
│   └── data-quality/
├── examples/
│   ├── bindings/
│   ├── http-executor/
│   ├── embedded-ui/
│   └── latent-handoff/             # 可选实验执行器、模型/profile 锁定与两模式演示
├── tests/
│   ├── protocol/
│   ├── conformance/
│   ├── integration/
│   ├── fault_injection/
│   ├── communication/             # 标准模式无额外依赖、真实 latent 与消费负例
│   └── e2e/
├── deploy/
├── docs/adr/
├── THIRD_PARTY_NOTICES.md
└── REFERENCES.md
```

初期一个核心 Python distribution 足够；目录划分表示依赖边界，不要求发布十几个独立包。latent 模型适配通过可选依赖组、独立插件包或远程实验服务安装，禁止核心 import 链强制引入推理依赖。UI、Client 可以独立构建，避免将 Python 运行时强加给前端集成方。

<a id="sec-23-2"></a>

### 23.2 模块依赖方向

protocol 不依赖 API/Runtime/backend；compiler 只依赖 protocol 与注册能力接口；runtime 依赖自己的 backend/adapter 接口；LangGraph 实现依赖 runtime 接口，而不是让 protocol 导入 LangGraph。

API、CLI、Python SDK 使用同一 application 层。任何直接写业务表绕过 application 命令的实现都不得合并。

<a id="sec-23-3"></a>

### 23.3 工程质量门槛

Python 启用类型检查和格式/静态检查；TypeScript 使用 strict。公共接口必须包含类型、错误语义和至少一个成功/失败测试。Schema 与客户端类型通过 CI 校验一致。

每个行为测试引用本文 requirement 或 acceptance ID。禁止将 Mock 链路、真实 Adapter 链路和真实业务验收混成一个绿色“全部通过”。测试报告必须区分三者。

<a id="sec-23-4"></a>

### 23.4 参考代码与许可证

React Flow、LangGraph、Langflow、Sim、Langfuse、Temporal 等可以作为依赖或设计参考，但不整体 Fork 其平台成为永久核心。复制源码前记录来源文件、commit、许可证、修改内容和对应 NOTICE。

ELK.js 当前许可证为 EPL-2.0；Langfuse 的部分企业目录采用独立许可，不能笼统视为全部同一许可。[E10][E11] 实际发版必须按锁定依赖与复制文件检查，本文不替代对具体分发物的许可核查。

自有代码的开源许可不在本次用户要求中预设为已授权；正式公开发布前由权利人确认。该发布事项不阻止内部开发，不得擅自为原有或第三方代码改变许可。

<a id="sec-23-5"></a>

### 23.5 模块安排建议

以下是工程职责建议，不是要求固定文件路径或发布多个软件包：

| 模块 | 职责 |
|---|---|
| protocol / schemas | 既有 Workflow 契约与经批准扩展；独立于后端和 UI 库。 |
| application / policy | API、CLI、宿主与通道共用的受控命令入口。 |
| binding / registry | Adapter、执行配置、资源与支持性解析。 |
| runtime / backend | 持久台账、流程推进、等待、控制和恢复。 |
| execution-host | 受管 Agent、程序、工作区、工具步骤与取消。 |
| connector | 远程配对、任务领取、观察回传与本地持久关联。 |
| integrations / channels | 外部平台映射、飞书等交互与通知；不控制图语义。 |
| artifacts | 文件提交、版本、授权与传输。 |
| delivery / packaging | 依赖完整性、Workflow Package、Runnable Bundle 与目标安装。 |
| inspector / ui / client | 统一详情、操作、宿主嵌入与机器客户端。 |

可先采用单一后端发行产物和独立 UI 包；不因模块划分增加必需基础服务。

<a id="sec-23-6"></a>

### 23.6 需要持久化的新信息族

执行配置修订与有效版本；Agent/程序安装资产；受管执行引用与工作区关联；Connector 身份及任务关联；未回传观察；内部步骤及工具结果关联；通道消息与 HumanRequest 映射；交付物依赖和目标安装记录。

这是语义清单，不是本次冻结的数据库 DDL。尽量复用本规范的 runs、scopes、invocations、attempts、inbox/outbox、events、artifacts 和命令回执，避免两套业务台账。

涉及派发、人工决定、产物登记和推进的事务必须明确责任；不能假设远程台账与 Runtime 数据库存在分布式原子提交。

<a id="sec-23-7"></a>

### 23.7 依赖方向

协议不导入具体 Agent、模型 SDK、React Flow 或外部平台类型。Execution Host / Adapter 实现依赖公共接口，UI 通过 DTO 显示事实。

不通过 CLI 直接写 Ledger 绕过 Application Commands；不让通道回调自行推进 Graph；不让交付安装器执行包内任意源码。

<a id="sec-23-8"></a>

### 23.8 工程证据

公共新增能力必须附 Schema/类型、成功与失败测试、权限检查、恢复说明和支持矩阵。Mock、真实执行、真人操作与生产安全验证分开记录。

历史仓库审阅中的版本冻结、人工原子推进、完整幂等指纹、支持性门禁和注册式执行问题作为回归主题；本规范不声称它们在最新仓库中仍存在或已修复。

---

<a id="s24"></a>

## 24. 实施阶段、职责与进入条件

<a id="sec-24-1"></a>

### 24.1 唯一实施路线

阶段表示进入条件与证据依赖，不假定团队人数，不承诺工期。可以并行制作 UI 原型和 Adapter 模板，但真实副作用不能绕过已经固定的权限/幂等/恢复边界。

| 阶段 | 交付与进入条件 | 完成证据 | 历史阶段映射 |
|---|---|---|---|
| M0 契约/工程/注册 | 三种资源、Schema、六原语形状、标准通信、组件描述、原语/模板 source map、G-01—G-04 最小冻结；锁依赖和基础构建 | 诊断可定位；未知特性拒绝；不执行业务 | P0、D0 |
| M1 持久执行骨架 | 同一 application 命令、业务台账、后端适配、fixture builtin、人类请求、提交身份 | 决定和推进意图原子；版本固定；纯本地纵向路径 | P1 基础、D0 |
| M2 恢复/权限/控制 | inbox/outbox、查询核对、超时、暂停/取消、幂等、故障注入与输出错误落库 | 响应丢失/重启/重复审批不重复业务；未知先核对 | P2 |
| M3 真实受管执行 | G-03—G-05、真实 Agent/程序、Execution Host、工作区、Artifact、内部事件 | 真实模型/程序/真人交付，非固定字符串 | D1、P1 真实部分 |
| M4 通用组合/标准库/控制台 | workflow/parallel/repeat，任意受支持参与者组合；人工表单、双击详情、运行命令与测试 | 第二种人数/领域无需改 Runtime；三层轮次清楚；真实事件驱动 UI | P4 组合、P3 UI、D2、D4 作者部分 |
| M5 外部与远程接入 | HTTP Job/Bridge、Connector 配对/传输、通道、受控上传及对应 G 项 | 同平台换 Agent 只配置；断线核对原执行；渠道决定唯一 | P1 HTTP、D3、D4 通道 |
| M6 完整交付/嵌入/离线 | Package/Bundle、依赖闭合、目标安装、宿主客户端/可选 UI、离线资源与 G-13—G-16 | 干净目标环境运行，原站点断开；声明的离线流程禁外网真实运行 | P3 交付、D5、D6 |
| M7 综合发布 | 全体 AC/SUP/RDI/CMP、性能与备份、第二场景、更新/卸载、许可与支持矩阵 | 第 25.9 节完整证据；未满足只称预览 | P4 验收、D6 |
| E1 实验并行 | M1 契约固定后，锁定一组真实 latent 导出/消费组合 | 两逻辑调用真实消费，同 Workflow 关闭对照 | 原 E1 |
| E2 实验集成 | M2/M4/M6 对应持久化、UI与交付边界完成 | 全 LH；默认标准包无实验依赖仍可运行 | 原 E2 |

标准包可以单独部署，实验依赖按需安装；不把标准包可用误记为全部项目发布门槛已满足。原 P/D 阶段只保留为历史映射，不再作为另一套排序指令。

<a id="sec-24-2"></a>

### 24.2 职责与接口门禁

Runtime 负责人维护状态和恢复；执行负责人维护真实 Agent/程序、工具台账和工作区；接入负责人维护注册/Bridge/Connector/通道；UI 负责人维护事实驱动交互；交付负责人维护依赖、目标独立运行和宿主边界；测试负责人维护跨层证据。角色是职责，不是团队人数配置。

所有 G 项由对应负责人在进入其功能开发前关闭。未知线级接口可以先做隔离原型，但未有 Schema/类型/错误/授权/版本测试不得成为对外接口。标准库描述和业务模板先完成正反例，再接真实执行。

<a id="sec-24-3"></a>

### 24.3 纵向交付次序

先证明全内建流程真实完成，再替换一个外部实现，再跨电脑，再交付干净目标。可在受限试点中交叉开展，但必须记录真实依赖与未验收部分。

外部作者使用版本匹配的指南、Schema、能力目录、组件模板和 CLI/API 完成第二套流程。平台级适配是一次性成本；第二套业务仍需改核心时记录抽象缺口，不称作配置复用。

首批循环/并行/人工场景应尽早进入 M4，不能一直增加静态语法和演示页面而没有真实协作。原语实现与标准组件共用同一 Runtime，不自建模板引擎。

---

<a id="s25"></a>

## 25. 验收清单与完成定义

<a id="sec-25-1"></a>

### 25.1 强制验收

| ID | 场景 | 必须得到的结果 |
|---|---|---|
| AC-01 | 导入合法包 | 文件/Schema/入口均验证；无业务调用 |
| AC-02 | 重复键、未知必需功能、非法引用 | 精确报错；不能忽略执行 |
| AC-03 | 显式同级图环、递归或超限组合 | 编译拒绝 |
| AC-04 | 未绑定 slot、错误能力或不支持 Skill | 预检阻塞并说明 |
| AC-05 | Binding 权限超过部署/用户授权 | 服务端拒绝，不只隐藏按钮 |
| AC-06 | 相同包切换两种执行实现 | Workflow 内容和摘要不变；Binding 和评测分别记录 |
| AC-07 | 同一命令重复 POST | 返回同一回执/资源，无重复 Run |
| AC-08 | 同 key 不同请求正文 | 409，不覆盖旧执行 |
| AC-09 | 外部创建成功后响应丢失 | 按 key 找回同一执行或 blocked；绝不盲目新建 |
| AC-10 | 保存提交意图后进程崩溃 | 恢复后继续处理同一意图 |
| AC-11 | 业务结果落库后 Checkpoint 保存失败 | 重入复用结果，不重复外部调用 |
| AC-12 | 等待人工时重启 Runtime | 请求、版本和等待关系仍在 |
| AC-13 | 人工双击/重复提交 | 只有一份有效最终决定 |
| AC-14 | 审批对象版本改变 | 旧批准不可继续生效 |
| AC-15 | 人工到期/拒绝 | 不自动批准；沿显式业务路径或失败 |
| AC-16 | 外部终态消息重复、乱序 | 去重，不回退事实；冲突进入核对 |
| AC-17 | 用户取消与结果完成竞争 | 按持久顺序处理；取消后不派发新下游 |
| AC-18 | 无法确认外部已停止 | blocked/待核对，不显示安全取消 |
| AC-19 | 暂停时已有工作完成 | 保存结果、不派发新工作；继续时不重跑已完成工作 |
| AC-20 | 写入后超时 | 不因超时自动重复写入 |
| AC-21 | 安全重试 | 次数、输入、effect key、延迟均符合声明 |
| AC-22 | executor 拥有内部重试 | Runtime 不重复叠加自动重试 |
| AC-23 | switch 多项同时为 true | 首个匹配胜出，选择持久且可解释 |
| AC-24 | parallel 乱序完成 | 按分支 ID 汇合，不按完成先后错配输出 |
| AC-25 | parallel 部分失败 | 取消/核对其他活动分支后再结束，无悬挂执行 |
| AC-26 | repeat 达上限 | 精确失败，保留每轮记录，不无限执行 |
| AC-27 | 子流程失败/取消 | 父级正确传播，无权限提升或丢失归属 |
| AC-28 | 输出 Schema 错误或产物缺失 | 不标成功；证据定位到具体调用/尝试 |
| AC-29 | Artifact 被改动或跨 namespace 访问 | 摘要校验/授权拒绝 |
| AC-30 | 切换包或 Binding 新版本 | 旧 Run 不热替换；新 Run 固定新部署 |
| AC-31 | 回滚部署 | 仅影响新 Run，不宣称撤销历史副作用 |
| AC-32 | 无 Langfuse/无 OTel 后端 | 核心运行、日志、审阅、核对可用 |
| AC-33 | 外部执行器没有内部 Trace | 明确显示观测范围，不伪造工具调用 |
| AC-34 | SSE 断线/游标过期 | 快照+游标恢复，不丢失界面关键状态 |
| AC-35 | 嵌入 UI | 不破坏宿主样式/路由/登录；退出组件释放订阅 |
| AC-36 | CLI 与 UI 执行同一操作 | 同一权限、状态和幂等语义 |
| AC-37 | Eval 含失败、未知和无成本样本 | 全部计入并注明，不虚增成功率 |
| AC-38 | 恶意归档、任意安装脚本、恶意 HTML | 拒绝/安全呈现，不执行 |
| AC-39 | Worker 双启动 | 只有单活调度；另一实例不派发 |
| AC-40 | 数据库+Artifact+Checkpoint 备份恢复 | 先核对活动外部工作，再恢复推进 |
| AC-41 | 真实非 Mock 外部执行器 | 完成输入—执行—结果—人工—交付；保存实测报告 |
| AC-42 | 第二个非同类业务示例 | 不新增核心行业字段即可完成流程 |
| AC-43 | 未知状态的人工核对 | 需要授权与证据；不能伪造结果或自动满足审批 |
| AC-44 | 凭据/权限撤销、执行器版本漂移 | 后续派发被阻止；版本与原因可解释 |
| AC-45 | 日志超限、遥测中断 | 不丢控制事件，不拖垮核心运行 |
| AC-46 | 关闭浏览器/CLI 连接 | 不取消后台持久 Run；重新连接可查询 |
| AC-47 | 通信字段缺省或 enabled=false | 均解析为标准模式；已有包/Binding 无需改写 |
| AC-48 | 不安装 latent 插件、推理库、模型或向量服务 | 默认关闭时核心运行、审计和 UI 全部可用；不探测 latent 依赖 |
| AC-49 | enabled=true 但 routes 缺失、实现不可用或不兼容 | 预检明确拒绝；无业务派发，不忽略开关、不假报 latent 已使用 |

<a id="sec-25-2"></a>

### 25.2 验证样例组合

必须维护两类参考 Preset：内容交付（生产→验证→审阅）与数据质量处理（并行检查→有界修正→汇总）。它们用于证明通用性，不定义项目只服务这些场景。

每类至少有确定性 fixture。至少一类再绑定真实 Agent、远程服务或实际本地执行器，不能用全部 Mock 证明外部接入已经成立。未获得真实凭据时如实标记该验收尚未完成，不阻止继续其他开发工作，但不能发布为全部通过。

<a id="sec-25-3"></a>

### 25.3 性能验证目标

建立固定环境与样本，测试 100 个静态节点的 Graph、20 个同时等待的 Run 和 10,000 条分页事件。首屏可交互目标为 2 秒以内；本地已提交控制事件到 UI 可见目标为 1 秒以内。测试必须注明机器、网络和数据规模，这些是优化目标而不是当前实测承诺。

M0—M7 均优先保证正确性与可解释性，不以吞掉事件、提前标成功或省略授权换取漂亮耗时。

<a id="sec-25-4"></a>

### 25.4 完成定义

只有本章 25.9 的完整门槛满足，项目才可标为完整 V0.1；25.1 和 25.5 只是保留的基础/实验测试集合，不独立取代新增 SUP/RDI/CMP。标准发行包本身不要求捆绑或启用 latent 后端。

“页面已经画出来”“可以运行一次”“日志看起来正常”“单元测试通过”都不单独构成完成。


<a id="sec-25-5"></a>

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

<a id="sec-25-6"></a>

### 25.6 人工与作者补充验收

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

<a id="sec-25-7"></a>

### 25.7 受管、接入、交付补充验收

| ID | 场景 | 必须结果 |
|---|---|---|
| RDI-01 | 统一调用契约 | 人、程序、受管 Agent、外部 Agent 均经过相同输入输出校验和标准执行观察；不以私有结果结构推进。 | 第 4.4 节、第 27.6 节、第 9.12 节 |
| RDI-02 | 内外绑定替换 | 同一 Workflow 与业务 Schema 不变，新 Binding/Deployment 可选择内建或外部实现；不迁移活动 Run。 | 第 4.4 节、第 27.1 节 |
| RDI-03 | 管理归属与位置 | 远程受管与外部平台可区分；连接位置不被当作生命周期权威。 | 第 4.4 节、第 5.5 节 |
| RDI-04 | 注册式扩展 | 新增一个执行器实现或同平台第二个 Agent，无需修改 Compiler/Runner 的业务分支。 | 第 8.5 节、第 9.17 节 |
| RDI-05 | 能力支持报告 | 已声明、已安装、可用、已验证及证据范围分开；未验证不能假报通过。 | 第 8.5 节、第 9.17 节 |
| RDI-06 | 全内建真实协作 | 不连接第三方 Agent 平台，用真实模型、两份 Agent 配置、程序和真人完成交付。 | 第 1.4 节、第 27.6 节、第 21.7 节 |
| RDI-07 | 内建程序包装 | 输入按 Schema 读取，日志不混入结果，输出有效后才释放下游。 | 第 4.4 节、第 27.6 节 |
| RDI-08 | 内建 Agent 内部步骤 | 记录真实阶段、工具/模型调用与结果引用；不以生成解释冒充实际轨迹。 | 第 27.6 节、第 15.4 节 |
| RDI-09 | 业务失败与执行失败 | valid=false 或 decision=reject 走显式业务分支，不自动当传输错误重试。 | 第 4.4 节、第 13.24 节 |
| RDI-10 | 配置版本固定 | 运行中更改 Profile/Binding/Schema 不改变旧实例；漂移阻塞并提供原因。 | 第 27.1 节、第 12.8 节 |
| RDI-11 | Session 隔离 | 并发任务不会共享未授权历史；显式复用的范围、源材料与调用关联可追溯。 | 第 27.1 节、第 27.12 节 |
| RDI-12 | 工作区隔离与并发 | 共享可写工作区存在明确策略；一个调用不覆盖另一调用已固定产物。 | 第 27.12 节 |
| RDI-13 | 资源与凭据 | 每次只注入所需凭据和授权资源；内建执行无法直接修改 Runtime/审批数据库。 | 第 27.6 节、第 10.6 节 |
| RDI-14 | 导入不执行源码 | 导入含脚本/安装钩子的未批准内容不会自动执行或取得可信注册。 | 第 27.6 节、第 10.6 节、第 16.7 节 |
| RDI-15 | 真实隔离声明 | 可信本地模式不标沙箱；多人代码执行仅对已测试的隔离与限额组合声称支持。 | 第 27.6 节、第 10.6 节 |
| RDI-16 | 输出不合规 | 保留原始观察和校验错误；不悬挂模糊状态，不盲目重跑可能已写入的业务。 | 第 27.6 节、第 12.8 节 |
| RDI-17 | 同 key 不同语义 | 改变输入、决定、主题或主体却复用 key 时冲突；合法重放返回原结果。 | 第 12.8 节 |
| RDI-18 | 决定后进程退出 | 决定、事件和推进意图持久；重启后完成同一推进，不永久等待、不重复业务。 | 第 12.8 节 |
| RDI-19 | 提交回执丢失 | 先核对原提交或维持未知，不因网络失败新建业务动作。 | 第 28.1 节、第 9.12 节、第 12.8 节 |
| RDI-20 | 运行能力门禁 | 可解析但当前不可执行的类型/依赖在业务派发前拒绝，不能中途才发现。 | 第 12.8 节 |
| RDI-21 | 远程配对 | 单次短时配对只得到受限身份，重复使用或撤销后的配对/凭据不能新增执行。 | 第 28.1 节、第 10.6 节 |
| RDI-22 | 出站接入 | 在已声明可达网络中，远端无需公网入站服务完成领取与回传；不夸大网络穿透。 | 第 28.1 节 |
| RDI-23 | 一端多执行配置 | 同一个 Connector 登记多个允许的 Agent/程序，不暴露未选择目录或能力。 | 第 28.1 节 |
| RDI-24 | 重复领取 | 相同提交身份重复投递/领取找回同一次执行，不启动第二个进程。 | 第 28.1 节、第 12.8 节 |
| RDI-25 | 断线状态 | 心跳丢失显示连接/新鲜度问题，不将其直接记为任务失败或可转派。 | 第 28.1 节、第 15.4 节 |
| RDI-26 | 重新连接 | 按原引用回传待发送事件与结果；重复事件去重，不串 Run。 | 第 28.1 节、第 15.4 节 |
| RDI-27 | 无法核实旧进程 | PID/终端现象不足以证明停止时进入核对，不重新派发旧业务。 | 第 28.1 节、第 12.8 节 |
| RDI-28 | 外部平台对象选择 | 通过授权发现或显式 ID 接入原 Agent/工作区/配置，不复制整个平台。 | 第 27.1 节、第 9.12 节 |
| RDI-29 | 远端保证不足 | 缺取消/lookup/版本固定等能力时准确报告；严格部署条件不满足则拒绝。 | 第 9.12 节 |
| RDI-30 | 重试责任唯一 | 远端内部重试或返工已生效时，Runtime 不再自动创建同类第二份工作。 | 第 9.12 节、第 12.8 节 |
| RDI-31 | 人工结构化结果 | 人能填写规定结果或交付文件，服务端校验输出与 Artifact，不要求普通用户手写 JSON。 | 第 13.24 节 |
| RDI-32 | 人工入口可用性 | 缺入口、未送达、已送达待处理和过期分别展示；没有实际入口时不能激活。 | 第 13.24 节、第 16.12 节 |
| RDI-33 | Web 与飞书同时操作 | 同一请求只有一份最终决定，旧版本/重复/过期操作被正确拒绝或重放。 | 第 13.24 节、第 12.8 节 |
| RDI-34 | 可信操作者 | 不能通过昵称、正文 actor、任意 userId 或服务 token 冒充真人决定。 | 第 13.24 节、第 10.6 节、第 17.5 节 |
| RDI-35 | 多流程同一会话 | 消息、卡片及结果按明确关联进入目标 Run/请求，不能猜“最近的 Agent”。 | 第 13.24 节 |
| RDI-36 | 外部文件提交 | 上传/登记完成后才产生可验证 ArtifactRef；跨权限读取和错误版本被拒绝。 | 第 27.12 节、第 13.24 节 |
| RDI-37 | 内部多轮交互 | 仅对已实现可选交互的执行器投递，记录追加事件，不改写原输入或自行批准。 | 第 13.24 节 |
| RDI-38 | 开始和暂停派发 | 创建持久 Run；暂停仅停止新派发，当前执行观察继续且 deadline 语义不变。 | 第 11.8 节 |
| RDI-39 | 停止与完成竞争 | 遵守持久控制顺序，显示请求/确认差异，不因迟到结果派发取消后的下游。 | 第 11.8 节、第 12.8 节 |
| RDI-40 | 停止不影响共享资源 | 单个 Run 取消不关闭其他 Run 的模型服务、工作区或执行宿主。 | 第 27.6 节、第 11.8 节 |
| RDI-41 | 重跑与单节点调试 | 新建独立执行，不重写旧终态、不复制批准、不绕过依赖推进生产 Run。 | 第 11.8 节 |
| RDI-42 | 双击与替代入口 | 单击摘要、双击详情及键盘/触屏访问一致；不同时误触画布缩放。 | 第 19.7 节 |
| RDI-43 | 定义与实例区分 | 未选 Run 只显示定义；历史详情使用对应版本与 Attempt，不读取最新配置冒充历史。 | 第 19.7 节 |
| RDI-44 | 循环三层区分 | 业务轮次、Attempt 和 Agent 内部步数可分别选择，前轮输出不被覆盖。 | 第 15.4 节、第 19.7 节 |
| RDI-45 | 外部观测范围 | 只提供边界信息时明确标识，能跳转原生记录但不把外链当唯一详情。 | 第 15.4 节、第 19.7 节 |
| RDI-46 | 重新订阅与关闭页面 | 断线可按快照/游标恢复，关闭 UI/CLI 不取消 Run，布局和选中不随事件抖动。 | 第 15.4 节、第 19.7 节 |
| RDI-47 | 外链与嵌入安全 | 外部入口受信任与授权，不泄露长期 token，不执行不可信 HTML；宿主样式和路由不破坏。 | 第 19.7 节、第 10.6 节 |
| RDI-48 | 完全离线真实运行 | 禁止外网后，真实本地模型、程序和人工产出文件；不使用固定字符串伪装 Agent。 | 第 21.7 节 |
| RDI-49 | Latent 非默认依赖 | 关闭时不加载/探测 latent 依赖；普通内建/外部能力独立运行。 | 第 21.7 节、第 14.17 节 |
| RDI-50 | Latent 交付与切换 | 沿用 LH；目标环境重新验证组合，活动 Run 不热切换，失败不静默文本回退。 | 第 14.17 节 |
| RDI-51 | 交付依赖完整性 | 包、实现、模型、UI、存储、身份和人工入口逐项归类；必需缺口阻止激活。 | 第 16.7 节、第 16.12 节 |
| RDI-52 | 无隐含源环境依赖 | 交付检查定位原目录、原数据库 ID、未打包程序或原服务地址，不能伪装完整包。 | 第 16.7 节、第 16.12 节 |
| RDI-53 | 干净环境安装 | 不复制开发数据库、个人授权或会话，使用交付物及明确 Binding 完成真实运行。 | 第 16.12 节、第 17.5 节 |
| RDI-54 | 原开发平台不可达 | 切断原站点后目标实例仍能启动、人工处理、继续、停止及读取结果。 | 第 17.5 节、第 16.18 节 |
| RDI-55 | 宿主身份与命令复用 | 宿主按受信任映射调用同一命令层；不另写流程状态机，不用管理员 token 代替用户。 | 第 17.5 节 |
| RDI-56 | 异步业务调用 | 返回持久 Run 引用，宿主断开/重试查询不重新执行；事件丢失可重新查询。 | 第 17.5 节 |
| RDI-57 | 流程包与完整 Bundle | 已有 Runtime 能导入轻量包；无 Runtime 的目标使用随附/锁定组件独立部署。 | 第 16.7 节、第 16.12 节 |
| RDI-58 | 兼容性与离线资源 | 版本/硬件/模型或资源不满足时预检明确；离线包不能仅依赖下载链接。 | 第 21.7 节、第 16.12 节 |
| RDI-59 | 重复安装及启动 | 相同内容与合法重复命令可核对去重；同版本不同内容不得静默覆盖。 | 第 16.12 节、第 17.5 节 |
| RDI-60 | 升级与回滚 | 新 Run 使用新部署，旧 Run 保持原依赖；回滚不宣称撤销历史业务副作用。 | 第 16.18 节 |
| RDI-61 | 卸载与共享运行环境 | 停用新入口、处理活动执行后按策略卸载；共享资源和必须保留的记录不被删除。 | 第 16.18 节 |
| RDI-62 | 目标环境备份恢复 | 恢复包/台账/Checkpoint/产物和必要关联，先核对外部工作，不形成两个同 Run 调度权威。 | 第 12.8 节、第 16.18 节 |
| RDI-63 | 原生作者闭环 | 外部或本地作者通过契约/目录/诊断生成、修复、测试；不改核心，不删验收求通过。 | 第 9.17 节、第 21.7 节 |
| RDI-64 | 真实证据与完成声明 | 每项报告版本、环境、命令与证据；未测/失败/不支持分开，Mock 不替代真实接入与离线验收。 | 第 23.5 节、第 24 节、第 25.7 节 |

<a id="sec-25-8"></a>

### 25.8 通用组合与标准库验收

| ID | 场景 | 必须结果 |
|---|---|---|
| CMP-01 | 同模板从 2 Agent 扩展为 3 Agent＋程序＋人 | 不改 Runtime 核心；生成新定义与绑定即可表达 |
| CMP-02 | 纯程序或纯人工流程 | 不加载或强制绑定模型 |
| CMP-03 | 角色改名、复用执行配置 | 控制逻辑不依赖角色字符串；调用身份仍独立 |
| CMP-04 | 仅用两条分支表达并行 | 编译拒绝隐式 fan-out；要求 parallel |
| CMP-05 | 模板展开 | 结果完全由六种核心节点表达，无隐藏私有解释器 |
| CMP-06 | 模板版本和传递依赖 | 锁定摘要，保留 source map，不运行时下载最新版 |
| CMP-07 | 未安装组件/执行器 | 目录报告缺口，激活前拒绝，不编造可用性 |
| CMP-08 | Schema 字段缺失、null 与类型不匹配 | 精确诊断，无隐式强转 |
| CMP-09 | 相同结构但能力/权限不同 | 拒绝不满足绑定，Schema 不授予身份 |
| CMP-10 | 目标字段静态无法证明兼容 | 标注需运行时校验，不假报已证明 |
| CMP-11 | 数据引用指向未选中分支 | 静态拒绝或采用统一子流程输出；不读取不存在值 |
| CMP-12 | 开发交付新版本 | 旧评审/人工批准不能批准新版本 |
| CMP-13 | 评估报告缺失、重复、未知 ID | gate 拒绝契约错误，不当通过或新增票数 |
| CMP-14 | report subjects 与 product 不一致 | 阻止推进，错误定位到报告/产物版本 |
| CMP-15 | findings 有阻断项但 verdict=pass | 固定策略仍产生 revise，不只相信 verdict |
| CMP-16 | 分支完成顺序颠倒 | 按 branch ID 汇合，相同显式输入得到同一纯聚合结果 |
| CMP-17 | 并行一个分支失败/停止未知 | 取消或核对其余活动，不能提前成功 |
| CMP-18 | 机器要求修改 | 本轮正常输出 revise，生成新 Scope，而非技术重试 |
| CMP-19 | 人要求修改与拒绝 | 前者进入下一轮，后者明确结束，不混淆 cancel |
| CMP-20 | 人不参与的一轮 | humanDecision=null，不伪造 HumanRequest/真人决定 |
| CMP-21 | always 人工策略且机器未通过 | 默认不能用 approve 越过机器门槛 |
| CMP-22 | 多个独立真人请求 | 每请求一份决定；需要身份隔离时由可信记录验证 |
| CMP-23 | repeat 达到上限仍需修改 | LOOP_LIMIT_EXCEEDED，无隐式额外轮次或自动接受 |
| CMP-24 | 轮次输出与下一轮输入 | nextInput 通过同一约束 Schema，保留目标和必需约束 |
| CMP-25 | 业务反馈缺少明确内容 | 可定位阻塞/契约错误，不生成无依据修改指令 |
| CMP-26 | 网络重发或恢复 | 固定 input/Context 和原 key，不重新生成不同交接 |
| CMP-27 | Context 超限 | 只裁剪可选内容并记录；必需材料不能静默丢失 |
| CMP-28 | 跨机器相同路径 | 必须验证/取得固定 Artifact，不能假设相同文件 |
| CMP-29 | Artifact 无权限、内容变更 | 拒绝读取/提交或核对，不能扩大权限 |
| CMP-30 | 外部自带返工/重试 | 所有权明确，一类新执行不被两侧重复创建 |
| CMP-31 | 外部完整工作流作为 call | 原生内部状态由外部管理；只控制承诺的边界 |
| CMP-32 | 运行、草稿编辑、演示通道 | 相互隔离；作者 status 补丁不改运行事实 |
| CMP-33 | Scope 全失败或全未运行 | UI 不聚合显示成功，轮次与 Attempt 不串 |
| CMP-34 | latent 路由跨轮次或多源隐式融合 | 预检拒绝，不突破原 route/profile 边界 |
| CMP-35 | 标准模式相同组合 | 无 latent/向量依赖仍完整执行 |
| CMP-36 | 输出代码或任意 URL | 不自动安装/执行/提权，走受控注册 |
| CMP-37 | 第二种非开发业务 | 不增加核心角色/行业字段就能复用原语和交接 |
| CMP-38 | 干净目标环境安装组件模板 | 依赖可解析，需填项明确；不依赖作者机器或源数据库 |
| CMP-39 | 作者完成第二套流程 | 主要改 Schema/节点/参数/绑定；记录实际核心改动为缺口 |
| CMP-40 | Fixture、真人、模型、恢复报告 | 分层记录；示例模拟不宣称真实协作/并发或生产恢复已通过 |

<a id="sec-25-9"></a>

### 25.9 证据分层与最终完成门槛

每项验收保存：代码/依赖版本、环境、输入与测试身份、命令、观察结果、预期、证据摘要、测试层次及未解决限制。允许结果为通过、失败、未测、被阻塞、不支持，不能将“不适用/未测”算作通过。

Fixture 验证协议和业务映射；真实 Agent 验证推理/工具交付；真人测试验证实际操作；故障注入验证恢复；目标干净部署验证独立交付。它们相互不能替代。

必须覆盖：全内建、混合执行、干净目标交付、宿主嵌入、声明范围内的完全离线，以及 2 Agent＋1 人、3 Agent＋1 程序＋1 人和至少一种非 Agent 主导流程。参与者数量只用作兼容性样例，不是业务模型限制。

完整 V0.1 同时满足 AC-01—AC-49、LH-01—LH-14、SUP-01—SUP-28、RDI-01—RDI-64、CMP-01—CMP-40，以及接口门禁和依赖许可检查。标准包不强制装载 latent 依赖，但项目需有一个单独可安装、真实验收的实验实现。

“页面已完成”“全量静态检查通过”“状态可修改”“一条 Mock 路径成功”均不能单独构成完成。前端实时状态必须来自实际 Runtime；回放、导入快照和演示数据应显式区分。

<a id="sec-25-10"></a>

### 25.10 v1 稳定试用发布门槛

以下新增门槛与原222个 AC/LH/SUP/RDI/CMP/PORT/G ID 一起强制追踪，主签收 owner 见发布证据索引。每项须绑定固定实现/产物快照，保留失败、未知、跳过及真实证据来源。pending/failed/blocked 不能变成 passed，已有部分实现测试不能签收完整 ID。

| ID | 门槛 | 必须得到的结果 | 主签收工作包 |
|---|---|---|---|
| V1-01 | 真实核心闭环 | Agent、程序、真人、产物真实协作；关闭页面和重启不丢事实。 | W19 |
| V1-02 | 作者体验 | 20项创建/修改/修复/重绑定任务完整统计；Schema、诊断、eval、语义diff均可用。 | W19 |
| V1-03 | 可替换性 | Codex、Claude、Pi真实执行；同包换Binding，固定原生版本及能力差异。 | W25 |
| V1-04 | 会话与权限 | 多会话单写、resume/fork协商、授权续接、收窄权限后清理越权上下文。 | W18 |
| V1-05 | 远程通道与宿主 | 第二机器Connector、飞书真实回调与程序写入、两个宿主技术栈实测。 | W20 |
| V1-06 | 持久服务 | PostgreSQL真实事务、LangGraph持久checkpoint、单活及崩溃恢复。 | W16 |
| V1-07 | 安全 | 实际沙箱、可信主体、Secret生命周期、跨namespace拒绝；无阻塞安全缺陷。 | W26 |
| V1-08 | 安装运维 | 固定产物干净安装、旧Run升级兼容、回滚、备份恢复与安全GC。 | W29 |
| V1-09 | 离线 | 禁外网真实本地模型/工具/真人/产物；安装资源与运行依赖闭合。 | W22 |
| V1-10 | 实验交付 | 独立安装真实latent导出/消费，LH全验收，标准包默认不加载实验依赖。 | W29 |
| V1-11 | 兼容矩阵 | §21.11所有必需目标有固定版本/产物digest/安装运行证据；无skip冒充支持。 | W25 |
| V1-12 | 稳定性 | §21.12完整6小时预检及72小时soak、基础SLO、故障矩阵达标，无一致性或权限破坏。 | W27 |
| V1-13 | 真实试用 | 至少5套独立干净安装、2种宿主、10名真人、500个记录Run，其中50次真实Agent任务且包含真实人工决定；保留全部失败和弃用。 | W28 |
| V1-14 | 证据完整 | 每一必需ID有owner、必需证据层、测试/报告与结论；固定最终产物digest一致。 | W29 |
| V1-15 | 发布交付 | 全部P0/P1和影响核心使用的P2关闭；剩余P3公开；最终独立review通过，实现/报告/状态回执均在origin/dev；正式发布另经授权。 | W29 |
| V1-16 | 版本兼容 | §0.7各公开面未知版本/字段、v0.1导入、过期客户端及弃用行为有正反例和真实兼容证据。 | W25 |

试用覆盖 personal/team、远程、飞书和 offline 声明场景；安装者只靠文档完成首次运行，记录耗时、求助、修复回合。维护者暗中修环境不算独立安装成功。真实账号/反馈留在受控位置，公共报告仅放脱敏统计与证据引用。缺真人/资源保持 blocked，不能生成伪用户补数。影响安装的修复生成新 RC 并复验受影响试用。

W29按同一RC快照签收全部门槛。大范围试用不等于无限容量或敌对多租户生产认证；release_ready 与 released 分开，推送dev不是正式Release。

---

<a id="s26"></a>

## 26. 后续演进边界

V0.2 之后按真实需求考虑：额外 Adapter 和 MCP/A2A、完整结构化 Graph Diff、外部 Eval 后端、更多存储、分布式 Worker、第二运行后端、受控发布自动化、Memory 实验与生态注册。Latent 的默认关闭开关和首个真实后端属于 V0.1；更多跨模型 profile、跨 scope 通信、多源 latent 融合和跨权限域共享作为后续扩展，不回填成首版已有能力。

任何新后端必须公开支持的 feature set，并运行同一 conformance suite。任何新 Adapter 必须说明幂等、取消、结果核对和观测能力；不能仅展示一个产品 Logo 即称支持。

任何新增核心字段必须至少用两类场景说明必要性；业务专有字段优先放入节点 payload、Capability 或扩展中。增加“更自由”的能力不能取消已有的权限、版本、审计和恢复边界。

**项目长期的核心资产是契约、一致性测试、可交付包、可靠适配经验和验收闭环；不是某个框架内部对象、一个特定平台或一张图。**

---

<a id="s27"></a>

## 27. 受管执行配置、Execution Host 与工作区

<a id="sec-27-1"></a>

### 27.1 配置模型的地位

`AgentProfile`、程序执行配置、连接配置是本次讨论提出的工程概念。它们首先属于环境注册与部署层，不自动成为新的 Workflow 顶层资源。名称及序列化结构在 第 0.5 节 冻结后才能进入公开 SDK。

配置与运行实例分离：配置可被多个调用使用；每次调用生成独立执行身份。配置更新建立不可变修订，活动运行继续使用原修订。

<a id="sec-27-2"></a>

### 27.2 受管 Agent 配置的最小信息

| 类别 | 需要描述的信息 |
|---|---|
| 行为 | 角色、系统提示、交付要求、Prompt/Skill 的内容或版本引用。 |
| 模型 | 已注册模型配置、本地或远程推理绑定、有效版本和必要配置。 |
| 工具 | 允许调用的工具、各自 Schema、动作范围及实际授权。 |
| 工作区 | 初始化模板、输入挂载、读写范围、隔离和保留要求。 |
| 限制 | 内部步数、deadline、输出大小及可实际实施的资源限制。 |
| 会话 | 默认按调用隔离；需要复用时的明确范围和历史上下文来源。 |
| 交付 | 业务输出 Schema、产物登记、内部事件与审计摘要要求。 |

多个 Agent 可以共享同一个模型服务；不能因此共享未授权的会话、工作区和调用结果。多 Agent 不要求每个 Agent 都加载一份独立权重。

<a id="sec-27-3"></a>

### 27.3 外部 Agent 执行配置

记录：外部连接引用、Agent 稳定 ID、配置修订、工作区引用、允许的信息资源范围、会话策略、契约及保证。外部平台有发现接口时可列举授权范围内对象；没有发现接口时允许显式录入并验证，不得靠猜测。

外部平台只允许“最新配置”而不能固定修订时，报告实际限制；不能把期望的旧版本显示为实际生效版本。无法满足部署保证时阻止激活或后续派发。

<a id="sec-27-4"></a>

### 27.4 程序配置

程序配置关联受信任安装资产、入口、输入输出协议、参数白名单、资源和工作区要求。开发者主要实现业务函数；Execution Host/Wrapper 负责公共生命周期。

从包中发现一个脚本不是执行授权。明确区分编辑、构建、审核、安装、注册、绑定和调用。参数不能绕开命令与文件访问限制。

<a id="sec-27-5"></a>

### 27.5 Workflow 中不应出现的环境细节

具体模型凭据、主机地址、私有目录、外部 Agent 账号和聊天群目标保留在受控 Binding/注册配置中。业务 Workflow 用逻辑 slot、Capability 和 Schema 表达要求。

可移植模板可以描述需要什么环境，不得将原开发环境的注册 ID 当成跨环境永远有效的唯一来源。

<a id="sec-27-6"></a>

### 27.6 内建 Agent 必须是真实执行器

至少提供一个可配置的真实 Agent Executor，完成任务输入与授权材料读取、模型调用、允许工具使用、过程记录、必要人工等待、结构化输出及真实 Artifact 交付。

不得以固定字符串生成器代替该验收。可以复用既有 Agent 框架或 SDK，但公共协议不得暴露其内部对象，也不从零发明新的通用模型框架。

<a id="sec-27-7"></a>

### 27.7 一次调用的装配与执行

```text
验证输入、配置、授权与版本
          ↓
持久化调用和提交身份
          ↓
准备隔离工作区及必要执行环境
          ↓
注入最小配置与凭据引用解析结果
          ↓
启动 Agent / 程序，记录实际执行引用
          ↓
观察步骤、等待、错误与产物
          ↓
确认执行终态，校验业务输出和产物
          ↓
提交事实与后续推进意图
```

进程、容器或 SDK 对象不替代持久执行身份。环境准备失败、程序启动失败、输出不合规和执行结果未知必须分别记录，不能都归为普通“Agent 失败”。

<a id="sec-27-8"></a>

### 27.8 输入输出与日志

沿用本规范的程序包装边界：Local Process 使用结构化输入和单一结构化结果，日志与结果分离。内部工具和子程序同样需要可解释的错误与输出；不能把 stderr 日志拼成节点业务结果。

输出校验失败必须留存观察与错误，不能只抛异常退出、把数据库留在模糊的运行状态。可能发生的副作用在失败后继续按既有核对规则处理。

<a id="sec-27-9"></a>

### 27.9 内部工具调用与恢复

持久 Checkpoint 不能保证所有模型/工具调用自动恢复。受管 Agent 必须记录工具调用关联、输入主题、开始与观察结果；对有写入的工具，恢复时不能无条件再次执行。

已确认的结果可复用；未知结果先核对。具体工具调用台账字段与宿主恢复实现属于 第 0.5 节 待冻结事项，但不降低本规范的副作用安全要求。

<a id="sec-27-10"></a>

### 27.10 人工等待与共享资源

等待人工的记录必须持久，关闭界面不丢失。实现应避免把一个浏览器请求、连接或不可恢复的 Python 栈当作等待权威。确需保持外部 Session 时，要声明其保留与恢复方式。

共享模型服务或长期执行宿主与单次执行实例分开。一个 Run 停止、失败或卸载，不能结束其他 Run 正在使用的模型服务或长期工作区。

<a id="sec-27-11"></a>

### 27.11 最小资源隔离

可信本地开发模式可以使用明确授权的本地进程，但不得宣传为不可信代码沙箱。多人服务场景中的用户代码必须选择并验证相应隔离方式、文件与网络策略、运行身份和资源限额。

具体容器/沙箱后端本轮未冻结。采用容器不是自动获得所有安全保证。执行进程不能获得 Runtime 数据库或审批表写权限，不得因“内建”而跳过 Policy。

<a id="sec-27-12"></a>

### 27.12 对象必须分开

| 对象 | 含义 |
|---|---|
| Agent / 执行配置 | 提供能力的长期配置。 |
| Workspace | 文件、资源、运行容器或远程工作环境。 |
| Session / Conversation | 可能携带历史上下文的一段会话。 |
| ExternalExecutionRef | 外部实际执行的持久引用。 |
| Invocation / Attempt | Multiverse 的逻辑调用与执行尝试。 |

不把 Session 当 Agent 身份，不用一个全局 conversation ID 关联所有任务。调用默认隔离；复用的范围、授权和历史材料必须可追溯。

<a id="sec-27-13"></a>

### 27.13 工作区管理

外部工作区默认保留在外部；Multiverse 保存引用、可用版本/基线和本次交付物，不要求镜像整个文件系统。内部工作区由受管执行宿主准备并记录所有者。

共享可写工作区须采用明确的隔离副本、串行使用或外部已验证协调机制。路径字符串相同不等于内容相同；换机器不自动继承文件、进程和 Session。

创建、使用、保留、清理分别有责任归属。取消节点不得删除长期工作区或其他调用资源。Git 只是一种场景下的工作区实现，不进入核心行业字段。

<a id="sec-27-14"></a>

### 27.14 外部信息访问

外部 Agent 已有知识库和工具可继续使用，不强制复制到 Multiverse。记录本次允许范围以及可提供的来源、版本和证据。

执行器无法提供必需来源证据时，应报告验收缺口；不能由摘要模型虚构引用。Capability 不等于数据权限，过宽的远端固定账号不能被一段 Prompt 宣称已经收窄。

新增资料通过明确输入、Artifact 或交互记录进入；新增授权走权限机制，不把聊天请求直接转成访问权。

<a id="sec-27-15"></a>

### 27.15 产物交接

必需依赖按固定 ID/版本直接取得；向量检索不是必需产物的传输机制。下游无权读取时停止相关派发，而不是扩大下载权限。

文件提交遵循：完成存储/外部登记 → 摘要或不可变版本核验 → ACL 检查 → 形成 ArtifactRef → 业务结果引用。上传中的文件、浏览器本地路径或随意字符串不构成交付。

可变工作区内容不作为已验收产物。大文件、模型权重和 latent 二进制不放进 Graph 状态；通过受控对象引用与限额管理。

---

<a id="s28"></a>

## 28. 远程 Connector：配对、派发与恢复

<a id="sec-28-1"></a>

### 28.1 定位

Connector 是运行在目标电脑上的轻量接入进程，不是 AI Agent，不是第二个 Workflow Runtime。它承载注册的本地执行能力，接收授权任务，记录实际执行引用并回传观察。

一台机器安装一次，可以登记多个 Agent/程序/工作区。默认只暴露明确选择的能力，不扫描上传整个文件系统。远程机器不需要安装完整 Inspector。

<a id="sec-28-2"></a>

### 28.2 配对与连接体验

```text
在 Multiverse 选择“接入电脑”
             ↓
在目标机器安装 Connector，并使用短时单次凭据配对
             ↓
换取受限、可撤销的连接身份
             ↓
明确选择执行实现、工作区与允许资源
             ↓
验证配置、协议和实际保证
             ↓
注册为可绑定执行器
```

配对不能自动授予管理员权限。模型密钥可保留在执行机器，仅按需要向该次执行提供；不得为接入而强制把整台机器的凭据上传到中心。

配对凭据的精确格式、有效期、轮换及吊销端点尚未冻结，见 第 0.5 节。不得在公开命令示例中伪装已有可安装 Connector。

<a id="sec-28-3"></a>

### 28.3 建议的传输形态

沿用此前建议：首个实现优先由远端主动发起 HTTPS 长轮询领取已分配工作并回报结果，降低入站网络配置要求。长连接可后续按需要增加，不改变调用身份和状态语义。

这不是无网络前提的穿透能力。目标机器必须能访问实际 Runtime 服务地址；隔离网络需要明确网络或中继配置。该传输是实施提案，不自动替换已有 HTTP Job API。

领取工作只领取 Runtime 已授权的执行意图，不允许 Connector 自行决定 Workflow 分支。多 Connector 不改变单活调度规则。

<a id="sec-28-4"></a>

### 28.4 本地持久关联与离线恢复

Connector 必须保存已接受提交与本地执行的关联，维护未回传事件/结果，并在重新连接后按原身份核对。可复用 Execution Host 的本地台账能力，不另建不兼容协议。

同 key 重复领取不能重复启动进程。Connector 的本地去重也不能证明外部工具副作用未发生；未知写入仍按原规则核对。

心跳消失只表示连接或观察问题。不得把心跳超时等同于节点失败、进程已停或允许转派。重新配对或换机器不能自动继承活动 Session/Checkpoint。

<a id="sec-28-5"></a>

### 28.5 可见性与停止范围

控制台分别显示连接状态、任务状态、最近观察时刻及恢复保证。Connector 取消单次任务，只能影响该任务拥有的进程/容器和明确关联子执行。

停止 Connector 服务属于管理操作，应说明是否停止领取、是否等待当前任务、哪些执行可能继续；不能用一个“离线”标签伪造所有任务已结束。具体排空接口留在 第 0.5 节。

---

<a id="s29"></a>

## 29. 通用组合与协作标准库

<a id="sec-29-1"></a>

### 29.1 最小而完整的组合基础

<a id="sec-29-1-1"></a>

#### 29.1.1 为什么不只保留循环和分支

在已经具备顺序调用与状态存储的前提下，分支和循环能表达许多业务选择；它们本身并不提供一个真实执行契约，也不提供并发汇合、人的提交、文件交付或跨服务恢复。

例如，两个检查并行执行且都完成后才能交付，不能把“画两条分支”当成已经定义了并行语义；等待真人三天，也不能用一个不断轮询的业务 while 循环代替持久 HumanRequest。

核心继续保留下列六种节点。顺序由 `next` 表达，不另造 sequence 节点。

| 原语 | 必需语义 | 不承担的事 |
|---|---|---|
| `call` | 对固定输入调用已绑定能力，观察、等待并验证输出 | 不根据品牌或人数创建特殊状态机 |
| `switch` | 有序条件，首个命中，明确 default，记录决定 | 不发起隐式并行，不执行任意代码条件 |
| `repeat` | 子流程一轮一 Scope；until、feedback 和最大轮数明确 | 不无限循环，不覆盖历史，不等同于执行重试 |
| `workflow` | 按输入输出契约复用包内子流程，保留层级与取消关系 | 不让子流程提权，不把父级私有状态变成隐式全局变量 |
| `parallel` | 静态分支、受限并发、`join: all`、稳定分支 ID | 不默认 first-success、抢答、多数票或动态 map |
| `end` | 确定当前 Scope 的终止及有效输出/错误 | 不把 HTTP 200、聊天“完成”当成功 |

<a id="sec-29-1-2"></a>

#### 29.1.2 持久等待是调用生命周期，不强加第七种节点

人工、异步 API 和外部 Job 都通过 `call` 的等待状态与 Adapter 的观察/恢复机制工作。已有 HumanRequest 不需要作者设计线程、锁或轮询循环。

任意事件订阅、可持久定时器或中途交互可以由明确注册的执行能力提供，但在该能力的契约、身份、超时与恢复方式冻结并验证前不得声明已支持。普通业务循环不是定时任务系统。

<a id="sec-29-1-3"></a>

#### 29.1.3 自由度的维度

人数、Agent 数量、角色名称、执行地点、工具品牌不产生新的节点类型。顺序、并行、迭代、人工位置及终止规则由图和业务契约表达。

静态图可由作者在构建时按清单生成更多分支；构建后的分支及 slot 仍固定进包。运行时按结果选择已有路径与运行时生成新图是不同能力，首版仅支持前者。

同一执行配置可以被多个逻辑节点绑定，但每次激活仍有独立 Scope/Invocation/Attempt。需要评审独立性时，部署策略须验证实际执行身份、权限或上下文隔离要求，不能仅因节点名字不同就视为独立审核。

<a id="sec-29-2"></a>

### 29.2 责任分工与自定义边界

| 层次 | 框架固定并实现 | 作者/业务开发可配置 | 扩展条件 |
|---|---|---|---|
| 执行协议 | ExecutionRequest/Observation、持久身份、幂等、终态、错误 | 节点使用哪些已注册能力 | Adapter conformance，不另造平行生命周期 |
| 业务契约 | Schema 验证、版本与来源绑定 | 字段、单位、允许值、验收标准 | 新版本和兼容性检查 |
| 控制组合 | 六种节点语义、作用域、等待、并发规则 | 依赖、分支、循环、人工位置、限额 | 不突破支持矩阵和资源上限 |
| Context 与交接 | 输入冻结、授权读取、产物和交接关联 | 必需材料、可选摘要、裁剪策略选择 | 不丢弃正确性必需输入，不伪造来源 |
| 外部调用 | 公共 SDK、查询/回调、映射记录 | 连接、执行者、工作区、参数 | 新平台适配一次，之后配置复用 |
| 真人参与 | 请求身份、权限、版本、提交与审计 | 输出表单、选择、顺序和业务后果 | 模型不得冒充真人；复杂会签不隐式出现 |
| 安装发布 | 构建、预检、版本固定、受控激活 | 业务包、资源绑定和授权申请 | 生成源码不等于可信安装或发布 |

任何工作流作者不得手工生成或修改 runtime 状态、审批事实、Lease、dispatchKey 等内部权威字段。展示结果可以包含业务上的 source 标签，但可信操作者和执行来源来自运行记录，不信任业务 JSON 自报。

新业务尽量只增加 Schema、Prompt、注册校验程序或普通子 Workflow。需要新增底层语义时，走独立版本和一致性测试，不用无校验 `extensions` 隐藏一个新的 Runtime。

<a id="sec-29-3"></a>

### 29.3 三层组件体系与标准库地位

<a id="sec-29-3-1"></a>

#### 29.3.1 核心原语、可执行组件与可组合模板

核心原语只有 第 29.1 节 的六种。可执行组件是已注册 `call` 能力，例如文件检查、结构化转换、模型调用、人工提交或外部服务。

协作模板由普通 Workflow、Schema、默认参数和测试材料组成。模板展开后必须能按核心原语完整表达，不能留下只有私有模板解释器理解的节点。模板可以拆开、修改、版本化与打包；修改后仍走同一验证和发布路径。

身份创建、事务保存、条件判断持久化、普通引用交接等 Runtime 服务不能变成作者必须逐个连接的“数据库节点”“状态节点”。这些公共复杂度由框架自动完成。

<a id="sec-29-3-2"></a>

#### 29.3.2 首批标准库能力

| 能力类别 | 可复用行为 | 权限/副作用边界 |
|---|---|---|
| 结构化 Agent 调用 | 角色配置、工具限额、结构化结果与产物 | 执行器实施权限；角色不授权 |
| 程序与遗留 Wrapper | 明确 stdin/stdout 或 HTTP 数据契约 | 原生不支持的恢复保证不能伪造 |
| 产物验证与交接 | 存在性、内容/外部版本、访问与来源检查 | 实际读取数据需要授权，不能仅检查字符串 |
| 审阅结果检查 | 被审阅对象一致、结论允许、证据与问题结构完整 | 不把 Schema 合格当业务评审正确 |
| 纯业务聚合/转换 | 对显式输入做确定性映射和策略计算 | 不读取时钟/网络/数据库隐式决定 |
| 反馈构造 | 构造下一轮输入并保留出处与未解决事项 | 不修改旧输入、旧产物或用户目标 |
| 人工工作 | approval/review/input 与真实可操作入口 | 决定只有一个权威，版本绑定 |
| Context 组装 | 合并必需材料和可选信息，记录实际输入 | 必需约束不能因裁剪或 latent 而丢失 |

这里的“纯”指只依赖已声明输入和固定配置；读取文件、调用模型或网络均不属于纯转换。纯组件也接受普通执行契约并留下结果证据，只是不应获得额外访问能力。

<a id="sec-29-3-3"></a>

#### 29.3.3 描述记录：帮助作者发现，不增加顶层资源

本轮定义标准库组件描述记录的最小语义，部署/构建目录和能力查询可复用该记录。它不是 `kind: Component`，不能作为第四种可执行 YAML 资源导入。

| 字段 | 类型 | 规则 |
|---|---|---|
| `schemaVersion` | string | 固定 `multiverse.component/v1`，与核心协议版本分开 |
| `id` | string | 命名空间化组件身份，非品牌或人数固定模型 |
| `version` | string | SemVer；同版本不同内容不可静默覆盖 |
| `contentDigest` | string | 实际发行文件清单摘要 |
| `kind` | enum | 描述层 `executor` 或 `template`；不是 NodeDefinition.type |
| `description` | string | 可本地化用途与适用边界 |
| `inputSchema` / `outputSchema` | SchemaRef | 描述产物内的相对路径与文件摘要 |
| `configSchema` | SchemaRef 或 null | 组件配置的可验证规则；无配置时显式 null |
| `requiredFeatures` | string[] | 核心或已注册必需扩展的能力 ID |
| `capabilities` | string[] | 所需/提供能力，目录同时标明使用方式 |
| `effects` | object | 沿用 class/actions；声明不授予权限 |
| `implementation` | object | executor 描述引用，或模板包摘要＋workflowId；内容互斥 |
| `tests` | TestRef[] | 相对测试材料、用途和摘要；不是“测试已经通过” |

SchemaRef 为 `{path, digest}`；路径属于描述产物根目录、禁止远程 Schema；摘要为 `sha256:` 加 64 位小写十六进制。TestRef 使用相同路径/摘要加 `level=static|fixture|real|fault`。`capabilities` 字段在 executor 记录表示提供能力，在 template 记录表示入口所需能力；两者须在目录中连同 kind 一起展示，不跨含义匹配。

`contentDigest` 使用固定发行清单的相对路径、长度和文件摘要计算，排除描述文件本身、锁文件和签名文件以避免自引用；描述文件的外部摘要另由包清单锁定。实际安装还须进行路径归一化、目录边界和符号链接检查，不能仅靠字符串正则证明路径安全。

`implementation` 的 executor 分支为 `{executorRef, adapter, adapterVersion}`；template 分支为 `{packageDigest, workflowId}`，校验时只能出现其一。具体环境可用性不写进不可变组件描述，而由下一节环境状态提供。

<a id="sec-29-3-4"></a>

#### 29.3.4 可发现性与可用性分开

目录必须分别给出 declared、installed、available、verified，以及 scope、版本、验证证据与检查时点。一个模板可用不意味着它所需的所有执行器已安装，Capability 匹配不意味着质量合格。

不为普通目录读取加载模型、访问 latent 服务或执行业务探测。未知组件允许作者生成明确的待绑定清单，但不允许声称可运行。

<a id="sec-29-3-5"></a>

#### 29.3.5 模板锁定和发布

模板在构建时展开或以包内子 Workflow 固定；传递依赖必须进入锁定清单。运行时不从公网拉取最新版模板。保留组件版本到展开节点的 source map，便于诊断、Diff 和升级。

标准库是框架随附的开发能力，不是强制所有业务都使用相同 ReviewReport 的万能规范。自定义契约可以不用标准模式，但仍遵守核心执行和数据边界。

<a id="sec-29-4"></a>

### 29.4 统一 I/O、业务 Schema 与兼容性

每个 Workflow 入口、`call` 输入输出和被复用子 Workflow 边界都使用独立可验证 Schema。字段必须定义类型、语义、必需性、空值/缺失差异、单位/格式、额外字段策略和版本。

协议层拒绝未知字段；业务 payload 按自身 Schema 决定额外字段。适配器不得把不合法输出自动补成“成功”或悄悄删除影响验收的内容。需要格式转换时提供显式、可测试的映射；模型抽取结果要记录为派生内容，不能当原生事实。

兼容检查分五层：结构、含义、能力、授权/副作用、执行保证。相同 JSON 形状只是必要条件之一。静态不能证明的关系返回 runtime_validation_required，前后边界继续运行时验证。

核心业务结果不能包含可直接修改状态的 `nextNode` 或 `status` 指令。业务 Schema 可以有同名业务字段，但 Runtime 仅通过 Workflow 中的显式 Predicate 使用它，不将其当控制命令执行。

一个节点返回结果合法，仍要检查必需 Artifact、来源、终态及审批要求。校验程序运行成功但业务 `valid=false`，审阅成功但要求修改，均不是传输失败。

<a id="sec-29-5"></a>

### 29.5 状态交接和协作通信的默认行为

<a id="sec-29-5-1"></a>

#### 29.5.1 默认不需要 Agent 直接相连

```text
源执行器 → Adapter 的执行观察 → Runtime 验证并持久化
         → 显式数据引用与 Context 组装 → 目标执行器
```

源执行者不必知道目标的地址、模型、工作区或 Session。Runtime 负责关联源版本、目标调用、权限、输入快照和必要唤醒。一次源结果可被多个授权下游读取，读取的是不可变内容，不是可被并行修改的共享缓存。

<a id="sec-29-5-2"></a>

#### 29.5.2 控制流、数据流、交互事件分离

`next/switch/repeat/parallel` 决定何时可以激活；ValueExpr 决定输入取什么；交互事件仅在有相应契约的等待点生效。数据引用不隐式新增执行边，聊天消息不隐式完成节点。

必需任务输入、验收要求、权限、版本和产物直接传递。可读 Handoff 是解释，Memory 是可选相关信息；二者不替代必要依赖和执行事实。

<a id="sec-29-5-3"></a>

#### 29.5.3 交接记录与 Context

沿用本规范 HandoffRecord 的持久关联。标准交接至少能追溯源 Scope/Invocation/Attempt、源输出和 Artifact 版本、目标 Invocation/Attempt、实际 Context 摘要、材料来源与裁剪策略。审计摘要可由有证据的模板生成，不必每条边都额外调用模型。

已固定的 Context 在同一调用的安全重试中复用；网络重发不重新检索或重新生成摘要得到不同输入。任务内容变化和业务返工创建新的调用，不能复用旧 dispatchKey。

Context 达上限时，允许按预先固定策略裁剪可选内容，记录去掉了什么；必需材料仍放不下时阻止派发并报告，不无声截断。授权撤销在派发和读取时重新校验，旧快照不是永久访问许可证。

<a id="sec-29-5-4"></a>

#### 29.5.4 文件、工作区与跨机器

工作区是执行环境，Artifact 是交付。审阅者读取的是同一不可变候选版本，不能让并发生产者持续修改的目录成为审阅对象。

相同路径字符串、同一个分支名或“最新文件”不是可靠交接。跨机器由已授权的 Artifact/Workspace Adapter 获取固定版本；需要现场测试时，固定测试环境和测试对象，不把读取报告等同于独立重跑。

<a id="sec-29-6"></a>

### 29.6 通用循环，而不是固定人数的“团队模式”

<a id="sec-29-6-1"></a>

#### 29.6.1 循环单元是子 Workflow

`repeat` 的 body 可以是一个程序、一个人、若干 Agent 或混合流程；不要求存在 producer、reviewer 或 approver 这几个角色。例子可以采用这些名称，但框架不据名称赋予权限或改变状态。

每轮都是新 Scope。第一轮使用 repeat.input；本轮正常结束后用 iteration.output/index 判断 until；未结束则由 feedback 构造下一轮输入；达到上限返回 LOOP_LIMIT_EXCEEDED。

业务要求修改通过正常输出表达。基础设施失败、未确认停止或未知副作用不得用“再循环一次”掩盖。`onError` 只处理已确定且没有活动未知执行的错误。

<a id="sec-29-6-2"></a>

#### 29.6.2 退出条件与成功条件分开

“循环结束”不等于“业务被接受”。常见模板可令 until 为 `outcome != revise`，然后由外层 switch 将 accepted 导向成功、rejected 导向明确拒绝结束。

多种分支必须产出相同的轮次输出契约。未经过人工节点的分支必须显式给出 `humanDecision: null`，不能读被跳过节点；汇合后读取本轮统一输出，不跨分支读取内部私有值。

<a id="sec-29-6-3"></a>

#### 29.6.3 不固定人工位置

可以每轮都问人，只在机器检查通过后问人，只在特定业务条件下问人，或完全没有人工。选择必须展开为显式图和分支，不能仅在 Prompt 中写“必要时请人”。

人要求修改、拒绝本次业务和取消执行是三种行为：修改进入下一轮；业务拒绝是合法输出；取消是有权限的运行控制命令，需要结束活动执行。不得混为一个 reject。

<a id="sec-29-6-4"></a>

#### 29.6.4 人数不是 HumanRequest 的投票人数

一个流程可以包含多个 Human call，每个请求保持只接受一次有效最终决定。顺序审批或静态 parallel 全部等待可组合；需要不同真人身份时由可信身份与运行策略验证，不能让 JSON 自报名字证明独立性。

首版不内置多人抢答、法定人数提前通过或会签撤回。需要所有人的独立意见时，可用多个明确请求、`join: all` 和注册的汇总组件；它是多个请求的组合，不改变单个 HumanRequest 的协议。

<a id="sec-29-7"></a>

### 29.7 并行、聚合和复杂业务规则

<a id="sec-29-7-1"></a>

#### 29.7.1 并行不是“多画一条线”

`parallel` 分支是静态子 Workflow，branch ID 在包内固定。输出按 ID 汇合，不按到达顺序或数组下标猜对应关系。失败处理沿用 stop_on_failure；存在未知活动分支时不能提前成功或安全失败。

并行检查同一不可变产物可以成立；并行写同一共享工作区必须额外隔离或采用已经验证的协调方式。框架不自动合并文件修改或业务写入。

<a id="sec-29-7-2"></a>

#### 29.7.2 汇合完成与业务通过分开

join:all 只确认所有分支正常完成并取得输出，不代表所有检查认可业务结果。一个检查输出 revise 并不造成技术失败；后继纯决策组件或 switch 根据所有已取得结果判断。

复杂规则（多数、权重、冲突排序、风险阈值、独立检查集）先由已注册程序对显式输入形成结果，再由 switch 使用。程序不得自行跳过未完成分支。首版多数规则只能在全部声明分支结束后计算，不声称提供 quorum 提前取消能力。

<a id="sec-29-7-3"></a>

#### 29.7.3 建议的通用评估记录

可选标准库提供 EvaluationReport 模板：目标 subjects、结论、findings、evidenceRefs、revisionRequests。结论词汇由契约定义；参考模板采用 pass/revise/reject，不要求所有业务都使用这三种值。

聚合必须明确缺报告、重复 ID、目标不匹配、未知结论和矛盾结果的处理。缺失不得当通过；重复不能当多一票；机器报告不能产生可信真人批准。

策略版本和本次实际输入固定，输出包含足以解释结论的来源。需要模型判断时，将其作为普通有成本的 Agent call，不能把非确定性判断隐藏在纯条件函数里。

<a id="sec-29-8"></a>

### 29.8 参考协作契约与确定性辅助组件

<a id="sec-29-8-1"></a>

#### 29.8.1 定位

以下是本轮新增的标准库参考契约，不是所有 Workflow 的强制业务字段。标准库版本固定为 1.0.0；参考文件位于交付包的 `examples/generic-collaboration/`，同时收录到本规范附录。它们遵守本规范，不新增核心节点种类。

这些名字是规范中的待实现/注册目标，不能因为本规范给出名字就宣称当前运行环境已安装。

| 契约 | 语义 |
|---|---|
| WorkBrief | objective、constraints、acceptanceCriteria、materials、feedback |
| WorkProduct | materials、summary、evidenceRefs |
| SubjectRef | 当前参考模板要求已登记 Artifact 的引用和内容摘要；其他业务可使用显式定义的外部不可变版本契约 |
| EvaluationReport | 同一候选 subjects、verdict、findings、revisionRequests、evidenceRefs |
| HumanDecision | 沿用 Human review 的 `{decision, comment}`；参考 choice 为 approve/revise/reject |
| RoundResult | outcome、materials、assessments、humanDecision、feedback、nextInput |

反馈的 source 是业务来源标签；真正来源、身份、调用及时间由 Runtime 关联，不信任客户端自报。SubjectRef 字符串合法不代表 Artifact 已存在，仍须对登记元数据及读取权限进行验证。

<a id="sec-29-8-2"></a>

#### 29.8.2 `mverse.stdlib.evaluation-gate.v1`

输入为 `{brief, product, reports}`；reports 是稳定检查 ID → EvaluationReport 的映射。配置必须包含 `requiredReportIds` 和 `humanPolicy`，后者为 `on_pass|always|none`；另有 `rejectOnVerdict` boolean 默认 true，`blockingSeverities` 默认 `[blocker, major]`。

按如下固定顺序处理：

1. 对输入/配置做 Schema 校验；requiredReportIds 非空且唯一，reports 的键集合必须与其相等，未知额外报告不能悄悄参与决策。
2. 每份 report 的 subject 集合必须与 product.materials 的引用和摘要集合精确相等，集合中不允许重复；不比较数组顺序。
3. 引用已验证状态由前置 Artifact 检查/Runtime 提供；本纯组件不发起网络读取，也不能自行认证来源。
4. 任一 reject 且 rejectOnVerdict=true，输出 route=reject。
5. 任一 revise，或 finding 的 severity 命中 blockingSeverities，输出 route=revise；rejectOnVerdict=false 时 reject 按 revise 处理，绝不变成 pass。
6. 没有上述问题时输出 pass 所对应路径；humanPolicy=on_pass/always 为 request_human，none 为 accept。always 只将 revise 变为 request_human，不允许覆盖第 4 步的显式终止拒绝。
7. 反馈按 report ID、finding ID 排序，保留 revisionRequests 原顺序；相同 report 内 finding ID 重复报错。不依赖到达先后、时间、随机数、Memory 或外部读取。

输出 `{route, feedback, machinePassed}`，route 为 request_human/revise/reject/accept；machinePassed 仅在没有 reject/revise 和阻断问题时为 true。request_human 不自动代表机器通过。涉及人绕过机器门槛的业务需不同的显式策略与授权，参考实现不提供隐式覆盖。

上述 subject、报告集合和策略验证失败属于契约错误，不能输出 revise 来掩盖错误绑定。规则不声称证明审阅结论真实或业务必然正确。

humanPolicy 的 `none` 只允许用于业务没有必需人工门槛的部署。不能为通过校验，将用户明确要求的人工参与改为 none；此类变更需要业务要求、契约、版本和发布审阅同步改变。

<a id="sec-29-8-3"></a>

#### 29.8.3 `mverse.stdlib.round-resolve.v1`

输入 `{brief, product, reports, gate, humanDecision}`，humanDecision 为上述对象或 null。输出 RoundResult。

- gate.route=reject → rejected，必须 humanDecision=null。
- gate.route=revise → revise，必须 humanDecision=null。
- gate.route=accept → accepted，必须 machinePassed=true 且 humanDecision=null。
- gate.route=request_human → humanDecision 必须存在。reject → rejected；revise → revise；approve 只有 machinePassed=true 才 → accepted，否则仍 revise，并记录机器门槛未满足。

参考人工配置要求 revise/reject 提交非空 comment。该组件验证输出结构，但可信人工身份和主题由 Human Adapter/Runtime 验证；业务对象中的 approve 本身不是授权证据。

nextInput 原样保留本轮 brief 的 objective/constraints/acceptanceCriteria，用 product.materials 作为下一轮候选，并按固定顺序组合 gate.feedback 与有身份关联的人工业务意见。缺少可执行修改意见时返回可定位契约错误或按已配置补充输入分支处理，不凭模型猜测修改目标。

feedback 不自动携带所有历史聊天；完整记录保存在历史 Scope。保留未解决约束的责任不能被简单截断掉，必要时使用明确的反馈汇总组件并记录摘要来源与测试。

<a id="sec-29-8-4"></a>

#### 29.8.4 辅助组件不是额外的“团队成员”

框架可能需要 gate、resolve、Artifact 检查等确定性组件；它们是运行步骤，不意味着用户必须额外安排人员或 Agent。界面应能折叠纯数据处理步骤，同时保留诊断入口。

“3 Agent＋1 个软件＋1 个人”的角色清单，不限制实际图中只能存在 5 个节点；同一角色可有多次调用，控制与验证步骤可多于参与者数。

<a id="sec-29-9"></a>

### 29.9 三种组合及变化方式

| 示例 | 组合方式 | 与框架关系 |
|---|---|---|
| 2 Agent＋1 人 | 一个生成 call、一个评估 call、受控人工 review；外围 repeat | 只是协作模板，不固化两 Agent |
| 3 Agent＋1 软件＋1 人 | 生成后两个 Agent 评估与一个程序检查并行；join all 后门槛与人工；外围 repeat | 复用相同契约、交接和调用规则 |
| 0 Agent＋多个人/程序 | 程序准备材料，多个明确人工请求顺序或静态并行，程序汇总 | 不需要引入模型才能运行 |

改变参与者数量通常意味着生成新的静态 Workflow/子流程版本和 Binding。只改变某个已声明 slot 的执行实现则只创建新的绑定/部署并重新验证。两者都不得改变活动 Run。

角色名称、用户任务和验收标准属于业务；示例中的报告和候选可替换为合同、数据、设计稿、代码提交或其他领域内容。新增第二种业务不应修改 Runtime。

参考三种参与者组合的完整 Workflow 示例及所有本地 Schema 见本规范附录 E；可机读文件随交付 ZIP 提供。参考 fixture 仅验证映射、分支与限定组合，不是真实 Agent、真人、并发调度或跨服务恢复验收。

<a id="sec-29-10"></a>

### 29.10 外部平台已有通信/协作时的适配

默认使用框架的标准输入、观察、产物和 Handoff。外部原生 SDK、HTTP、聊天 Session 或已有协议由 Adapter 转换，不要求工作流作者为每套流程重新实现它。

外部有完整循环时可整体作为一个 call，由外部管理内部协作；Multiverse 展示边界与可提供的内部事件。需要 Multiverse 控制每一步时，外部须暴露相应边界，或将步骤拆成明确 Workflow。

必须分别明确技术重试、业务返工循环、人工决定三种所有权。现有 retryOwner 仅定义自动执行重试，不能推导外部所有业务返工都已解决。接入说明必须记录哪个系统创建哪一类后续执行，并通过重复事件测试。

外部输出结构不一致时可以做受控映射；外部保证不足时显示真实等级并在需要时拒绝绑定。普通 404、断线或聊天未回复不能证明外部尚未执行。

跨平台通信能力不意味着可以继承原 Session 或全部知识权限。目标需要的业务材料显式提供，外部工作区和配置通过固定执行配置引用。

<a id="sec-29-11"></a>

### 29.11 运行控制、循环查看与人类操作

定义视图显示结构和契约，运行视图显示具体 Scope/Invocation/Attempt。人数与执行者变化不能破坏身份映射。

双击详情、单击摘要及键盘/触屏入口沿用统一控制台。循环详情分别展示业务轮次、执行尝试和 Agent 内部步骤。未到达的人工节点不能显示为已创建待办；整组失败或尚未运行不能聚合显示为成功。

运行状态只来自 Runtime 查询与事件；作者修改草稿、demo 事件与执行观察三个通道隔离。界面允许“开始”“暂停派发”“停止”“重新运行”，语义沿用本规范，不通过补丁将 status 改回 ready。

人工可在多个界面查看同一请求，但只产生一份有效决定。表单展示默认值不是提交；输出必须关联实际对象版本。软件审阅不自动授予人的最终批准权。

<a id="sec-29-12"></a>

### 29.12 Latent 与协作标准库的关系

标准库不以 latent、向量检索或共享黑板为前置条件。标准模式已经能构造所有已支持组合。

开启 latent 只改变已验证同 Scope call 路由的机器上下文。业务输入输出、必需约束、产物版本与人工决定保持显式。首版不支持跨 Scope/跨轮次隐式 latent 缓存；下一轮反馈使用明确的业务数据。

多 Agent 并行可以各自有独立合法路由，但同一目标最多一个 latent 来源；不得因“自由组合”自动拼接不同模型 KV。需要聚合时使用显式、经过验证的聚合能力，不突破原 profile 边界。

整个模板的 supported 标签不能替代各 route 的实际消费记录。外部不能消费时按预检或原失败/核对规则处理，不静默退回文本，关闭则不加载专属依赖。

<a id="sec-29-13"></a>

### 29.13 作者工具与扩展开发流程

作者输入应包含目标、验收和约束；作者读取已安装版本的协议、组件描述、能力/入口目录与样例，选择模板或从六种原语构建。组件目录是导航，不是安装授权。

必须提供以下可机器处理的结果：定义校验、Schema/数据流诊断、当前后端支持检查、Binding/权限检查、模板来源/展开 Diff、Fixture 结果、授权真实执行结果和交付依赖缺口。

每个诊断包含 code、file、pointer、severity、message、suggestion；可携带 expected/actual/details，但不能泄露机密。静态检查不得调用外部执行器。

业务作者只改包、Schema、策略参数和 Binding。首次平台适配由集成开发实现；新 Adapter 经过契约测试后注册，后续流程复用。作者可以生成待审阅实现代码，不能自动把它安装成可信执行器。

没有现成模板时，按已有原语构造仍然有效；没有表达能力时明确报告 UNSUPPORTED_FEATURE，而不是把自建线程/循环/状态数据库藏在配置里宣称已被 Runtime 管理。

<a id="sec-29-14"></a>

### 29.14 自由组合的边界与完整性检查

| 场景 | 首版表达方式/结论 |
|---|---|
| 任意角色命名、有限数量混合参与者 | 支持，受静态节点/分支/Scope/资源上限约束 |
| 顺序、分支、多轮业务返工 | call/next、switch、repeat |
| 多个静态检查同时执行 | parallel join all；聚合结论独立计算 |
| 人的长时间等待、外部异步执行 | 已注册 human/http_job 等调用生命周期；不是内存等待 |
| 复用一段流程、按领域定制 Schema | 包内 workflow 与版本化契约 |
| 条件需要网络、时间或模型判断 | 先通过显式已支持 call 得到持久结果，再 switch |
| 多数票提前结束、first-success、动态无限 fan-out | 不属于首版；不能用 all 汇合冒充 |
| 多人同一请求的会签/撤回 | 不属于单个 HumanRequest；多个独立请求可组合 |
| 自动从聊天生成并直接启用任意新节点 | 不支持；只允许新版本提案与受控发布 |
| 活动 Run 热替换实现/图、跨引擎活动迁移 | 不支持，使用新部署/新 Run 或独立迁移设计 |
| 任意外部平台、任意模型 latent 互通 | 不承诺；按 Adapter/Profile 与真实测试组合声明 |
| 无限等待、无限循环、无限上下文与无限预算 | 不支持；需要明确截止、上限和资源策略 |

“覆盖周到”指对支持与不支持的情况都定义行为，不是承诺所有可能场景都已经具备实现。

支持检查应遍历所有可达路径及引用的子 Workflow，检查必需组件、入口、Schema、权限、控制结构和依赖。避免前面已产生业务写入，后面才发现没有执行器或人工表单。

---

<a id="s30"></a>

## 30. Agent 优先开发与跨环境连续性

本章于修订 2.1.0 新增，将 Agent 第一开发者、可移植接入与会话切换要求纳入唯一规范。研究依据见 `docs/research/2026-09-26-portability-and-agent-authoring.md`；研究不是第二份规范。本章冻结行为边界，不宣称相应执行宿主、通道或迁移接口已经实现。

### 30.1 第一开发者与权威源

框架的第一开发者是 Agent。Workflow Package 文件、业务 Schema 与 Binding 是开发入口；CLI/API 必须支持主要编写、验证、试验和审阅准备操作，不能要求拖图才能获得完整功能。作者 Agent 与运行 Agent 的授权仍按第 20.6 节分离。

图形界面辅助理解、审阅、人工任务和编辑。GUI 修改必须回到同一资源模型、编译器、诊断及版本冲突规则。布局信息不得改变执行语义；活动 Run 继续绑定原快照。Agent 不必每次读取整份规范，Authoring Kit 应提供短入口和按需契约导航。

作者路径为：发现可用能力 → 先定义交付与 Schema → 生成/局部修改包 → Validate → 预检 → Fixture/授权实测 → 语义 Diff → 有权主体审阅与部署。尚未实现的动作必须标为未支持，不用可运行形式伪造命令。

### 30.2 编写准确性与效率

资源和节点使用稳定 ID，小文件与显式依赖；局部修改不应产生无关全文重排。每种可安装执行配置应有版本化配置 Schema、输入输出契约、副作用与恢复保证；缺失能力形成待绑定清单，不能编造 executorRef。

机器输出必须能区分语法有效、注册能力匹配、实时可用、授权充分和业务验收通过。诊断包含稳定错误码、源文件与 JSON Pointer，必要时给出 expected/actual、修复建议和依赖节点。能独立确认的错误尽量聚合；stdout 只含机器结果，日志写 stderr。

语义 Diff 应覆盖节点/边、Schema、能力、副作用、授权、依赖、会话/工作区策略与验收变化，固定基线摘要并处理并发修改。任何自动建议不得通过降低验收或绕过人类角色使测试通过。

作者效率以固定任务集记录首次验证通过率、修复回合、Token、时间和错误授权次数；失败计入分母。速度目标不得覆盖权限与结果正确性要求。

### 30.3 本地只读预检的已冻结子集

`mverse preflight <package> --binding <binding> [--json]` 为本地注册元数据预检。必须复用编译器和 Runtime 注册表检查，不启动 Runner、创建 Run/数据库、运行节点、探测网络或解析凭据。检查包内全部 Workflow，包括嵌套调用目标。

输出遵循 `schemas/preflight-report.schema.json`：`reportVersion=multiverse.preflight/v0.1`、`scope=local-registry`、`ok`、`checked`、`notChecked`、`planDigests` 和 `diagnostics`。`checked` 表示已执行检查阶段，不表示每项通过；静态校验提前失败时注册表阶段位于 `notChecked`。`ok=true` 只表示本次检查未发现问题，不是授权、实时健康或可部署证明。

退出码 0 表示本子集通过，2 表示校验/预检问题；命令行参数使用错误仍按 CLI 处理。检查使用同一注册表快照；编译后 Binding 摘要变化以 `BINDING_CHANGED_DURING_PREFLIGHT` 拒绝。报告不锁定磁盘文件，执行前 Runtime 必须重新校验。配置、凭据、真实网络、权限/沙箱实施、人工送达和业务质量都保持未检查，不能默默视为成功。

已有编译诊断继续使用第 6 章规则。注册状态错误使用 `EXECUTOR_NOT_INSTALLED`、`EXECUTOR_UNAVAILABLE`、`EXECUTOR_UNVERIFIED`，给出 Binding 的 executorRef 指针、工作流/节点/slot 和源定义位置。报告不回显 Binding 配置或 Secret 明文；本命令只在调用者已有本地文件权限下运行，不构成多租户公开查询接口。

该子集不关闭 G-15，也不宣称完整部署预检完成。本地进程目录中的 `permissionLevel=trusted_local` 表示继承 Worker 用户权限；禁止标为已实施沙箱。

### 30.4 可移植交付与宿主接入

可移植性包含业务契约、执行依赖、人工入口、身份/资源映射、产物与测试闭环。换目标时应保留业务包摘要，通过目标 Binding 配置执行位置、身份、凭据引用、工作区和通道；不支持的能力在派发前报告。

独立服务、Python 内嵌和宿主 HTTP 集成必须复用同一应用命令/查询语义。宿主只需映射身份、业务对象和呈现，不能直接修改 Ledger。UI 组件是可选客户，不掌握状态权威。客户端卸载释放订阅，不撤销已经持久化的 Run。具体认证委托/组件 ABI 仍由 G-15 冻结。

宿主适配后的第二套业务不得要求改 Compiler、Runner 或通用宿主 Glue；否则记录兼容缺口。跨平台支持声明必须至少包含独立运行、真实宿主与干净目标交付证据，不能由导出一个 JSON 或嵌入 iframe 替代。

### 30.5 通道、程序与执行端分离

飞书等人类通道投递同一个 HumanRequest，维护外部消息、请求、主体与版本关联。回调由通道验证来源、抵御重放并映射真实主体，再提交同一 decision 命令；应用机器人身份不冒充批准人。先持久接收，再异步处理和更新卡片；重复、过期、转发、撤销和投递失败有明确状态。具体 API/期限按被接入版本核验，不在此猜定。

飞书文档/表格写入属于程序/外部服务动作，独立于人类通道授权和生命周期。消息送达不等于任务完成，群成员身份不等于审批权限。没有飞书时，独立人工入口仍可用。

远程 Connector 采用第 28 章的出站、受限注册与持久派发关联。一个目标可提供多个 CLI；用户明确选取可管理实例和目录，不能扫描并接管未授权原生会话。原生 SDK/RPC 优先于终端文本抓取。MCP/ACP/A2A/AG-UI 均通过适配与版本协商接入，不改变 Runtime 事实权威。

### 30.6 身份与会话基数

AgentIdentity 是 namespace 内长期身份，AgentProfileRevision 是不可变行为配置；两者不等于一次模型实例或会话。一个身份可以有多个配置修订、会话分支和执行位置。CollaborationThread 表达跨人/Agent 的业务上下文，不直接复用某 CLI 的 session ID。

AgentSession 表达授权 scope 内的上下文分支；NativeSessionBinding 关联原生 provider、执行安装/存储身份、原生 session ID 和兼容版本，并保留生效历史。无状态执行可以没有持久原生 session；有状态 turn 必须记录其实际关联。原生 session ID 不保证全局唯一，不得脱离 provider/存储身份查询。

默认按任务隔离。复用必须显式声明任务/项目范围和可读材料；同一 Agent 名称不授予跨项目或跨主体读取历史的权力。Invocation/Attempt 保持原有执行身份，与 session/turn 记录关联，不能彼此替代。

### 30.7 新建、恢复、分叉和续接

| 模式 | 规则 |
|---|---|
| 新建 | 只注入显式任务输入、授权产物与可选获准记忆；禁止自动使用工作目录最新 session。 |
| 原生恢复 | 后端已证明支持恢复，并验证原生存储、兼容版本、工作区、权限上下文与历史访问权。 |
| 原生分叉 | 后端已证明支持从可识别 checkpoint 分叉，生成新关联；不自动复制文件系统或批准事实。 |
| 可移植续接 | 建立目标新原生 session，注入经过授权的任务目标、约束、已确认事实、产物、未决问题与下一步；记录来源和丢失信息。 |

跨 CLI 默认使用可移植续接，不能宣称原生 session/推理状态/进程无损转换。跨机器原生恢复只在具体后端、文件与原生存储完整性和授权均验证后提供。相同路径不是工作区相同的证据。

旧 session 仍有运行任务、工具结果不明或取消未确认时，必须先核对，不得通过新建/分叉/更换机器重做同一副作用。已完成旧任务的后续需求形成新的 Invocation，不改写旧完成事实。

### 30.8 切换与协作一致性

会话/执行端切换顺序：停止新派发 → 核对在途 Attempt/工具动作 → 固定上下文与产物、工作区基线 → 检查目标策略和材料访问 → 准备目标关联 → 以版本比较更新与 fencing token 切换 → 取得单写租约后继续。

切换失败不能丢失旧关联或把目标标为已经生效。并发切换只有一个版本更新成功；过期 token 的迟到观察留审计但不得推进新的执行。租约过期或心跳消失不证明旧进程已经停止，仍遵守 unknown 核对规则。具体台账、租约、撤销与操作 API 由 G-17 冻结。

同一原生会话默认单写；多 Agent 协作共享显式产物和授权事实，各自持有上下文。并行工作默认独立可写副本；共享写目录须明确协调。合并文件是有输入、diff、验证和产物的显式操作，不把合并聊天记录当作完成协作。

### 30.9 记忆独立与上下文授权

Memory 生命周期独立于 AgentSession；namespace 至少表达租户/主体/项目访问边界，不能仅按 agentId 查询。长期身份连续不要求一条无限增长的 transcript。个人偏好、Agent 经验、项目知识和组织知识按实际授权区分。

记录具有来源、版本、作用域和保留/删除策略。实际注入的记录、版本、裁剪与引用进入 Context 快照；并发写入先形成候选/版本化更新，不能默默覆盖冲突。未经验证的记忆不能成为审批、执行完成或路由事实。外部知识可按授权原地查询，不强制集中迁移。V0.1 默认关闭语义检索不变。

权限收窄时已进入旧原生历史的信息不能通过工具禁用撤回。必须重新检查历史和检索权限，必要时用获准材料创建干净上下文，撤销旧上下文的后续访问；不声称能抹除第三方已经收到的资料。新的资料权限也不会自动追认旧审批。

### 30.10 执行策略与沙箱不足

有效授权取组织/租户、调用主体、部署 Binding、工作区、执行端与工具服务约束的交集。沙箱是技术隔离，Policy 是授权，审批是具体动作许可，三者分开记录。执行端必须报告实际实施者和保证，不得将 Prompt、审批开关或容器名称当作沙箱证明。

可信单用户本机可明确选择 trusted local；多人、不可信代码、Agent 生成代码须采用并验证符合要求的隔离环境。已经由外层容器/VM 实施的隔离可以复用，但必须提供相应证据。纯服务调用可以不创建代码沙箱，仍受凭据、工具、网络和业务授权约束。

权限不足应分类诊断：挂载/依赖、网络、工具 scope、OS 身份、策略拒绝或能力不支持。优先在已有授权内修复环境、使用窄能力代理或选择合适执行端；不得自动关闭沙箱、扩大授权或无限重试。需要新增权限时持久化权限请求；记录具体动作/资源/主题摘要、策略版本、时限和次数，由有权主体决定。

批准后冻结并实施新策略，再重新预检、恢复或创建上下文；旧审批不自动跨工作区、身份、策略 revision 或输入变化复用。外部系统本身禁止的权限不能由平台审批绕过。部署/发布等高权限操作优先拆为受控程序节点。具体策略映射和沙箱后端继续受 G-05/G-18 限制。

### 30.11 新增验收

| ID | 场景 | 必须证据 |
|---|---|---|
| PORT-01 | Agent 独立完成文件编写与修改 | 无 GUI 必需步骤；发现、Validate、预检、测试与审阅材料可由 CLI/API 完成；未实现步骤明确拒绝。 |
| PORT-02 | 第二流程与第二目标 | 同宿主无需新 Glue；跨目标保留业务包，仅换 Binding；缺口在派发前呈现。 |
| PORT-03 | 本地注册预检 | 正例/反例、稳定 JSON、节点定位、无数据库/执行/网络副作用，未检查项准确。 |
| PORT-04 | 原生恢复与跨 CLI 续接 | 同后端恢复证据、跨后端新关联与来源链；不复制旧批准。 |
| PORT-05 | 并发与失联切换 | CAS/单写租约/迟到观察/unknown 写入核对；无重复派发。 |
| PORT-06 | 工作区及权限变化 | 重新校验、隔离并行写入、清理越权历史、策略实施与可解释拒绝。 |
| PORT-07 | 飞书两种接入 | 人工主体不被程序身份替代；重复回调、失效卡片、断线投递和真实写入去重。 |
| PORT-08 | 作者效率与辅助编辑 | 固定任务集完整统计；GUI 往返保持业务语义；并发编辑冲突可发现。 |

现有原型只实现 PORT-03 的本地注册子集及相关元数据准确性。其他项目按第 24 章纵向阶段逐步验收，不能由文档或 mock 代替真实证据。

---

<a id="appendix-a"></a>

## 附录 A. 规范性参考样例

以下 `file:` 标记给出目标仓库内的文件路径。它们是实现协议与测试时的基准输入，不表示 Runtime、公开包或外部账号已经存在。工作流包内文件与环境 Binding 分开放置。

### A.1 包 Manifest

<!-- file: presets/content-delivery/manifest.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: content-delivery
  version: 0.1.0
  description: 生产、验证并由人审阅一份可交付内容。
spec:
  workflows:
    delivery: workflows/delivery.yaml
  entrypoints: [delivery]
  requiredFeatures:
    - core.call
    - core.switch
    - core.human
  evalSuites:
    - evals/suite.yaml
```

### A.2 完整 Workflow

<!-- file: presets/content-delivery/workflows/delivery.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: delivery
  version: 0.1.0
spec:
  inputSchema: schemas/request.json
  outputSchema: schemas/final-output.json
  entry: produce
  defaults:
    runDeadlineSeconds: 604800
    callDeadlineSeconds: 3600
    maxAttempts: 1
    maxConcurrency: 4
  nodes:
    produce:
      type: call
      title: 生成交付物
      slot: producer
      inputSchema: schemas/request.json
      outputSchema: schemas/deliverable.json
      input:
        ref: input#
      requires:
        capabilities: [content.produce@1]
      effects:
        class: write
        actions: [content.produce]
      retry:
        maxAttempts: 1
      next: verify

    verify:
      type: call
      title: 校验内容契约
      slot: verifier
      inputSchema: schemas/deliverable.json
      outputSchema: schemas/verification.json
      input:
        ref: nodes.produce.output#
      requires:
        capabilities: [data.validate@1]
      effects:
        class: none
        actions: []
      next: verify-route

    verify-route:
      type: switch
      cases:
        - id: valid
          when:
            op: eq
            left: {ref: "nodes.verify.output#/valid"}
            right: {literal: true}
          next: review
      default: invalid

    review:
      type: call
      title: 人工审阅
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

    review-route:
      type: switch
      cases:
        - id: approved
          when:
            op: eq
            left: {ref: "nodes.review.output#/decision"}
            right: {literal: approve}
          next: complete
      default: rejected

    complete:
      type: end
      outcome: succeeded
      output:
        object:
          deliverable: {ref: "nodes.produce.output#"}
          review: {ref: "nodes.review.output#"}

    invalid:
      type: end
      outcome: failed
      error:
        code: DELIVERABLE_INVALID
        message: 交付物未通过本工作流要求的校验。

    rejected:
      type: end
      outcome: failed
      error:
        code: DELIVERABLE_REJECTED
        message: 审阅人拒绝了当前版本的交付物。
```

路径解析约定：Workflow 中的 `inputSchema`、`outputSchema`、资源引用均相对**包根目录**，不是相对 YAML 所在目录。JSON Schema 内的 `$ref` 按 Schema 文件自身位置解析。二者不能混用。

此样例不自动发布外部内容，也不在拒绝后暗中重新生成。需要业务修订时使用另一个显式 repeat 工作流，而不是复用 transport retry。

### A.3 业务 Schema

<!-- file: presets/content-delivery/schemas/request.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["goal"],
  "properties": {
    "goal": {"type": "string", "minLength": 1, "maxLength": 8000}
  }
}
```

<!-- file: presets/content-delivery/schemas/deliverable.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["text", "artifact_refs"],
  "properties": {
    "text": {"type": "string", "minLength": 1, "maxLength": 100000},
    "artifact_refs": {
      "type": "array",
      "maxItems": 100,
      "items": {"type": "string", "minLength": 1}
    }
  }
}
```

<!-- file: presets/content-delivery/schemas/verification.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["valid", "findings"],
  "properties": {
    "valid": {"type": "boolean"},
    "findings": {"type": "array", "items": {"type": "string"}}
  }
}
```

<!-- file: presets/content-delivery/schemas/review-input.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["deliverable", "verification"],
  "properties": {
    "deliverable": {"$ref": "deliverable.json"},
    "verification": {"$ref": "verification.json"}
  }
}
```

<!-- file: presets/content-delivery/schemas/review-output.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["decision", "comment"],
  "properties": {
    "decision": {"type": "string", "enum": ["approve", "reject"]},
    "comment": {"type": "string", "maxLength": 8000}
  }
}
```

<!-- file: presets/content-delivery/schemas/final-output.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["deliverable", "review"],
  "properties": {
    "deliverable": {"$ref": "deliverable.json"},
    "review": {"$ref": "review-output.json"}
  }
}
```

ArtifactRef 必须在运行边界解析为第 14 章的真实授权对象。样例只使用其 opaque ID 字符串，不能把任意字符串当作已经验证的产物。

### A.4 环境 Binding：本地确定性实现

<!-- file: examples/bindings/content-local.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: BindingSet
metadata:
  name: content-local
  version: 0.1.0
spec:
  slots:
    producer:
      adapter: builtin
      executorRef: example.content-fixture.v1
      config: {}
      secretRefs: {}
      grants:
        - action: content.produce
          resource: namespace:demo
    verifier:
      adapter: builtin
      executorRef: builtin.nonempty-deliverable.v1
      config: {}
      secretRefs: {}
      grants: []
    reviewer:
      adapter: human
      executorRef: builtin.human-review.v1
      config:
        requestType: review
        choices: [approve, reject]
        authorizedSubjects: [example-reviewer]
        requireCommentFor: [reject]
      secretRefs: {}
      grants: []
```

这组注册 ID 是需要在示例运行环境中实现并预注册的 ID，不是已发布的现成服务。fixture 只生成固定结构内容，用于协议测试，不能当作真实 Agent 效果展示。

`grants` 每项严格为 `{action: string, resource: string}`，资源解析由环境注册的 Policy 实现，默认精确匹配，不支持隐式通配提升权限。

Human config 固定支持 requestType、choices、authorizedSubjects、requireCommentFor。choices 必须与输出 Schema 的 decision 枚举一致；服务端生成 subject，不能由 config 伪造。example-reviewer 是需配置的已验证主体，不是公开默认密码或自动批准身份。

### A.5 环境 Binding：远程实现

<!-- file: examples/bindings/content-remote.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: BindingSet
metadata:
  name: content-remote
  version: 0.1.0
spec:
  slots:
    producer:
      adapter: http_job
      executorRef: example.remote-content.v1
      config: {}
      secretRefs:
        authorization: secret://demo/remote-content-token
      grants:
        - action: content.produce
          resource: namespace:demo
    verifier:
      adapter: builtin
      executorRef: builtin.nonempty-deliverable.v1
      config: {}
      secretRefs: {}
      grants: []
    reviewer:
      adapter: human
      executorRef: builtin.human-review.v1
      config:
        requestType: review
        choices: [approve, reject]
        authorizedSubjects: [example-reviewer]
        requireCommentFor: [reject]
      secretRefs: {}
      grants: []
```

远程 endpoint、TLS 和支持的 Schema 通过运营者 Executor Registry 注册。`secret://...` 是引用语法，实际 Secret Provider 未配置时必须预检失败。这个 Binding 没有硬编码进 Workflow，也不加入包的实际环境配置。

本地与远程实现应使用同一 `request.json` / `deliverable.json` 对外契约；remote 可以接 Agent、现成服务或任何满足契约的系统，而不是特定品牌专用接口。

### A.6 数据集与门禁

<!-- file: presets/content-delivery/evals/cases.jsonl -->
```jsonl
{"case_id":"basic-delivery","input":{"goal":"生成一段说明工作流输入、执行和验收关系的文本。"},"expected":{"review_decision":"approve"},"tags":["smoke"]}
{"case_id":"alternative-topic","input":{"goal":"生成一份简短的数据质量检查说明。"},"expected":{"review_decision":"approve"},"tags":["portability"]}
```

<!-- file: presets/content-delivery/evals/suite.yaml -->
```yaml
version: 1
workflow: delivery
dataset: evals/cases.jsonl
evaluators:
  - id: builtin.output-schema.v1
    config: {}
  - id: builtin.field-equals.v1
    config:
      outputPointer: /review/decision
      expectedPointer: /review_decision
gate:
  requiredPassRate: 1.0
  maxUnknown: 0
  allowMissingCost: true
```

Suite 不是顶层可导入资源，使用上述独立文件结构。dataset 路径相对包根；expectedPointer 相对该 case 的 expected。门禁先要求 Run succeeded，再聚合 evaluator；失败 Run 不因没有 output 而被跳过。

这些用例经过人工节点，运行时会等待真正的授权决定。CI 可以用明确的测试身份通过相同决策 API 提交预置决定，但报告必须标记 fixture 决策，不能冒充真实人工评价。

### A.7 控制节点的规范形状

下列是节点片段，不是完整可导入包。引用的子流程需要随实际包定义。

```yaml
# 同一输入交给两个显式子流程；两个都成功才汇合。
inspect:
  type: parallel
  title: 并行检查
  join: all
  maxConcurrency: 2
  branches:
    format:
      workflow: check-format
      input: {ref: "input#"}
    content:
      workflow: check-content
      input: {ref: "input#"}
  next: route

# 子流程输出含 valid 与 data；下一轮只传递规定的 input。
repair:
  type: repeat
  workflow: repair-round
  input:
    object:
      data: {ref: "input#/data"}
  maxIterations: 3
  until:
    op: eq
    left: {ref: "iteration.output#/valid"}
    right: {literal: true}
  feedback:
    object:
      data: {ref: "iteration.output#/data"}
  next: summarize

summarize:
  type: workflow
  workflow: summary
  input: {ref: "nodes.repair.output#"}
  next: complete
```

第二 Preset 的最小业务定义：输入为 `{data: ...}`；check-format 与 check-content 输出各自 `{valid, findings}`；route 根据两条分支决定是否进入 repair；repair-round 输出 `{data, valid, findings}`；summary 产生统一质量报告。修正算法由已注册程序或外部执行器实现，不增加核心协议字段。

成功分支不允许读取根本没有执行的 repair.output。实际第二 Preset 必须在分支内部完成报告映射，或将可选修正封装进输出契约一致的子流程，遵守第 7.9 节的数据路径规则。

### A.8 最低 Adapter Contract 测试

通用 HTTP 示例执行器必须使用自己的持久表，将 dispatchKey 与包含 inputDigest、冻结 Context、输出契约和授权主题的语义请求指纹原子绑定；重复 submit 返回同一 executionRef；测试开关可在“创建后响应前”断开连接，用于 AC-09。

它至少提供 accepted→running→succeeded、明确失败、延迟取消确认、unknown、重复 revision、相同 revision 冲突、输出 Schema 不合法等可控行为。该示例只验证契约，不代表某个实际模型或远程服务已经具备同样保证。


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

---

<a id="appendix-b"></a>

## 附录 B. 一致性校验与首日施工清单

### B.1 首日需要产生的文件和测试

在 M0 中创建资源 Schema、ValueExpr/Predicate 类型、通信开关 Schema、附录 A 的真实样例文件，以及至少以下测试：合法包、缺失 slot、重复 YAML 键、悬空边、同级环、缺失数据引用、无默认 switch、非法 repeat 上限、未实现 requiredFeature、私密配置误入归档、通信缺省关闭、字符串布尔值拒绝、开启而无 routes 拒绝、关闭时不加载 latent 依赖。

下面给出 ValueExpr 的完整结构 Schema。它只校验表达式形状；引用是否在允许 scope、是否可达、Pointer 是否存在仍由语义校验器处理。

<!-- file: schemas/value-expr.schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Multiverse ValueExpr v0.1",
  "$ref": "#/$defs/value",
  "$defs": {
    "value": {
      "oneOf": [
        {
          "type": "object",
          "required": ["literal"],
          "properties": {"literal": {}},
          "additionalProperties": false
        },
        {
          "type": "object",
          "required": ["ref"],
          "properties": {"ref": {"type": "string", "minLength": 1}},
          "additionalProperties": false
        },
        {
          "type": "object",
          "required": ["object"],
          "properties": {
            "object": {
              "type": "object",
              "additionalProperties": {"$ref": "#/$defs/value"}
            }
          },
          "additionalProperties": false
        },
        {
          "type": "object",
          "required": ["array"],
          "properties": {
            "array": {
              "type": "array",
              "items": {"$ref": "#/$defs/value"}
            }
          },
          "additionalProperties": false
        }
      ]
    }
  }
}
```

### B.2 规范计划的最小接口

`compile(package, binding_snapshot, feature_set) -> ExecutionPlan`。

ExecutionPlan 必须包括 plan_version、package_digest、binding_digest、workflow_id、输入输出 Schema 摘要、全部节点的规范化字段、显式默认值、边/子流程关系、source_map、required_features、显式通信模式、route/profile 摘要和 compiled_plan_digest。

source_map 将节点、条件、输入映射与源文件 JSON Pointer 对应。Inspector 错误和测试失败必须能反查源位置，而不是只暴露编译生成的随机节点名。

计划内容必须可序列化和持久化，不包含 Python callable、连接池、Secret 明文或 LangGraph 私有对象。具体可调用实现由已安装 backend/adapter 在运行时装配。

### B.3 首次纵向演示的判定

用附录 A 的本地 Binding 产生结果，经校验后进入人工请求；以被授权身份批准，得到 final-output；以拒绝身份路径得到明确失败。然后只替换 producer Binding 到通用 HTTP 示例执行器，重复同一用例；杀死并重启 Worker，运行仍能找到同一外部引用。

这证明最小范式、契约与恢复链路，不证明真实 Agent 的业务质量。随后以真实执行器完成 AC-41，保存独立报告。

### B.4 文档与实现的检查边界

本文中的 JSON/YAML 可以在编写阶段做语法、引用、Schema 和结构检查。这些静态检查不等于 Runtime 已经实现，亦不等于任何故障恢复、服务性能、安全隔离或业务质量已经通过测试。

开发完成后的报告必须引用具体代码 commit、依赖锁文件、测试环境、用例 ID 和结果；禁止仅凭本规范自称通过认证。

---

<a id="appendix-c"></a>

## 附录 C. 来源与修订记录（非当前第三方能力审计）

### C.1 来源基线

| 代码 | 文件 | 修订/用途 |
|---|---|---|
| B | MULTIVERSE_SPEC.md | 1.1.0，执行协议、状态、安全与基础交付基线 |
| S | MULTIVERSE_APPEND_SPEC.md | 1.0.0，作者、人工、程序和 I/O 补充 |
| R | MULTIVERSE_RUNTIME_INTEGRATION_DELIVERY_SPEC.md | 1.0.0，受管/远程/统一控制台与完整交付 |
| T | MULTIVERSE_GUIDE_SPEC3.md | 1.0.0，本轮通用组合和标准库新设计 |
| I | 初始架构方案、技术与参考选型草案 | 只核对统一边界、独立交付和复用基础设施的原始意图，不恢复过时阶段安排 |

B/S/R/T 的输入文件摘要及迁移映射见附录 G。未发现另一份已独立形成的“Spec3”；本轮第三追加按该编号交付。合并版是唯一后续权威；原文件保留原样供历史追溯。

### C.2 沿用的外部参考标识

以下资料列表从原主规范沿用，用于来源追溯。本轮没有联网核验最新功能、许可证或版本；实现者以锁定版本和实际许可/测试检查为准。它们不覆盖正文的明确契约。

以下为修订 1.0.0 记录的资料（基准日期 2026-09-19），只支撑正文中标注的第三方能力、协议或许可事实；不替代本文的项目决策。官方文档后续变化不自动改变本规范或锁文件。

| 编号 | 来源 | 地址与用途 |
|---|---|---|
| E1 | LangGraph Persistence | `https://docs.langchain.com/oss/python/langgraph/persistence`；持久 saver 与 Checkpoint |
| E2 | LangGraph Interrupts | `https://docs.langchain.com/oss/python/langgraph/interrupts`；中断恢复与节点重入 |
| E3 | JSON Schema Draft 2020-12 Core | `https://json-schema.org/draft/2020-12/json-schema-core`；Schema 规范版本 |
| E4 | React Flow Layouting | `https://reactflow.dev/learn/layouting/layouting`；外部布局库与 ELK |
| E5 | OpenTelemetry Sampling | `https://opentelemetry.io/docs/concepts/sampling/`；观测可采样，与权威事件区分 |
| E6 | Langfuse Self-hosting | `https://langfuse.com/self-hosting`；自托管组件与部署边界 |
| E7 | RFC 6901 JSON Pointer | `https://www.rfc-editor.org/rfc/rfc6901`；路径读取语义 |
| E8 | PostgreSQL Explicit Locking | `https://www.postgresql.org/docs/17/explicit-locking.html`；锁与 advisory lock |
| E9 | RFC 8785 JCS | `https://www.rfc-editor.org/rfc/rfc8785`；规范化 JSON 摘要 |
| E10 | ELK.js LICENSE | `https://github.com/kieler/elkjs/blob/master/LICENSE.md`；EPL-2.0 |
| E11 | Langfuse LICENSE | `https://github.com/langfuse/langfuse/blob/main/LICENSE`；许可范围例外 |

### C.3 本轮编制与检查边界

本轮进行文档合并、编号/引用/来源覆盖检查、规范样例解析、业务 Schema 正反例和限定的组合模拟。不运行真实模型、网络 Adapter、飞书、Connector、LangGraph 故障恢复或目标部署。检查脚本和报告随交付材料提供；报告具体列明哪些测试属于本轮静态/Fixture。

新增标准库描述和纯组件语义在第 29 章明确标为本轮设计；G-01—G-16 仍按门禁收敛。没有以文字“详细完整”替代尚需实现的线级接口。

---

<a id="appendix-d"></a>

## 附录 D. 人工业务契约与程序包装参考

以下内容用于说明追加要求，不是一份完整可独立部署的 Workflow Package。`file` 路径是目标样例路径，`node fragment` / `binding fragment` 是合并位置；省略的 Workflow、其他 slots、注册对象、权限和文件须按本规范补齐。

示例业务字段不成为核心协议字段。样例中的 Artifact ID、执行器 ID 和身份是占位值，不代表已经存在或有权访问。真实运行必须解析与验证。

### D.1 统一的人工审阅节点

此节点沿用本规范 call 形状；只有 Binding 决定具体采用内建人工页面还是符合相同要求的外部人工服务。

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

### D.2 人工完成工作并提交文件

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

`example.manual-editor.v1` 与 `example-editor` 必须在示例环境中预注册并验证。这个片段使用本规范已有 Human config 字段；没有假设新增页面 URL 字段已经存在。人工任务是否涉及外部业务副作用，应在实际节点 effects 中按真实语义声明。

提交到既有 HumanRequest decision 接口时，业务结果位于 decision 中；expectedVersion、subjectDigest 和 Idempotency-Key 由客户端按真实请求获取并提交。下面只展示 decision 的值，不是完整 HTTP 请求：

<!-- example: manual-decision-value -->
```json
{
  "artifact_refs": ["example-artifact-id"],
  "change_summary": "修正术语，补充缺失章节，并更新引用。"
}
```

该样例可通过业务形状检查，但真实运行中占位 Artifact ID 不应通过存在性/授权校验。测试必须将这两个层次分开。

### D.3 固定程序输出的是业务结论

<!-- example: verification-business-output -->
```json
{
  "valid": false,
  "findings": ["交付物缺少必需章节"]
}
```

该对象符合本规范示例的 verification Schema。它表示校验已执行但交付物不满足业务要求，不意味着进程崩溃。Runtime 根据显式 switch 路由，而不是自动重试校验器或改写 valid。

### D.4 最小边界用例

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

<a id="appendix-e"></a>

## 附录 E. 不固定参与者数量的完整规范样例

### E.1 适用范围与运行条件

本附录把新增的标准库参考 Schema 和三个可组合入口完整收入唯一规范；相同字节的 YAML/JSON 同时位于 `examples/generic-collaboration/`。无 ZIP 时可按标注路径还原文件，不需要查旧补充来补齐定义。

| 入口 | 业务参与者 | 结构与说明 |
|---|---|---|
| `two-agent-human` | 两个 Agent 与一人 | 生产、评估、可选人工、单轮结果；外层有界 repeat。 |
| `three-agent-human` | 三个 Agent、一个程序和一人 | 生产后两个 Agent 评估及一个程序检查并行；全汇合再处理人工与业务结论。 |
| `program-human` | 程序和人，无 Agent | 程序准备材料、人工交付、程序检查；使用普通子 Workflow。 |

参与者数量不包括纯 gate/resolve 辅助步骤；增加辅助程序节点不是新增一个必须存在的团队角色。例子不是唯一可用拓扑。

本附录是规范性参考输入，不是已经在现有仓库版本部署成功的成品。`example.*`、测试身份和资源范围是占位配置；真实使用必须安装相应 Executor、绑定身份和资源，检查全部 requiredFeatures，再进行独立真实验收。组件名称出现不构成“已安装”证据。

跨分支结果通过统一 RoundResult 返回，自动分支显式使用 null 人工决定，不读未执行节点；循环退出和业务成功分别判断。并行失败/取消遵守第 7/11/12 章，不以本附录的顺序 Fixture 模拟代替真实并发保证。

`program-human` 的最终输出是一份已完成的检查报告；执行成功只表示报告已合法交付，不自动表示报告的 verdict=pass。需要强制通过时，作者按第 7.4 节显式增加 switch。

SchemaRef 中 `$ref` 只解析包内文件。SubjectRef 的内容摘要和 ID 仅定义形状，真实执行还须检查对象存在、版本和权限；Fixture 用模拟元数据，不证明真实 Artifact 或真人身份。

### E.2 包 Manifest

<!-- embedded-file: examples/generic-collaboration/manifest.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: WorkflowPackage
metadata:
  name: generic-collaboration
  version: 1.0.0
  description: 规范示例；Fixture 验证不等于真实模型或生产 Runtime 验收。
spec:
  workflows:
    program-check: workflows/program-check.yaml
    program-human-body: workflows/program-human-body.yaml
    program-human: workflows/program-human.yaml
    review-a: workflows/review-a.yaml
    review-b: workflows/review-b.yaml
    three-agent-human: workflows/three-agent-human.yaml
    three-agent-round: workflows/three-agent-round.yaml
    two-agent-human: workflows/two-agent-human.yaml
    two-agent-round: workflows/two-agent-round.yaml
  entrypoints:
  - two-agent-human
  - three-agent-human
  - program-human
  requiredFeatures:
  - core.call
  - core.switch
  - core.human
  - core.repeat
  - core.parallel
  - core.nested
```

### E.3 业务契约与组件描述 Schema

第 29.8 节固定参考辅助组件的业务语义；这些 Schema 不能替代主体真实性、资源授权和契约语义校验。

#### E.3.1 `subject-ref.json`

<!-- embedded-file: examples/generic-collaboration/schemas/subject-ref.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "artifactRef": {
      "type": "string",
      "minLength": 1
    },
    "digest": {
      "type": "string",
      "pattern": "^sha256:[0-9a-f]{64}$"
    }
  },
  "required": [
    "artifactRef",
    "digest"
  ],
  "additionalProperties": false
}
```

#### E.3.2 `feedback.json`

<!-- embedded-file: examples/generic-collaboration/schemas/feedback.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "source": {
      "type": "string",
      "minLength": 1
    },
    "code": {
      "type": "string",
      "minLength": 1
    },
    "message": {
      "type": "string",
      "minLength": 1
    },
    "subject": {
      "$ref": "subject-ref.json"
    }
  },
  "required": [
    "source",
    "code",
    "message"
  ],
  "additionalProperties": false
}
```

#### E.3.3 `brief.json`

<!-- embedded-file: examples/generic-collaboration/schemas/brief.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "objective": {
      "type": "string",
      "minLength": 1
    },
    "constraints": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "acceptanceCriteria": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "minItems": 1
    },
    "materials": {
      "type": "array",
      "items": {
        "$ref": "subject-ref.json"
      }
    },
    "feedback": {
      "type": "array",
      "items": {
        "$ref": "feedback.json"
      }
    }
  },
  "required": [
    "objective",
    "constraints",
    "acceptanceCriteria",
    "materials",
    "feedback"
  ],
  "additionalProperties": false
}
```

#### E.3.4 `product.json`

<!-- embedded-file: examples/generic-collaboration/schemas/product.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "materials": {
      "type": "array",
      "items": {
        "$ref": "subject-ref.json"
      },
      "minItems": 1
    },
    "summary": {
      "type": "string",
      "minLength": 1
    },
    "evidenceRefs": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      }
    }
  },
  "required": [
    "materials",
    "summary",
    "evidenceRefs"
  ],
  "additionalProperties": false
}
```

#### E.3.5 `report.json`

<!-- embedded-file: examples/generic-collaboration/schemas/report.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "subjects": {
      "type": "array",
      "items": {
        "$ref": "subject-ref.json"
      },
      "minItems": 1
    },
    "verdict": {
      "enum": [
        "pass",
        "revise",
        "reject"
      ]
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          },
          "severity": {
            "enum": [
              "blocker",
              "major",
              "minor",
              "info"
            ]
          },
          "message": {
            "type": "string",
            "minLength": 1
          },
          "evidenceRefs": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1
            }
          }
        },
        "required": [
          "id",
          "severity",
          "message",
          "evidenceRefs"
        ],
        "additionalProperties": false
      }
    },
    "revisionRequests": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "evidenceRefs": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      }
    }
  },
  "required": [
    "subjects",
    "verdict",
    "findings",
    "revisionRequests",
    "evidenceRefs"
  ],
  "additionalProperties": false
}
```

#### E.3.6 `human-input.json`

<!-- embedded-file: examples/generic-collaboration/schemas/human-input.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "objective": {
      "type": "string",
      "minLength": 1
    },
    "constraints": {
      "type": "array",
      "items": {
        "type": "string"
      }
    },
    "acceptanceCriteria": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "minItems": 1
    },
    "materials": {
      "type": "array",
      "items": {
        "$ref": "subject-ref.json"
      },
      "minItems": 1
    },
    "reports": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": {
        "type": "string",
        "pattern": "^[a-zA-Z][a-zA-Z0-9_.-]*$"
      },
      "additionalProperties": {
        "$ref": "report.json"
      }
    }
  },
  "required": [
    "objective",
    "constraints",
    "acceptanceCriteria",
    "materials",
    "reports"
  ],
  "additionalProperties": false
}
```

#### E.3.7 `decision.json`

<!-- embedded-file: examples/generic-collaboration/schemas/decision.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "decision": {
      "enum": [
        "approve",
        "revise",
        "reject"
      ]
    },
    "comment": {
      "type": "string"
    }
  },
  "required": [
    "decision",
    "comment"
  ],
  "additionalProperties": false
}
```

#### E.3.8 `gate-input.json`

<!-- embedded-file: examples/generic-collaboration/schemas/gate-input.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "brief": {
      "$ref": "brief.json"
    },
    "product": {
      "$ref": "product.json"
    },
    "reports": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": {
        "type": "string",
        "pattern": "^[a-zA-Z][a-zA-Z0-9_.-]*$"
      },
      "additionalProperties": {
        "$ref": "report.json"
      }
    }
  },
  "required": [
    "brief",
    "product",
    "reports"
  ],
  "additionalProperties": false
}
```

#### E.3.9 `gate-config.json`

<!-- embedded-file: examples/generic-collaboration/schemas/gate-config.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "requiredReportIds": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "minItems": 1,
      "uniqueItems": true
    },
    "humanPolicy": {
      "enum": [
        "on_pass",
        "always",
        "none"
      ]
    },
    "rejectOnVerdict": {
      "type": "boolean",
      "default": true
    },
    "blockingSeverities": {
      "type": "array",
      "items": {
        "enum": [
          "blocker",
          "major",
          "minor",
          "info"
        ]
      },
      "uniqueItems": true,
      "default": [
        "blocker",
        "major"
      ]
    }
  },
  "required": [
    "requiredReportIds",
    "humanPolicy"
  ],
  "additionalProperties": false
}
```

#### E.3.10 `gate-output.json`

<!-- embedded-file: examples/generic-collaboration/schemas/gate-output.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "route": {
      "enum": [
        "request_human",
        "revise",
        "reject",
        "accept"
      ]
    },
    "feedback": {
      "type": "array",
      "items": {
        "$ref": "feedback.json"
      }
    },
    "machinePassed": {
      "type": "boolean"
    }
  },
  "required": [
    "route",
    "feedback",
    "machinePassed"
  ],
  "additionalProperties": false
}
```

#### E.3.11 `round-resolve-input.json`

<!-- embedded-file: examples/generic-collaboration/schemas/round-resolve-input.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "brief": {
      "$ref": "brief.json"
    },
    "product": {
      "$ref": "product.json"
    },
    "reports": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": {
        "type": "string",
        "pattern": "^[a-zA-Z][a-zA-Z0-9_.-]*$"
      },
      "additionalProperties": {
        "$ref": "report.json"
      }
    },
    "gate": {
      "$ref": "gate-output.json"
    },
    "humanDecision": {
      "oneOf": [
        {
          "$ref": "decision.json"
        },
        {
          "type": "null"
        }
      ]
    }
  },
  "required": [
    "brief",
    "product",
    "reports",
    "gate",
    "humanDecision"
  ],
  "additionalProperties": false
}
```

#### E.3.12 `round-result.json`

<!-- embedded-file: examples/generic-collaboration/schemas/round-result.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "outcome": {
      "enum": [
        "accepted",
        "revise",
        "rejected"
      ]
    },
    "materials": {
      "type": "array",
      "items": {
        "$ref": "subject-ref.json"
      },
      "minItems": 1
    },
    "assessments": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": {
        "type": "string",
        "pattern": "^[a-zA-Z][a-zA-Z0-9_.-]*$"
      },
      "additionalProperties": {
        "$ref": "report.json"
      }
    },
    "humanDecision": {
      "oneOf": [
        {
          "$ref": "decision.json"
        },
        {
          "type": "null"
        }
      ]
    },
    "feedback": {
      "type": "array",
      "items": {
        "$ref": "feedback.json"
      }
    },
    "nextInput": {
      "$ref": "brief.json"
    }
  },
  "required": [
    "outcome",
    "materials",
    "assessments",
    "humanDecision",
    "feedback",
    "nextInput"
  ],
  "additionalProperties": false
}
```

#### E.3.13 `component-descriptor.json`

<!-- embedded-file: examples/generic-collaboration/schemas/component-descriptor.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "schemaVersion": {
      "const": "multiverse.component/v1"
    },
    "id": {
      "type": "string",
      "pattern": "^[a-z][a-z0-9.-]+$"
    },
    "version": {
      "type": "string",
      "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"
    },
    "contentDigest": {
      "type": "string",
      "pattern": "^sha256:[0-9a-f]{64}$"
    },
    "kind": {
      "enum": [
        "executor",
        "template"
      ]
    },
    "description": {
      "type": "string",
      "minLength": 1
    },
    "inputSchema": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "minLength": 1,
          "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*://)[^\\\\]+$"
        },
        "digest": {
          "type": "string",
          "pattern": "^sha256:[0-9a-f]{64}$"
        }
      },
      "required": [
        "path",
        "digest"
      ],
      "additionalProperties": false
    },
    "outputSchema": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "minLength": 1,
          "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*://)[^\\\\]+$"
        },
        "digest": {
          "type": "string",
          "pattern": "^sha256:[0-9a-f]{64}$"
        }
      },
      "required": [
        "path",
        "digest"
      ],
      "additionalProperties": false
    },
    "configSchema": {
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "minLength": 1,
              "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*://)[^\\\\]+$"
            },
            "digest": {
              "type": "string",
              "pattern": "^sha256:[0-9a-f]{64}$"
            }
          },
          "required": [
            "path",
            "digest"
          ],
          "additionalProperties": false
        },
        {
          "type": "null"
        }
      ]
    },
    "requiredFeatures": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "uniqueItems": true
    },
    "capabilities": {
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^[a-z][a-z0-9.-]*\\.[a-z][a-z0-9.-]*@[1-9][0-9]*$"
      },
      "uniqueItems": true
    },
    "effects": {
      "type": "object",
      "properties": {
        "class": {
          "enum": [
            "none",
            "read",
            "write"
          ]
        },
        "actions": {
          "type": "array",
          "items": {
            "type": "string"
          },
          "uniqueItems": true
        }
      },
      "required": [
        "class",
        "actions"
      ],
      "additionalProperties": false
    },
    "implementation": {
      "oneOf": [
        {
          "type": "object",
          "properties": {
            "executorRef": {
              "type": "string",
              "minLength": 1
            },
            "adapter": {
              "enum": [
                "builtin",
                "local_process",
                "http_job",
                "human"
              ]
            },
            "adapterVersion": {
              "type": "string",
              "pattern": "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"
            }
          },
          "required": [
            "executorRef",
            "adapter",
            "adapterVersion"
          ],
          "additionalProperties": false
        },
        {
          "type": "object",
          "properties": {
            "packageDigest": {
              "type": "string",
              "pattern": "^sha256:[0-9a-f]{64}$"
            },
            "workflowId": {
              "type": "string",
              "minLength": 1
            }
          },
          "required": [
            "packageDigest",
            "workflowId"
          ],
          "additionalProperties": false
        }
      ]
    },
    "tests": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "minLength": 1,
            "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*://)[^\\\\]+$"
          },
          "digest": {
            "type": "string",
            "pattern": "^sha256:[0-9a-f]{64}$"
          },
          "level": {
            "enum": [
              "static",
              "fixture",
              "real",
              "fault"
            ]
          }
        },
        "required": [
          "path",
          "digest",
          "level"
        ],
        "additionalProperties": false
      }
    }
  },
  "required": [
    "schemaVersion",
    "id",
    "version",
    "contentDigest",
    "kind",
    "description",
    "inputSchema",
    "outputSchema",
    "configSchema",
    "requiredFeatures",
    "capabilities",
    "effects",
    "implementation",
    "tests"
  ],
  "additionalProperties": false,
  "allOf": [
    {
      "if": {
        "properties": {
          "kind": {
            "const": "executor"
          }
        }
      },
      "then": {
        "properties": {
          "implementation": {
            "required": [
              "executorRef"
            ]
          }
        }
      },
      "else": {
        "properties": {
          "implementation": {
            "required": [
              "packageDigest"
            ]
          }
        }
      }
    }
  ]
}
```

### E.4 两 Agent 与一人的有界循环

外层是 repeat 与最终结果路由；内层是普通单轮 Workflow。固定三个循环不是框架限制，而是本例参数。

#### `two-agent-human`

<!-- embedded-file: examples/generic-collaboration/workflows/two-agent-human.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: two-agent-human
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/round-result.json
  entry: cycle
  nodes:
    cycle:
      type: repeat
      workflow: two-agent-round
      input:
        ref: input#
      until:
        op: ne
        left:
          ref: iteration.output#/outcome
        right:
          literal: revise
      feedback:
        ref: iteration.output#/nextInput
      maxIterations: 3
      next: outcome
    outcome:
      type: switch
      cases:
      - id: accepted
        when:
          op: eq
          left:
            ref: nodes.cycle.output#/outcome
          right:
            literal: accepted
        next: complete
      default: rejected
    complete:
      type: end
      outcome: succeeded
      output:
        ref: nodes.cycle.output#
    rejected:
      type: end
      outcome: failed
      error:
        code: BUSINESS_REJECTED
        message: 本次业务被明确拒绝；不是传输失败，也不自动重试。
```

#### `two-agent-round`

<!-- embedded-file: examples/generic-collaboration/workflows/two-agent-round.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: two-agent-round
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/round-result.json
  entry: produce
  nodes:
    produce:
      type: call
      slot: producer
      inputSchema: schemas/brief.json
      outputSchema: schemas/product.json
      input:
        ref: input#
      requires:
        capabilities:
        - work.produce@1
      effects:
        class: read
        actions:
        - artifact.read
      next: assess
    assess:
      type: call
      slot: review.a
      inputSchema: schemas/brief.json
      outputSchema: schemas/report.json
      input:
        object:
          objective:
            ref: input#/objective
          constraints:
            ref: input#/constraints
          acceptanceCriteria:
            ref: input#/acceptanceCriteria
          materials:
            ref: nodes.produce.output#/materials
          feedback:
            ref: input#/feedback
      requires:
        capabilities:
        - work.evaluate@1
      effects:
        class: read
        actions:
        - artifact.read
      next: gate
    gate:
      type: call
      slot: gate.two
      inputSchema: schemas/gate-input.json
      outputSchema: schemas/gate-output.json
      input:
        object:
          brief:
            ref: input#
          product:
            ref: nodes.produce.output#
          reports: &id001
            object:
              reviewA:
                ref: nodes.assess.output#
      requires:
        capabilities:
        - data.decide@1
      effects:
        class: none
        actions: []
      next: route
    route:
      type: switch
      cases:
      - id: human
        when:
          op: eq
          left:
            ref: nodes.gate.output#/route
          right:
            literal: request_human
        next: human
      default: resolve-auto
    human:
      type: call
      slot: human
      inputSchema: schemas/human-input.json
      outputSchema: schemas/decision.json
      input:
        object:
          objective:
            ref: input#/objective
          constraints:
            ref: input#/constraints
          acceptanceCriteria:
            ref: input#/acceptanceCriteria
          materials:
            ref: nodes.produce.output#/materials
          reports: *id001
      requires:
        capabilities:
        - human.review@1
      effects:
        class: none
        actions: []
      next: resolve-human
      deadlineSeconds: 259200
    resolve-auto:
      type: call
      slot: resolve
      inputSchema: schemas/round-resolve-input.json
      outputSchema: schemas/round-result.json
      input:
        object:
          brief:
            ref: input#
          product:
            ref: nodes.produce.output#
          reports: *id001
          gate:
            ref: nodes.gate.output#
          humanDecision:
            literal: null
      requires:
        capabilities:
        - data.transform@1
      effects:
        class: none
        actions: []
      next: return-auto
    return-auto:
      type: end
      outcome: succeeded
      output:
        ref: nodes.resolve-auto.output#
    resolve-human:
      type: call
      slot: resolve
      inputSchema: schemas/round-resolve-input.json
      outputSchema: schemas/round-result.json
      input:
        object:
          brief:
            ref: input#
          product:
            ref: nodes.produce.output#
          reports: *id001
          gate:
            ref: nodes.gate.output#
          humanDecision:
            ref: nodes.human.output#
      requires:
        capabilities:
        - data.transform@1
      effects:
        class: none
        actions: []
      next: return-human
    return-human:
      type: end
      outcome: succeeded
      output:
        ref: nodes.resolve-human.output#
```

### E.5 三 Agent、程序与人的组合

三个静态检查分支都读取同一生产结果；聚合按分支 ID，不按完成次序。三个分支都完成后再由纯 gate 判断业务。

#### `three-agent-human`

<!-- embedded-file: examples/generic-collaboration/workflows/three-agent-human.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: three-agent-human
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/round-result.json
  entry: cycle
  nodes:
    cycle:
      type: repeat
      workflow: three-agent-round
      input:
        ref: input#
      until:
        op: ne
        left:
          ref: iteration.output#/outcome
        right:
          literal: revise
      feedback:
        ref: iteration.output#/nextInput
      maxIterations: 3
      next: outcome
    outcome:
      type: switch
      cases:
      - id: accepted
        when:
          op: eq
          left:
            ref: nodes.cycle.output#/outcome
          right:
            literal: accepted
        next: complete
      default: rejected
    complete:
      type: end
      outcome: succeeded
      output:
        ref: nodes.cycle.output#
    rejected:
      type: end
      outcome: failed
      error:
        code: BUSINESS_REJECTED
        message: 本次业务被明确拒绝；不是传输失败，也不自动重试。
```

#### `three-agent-round`

<!-- embedded-file: examples/generic-collaboration/workflows/three-agent-round.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: three-agent-round
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/round-result.json
  entry: produce
  nodes:
    produce:
      type: call
      slot: producer
      inputSchema: schemas/brief.json
      outputSchema: schemas/product.json
      input:
        ref: input#
      requires:
        capabilities:
        - work.produce@1
      effects:
        class: read
        actions:
        - artifact.read
      next: checks
    checks:
      type: parallel
      branches:
        reviewA:
          workflow: review-a
          input:
            object:
              objective:
                ref: input#/objective
              constraints:
                ref: input#/constraints
              acceptanceCriteria:
                ref: input#/acceptanceCriteria
              materials:
                ref: nodes.produce.output#/materials
              feedback:
                ref: input#/feedback
        reviewB:
          workflow: review-b
          input:
            object:
              objective:
                ref: input#/objective
              constraints:
                ref: input#/constraints
              acceptanceCriteria:
                ref: input#/acceptanceCriteria
              materials:
                ref: nodes.produce.output#/materials
              feedback:
                ref: input#/feedback
        program:
          workflow: program-check
          input:
            object:
              objective:
                ref: input#/objective
              constraints:
                ref: input#/constraints
              acceptanceCriteria:
                ref: input#/acceptanceCriteria
              materials:
                ref: nodes.produce.output#/materials
              feedback:
                ref: input#/feedback
      join: all
      maxConcurrency: 3
      next: gate
    gate:
      type: call
      slot: gate.three
      inputSchema: schemas/gate-input.json
      outputSchema: schemas/gate-output.json
      input:
        object:
          brief:
            ref: input#
          product:
            ref: nodes.produce.output#
          reports: &id001
            ref: nodes.checks.output#/branches
      requires:
        capabilities:
        - data.decide@1
      effects:
        class: none
        actions: []
      next: route
    route:
      type: switch
      cases:
      - id: human
        when:
          op: eq
          left:
            ref: nodes.gate.output#/route
          right:
            literal: request_human
        next: human
      default: resolve-auto
    human:
      type: call
      slot: human
      inputSchema: schemas/human-input.json
      outputSchema: schemas/decision.json
      input:
        object:
          objective:
            ref: input#/objective
          constraints:
            ref: input#/constraints
          acceptanceCriteria:
            ref: input#/acceptanceCriteria
          materials:
            ref: nodes.produce.output#/materials
          reports: *id001
      requires:
        capabilities:
        - human.review@1
      effects:
        class: none
        actions: []
      next: resolve-human
      deadlineSeconds: 259200
    resolve-auto:
      type: call
      slot: resolve
      inputSchema: schemas/round-resolve-input.json
      outputSchema: schemas/round-result.json
      input:
        object:
          brief:
            ref: input#
          product:
            ref: nodes.produce.output#
          reports: *id001
          gate:
            ref: nodes.gate.output#
          humanDecision:
            literal: null
      requires:
        capabilities:
        - data.transform@1
      effects:
        class: none
        actions: []
      next: return-auto
    return-auto:
      type: end
      outcome: succeeded
      output:
        ref: nodes.resolve-auto.output#
    resolve-human:
      type: call
      slot: resolve
      inputSchema: schemas/round-resolve-input.json
      outputSchema: schemas/round-result.json
      input:
        object:
          brief:
            ref: input#
          product:
            ref: nodes.produce.output#
          reports: *id001
          gate:
            ref: nodes.gate.output#
          humanDecision:
            ref: nodes.human.output#
      requires:
        capabilities:
        - data.transform@1
      effects:
        class: none
        actions: []
      next: return-human
    return-human:
      type: end
      outcome: succeeded
      output:
        ref: nodes.resolve-human.output#
```

#### `review-a`

<!-- embedded-file: examples/generic-collaboration/workflows/review-a.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: review-a
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/report.json
  entry: execute
  nodes:
    execute:
      type: call
      slot: review.a
      inputSchema: schemas/brief.json
      outputSchema: schemas/report.json
      input:
        ref: input#
      requires:
        capabilities:
        - work.evaluate@1
      effects:
        class: read
        actions:
        - artifact.read
      next: return
    return:
      type: end
      outcome: succeeded
      output:
        ref: nodes.execute.output#
```

#### `review-b`

<!-- embedded-file: examples/generic-collaboration/workflows/review-b.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: review-b
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/report.json
  entry: execute
  nodes:
    execute:
      type: call
      slot: review.b
      inputSchema: schemas/brief.json
      outputSchema: schemas/report.json
      input:
        ref: input#
      requires:
        capabilities:
        - work.evaluate@1
      effects:
        class: read
        actions:
        - artifact.read
      next: return
    return:
      type: end
      outcome: succeeded
      output:
        ref: nodes.execute.output#
```

#### `program-check`

<!-- embedded-file: examples/generic-collaboration/workflows/program-check.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: program-check
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/report.json
  entry: execute
  nodes:
    execute:
      type: call
      slot: program.check
      inputSchema: schemas/brief.json
      outputSchema: schemas/report.json
      input:
        ref: input#
      requires:
        capabilities:
        - artifact.validate@1
      effects:
        class: read
        actions:
        - artifact.read
      next: return
    return:
      type: end
      outcome: succeeded
      output:
        ref: nodes.execute.output#
```

### E.6 没有 Agent 的程序与人工流程

此入口证明 Agent 不是节点的父类型，人工也不限于 approve/reject。人接收程序准备的材料并提交 WorkProduct，然后由程序检查。

#### `program-human`

<!-- embedded-file: examples/generic-collaboration/workflows/program-human.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: program-human
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/report.json
  entry: body
  nodes:
    body:
      type: workflow
      workflow: program-human-body
      input:
        ref: input#
      next: return
    return:
      type: end
      outcome: succeeded
      output:
        ref: nodes.body.output#
```

#### `program-human-body`

<!-- embedded-file: examples/generic-collaboration/workflows/program-human-body.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: Workflow
metadata:
  name: program-human-body
  version: 1.0.0
spec:
  inputSchema: schemas/brief.json
  outputSchema: schemas/report.json
  entry: prepare
  nodes:
    prepare:
      type: call
      slot: program.prepare
      inputSchema: schemas/brief.json
      outputSchema: schemas/product.json
      input:
        ref: input#
      requires:
        capabilities:
        - data.prepare@1
      effects:
        class: none
        actions: []
      next: manual
    manual:
      type: call
      slot: human.input
      inputSchema: schemas/brief.json
      outputSchema: schemas/product.json
      input:
        object:
          objective:
            ref: input#/objective
          constraints:
            ref: input#/constraints
          acceptanceCriteria:
            ref: input#/acceptanceCriteria
          materials:
            ref: nodes.prepare.output#/materials
          feedback:
            ref: input#/feedback
      requires:
        capabilities:
        - human.input@1
      effects:
        class: none
        actions: []
      next: check
    check:
      type: call
      slot: program.check
      inputSchema: schemas/brief.json
      outputSchema: schemas/report.json
      input:
        object:
          objective:
            ref: input#/objective
          constraints:
            ref: input#/constraints
          acceptanceCriteria:
            ref: input#/acceptanceCriteria
          materials:
            ref: nodes.manual.output#/materials
          feedback:
            ref: input#/feedback
      requires:
        capabilities:
        - artifact.validate@1
      effects:
        class: read
        actions:
        - artifact.read
      next: return
    return:
      type: end
      outcome: succeeded
      output:
        ref: nodes.check.output#
```

### E.7 环境 Binding 与样例业务输入

下面 Binding 是带占位执行器和身份的测试示例。环境需要显式替换/注册并通过预检；不能自动把 `example-human` 或 `artifact:current-run` 当成实际授权。标准模式关闭 latent；不声明真实神经表示通信已可用。

<!-- embedded-file: examples/generic-collaboration/bindings.example.yaml -->
```yaml
apiVersion: multiverse/v0.1
kind: BindingSet
metadata:
  name: generic-collaboration-fixture
  version: 1.0.0
spec:
  slots:
    producer:
      adapter: builtin
      executorRef: example.producer.v1
      config: {}
      secretRefs: {}
      grants:
      - action: artifact.read
        resource: artifact:current-run
    review.a:
      adapter: builtin
      executorRef: example.review.a.v1
      config: {}
      secretRefs: {}
      grants:
      - action: artifact.read
        resource: artifact:current-run
    review.b:
      adapter: builtin
      executorRef: example.review.b.v1
      config: {}
      secretRefs: {}
      grants:
      - action: artifact.read
        resource: artifact:current-run
    program.check:
      adapter: builtin
      executorRef: example.program.check.v1
      config: {}
      secretRefs: {}
      grants:
      - action: artifact.read
        resource: artifact:current-run
    gate.two:
      adapter: builtin
      executorRef: mverse.stdlib.evaluation-gate.v1
      config:
        requiredReportIds:
        - reviewA
        humanPolicy: on_pass
        rejectOnVerdict: true
        blockingSeverities:
        - blocker
        - major
      secretRefs: {}
      grants: []
    gate.three:
      adapter: builtin
      executorRef: mverse.stdlib.evaluation-gate.v1
      config:
        requiredReportIds:
        - reviewA
        - reviewB
        - program
        humanPolicy: on_pass
        rejectOnVerdict: true
        blockingSeverities:
        - blocker
        - major
      secretRefs: {}
      grants: []
    resolve:
      adapter: builtin
      executorRef: mverse.stdlib.round-resolve.v1
      config: {}
      secretRefs: {}
      grants: []
    human:
      adapter: human
      executorRef: builtin.human-review.v1
      config:
        requestType: review
        choices:
        - approve
        - revise
        - reject
        authorizedSubjects:
        - example-human
        requireCommentFor:
        - revise
        - reject
      secretRefs: {}
      grants: []
    program.prepare:
      adapter: builtin
      executorRef: example.program-prepare.v1
      config: {}
      secretRefs: {}
      grants: []
    human.input:
      adapter: human
      executorRef: builtin.human-input.v1
      config:
        requestType: input
        choices: []
        authorizedSubjects:
        - example-human
      secretRefs: {}
      grants: []
  communication:
    latentHandoff:
      enabled: false
      routes: []
```

<!-- embedded-file: examples/generic-collaboration/fixtures/brief.json -->
```json
{
  "objective": "完成指定交付物并提交可核验的报告",
  "constraints": [
    "不更改本次目标和验收条件",
    "不执行未授权的外部写入"
  ],
  "acceptanceCriteria": [
    "交付内容与输入目标一致",
    "评估必须对应本次确定版本",
    "最终由授权人决定是否接受"
  ],
  "materials": [],
  "feedback": []
}
```

### E.8 本轮检查与真正验收的区别

随附 `checks/validate_examples.py` 只作离线 Schema、图形状、数据映射和限定 Fixture 行为检查，能够模拟部分分支、修订和人类决定。它不是生产 Runtime，不提供真实并发、授权、持久恢复、外部服务或模型调用保证；不得用它替代第 25 章的真实测试。

相同 Schema/样例应进入实际 Runtime 的 conformance tests。后续修改标准库语义，必须同步本文、样例、组件实现与正反例；不能只修改 Fixture 获得通过。检查结果见交付中的 `VALIDATION_REPORT.md`，它是测试记录，不是第二份规范。

---

<a id="appendix-f"></a>

## 附录 F. 给工作流作者与实现 Agent 的统一指引

本节是本规范的操作导航，不授予安装、执行、人工或发布权限。作者无需回查旧补充文档。

```text
你是 Multiverse 工作流作者，不是 Runtime，也不是审批人的替代身份。
1. 读取本规范的版本、六原语、Schema、当前环境能力目录和标准库模板。
2. 从用户交付目标、验收、副作用和人工操作需要出发，不从“几个人组成团队”推导核心模型。
3. 每个 call 定义输入输出、能力和 effects；人、Agent、程序和外部服务使用同一边界。
4. 使用 next/switch/repeat/workflow/parallel/end 组合。可自定义业务 Schema，不自行写状态同步、轮询线程或另一套协作引擎。
5. 常见协作优先选标准模板；模板展开/依赖固定，可随需要增加/减少参与者，不依赖角色名称。
6. 跨分支只读取已经成立的结果；轮次反馈构造新输入，旧产物与审批保持不可变。
7. 人工节点配置真实可操作入口：冻结材料只读，输出按契约提交，文件先登记；没有入口就报告依赖缺口。
8. 选用已注册受管或外部执行配置，工作区/Session/凭据保持边界；未知 executorRef 不猜测。
9. 基础通信由 Runtime 的标准交接承担。Latent 默认关闭；用户明确实验且 profile 真验证后才配置合法同 Scope route。
10. 开发代码只能成为待审阅安装资产，不能因写入包就获得服务器执行或网络权限。
11. 依次进行静态校验、支持性/Binding 预检、Fixture、经授权真实执行、Eval 和变更审阅。
12. 不删除必需约束、弱化验收、伪造产物或更改失败样本来制造通过；目标确需变化作为显式版本变更。
13. 输出包、契约/结构变化、模板/组件版本、待绑定项、权限影响、人工入口、测试层次与真实结果。
14. 运行控制与发布均走已定义且已实现的 application 接口，不直接写 Ledger/数据库。
15. 交付到目标环境时验证依赖闭合；原开发站点断开后仍应运行，不带走个人凭据或活动 Session。
```

实现者先读第 0.5 节 G 门禁和第 24 章阶段：先定义 Schema/错误/版本/权限及测试，再开放对应 SDK。不要给 Compiler/Runner 增加品牌分支、用模拟事件冒充执行状态、在两个平台重复返工，或以热更新跳过冻结规则。新功能必须能通过第 25 章相关正反例和真实边界测试。

---

<a id="appendix-g"></a>

## 附录 G. 来源保全、主题迁移与废止关系

### G.1 唯一权威与历史归档

本规范已将三份既有文档及 Spec 3 主题化合并；不是要求实现者继续同时阅读四份规则。历史文件保留原样，只用于追溯，后续行为变更应修改唯一规范。Spec 3 是本次新增章节的独立阅读本；合并后不独立演进。

初始架构草案中的统一黑盒节点、Workflow/Binding 分离、State/Memory/Context 分离和可交付包意图保留。初始技术草案中的“复用基础设施、独立核心契约”保留；曾经延后的 Latent、独立交付和 UI SDK 不再按旧路线延期。旧来源不是最新第三方能力或代码完成证据。

### G.2 输入文件校验摘要

这些摘要针对本轮使用的输入字节，用于核对来源而不是为旧内容授予并行效力。B 是原主规范而非本输出；T 是本轮 Spec 3。初始架构与技术草案只作意图参照。

| 来源 | 输入文件 | SHA-256 | 行数 |
|---|---|---|---|
| B | `MULTIVERSE_SPEC.md` | `759336d8f6d3e4e8ab12e92a9bce78798e15562a6ed6efa193534a55c0507765` | 2219 |
| S | `MULTIVERSE_APPEND_SPEC.md` | `a0b04eadbba5d1f56a06c579b3f6e1303b2f6b8b06f74b0dc294e7007642bfeb` | 1266 |
| R | `MULTIVERSE_RUNTIME_INTEGRATION_DELIVERY_SPEC.md` | `67835de724340793163af2a7b7926b161c134594d78c030890f11e3485436199` | 1554 |
| T | `MULTIVERSE_GUIDE_SPEC3.md` | `7d6bb20ac1a670b159bf9a3bd94a5aea434e91b29aa805ad87f1a469becbd2d3` | 447 |

### G.3 全部正文来源章节的迁移

“保留”表示保留要求并重排引用；“归并”表示重复要求在目标处只有一份协议表达；“替代”只涉及本规范明确列出的效力、范围和阶段变化，不放宽权限、恢复或审批不变量。细分小节随主题迁移，旧章节号不再作为执行依据。

| 来源 | 原章节/主题 | 新位置 | 处理 |
|---|---|---|---|
| B | 0. 文档效力、阅读方法与命名边界 | [0](#s00) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 1. 定位与产品目标 | [1](#s01) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 2. 不可破坏的原则 | [2](#s02) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 3. V0.1 范围与明确不做的事 | [3](#s03) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 4. 领域模型与身份 | [4](#s04) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 5. 技术栈与架构决策 | [5](#s05) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 6. 文档格式、通用类型与校验 | [6](#s06) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 7. Workflow Contract 与控制流 | [7](#s07) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 8. Capability、Binding 与部署解析 | [8](#s08) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 9. Executor Adapter Contract | [9](#s09) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 10. 权限、Policy 与安全边界 | [10](#s10) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 11. 生命周期、失败与人为控制 | [11](#s11) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 12. 持久执行、一致性与 LangGraph 集成 | [12](#s12) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 13. Human Request 与受控审阅 | [13](#s13) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 14. State、Artifact、Handoff、Context 与 Memory | [14](#s14) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 15. 运行事件、Trace 与可解释性 | [15](#s15) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 16. Workflow Package、Preset 与部署生命周期 | [16](#s16) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 17. Runtime HTTP API | [17](#s17) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 18. CLI 与无界面工作流 | [18](#s18) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 19. Inspector 与可嵌入 UI SDK | [19](#s19) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 20. Evaluation 与 AI 编辑闭环 | [20](#s20) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 21. 部署、运维与资源边界 | [21](#s21) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 22. 持久数据模型与事务要求 | [22](#s22) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 23. 仓库、模块与开发约束 | [23](#s23) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 24. 实施阶段、职责与进入条件 | [24](#s24) | 实施次序统一为 M0—M7/E1—E2；旧编号仅映射 |
| B | 25. 验收清单与完成定义 | [25](#s25) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| B | 26. 后续演进边界 | [26](#s26) | 核心要求保留；效力、范围与实施次序按 0/24 章显式统一 |
| S | S1. 外部 Agent 是原生工作流作者 | [20.5](#sec-20-5) | 人工/作者/数据规则按主题迁入 |
| S | S2. Authoring Kit：面向外部 Agent 的编写能力 | [20.9](#sec-20-9) | 人工/作者/数据规则按主题迁入 |
| S | S3. Vibe coding 的创建、修复与验证闭环 | [20.13](#sec-20-13) | 人工/作者/数据规则按主题迁入 |
| S | S4. 不变的输入输出规范化范式 | [6.6](#sec-6-6) | 人工/作者/数据规则按主题迁入 |
| S | S5. 契约版本、输入快照与数据边界 | [14.13](#sec-14-13) | 人工/作者/数据规则按主题迁入 |
| S | S6. 人工节点：审批、审阅与实际工作 | [13.5](#sec-13-5) | 人工/作者/数据规则按主题迁入 |
| S | S7. 人工页面与 Schema 驱动的交互 | [13.10](#sec-13-10) | 人工/作者/数据规则按主题迁入 |
| S | S8. 内建页面、嵌入页面与外部人工服务 | [13.16](#sec-13-16) | 人工/作者/数据规则按主题迁入 |
| S | S9. 人工产物提交与结构化结果通道 | [13.20](#sec-13-20) | 人工/作者/数据规则按主题迁入 |
| S | S10. 固定程序与通用 Wrapper | [9.7](#sec-9-7) | 人工/作者/数据规则按主题迁入 |
| R | R1. 产品定义与四种必须成立的使用形态 | [1.4](#sec-1-4) | 受管/接入/交付规则按主题迁入 |
| R | R2. 统一节点契约与执行分类 | [4.4](#sec-4-4) | 受管/接入/交付规则按主题迁入 |
| R | R3. 总体架构与两层 Runtime 责任 | [5.5](#sec-5-5) | 受管/接入/交付规则按主题迁入 |
| R | R4. Adapter、注册表与动态接入 | [8.5](#sec-8-5) | 受管/接入/交付规则按主题迁入 |
| R | R5. 执行配置、AgentProfile 与程序配置 | [27.1](#sec-27-1) | 受管/接入/交付规则按主题迁入 |
| R | R6. 受管执行宿主：内建 Agent、脚本与程序 | [27.6](#sec-27-6) | 受管/接入/交付规则按主题迁入 |
| R | R7. 工作区、Session、信息访问与产物 | [27.12](#sec-27-12) | 受管/接入/交付规则按主题迁入 |
| R | R8. 远程电脑接入：Multiverse Connector | [28.1](#sec-28-1) | 受管/接入/交付规则按主题迁入 |
| R | R9. 外部平台、工具与服务接入 | [9.12](#sec-9-12) | 受管/接入/交付规则按主题迁入 |
| R | R10. Integration Kit 与快速接入体验 | [9.17](#sec-9-17) | 受管/接入/交付规则按主题迁入 |
| R | R11. 人工交互、飞书与外部操作入口 | [13.24](#sec-13-24) | 受管/接入/交付规则按主题迁入 |
| R | R12. 独立运行与完全离线档位 | [21.7](#sec-21-7) | 受管/接入/交付规则按主题迁入 |
| R | R13. 状态、事件、内部步骤与循环观测 | [15.4](#sec-15-4) | 受管/接入/交付规则按主题迁入 |
| R | R14. 运行控制：开始、暂停、停止与重跑 | [11.8](#sec-11-8) | 受管/接入/交付规则按主题迁入 |
| R | R15. Inspector、双击详情与统一运行界面 | [19.7](#sec-19-7) | 受管/接入/交付规则按主题迁入 |
| R | R16. 持久恢复、幂等与接入前正确性门槛 | [12.8](#sec-12-8) | 受管/接入/交付规则按主题迁入 |
| R | R17. 权限、代码安装与数据隔离 | [10.6](#sec-10-6) | 受管/接入/交付规则按主题迁入 |
| R | R18. Workflow Package 与 Runnable Bundle | [16.7](#sec-16-7) | 受管/接入/交付规则按主题迁入 |
| R | R19. 依赖完整性、安装检查与即插即用 | [16.12](#sec-16-12) | 受管/接入/交付规则按主题迁入 |
| R | R20. 宿主接入契约与目标环境独立运行 | [17.5](#sec-17-5) | 受管/接入/交付规则按主题迁入 |
| R | R21. 交付界面、升级、回滚、卸载与备份 | [16.18](#sec-16-18) | 受管/接入/交付规则按主题迁入 |
| R | R23. 模块、持久记录与实现依赖 | [23.5](#sec-23-5) | 受管/接入/交付规则按主题迁入 |
| S | S0. 文档效力、来源与追加边界 | [0](#s00) | 旧行政效力由本规范 0 章替代 |
| S | S11. 与可选 Latent Handoff 的统一设计 | [14.6](#sec-14-6) | 重复 Latent 条款归并；只保留单一协议 |
| S | S12. 必须演示的混合流程 | [25.2](#sec-25-2) | 场景与边界并入统一验收、组合矩阵及附录 E |
| S | S13. 接口与配置缺口登记 | [0.5](#sec-0-5) | 统一到 G-01—G-16 与补充接口门禁 |
| S | S14. 实施顺序与职责 | [24](#s24) | 实施次序统一为 M0—M7/E1—E2；旧编号仅映射 |
| S | S15. 补充验收与完成定义 | [25.6](#sec-25-6) | 验收行与编号全部保留 |
| R | R0. 文档效力、依据与变更边界 | [0](#s00) | 旧行政效力由本规范 0 章替代 |
| R | R22. 与 Latent Handoff 及语义状态的关系 | [14.17](#sec-14-17) | 重复 Latent 条款归并；只保留单一协议 |
| R | R24. 待冻结接口与明确未作出的决定 | [0.5](#sec-0-5) | 统一到 G-01—G-16 与补充接口门禁 |
| R | R25. 实施阶段、交付顺序与职责 | [24](#s24) | 实施次序统一为 M0—M7/E1—E2；旧编号仅映射 |
| R | R26. 补充验收、证据与完成定义 | [25.7](#sec-25-7) | 验收行与编号全部保留 |
| T | T1. 最小而完整的组合基础 | [29.1](#sec-29-1) | 本轮新增通用组合要求 |
| T | T2. 责任分工与自定义边界 | [29.2](#sec-29-2) | 本轮新增通用组合要求 |
| T | T3. 三层组件体系与标准库地位 | [29.3](#sec-29-3) | 本轮新增通用组合要求 |
| T | T4. 统一 I/O、业务 Schema 与兼容性 | [29.4](#sec-29-4) | 本轮新增通用组合要求 |
| T | T5. 状态交接和协作通信的默认行为 | [29.5](#sec-29-5) | 本轮新增通用组合要求 |
| T | T6. 通用循环，而不是固定人数的“团队模式” | [29.6](#sec-29-6) | 本轮新增通用组合要求 |
| T | T7. 并行、聚合和复杂业务规则 | [29.7](#sec-29-7) | 本轮新增通用组合要求 |
| T | T8. 参考协作契约与确定性辅助组件 | [29.8](#sec-29-8) | 本轮新增通用组合要求 |
| T | T9. 三种组合及变化方式 | [29.9](#sec-29-9) | 本轮新增通用组合要求 |
| T | T10. 外部平台已有通信/协作时的适配 | [29.10](#sec-29-10) | 本轮新增通用组合要求 |
| T | T11. 运行控制、循环查看与人类操作 | [29.11](#sec-29-11) | 本轮新增通用组合要求 |
| T | T12. Latent 与协作标准库的关系 | [29.12](#sec-29-12) | 本轮新增通用组合要求 |
| T | T13. 作者工具与扩展开发流程 | [29.13](#sec-29-13) | 本轮新增通用组合要求 |
| T | T14. 自由组合的边界与完整性检查 | [29.14](#sec-29-14) | 本轮新增通用组合要求 |
| T | T0. 范围与来源边界 | [0](#s00) | 旧行政效力由本规范 0 章替代 |
| T | T15. 新增验收与实施顺序 | [25.8](#sec-25-8) | 验收行与编号全部保留 |

### G.4 原附录处理

| 原材料 | 本版位置与处理 |
|---|---|
| B 附录 A | 本版附录 A；保留核心参考样例及一次 latent 配置 Schema。 |
| B 附录 B | 本版附录 B；保留 ValueExpr Schema 与施工校验，阶段引用更新为 M。 |
| B 附录 C | 本版附录 C/G；历史来源保留，旧版本行政状态被替代。 |
| S 契约/人工示例 | 本版附录 D；保持片段性质，不声称可以独立部署。 |
| S 完整 Latent 摘录 | 与正文 14.6—14.12、附录 A.9、25.5 相同的内容不重复粘贴。 |
| S 作者指引 | 第 20/29 章与附录 F；不再要求回读旧文件。 |
| R 贯穿场景/协议片段 | 第 25.7 章原 RDI 验收、第 27/28 章与本版附录 E；不将占位接入参数变成已实现接口。 |
| R 实现者指引/来源 | 第 0/24 章、附录 C/F/G，保留接口未冻结与无实测声明。 |
| T 验收和来源 | 第 25.8/29 章与本附录；第三补充不继续作为平行依据。 |
| 历次代码审阅/市场分析 | 不转为核心协议；旧问题和测试报告仅属于其固定代码快照。 |

### G.5 合并检查边界

来源章节覆盖与验收编号检查证明已登记的要求可定位，不等于证明文档绝无语义遗漏，也不等于代码已经正确实现。发现相互矛盾或当前支持不明时应提交带定位的修订；不得自行选择更宽松解释。

本轮新增确定性标准库规则属于明确设计，未以外部行业标准名义声明；模板可替换，核心边界不可绕过。真实发布按第 25.9 节，而不是按 Markdown 体积、静态检查数量或示例生成成功决定。
