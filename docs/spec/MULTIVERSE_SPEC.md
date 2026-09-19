# Multiverse V0.1 唯一开发规范

**Portable workflows. Independent executors. Verifiable delivery.**

| 项目 | 固定值 |
|---|---|
| 项目工作名 | **Multiverse** |
| 产品说明 | 通用、可移植、可验证的工作流框架 |
| 仓库建议名 | `multiverse-workflow` |
| Python 导入名 | `multiverse_workflow` |
| CLI | `mverse` |
| 协议版本 | `multiverse/v0.1` |
| 本文修订版本 | `1.0.0` |
| 基准日期 | 2026-09-19 |
| 文档状态 | **开发基准：规定待实现行为，不表示代码已经实现或通过验收** |
| 权威文件 | `MULTIVERSE_SPEC.md` |

> **内部实现自由，外部边界确定。**
>
> Multiverse 通过统一契约组织 Agent、程序、人、API、远程服务与嵌套 Workflow；通过 Binding 适配环境；通过持久状态保证执行可解释、可恢复；通过评测与审阅控制变更。
>
> 任何行业、平台、模型、Agent 产品和运行环境，都只能成为适配对象或示例，不能成为核心协议的前提。

---

## 导航

| 阅读主题 | 章节 |
|---|---|
| 项目与范围 | [文档效力](#s00) · [定位](#s01) · [约束](#s02) · [首版范围](#s03) |
| 模型与技术 | [领域对象](#s04) · [技术栈与架构](#s05) |
| 协议与接入 | [格式与表达式](#s06) · [控制流](#s07) · [Binding](#s08) · [Adapter](#s09) · [权限](#s10) |
| 执行正确性 | [生命周期](#s11) · [持久恢复](#s12) · [人工审阅](#s13) · [数据与产物](#s14) · [事件与观测](#s15) |
| 产品接口 | [包与部署](#s16) · [HTTP API](#s17) · [CLI](#s18) · [Inspector/UI SDK](#s19) · [Eval](#s20) |
| 工程实施 | [运维](#s21) · [持久模型](#s22) · [代码仓库](#s23) · [开发阶段](#s24) · [46 项验收](#s25) · [演进](#s26) |
| 参考材料 | [完整样例](#appendix-a) · [首日施工与校验](#appendix-b) · [来源与修订](#appendix-c) |

---

<a id="s00"></a>

## 0. 文档效力、阅读方法与命名边界

### 0.1 唯一基准

本文合并并替代此前的初始架构方案、技术选型草案和讨论中的实现建议。实现 V0.1 不需要再从历史讨论中寻找未写明的规则。

本文中的 **MUST / 必须** 表示验收要求，**MUST NOT / 禁止** 表示禁止行为，**SHOULD / 应当** 表示偏离时需要说明理由并记录，**MAY / 可以** 表示可选实现。

第 0—26 章为规范性正文。附录 A 的示例、附录 B 的一致性校验方法属于规范性材料；附录 C 的来源说明不产生额外功能要求。文中标记为“后续”的能力不得被展示为 V0.1 已支持。

代码库中的 JSON Schema、OpenAPI、类型文件、数据库迁移和测试是本文的可执行表达，不是另一套可自行演进的规范。行为变更必须在同一变更中更新本文和对应测试；发现冲突时不得静默选择有利于现有实现的解释。

研发问题只允许三种处理：按本文实现；通过带测试的变更修改本文；明确标记为不支持并拒绝相关输入。禁止“先尽力运行，行为以后再解释”。

### 0.2 首次阅读顺序

负责人先读第 1—5、23—26 章；协议与后端开发再读第 6—18 章；前端开发读第 4、11、17、19 章；集成开发读第 9、10、13、16、21 章。所有人都必须使用第 25 章的验收清单。

### 0.3 项目命名

`Multiverse` 同时表达多个执行环境、多个实现和多种工作场景共享一套边界契约。对外使用完整描述 **Multiverse Workflow**，避免把项目误解为某一种多 Agent 聊天框架。

本次只确定工程工作名，不宣称公开包名、域名或商标已取得、无冲突或可注册。公开发布前确认分发名称；名称调整不得改变协议语义。CLI 使用 `mverse`，不使用通用系统命令 `mv`。

---

<a id="s01"></a>

## 1. 定位与产品目标

### 1.1 项目是什么

Multiverse 是三个相互独立、协同工作的产品层：

| 产品层 | 责任 | 不承担的责任 |
|---|---|---|
| Specification | 工作流、节点边界、能力、Binding、包与运行语义 | 定义 Agent 内部思维、固定业务领域 |
| Runtime | 解析、验证、部署、调用、等待、恢复、记录与受控操作 | 重造已有执行系统的设备和账户管理 |
| Inspector / UI SDK | 展示结构、状态、原因、证据、结果、评测和可执行操作 | 成为工作流定义的唯一存储或权限裁决者 |

工作流说明“什么需要发生”；Binding 说明“本环境由什么实现”；Runtime 决定“何时可以推进”；执行环境决定“实际允许做什么”。

### 1.2 第一版需要交付的用户价值

用户能够将一个包导入本地或远程运行环境，完成显式 Binding，执行包含程序、Agent 或其他外部执行器、人工环节的流程；遇到中断能看到真实状态、原因、证据与恢复路径；切换环境或执行器时不重写流程结构。

同一个 Runtime 可安装多个包，不要求每个 Workflow 配套部署一套独立平台。没有 Inspector，CLI/API 仍能完成全部核心操作；没有外部观测平台，仍能运行、查询、审阅和恢复。

### 1.3 不是本项目的默认形态

本项目不是聊天应用、Agent 市场、组织管理系统、模型路由网关、连接器市场、完整业务项目管理平台，也不是以拖拽搭建为主要入口的可视化编辑器。

这些能力可以出现在第三方产品或 Preset 中，但不得反向成为 Workflow Protocol 的必需字段。

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

---

<a id="s03"></a>

## 3. V0.1 范围与明确不做的事

### 3.1 发布必需能力

| 领域 | V0.1 必须实现 |
|---|---|
| 定义 | YAML/JSON 文档、独立 JSON Schema、确定性引用和条件表达式、静态检查 |
| 控制流 | 顺序、互斥条件分支、静态并行且全部汇合、受限嵌套 Workflow、显式有界循环 |
| 执行 | 统一调用契约、可信程序、Local Process、HTTP Job、内建 Human Adapter |
| 生命周期 | 持久运行状态、截止时间、受限重试、暂停调度、继续、取消请求、结果核对 |
| 数据 | 结构化输入输出、不可变 Artifact 引用、显式 Handoff、输入快照 |
| 交付 | 包构建、导入、预检、部署、版本固定、停用与新运行回滚 |
| UI | 独立 Inspector 与可嵌入 React 组件；状态、原因、证据和下一步同屏关联 |
| 评测 | 本地确定性 Evaluator、数据集执行、基线比较、机器可读报告 |
| 接入 | 独立 CLI/API、通用外部执行器契约、可选宿主 BFF 集成 |
| 观测 | 不可采样的运行事件；可选 OTel 导出 |
| 部署 | 本地单进程开发模式；PostgreSQL 支撑的单活 Worker 服务模式 |

“V0.1 必须实现”指发布门槛，不指第一天全部完成。按第 24 章分阶段交付，未完成阶段只能标记开发预览。

### 3.2 不进入 V0.1 发布阻塞项

不实现动态拓扑改写、任意图环、递归 Workflow、运行中换引擎、跨引擎迁移 Checkpoint、分布式多活调度、自动扩缩容、通用分布式事务、自动业务补偿、完整拖拽编辑器、公共包市场、内置 Agent 公司、完整 IAM、向量数据库、Latent Handoff。

MCP、A2A、Langfuse、其他观测后端、LLM Judge、自动优化器和其他执行后端作为扩展方向；不要求第一版提供生产级集成。扩展接口可以预留，但不能用空实现通过支持性检查。

### 3.3 可移植性分级

| 级别 | 定义 | V0.1 承诺 |
|---|---|---|
| P1 包可交付 | 无私有环境信息的包可以复制、解析、校验 | 必须 |
| P2 环境可部署 | 同一包在本地与服务环境通过不同 Binding 运行 | 必须，使用声明支持的组合 |
| P3 执行器可替换 | 不改 Workflow，只替换兼容 Binding，并重新验收 | 必须至少验证两种实现 |
| P4 引擎语义兼容 | 不同后端实现同一协议子集并通过一致性测试 | 设计边界；V0.1 只实现 LangGraph 后端 |
| P5 进行中的跨引擎迁移 | 一个后端的活动实例转到另一个后端继续 | 不支持 |

P3 不保证模型输出相同、成本相同或质量相同。兼容性、授权、可运行性和评测结果必须分别报告。

---

<a id="s04"></a>

## 4. 领域模型与身份

### 4.1 核心对象

| 对象 | 定义 | 标识与版本规则 |
|---|---|---|
| WorkflowDefinition | 一个可执行流程定义 | 包内 `workflow_id`；内容由包摘要固定 |
| NodeDefinition | 一个节点的类型、契约和流转规则 | 所属定义内唯一 `node_id` |
| WorkflowPackage | 定义、Schema、Prompt、Policy、Eval 等可交付文件集合 | `name`、SemVer、`package_digest` |
| BindingRevision | 一组逻辑 slot 到真实实现的映射 | 不可变 `binding_revision_id` 与摘要 |
| Deployment | 一个包版本加一个 BindingRevision 和环境策略 | 不可变 `deployment_id`；停用只阻止新 Run |
| WorkflowRun | 一次顶层工作流运行 | `run_id`，输入、快照和结果不可变引用 |
| ExecutionScope | 顶层或嵌套工作流的一次激活 | `scope_id`，包含父节点与迭代/分支路径 |
| NodeInvocation | 一个节点在特定 scope 中的一次逻辑调用 | `invocation_id`；不同循环轮次不是同一调用 |
| Attempt | 同一调用的一次执行尝试 | `attempt_id` 与从 1 开始的 `attempt_no` |
| ExternalExecutionRef | 外部系统返回的稳定工作引用 | Adapter ID + 外部 ID；可关联多个外部子尝试 |
| HumanRequest | 一个等待人的请求 | 请求 ID、subject digest、决策版本与截止时间 |
| Artifact | 一份输出内容或可验证外部资源 | 内容摘要/稳定版本 + 存储引用 + ACL |
| EvalRun | 一次固定数据集与版本组合的评测 | 独立 ID，关联生产式 Run，不覆盖原运行 |

运行时 ID 使用随机 UUID；身份连续性依赖持久映射和唯一约束，不依赖重新计算出同一个随机数。业务关联使用 `external_refs`，内容为命名空间化的 opaque 引用，不要求存在 Project、Task、Agent、Computer 等固定业务表。

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

### 4.3 核心身份字段

所有运行实体必须携带 `namespace_id`。API 中的 namespace 必须经过身份权限校验；不得信任客户端在正文里任意填写的租户字段。

执行关联最少包含：`run_id`、`scope_id`、`node_id`、`invocation_id`、`attempt_id`、`deployment_id`、`package_digest`、`binding_digest`。可选 `trace_id` 不得代替上述任何身份。

---

<a id="s05"></a>

## 5. 技术栈与架构决策

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

Node.js 24 为前端构建验证目标。依赖的精确版本在 P0 阶段通过安装、构建和最小恢复测试锁入 `uv.lock`、`pnpm-lock.yaml`；这不允许重新开放上述技术路线。未测试组合必须标记为未验证，而不是自动继承支持声明。

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

### 5.3 LangGraph 使用边界

LangGraph 提供持久 Checkpoint 与中断/恢复能力；内存 saver 在进程重启后不保留状态；生产式模式必须使用持久 saver。[E1]

LangGraph 中断后的节点可能从函数开头重新执行，因此节点重入必须安全；不能将创建外部工作与等待人工写成一段无幂等保护的代码。[E2]

本项目使用它执行规范化流程及其控制结构，不自建另一个竞争的通用图解释器。自身必须实现的部分是跨系统调用台账、幂等命令、输入输出契约、权限、部署与恢复核对。详细一致性规则见第 12 章。

### 5.4 不引入的基础设施

V0.1 默认部署不要求 Redis、Celery、Kafka、Temporal、ClickHouse、向量数据库、对象存储集群或外部 Trace 后端。可使用本地 Artifact volume；备份时必须一并备份。

Langfuse 官方自托管架构包含多个应用与存储组件，因此作为可选集成，而非轻量启动依赖。[E6] 重新评估 Temporal 的条件是执行基础设施负担和可靠性需求，不是“用户多了再说”；更换后端必须走 ADR、兼容测试和版本变更。

---

<a id="s06"></a>

## 6. 文档格式、通用类型与校验

### 6.1 顶层资源

V0.1 识别 `WorkflowPackage`、`Workflow`、`BindingSet` 三种声明文档。运行资源由 API 创建，不由 YAML 直接导入。

通用顶层字段：`apiVersion`、`kind`、`metadata`、`spec`，均必填。`metadata` 允许 `name`、`version`、`description`、`labels`；name 使用小写字母、数字、点、中划线，长度 1—64，首字符必须是字母。version 为 SemVer 字符串。

除明确列出的字段外拒绝未知字段。扩展只能位于 `extensions`，扩展键使用所属方命名空间。影响执行语义的扩展必须在包内 `requiredFeatures` 声明；不认识的必需扩展必须拒绝。UI 装饰类扩展可以忽略。

### 6.2 解析要求

仅允许 JSON 类型：object、array、string、number、boolean、null。禁止重复键、自定义 YAML tag、锚点/别名、合并键、隐式日期对象、NaN、Infinity、超出安全范围的整数和依赖语言对象的反序列化。

数字限制为有限 IEEE-754 可表达值；整数必须在 `[-(2^53-1), 2^53-1]`。业务中需要更高精度的数量使用带格式说明的字符串，禁止依靠客户端浮点四舍五入完成精确验收。

Workflow 中的 Schema/资源路径统一相对包根；JSON Schema 文件内部的 `$ref` 相对该 Schema 文件所在位置解析。JSON Schema 使用 Draft 2020-12。本地 `$ref` 必须归属当前包；仅允许相对文件路径与文件内 fragment。禁止安装/执行时下载远程 Schema。协议对象默认 `additionalProperties: false`，业务 payload 是否允许额外字段由其 Schema 明确决定。

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

### 6.4 Predicate：唯一条件语法

比较形式为 `{op, left, right}`；op 允许 `eq`、`ne`、`lt`、`lte`、`gt`、`gte`、`in`。组合形式为 `{all: [Predicate...]}`、`{any: [...]}`、`{not: Predicate}`。每个 Predicate 只使用一种形式；all/any 的数组必须非空。

`eq/ne` 按 JSON 类型和值比较，对象键顺序无关；数值比较仅接受 number；`in` 的右值必须为 array。所有引用必须存在，条件失败不得吞掉引用错误。禁止读时钟、随机数、网络和 Memory 做隐式路由。需要这些信息时，先通过显式节点生成持久输出，再进行条件判断。

### 6.5 验证顺序

解析 → 顶层 Schema → 文件/引用解析 → 节点和控制流校验 → Schema/数据映射检查 → Capability/Binding 匹配 → 权限和依赖预检 → 生成规范化计划。

静态检查不能证明任意 Schema 的完全包含关系。V0.1 必须验证明显冲突、必需引用及注册契约的 Schema 摘要；无法静态证明的映射标记 `runtime_validation_required`，实际调用前后仍严格校验，禁止报告为“已证明兼容”。

错误必须返回稳定 code、文件、JSON Pointer、中文/英文可本地化 message、严重程度和建议操作。

---

<a id="s07"></a>

## 7. Workflow Contract 与控制流

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

### 7.2 所有节点的公共字段

必填 `type`。可选 `title`、`description`、`extensions`。可调用/组合节点可以设置 `deadlineSeconds` 和 `onError`。除 `switch` 与 `end` 外，必须有 `next`。

`onError` 为目标 node_id，表示在错误已经确定、相关活动执行已经结束后走错误分支；没有它则当前 scope 失败。错误路径中可引用失败节点的 `.output`，其值固定为 `{error: ErrorEnvelope}`，并必须使用对应 Schema。`reconciling` 不是确定错误，不触发 `onError`。

### 7.3 call：统一执行节点

`type: call` 必填：`slot`、`inputSchema`、`outputSchema`、`input`、`requires`、`effects`、`next`。

`requires` 包含 `capabilities: string[]`，能力 ID 采用 `domain.action@major`。`effects` 包含 `class: none|read|write` 和 `actions: string[]`；它描述可能发生的外部业务影响，不包含 Runtime 自己记录状态的写入。

可选 `retry`：`maxAttempts`（1—3）、`initialDelaySeconds`（默认 2）、`backoffMultiplier`（默认 2）、`maxDelaySeconds`（默认 30）、`retryableCodes`（默认空数组）。是否实际允许重试同时受第 11 章约束。

不设置 `agent_type`、`model`、`machine` 等字段。执行器是人还是程序，不改变该节点的对外数据契约；特殊行为由 Adapter 能力声明，并受通用生命周期约束。

### 7.4 switch：互斥条件

必填 `cases` 和 `default`。cases 是非空有序数组，每项为 `{id, when, next}`；按顺序评估，首个为 true 的分支胜出。没有命中则走 default。选择及其输入摘要必须持久记录。

未选择分支不创建执行尝试。前端将其显示为未选中/跳过，而不是失败。两个分支可指向同一后继，但只有当前控制 token 到达的路径生效。

### 7.5 workflow：嵌套调用

必填 `workflow`（包内 workflow_id）、`input`、`next`。以独立 ExecutionScope 执行被引用流程，输入输出遵守被调用流程的 Schema。子流程成功后的输出为当前节点输出。

V0.1 禁止直接与间接递归，嵌套深度不超过 8，子流程不具有独立提升权限的能力。父级取消必须传递给子级；子级结果未知时父级不得成功结束。

### 7.6 parallel：静态并行且全部汇合

必填 `branches`、`join: all`、`next`；branches 是分支 ID 到 `{workflow, input}` 的映射。支持 2—16 个静态分支，`maxConcurrency` 可选且不得超过环境上限。

输出固定为 `{branches: {branch_id: child_output}}`。按照分支 ID 形成稳定结果映射，不使用完成时间决定数组位置。禁止并行分支隐式修改同一共享可变状态。

默认失败策略为 `stop_on_failure`：一个分支确定失败后，停止新分支、向已启动兄弟分支请求取消；所有活动分支已停止后才确定失败。无法确认停止则进入 `blocked`，不伪造全部终止。不支持 first-success、quorum、动态 map 或忽略失败自动汇合。

### 7.7 repeat：显式有界循环

必填 `workflow`、`input`、`until`、`feedback`、`maxIterations`、`next`。maxIterations 为 1—20。

第一轮输入来自 `input`；子流程成功后，用 `iteration.output` 和 `iteration.index` 判断 until。为 true 则输出最后一轮子流程输出并走 next；为 false 且未达到上限，则由 feedback 生成下一轮输入；达到上限仍未满足则报 `LOOP_LIMIT_EXCEEDED`。

每轮是新 scope、新 NodeInvocation、新审批主题；不得覆盖前一轮记录。一个子流程若确定失败，默认不当作“继续循环”，按 onError/失败规则处理。业务修订请求应通过成功输出中的显式业务值表达，而不是制造基础设施失败。

### 7.8 end：结束当前 scope

必填 `outcome: succeeded|failed`。成功结束必须提供 `output: ValueExpr` 并通过 Workflow.outputSchema；失败结束必须提供 `error: {code, message}`。不允许 next。

“外部执行返回 0”“HTTP 200”“模型说完成”均不自动等于工作流成功。只有选中成功 end、输出通过校验且无未核对活动执行，才可成功结束。

### 7.9 静态图与数据流限制

所有节点必须从 entry 可达，所有正常可选路径必须到达 end；悬空节点和边直接报错。数据引用必须支配当前读取点，或位于已经选中的同一分支；不能从互斥分支中任意读取一个“可能存在”的结果。

分支汇合需要统一输出时，将每条分支封装为子流程，统一其输出 Schema，或者在各分支中显式构造相同结果。禁止用后写覆盖前写的共享字典规避类型与路径检查。

---

<a id="s08"></a>

## 8. Capability、Binding 与部署解析

### 8.1 逻辑 slot

Workflow 只引用稳定的逻辑 slot，如 `producer`、`verifier`、`reviewer`。slot 不是特定产品名。一个 BindingSet 中每个被使用 slot 必须恰好解析到一个实现。

V0.1 不做自动模型竞价、质量路由或运行中故障切换到另一个提供者。可以给出候选匹配报告，但最终发布的 Deployment 必须固定选择。

### 8.2 BindingSet.spec

必填 `slots` 映射；可选 `limits`、`extensions`。每个 slot 包含：

| 字段 | 意义 |
|---|---|
| `adapter` | 已安装的 Adapter 类型：`builtin`、`local_process`、`http_job`、`human` |
| `executorRef` | 本环境已注册执行器 ID；不得由包安装阶段自动授权 |
| `config` | 该 Adapter 的非敏感配置，按 Adapter Schema 校验 |
| `secretRefs` | 字段名到 Secret Provider 引用；不包含 secret 值 |
| `grants` | 允许的 action/resource 范围，不得超过发起方权限 |

`capabilities` 不允许由 Binding 文件自行伪造后即被信任。解析器必须取得受信任的 ExecutorDescriptor 并校验 required capabilities。远程 descriptor 也是执行器声明，不是运行质量证明。

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

### 8.4 预检输出

预检必须逐项返回 `pass`、`warn`、`fail`、`unverified`。至少检查 Schema、功能子集、Adapter 安装与版本、Capability、权限交集、凭据可解析性、资源可达性、Artifact 可读写性、取消/恢复保证、质量基线是否存在。

凭据只验证引用及必要的最小探测，不写入日志。外部成本操作不得借“预检”名义执行。`unverified` 不能计作 pass；由环境策略决定是否阻止激活。

Deployment 固定包摘要、Binding 摘要、Descriptor 快照、解析计划摘要、策略版本与验证报告。真正调用前再次检查凭据有效性、授权撤销和资源可用性；冻结快照不赋予已撤销权限继续使用的权利。

---

<a id="s09"></a>

## 9. Executor Adapter Contract

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

### 9.3 ExecutionObservation

observe 结果必须包含：`executionRef`、`revision`、`status`、`observedAt`、`executionFinal`、`effectState`；可包含 `output`、`error`、`artifacts`、`usage`、`waitReason`、`externalRefs`。

- status 为 `accepted`、`running`、`waiting`、`succeeded`、`failed`、`cancelled`、`unknown`。
- revision 是同一 execution 的单调递增序号；重复版本不得改变内容。
- executionFinal 只有执行器确认不会再继续当前执行时才为 true。
- effectState 为 `none`、`possible`、`confirmed`、`not_applicable`。它用于安全判断，不能仅因 HTTP 请求失败而填 none。
- succeeded 必须 executionFinal=true，并提供可校验输出；failed/cancelled 如 executionFinal=false，Runtime 仍需等待或核对，不视为安全终止。
- usage 缺失应显示 unknown，不得以 0 冒充无成本。

外部终态必须单调。相互冲突的终态或相同 revision 不同内容触发 `EXECUTOR_PROTOCOL_VIOLATION`，保留证据并阻止自动推进。

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

lookup 的普通 404 不能自动解释为“可以安全重做”。只有 Descriptor 声明 strong，且响应明确为 `not_created`，才构成该提交没有创建工作的证明。业务系统的最终一致列表缺少某项不构成证明。

请求认证使用部署配置的受限凭据。必须验证 TLS；禁止以禁用证书验证解决连接问题。允许对明确配置的开发地址使用 HTTP，但不可作为公共服务默认设置。

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

### 9.6 通用宿主集成

宿主是任何通过 API 调用或承载界面的系统，不是特殊必需角色。集成层只负责身份映射、执行器注册、外部引用、动作转发与结果映射。

如外部系统已经拥有执行排队、内部重试、交付验收或人工决定，Adapter 必须声明清楚其责任边界。不能同时让 Runtime 和外部系统自动创建同一类重试或返工。`retryOwner=executor` 时，Runtime 只跟踪外部生命周期，不创建新的自动 Attempt。

接入不得直接读写第三方业务数据库，亦不得要求第三方采用本项目的 Task、Project 或 Agent 模型。NodeInvocation 与外部对象通过持久映射关联，不预设一对一关系。

---

<a id="s10"></a>

## 10. 权限、Policy 与安全边界

### 10.1 权限计算

一次实际执行的有效授权必须是以下范围的交集：节点声明的动作范围、Deployment 允许范围、当前发起人/服务身份权限、执行环境可以实施的范围。

声明 Capability 只是“支持某操作”；声明 Policy 只是“要求某限制”；只有网关、受限凭据、执行环境或可验证执行器实际实施，才能标记 `enforced`。

不能因为 Agent 在 Prompt 中被要求遵守，就显示网络、文件和命令权限已经隔离。

### 10.2 身份模式

首版提供本地受限 token 与集成用服务 token，不重造完整账户系统。每个身份具有 subject、namespace 和 scope；最低 scopes 为 `read`、`run:start`、`run:control`、`human:decide`、`deploy:write`、`executor:manage`、`reconcile:write`。

独立本地模式首次生成高强度随机 token，写入仅当前用户可读的凭据文件。默认监听 loopback。服务模式禁止匿名启动/部署/审批；反向代理认证必须通过受信任集成适配，不接受任意客户端 `X-User` 头。

外部服务转发人的操作时，必须有可验证的委托身份或限定范围的操作授权。服务 token 不能仅通过正文填写某人的名字就获得该人的权限。所有决定记录实际执行主体和经验证的代表主体。

### 10.3 审批的权限边界

人批准某项动作不扩大该 Deployment 的权限上限。审批对象必须含动作、资源、输入/产物摘要、包和 Binding 版本、必要的有效期。

有效凭据在调用时解析，只注入该次执行需要的最小集合。持久记录保存 secret reference 与可用时的版本标识，不保存 secret 明文。凭据轮换允许，但权限变更或语义相关配置变更必须重新预检；撤销立即阻止后续派发。

### 10.4 外部输入与导入安全

默认拒绝包内安装钩子、任意执行脚本、路径穿越、绝对路径、符号链接和解压炸弹。HTTP 连接地址来自运营者授权注册表，不能由模型输出直接变成允许访问的内部地址。重定向与 DNS 解析仍需按网络策略检查。

Artifact 默认不主动执行 HTML、JavaScript、宏或下载来的程序。纯文本与 JSON 预览必须转义。外部网页、模型输出、Memory 与 Artifact 中的指令均为不可信数据，不能取得系统权限。

### 10.5 命令与查询使用同一授权源

前端隐藏按钮不是授权控制。所有 API、CLI、自动化调用和宿主转发必须经过同一命令权限入口。若某个节点是发布或验收的强制门槛，不能通过另一个 API 直接绕过。

---

<a id="s11"></a>

## 11. 生命周期、失败与人为控制

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

### 11.2 WorkflowRun 状态

`queued`、`running`、`waiting`、`paused`、`stopping`、`blocked`、`succeeded`、`failed`、`cancelled`。

Runtime 单独保存 `control_mode=run|pause|cancel|fail` 与 `status`，避免用状态字符串同时表达意图和事实。

确定规则：有未解决 execution unknown 时 status=blocked；已要求 cancel/fail 且仍有活动执行时为 stopping；已暂停派发时为 paused；存在可推进或执行中的工作时为 running；全部剩余活动都在已知等待时为 waiting；所有必要结果和结束条件满足后才进入终态。

终态必须没有未核对活动执行。已经成功/失败的 Run 不因迟到事件复活；事件作为异常证据保留。外部事实若与已记录终态冲突，标记完整性事故，禁止静默重写历史。

### 11.3 重试规则

重试需要同时满足：错误码在允许列表；retryOwner=runtime；尚未达到次数；旧 Attempt 已最终结束；输入/授权主题不变；副作用安全条件成立。

副作用安全条件是以下之一：操作无外部写入；已经可靠证明未产生写入且不会继续执行；执行器实施 effectKey 级别的重复保护，重复调用不会产生额外业务动作。单纯支持 dispatchKey 去重不等于支持跨 Attempt 的业务幂等。

Schema 校验失败、权限拒绝、用户拒绝、输出缺失、结果未知默认不自动重试。禁止仅凭 HTTP 500、客户端超时或进程退出码认定写入未发生。

延迟按固定指数退避计算，实际 next_attempt_at 必须持久化。服务重启不重置次数或重新随机选择延迟。内建默认不加随机抖动；未来增加时也必须保存实际值。

### 11.4 超时

所有截止时间使用 UTC 并在开始时固定。调用 deadline 从首次创建 Attempt 开始计算，包含外部排队与等待；节点可显式设较长时限。Run 总 deadline 始终优先。

超时后先停止新派发并请求取消活动执行。确认停止后，以 `DEADLINE_EXCEEDED` 失败；不能确认则 blocked。人工请求到期不会默认批准。暂停调度不冻结 deadline，界面必须说明这一点。

### 11.5 暂停与继续

pause 表示“停止产生新的业务执行意图”，不表示冻结操作系统进程。已有执行可以继续上报结果；日志、状态核对、取消和审计仍工作。尚未真正派发的 outbox 项必须在发送前再次检查 control_mode。

resume 只解除调度暂停，不能代替人的决定、解决未知副作用、修改输入或替换 Binding。对 blocked 使用 resume 必须拒绝并返回所需核对动作。

### 11.6 取消与竞争

取消命令提交后先设置控制意图，再请求取消当前执行。若结果先完成，保留节点成功事实，但不得因迟到结果启动取消后的下游；Run 在确认所有活动结束后可 cancelled，并保留已发生副作用摘要。

若完成事务已经先将 Run 置为 succeeded，之后的取消返回 `ALREADY_TERMINAL`。以命令/状态事务的持久顺序决定控制竞争，不按浏览器到达顺序或不可靠外部时间判断。

V0.1 没有“强制取消即当作什么都没发生”的按钮。必要的人工处置必须提交可审计的核对证据，不能清空未知状态。

### 11.7 结果核对

允许的核对结论：`confirmed_succeeded`、`confirmed_failed`、`confirmed_cancelled`、`confirmed_not_started`。必须提供证据引用、对象版本、处理人和 reason。成功结论仍需输出 Schema 通过，且不能自动补齐业务审批。

confirmed_not_started 只有能确认旧提交不会稍后执行时才成立。核对后按原控制意图继续/失败/取消；如原重试策略仍允许剩余尝试，创建明确的新 Attempt，保留旧 Attempt 的“未创建”结论；次数不足则原调用结束，另行创建 Run，不因人工核对无限扩充 maxAttempts。无法确认就维持 blocked。

---

<a id="s12"></a>

## 12. 持久执行、一致性与 LangGraph 集成

### 12.1 权威与投影

Runtime 的业务状态表、调用台账和运行事件是 Multiverse 语义的权威记录；LangGraph Checkpoint 保存后端控制进度，不能覆盖外部执行事实。Inspector、缓存和 OTel 均为投影。

不要求实现可以从事件日志重建一切的通用 Event Sourcing 系统。要求关键状态变更、事件和必要 outbox 在同一数据库事务提交；快照与事件之间必须可核对。

### 12.2 四种幂等身份

| 身份 | 用途 | 生命周期 |
|---|---|---|
| API `Idempotency-Key` | 同一用户命令的重复提交 | 命令回执保留期内 |
| `transition_key` | 后端重入同一次语义状态变更 | Run 保留期内 |
| `dispatch_key` | 同一 Attempt 的外部提交去重 | 不短于 Run 与外部执行的保留期 |
| `effect_key` | 同一 invocation 的业务副作用去重 | 由执行器声明，必须覆盖配置重试与核对窗口 |

用户命令去重键的作用域是 namespace、subject、operation 和 key；相同 key 不同正文返回 409。不能因为客户端重试就另生成一份 Run。

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

### 12.4 Graph 节点的实现形状

编译后的外部调用至少区分“确保提交意图存在”“读取/等待持久结果”“验证并推进”。每一段重入前先检查对应持久记录；已有成功结果直接复用，不能重新调用外部模型或程序。

LangGraph 节点只在相关权威记录提交后返回完成。Checkpoint 保存失败时，下一次恢复允许重入，但 transition_key、dispatch_key 和既有结果确保不产生新的业务执行。Checkpoint 已保存但客户端未收到完成响应，也由同一逻辑识别。

不得假设 LangGraph saver 与应用表天然共享同一个原子事务。不能为了省事，将“保存 Checkpoint”与“外部创建工作”当成原子提交。[E1][E2]

### 12.5 单活 Worker

服务模式 V0.1 仅支持一个活跃调度 Worker；可以并发等待多个外部执行，但同一 Run 的图推进必须串行。

PostgreSQL 模式使用专用连接持有集群唯一调度 advisory lock；失去该连接即停止新的推进与发送。待执行意图存数据库，不存进程任务队列。PostgreSQL 提供应用可用的 advisory lock，但业务去重和未知结果处理仍由本项目负责。[E8]

SQLite 模式使用进程排他锁，只允许一个本地 Runtime，禁止共享数据库文件运行多个实例或置于网络文件系统上做生产服务。

HTTP/API 进程与 Worker 可分开启动，默认一个镜像提供不同命令。不使用 FastAPI 请求内 BackgroundTasks 作为持久工作流调度器。

### 12.6 Inbox、Outbox 与唤醒

外部回调先认证、限流、持久化 inbox，再应答；Worker 去重并应用。poll 取得的观察也走同一入站处理逻辑。每个执行器的 revision 单调，旧事件保留但不回退状态。

Outbox 项包含 ID、关联身份、动作、payload digest、not_before、处理状态、尝试次数和最后错误。重发需要稳定业务 key。不同动作使用不同 key；取消重试不创建新的执行。

图等待使用持久 wait record 和定期扫描作为兜底。唤醒只是提示；Worker 每次从数据库确认当前条件。事件早于 wait record 到达时，已有结果仍能被读取，不能永久漏唤醒。

### 12.7 Checkpoint 恢复与历史回放

日常恢复使用相同后端版本及持久 Checkpoint。若 Checkpoint 无法读取，默认 blocked 并报告 `BACKEND_RECOVERY_REQUIRED`，不得自动从头运行真实外部动作。

只读历史回放根据事件和快照还原过程，不调用执行器。调试重跑创建新 Run，默认使用录制结果或沙箱 Binding；生产副作用重跑需要新的显式授权。

V0.1 不支持不同 LangGraph 版本之间未经迁移测试的活动实例恢复。升级门禁必须包含真实旧 Checkpoint 兼容测试；无法兼容时先完成/停止旧实例或保留旧版本 Worker。

---

<a id="s13"></a>

## 13. Human Request 与受控审阅

### 13.1 人工请求模型

HumanRequest 必须包含：id、namespace、run/scope/invocation 关联、requestType、title、instructions、input、inputDigest、subjectRefs、subjectDigest、choices、decisionSchema、authorizedSubjects、createdAt、expiresAt、version、status。

requestType 为 `approval`、`review`、`input`。approval/review 的 choices 非空，决策归一化输出为 `{decision: <choice>, comment: <string>}`，缺省 comment 为 `""`；input 的 choices 为空，提交的 decision 必须是直接符合节点 outputSchema 的 JSON 对象，comment 只记审计、不注入业务输出。decisionSchema 必须与上述归一化输出契约一致。status 为 `pending`、`decided`、`expired`、`cancelled`。V0.1 每个请求只接受一次有效最终决定，不实现多人会签与投票。

subjectDigest 至少覆盖包、Binding、请求输入、被审阅 Artifact 版本和动作目标。需要重新审阅的内容变化必须创建新请求。

### 13.2 决策提交

提交包含 `decision`、必要 `comment`、`expectedVersion`、`subjectDigest` 和 Idempotency-Key。服务端在同一事务校验权限、请求未终止、未过期、版本匹配、主题匹配，再记录不可变决定并安排继续。

重复相同命令返回原回执。第二份冲突决定返回 409。读取页面不自动延长审批期限。

review 返回 approve/reject 并不直接改变整个 WorkflowRun 状态，而是作为节点输出供显式 switch 使用。request 的有效完成可对应业务拒绝；只有流程定义决定拒绝后是失败、修改循环还是其他处理。

### 13.3 两种人工来源

内建 human 由 Runtime 保存并验证决定。第三方审批系统可以作为 HTTP Job 执行器完成相同输出契约，其 Bridge 必须保留决策人的证据与对象版本。一个请求只能有一个最终决定权威，不能同时让两个界面互相覆盖。

### 13.4 人工输入不是任意状态编辑器

允许提交 Schema 规定的补充材料，不允许直接改 `node.status`、执行结果、Graph 或已经冻结的输入。需要修改工作目标时新建 Run，关联原 Run 并说明原因；有界业务返工通过 repeat 的显式输入传递完成。

---

<a id="s14"></a>

## 14. State、Artifact、Handoff、Context 与 Memory

### 14.1 State

State 只记录可确认事实：流程路径、输入输出摘要、尝试、外部引用、审批、版本、定时器和控制意图。禁止将模型生成的“已完成”文字直接转换为事实。

节点输出一旦成功固定，不被后续节点覆盖。需要累积结果时通过显式输入映射或受限循环 feedback 构造下一份输出。

### 14.2 Artifact

Artifact 元数据最少包含 `artifact_id`、namespace、所属运行/调用、name、media_type、size_bytes、digest、storage_ref、created_at、sensitivity、retention_policy、origin。

本地内容使用 SHA-256 标识；外部资源优先有内容摘要，否则必须有外部不可变版本，并标记 `verification=external_version_only`。可变 URL 不构成完整的可重现交付证据。

输出 JSON 只携带 ArtifactRef，不把大型文件或二进制写入 Graph Checkpoint。服务读取和下载必须检查 ACL，签名地址短期有效，不能把存储路径当公共下载链接。

文件系统存储先写临时对象并计算摘要，再原子归位；数据库事务只登记已经完成的对象。崩溃产生的未引用临时对象由垃圾回收清理，不能把部分文件登记为完成产物。

### 14.3 Handoff

V0.1 的 Handoff 是显式结构化数据：`summary`、`completed`、`remaining`、`constraints`、`evidence_refs`、`artifact_refs`、`warnings`。它随输入快照持久化。

摘要是解释，不是事实替代物。下游可以读取必要产物，不能仅依据上游自然语言声称测试通过。

### 14.4 Working Context

Context 由当前任务输入、允许读取的 State、显式 Handoff、授权 Artifact、固定 Prompt/Skill、可选 Memory 结果组装。组装结果保存摘要、引用、裁剪记录和策略版本；敏感正文按保留策略存储或脱敏。

Prompt/Skill 引用必须解析到包内内容摘要或环境已验证版本，不能假装一个目录存在即已经加载。执行器不支持某种 Skill 格式时预检失败或显示明确的非必需降级。

### 14.5 Semantic Memory

V0.1 默认关闭语义检索，仅定义 `put/search/get` Provider 接口及 provenance、namespace、权限、时间和来源引用字段。Memory 无权更新 State、审批或路由事实。

后续启用检索时，命中的记录 ID、版本和实际注入内容必须进入 Context 快照。嵌入向量、相似度和自动摘要均不能成为执行完成的依据。

Latent Handoff、Semantic Blackboard 与跨 Run 自学习保留为独立研究扩展，不能影响 V0.1 基础可运行性。

---

<a id="s15"></a>

## 15. 运行事件、Trace 与可解释性

### 15.1 必须持久化的事件

事件类型至少覆盖：包导入/部署/停用、Run 创建和控制、节点激活、Attempt 创建、外部提交确认、等待、取消请求、外部终态观察、输出校验、分支选择、并行分支创建/汇合、循环轮次、审批决定、结果核对、运行终结和安全拒绝。

运行事件字段：`event_id`、namespace、run/scope/invocation/attempt 引用、`seq`、`type`、`occurred_at`、`recorded_at`、actor、causation_id、correlation_id、payload、payload_schema_version。seq 在同一 Run 内严格递增；外部时钟仅作说明，记录顺序使用 seq。

状态快照返回 `last_event_seq`。前端从该位置继续订阅；断线重连不需要猜测漏掉哪些事件。

### 15.2 观测等级

`boundary` 至少能展示提交、等待、结果、版本、公开错误、外部引用和交付物；`internal` 可以进一步展示工具调用、模型调用和资源使用。不能观察到的内部操作应显示“执行器未提供”，不能显示“未发生”。

OTel 映射：Run 对应 trace 或根关联；NodeInvocation/Attempt 对应 span；工具/模型调用为可选子 span；异步与嵌套关系可用 link。敏感数据按 Policy 脱敏后导出。[E5]

长时间运行不要求把全部历史放进一个永不结束的内存 span。允许分段 span 并通过稳定运行身份关联。无 Trace 后端时，基础事件和 Inspector 仍必须完整工作。

### 15.3 错误解释模型

UI/API 的失败说明必须分别提供：

`reason_code`（机器判断）、`summary`（给人的一句话原因）、`evidence_refs`（日志/事件/输出/外部引用）、`next_actions`（当前身份可申请的操作）、`uncertainty`（已知/待确认）、`retry_safety`（安全/不安全/未知）。

禁止只显示“Failed”“Error occurred”或一段没有关联实体的堆栈。底层异常不得直接泄露凭据、完整请求头或敏感目录。

---

<a id="s16"></a>

## 16. Workflow Package、Preset 与部署生命周期

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

### 16.2 WorkflowPackage.spec

必填 `workflows`、`entrypoints`、`requiredFeatures`；可选 `assets`、`evalSuites`、`extensions`。

- workflows：workflow_id → 包内定义相对路径。
- entrypoints：可供用户直接运行的 workflow_id 数组，至少一个。
- requiredFeatures：显式功能 ID，如 `core.call`、`core.switch`、`core.human`、`core.parallel`、`core.repeat`、`core.nested`。
- assets：资源 ID → `{path, kind, format, version}`；kind 为 prompt/skill/policy。
- evalSuites：相对路径数组。

所有依赖的子 Workflow 必须随包一起存在；V0.1 不在执行时从公共注册表动态下载依赖。外部能力通过 Binding，不作为可执行源码自动安装。

### 16.3 内容摘要与可重现构建

单文件 digest 为实际字节的 SHA-256。构建生成按 UTF-8 路径顺序排列的文件清单，每项为 `{path, size, sha256}`；对清单使用 JCS 规范化 JSON，再计算 package_digest。[E9]

`package.lock.json` 保存清单与根摘要，但不参与自身的根摘要；签名/归档文件也不参与。打包只包含清单内文件，不包含 `.git`、本地 Binding、凭据、缓存和构建输出。检查解包后实际文件与清单完全一致。

同名同 version 但不同 digest 的包默认拒绝发布。编辑内容必须递增包版本。JSON/YAML 注释变化可能改变包字节摘要，这是有意保留来源差异；语义 Diff 可以另外说明“运行语义未变”。

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

### 16.5 更新与回滚

发布更新创建新 Deployment。旧 Run 继续使用旧解析计划和 Adapter/执行器版本要求；版本漂移导致无法安全调用时阻塞并说明，不偷偷跟随注册表的最新版本。

回滚表示将后续入口指向一个旧 Deployment，不撤销已经发生的代码修改、消息发送、文件写入或外部动作。V0.1 不提供隐式业务补偿。

### 16.6 外部平台嵌入的安装体验

任意宿主可以通过同一 API 实现“导入包—绑定执行能力—预检—激活—运行”。它不需要开放数据库，也不需要改成 Python。

Python 可以使用薄 SDK 调用相同 Application Commands；Go、Java、Node 等通过 HTTP Client、Sidecar 或 Service 接入。V0.1 不承诺这些语言都有进程内原生 Runtime。

一套共享服务默认承载多个 Deployment。只有明确的隔离或资源策略需要时，才使用独立实例；不是“一份工作流一套平台”。

---

<a id="s17"></a>

## 17. Runtime HTTP API

### 17.1 基本约定

API 前缀 `/api/v1/namespaces/{namespace}`。除健康检查与首次本地认证交换外，均要求授权。所有公开时间为 RFC 3339 UTC；所有身份使用 opaque 字符串，客户端不得解析其内部含义。

所有产生状态变化的 POST 必须带 `Idempotency-Key`。需要乐观并发控制的操作还必须带 `expectedVersion`。返回 `request_id` 便于关联，不向浏览器暴露内部数据库 ID 以外的敏感信息。

命令接收返回 202 与 CommandReceipt；仅在已完成纯本地事务时可返回 200/201。202 只代表已持久接收，不代表执行成功。

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
| `GET /runs/{id}` | — | 状态、控制意图、版本、问题摘要、lastEventSeq |
| `GET /runs/{id}/graph` | scopeId? | 规范图与运行投影，不返回 React Flow 私有模型 |
| `GET /runs/{id}/invocations` | scopeId?、cursor | 调用与 Attempt 摘要 |
| `GET /invocations/{id}` | — | 输入、输出、Attempt、原因、证据与允许动作 |
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

稳定错误码至少包括：`INVALID_SPEC`、`UNSUPPORTED_FEATURE`、`DATA_REFERENCE_MISSING`、`SCHEMA_VALIDATION_FAILED`、`BINDING_UNRESOLVED`、`CAPABILITY_MISMATCH`、`DEPENDENCY_UNAVAILABLE`、`SECURITY_REQUIREMENT_UNSUPPORTED`、`PERMISSION_DENIED`、`STATE_CONFLICT`、`IDEMPOTENCY_CONFLICT`、`ALREADY_TERMINAL`、`APPROVAL_EXPIRED`、`APPROVAL_SUBJECT_CHANGED`、`EXECUTION_UNKNOWN`、`EXECUTOR_PROTOCOL_VIOLATION`、`DEADLINE_EXCEEDED`、`LOOP_LIMIT_EXCEEDED`、`BUDGET_EXCEEDED`、`BACKEND_RECOVERY_REQUIRED`。

HTTP 映射：语法/参数 400、未认证 401、无权限 403、资源不可见 404、状态或幂等冲突 409、合法结构但语义不成立 422、限流 429、暂时服务不可用 503。未知副作用必须在错误语义中显式表达，不能让 SDK 将任意 503 自动转为新业务提交。

### 17.4 SSE 与重连

每个 SSE 事件使用对应 Run 的 seq 作为 event ID，并包含 event type 和 JSON payload。服务端先回放 after 之后的保留事件，再连续输出，避免“先读再订阅”的空隙。SDK 按 seq 去重并处理乱序。

游标过期返回 `CURSOR_EXPIRED` 与最新快照位置；客户端重新读取快照再继续。无权限或 token 失效立即停止流。

带 Bearer Token 的 UI 使用支持认证头的 fetch 流式客户端，不把 token 放在 URL、日志或浏览器持久存储中。以同源 BFF 接入时可使用其受保护的会话方案，但仍必须执行服务端授权。

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

退出码：0=操作成功或等待后 Run 成功；1=运行确定失败；2=参数/Spec 无效；3=权限或状态冲突；4=需要人工/结果核对且命令选择不继续等待；5=网络/服务暂不可用。`--wait` 不因断开终端而取消 Run。

---

<a id="s19"></a>

## 19. Inspector 与可嵌入 UI SDK

### 19.1 第一屏必须回答的问题

Run Detail 首屏必须同时显示：本次目标、当前状态、正在等待什么或卡在哪里、原因和证据入口、当前身份可执行的下一步、已完成交付物、运行所用版本。

Graph 是解释这些信息的手段，不是要求用户逐个点完才能知道流程失败原因的入口。状态不能只靠颜色，必须有文字和图标；waiting、blocked、paused、stopping 必须有不同说明。

### 19.2 首版页面

只保留 Packages、Deployments、Runs、Human Inbox、Evals 五类一级页面。Workflow Graph 与版本信息放在包/部署详情，Graph、Timeline、State、Artifact、Trace 放在 Run Detail 内。

高级 Graph Diff、复杂仪表盘、Memory 浏览器不阻塞首版。最低版本比较必须展示包摘要、Binding/权限变化、文本 Diff 与 Eval 变化；不能把“未测”显示成“没有退步”。

### 19.3 必须交付的组件

`WorkflowCanvas`、`RunSummary`、`NodeInspector`、`RunTimeline`、`ArtifactList`、`HumanRequestPanel`、`EvalSummary`。

UI SDK 接收框架领域模型、data client 和 action callbacks。它不自行创建账号、不决定权限、不强制宿主路由、不依赖唯一 QueryClient、不向 window 注册不可控全局状态。

React、ReactDOM 使用 peerDependency；首版明确验证 React 19。非 React 宿主可以使用独立 Inspector、iframe 隔离部署或 HTTP 自建界面，不要求迁移前端框架。iframe 必须配置明确来源与认证边界，不传递长期 token 到 URL。

### 19.4 图与布局规则

Graph DTO 使用 `nodes`、`edges`、`groups` 与稳定 domain IDs，不直接返回 React Flow 的内部持久对象。前端映射后展示。

ELK 在 Web Worker 中计算布局，结果按 package digest、scope 和布局版本缓存。运行状态变化不重新排列节点；用户选中、缩放、平移后不被增量事件强制重置。

默认折叠嵌套 Workflow；展开后保留父子路径。循环显示定义和当前轮次，而不是无限复制整张图。并行显示各分支状态与等待汇合条件。

节点卡片必须区分定义、invocation 与 attempt。点击失败的第三次尝试，不能只显示第一次日志。Artifact 边只表示明确的数据引用，不推断隐式共享文件。

### 19.5 视觉与交互要求

独立 Inspector 默认浅色中性背景、单一强调色、明确文字层级。宿主可覆盖主题 tokens。禁止向宿主注入全局 CSS reset；Tailwind utilities 与组件变量使用限定作用域，弹层挂载容器可配置。

每个页面实现 loading、empty、partial、stale、error、unauthorized 状态。控制命令显示“已请求/待确认”，直到事实状态变化；不能点击取消就立即将流程涂成已停止。

危险操作需要展示影响范围。审批显示产物版本和证据；subject 已变化时阻止旧表单提交。Trace/日志必须虚拟化和分页，不能一次加载全部 Token 历史。

### 19.6 SDK 数据接口

最小接口定义：`getRun`、`getGraph`、`listInvocations`、`getInvocation`、`listEvents`、`subscribeRun`、`listArtifacts`、`getHumanRequest`、`submitCommand`。

接口使用 AbortSignal/取消订阅；组件卸载后清理流。UI 必须显示服务端允许的 action，并在操作时仍接受服务端重新校验。服务端返回的业务值不能直接作为 HTML 插入。

---

<a id="s20"></a>

## 20. Evaluation 与 AI 编辑闭环

### 20.1 首版 Eval 数据模型

Dataset 是版本化 JSONL；每行包含 case_id、input、expected（可选）、tags（可选）。Suite 声明 workflow、dataset、evaluators、gate。Evaluator 通过已注册 ID 调用可信实现，禁止执行数据集内任意源码。

EvalRun 固定 package/binding/deployment、dataset digest、evaluator version、重复次数、种子（适用时）、预算、开始时间和运行环境。每个样本产生独立 Run 及结果，失败与超时也必须计入，不删除不利样本。

### 20.2 第一版 Evaluator

必须提供输出 Schema 检查、必需 Artifact 检查、结构化字段断言和运行成功率汇总。可增加可信业务校验程序。LLM Judge 保留接口，不作为唯一发布门槛。

最低指标：case pass、workflow status、latency、attempt count、unknown count、人工决定耗时、已知成本、成本覆盖率。无费用来源时 cost=null，coverage 标记 unavailable。

读取某份测试报告不能被标记为独立执行测试；Evaluator 必须声明证据来源和是否实际执行验证。

### 20.3 基线与门禁

发布比较必须使用同一数据集版本、明确的预算和次数。报告同时列出通过、失败、未知、跳过和样本数；小样本不宣称统计显著或普遍优越。

门禁是显式规则，例如 `requiredPassRate=1.0`、`maxUnknown=0`、`allowMissingCost=true`。质量门禁失败不允许把包自动升级为生产默认入口。

评测默认使用沙箱/只读 Binding。带写入副作用的生产评测必须单独授权，不得因为命令名叫 eval 就绕过 Policy。

### 20.4 AI 编辑的最小支持

V0.1 不内置自主优化 Agent。提供可解析文件、validate、eval、diff 和结构化诊断，让外部 AI 工具编辑。

变更路径固定为：创建新包版本 → Validate → 预检 → Eval → Diff → 人工发布决定。Diff 必须标出执行器能力、权限、依赖、流程结构和验收门槛的变化，不能只显示 Prompt 文本。

AI 提案没有修改活动 Run 的权力。自动 Merge、自动发布和自主扩权均不属于首版。

---

<a id="s21"></a>

## 21. 部署、运维与资源边界

### 21.1 两个受支持的运行档位

| 档位 | 组成 | 保证和限制 |
|---|---|---|
| `local` | 一个本地进程、SQLite、文件 Artifact、内建 Inspector 可选 | 单用户/可信开发；持久文件恢复；不提供集群与不可信代码隔离 |
| `service` | API 进程、单活 Worker、PostgreSQL、Artifact volume、反向代理可选 | 多身份隔离、持久命令和等待；执行器须满足部署声明的恢复要求 |

Sidecar 是 service 或 local 档位的一种放置方式，不产生第三套执行语义。Python Embedded 必须显式提供存储、调度生命周期与身份上下文；随请求创建临时 Runtime 然后丢弃不属于持久模式。

### 21.2 服务配置

需要提供 `DATABASE_URL`、`ARTIFACT_ROOT`、`AUTH_CONFIG_REF`、`EXECUTOR_REGISTRY_REF`、`PUBLIC_BASE_PATH`、`LOG_LEVEL`。可选 `OTEL_EXPORTER_OTLP_ENDPOINT`、`SECRET_PROVIDER_CONFIG_REF`。敏感值通过环境注入/挂载机密配置，不提交仓库。

启动顺序：迁移检查 → 数据库迁移任务 → API readiness → Worker 取得单活锁 → 扫描未完成工作。迁移失败时禁止启动调度。

健康检查区分 `/health/live`、`/health/ready` 和 Worker heartbeat。ready 检查数据库、迁移版本、Artifact 存储；外部执行器不可达不必令整个 API 下线，但必须阻止对应的新调用并展示局部不可用。

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
| 单调用 stdout/stderr 保留 | 各 10 MiB，超出标记截断，不影响事实状态 |
| 默认 Run 总截止时间 / 环境上限 | 7 天 / 30 天 |
| 取消确认宽限 | 30 秒；超出后进入核对，不伪造停止 |
| 正常观察轮询 / 失败后最大退避 | 2 秒 / 30 秒 |
| 控制事件与命令回执保留 | 至少关联 Run 保留期；默认终态后 90 天 |

并发预算按未终结的真实外部执行计数，包括外部排队；纯控制节点和空闲 HumanRequest 不占外部执行槽位。parallel 的 maxConcurrency 则限制未终结的子分支数量，等待中的分支仍占自己的分支名额，不能将两个计数混用。

限制达到时返回具体 code 和范围。不得因为日志截断而删除运行事实；不得因为遥测服务缓慢阻塞业务状态提交。

### 21.4 成本与预算

Run 可以设置 maxAttempts、maxInvocations、deadline 和可计量的费用预算。未知费用不能用 0 代替。硬费用上限只有在执行器支持可靠的预算实施/预留时才能保证；否则只能做已知消耗的软限制，预检报告必须区分。

并行派发前需要原子检查本地并发/调用额度。外部服务真正计费若滞后，不能宣传严格费用封顶。

### 21.5 备份与保留

备份必须覆盖应用数据库、LangGraph Checkpoint、包内容及 Artifact。恢复后先进入只读核对模式，检查活动外部执行，不能不加判断地重新派发。

不得自动删除活动 Run 的回执、输出、审批或恢复关联。删除/归档终态数据时保留说明性 tombstone，避免历史引用看似从未存在。Secret 明文从始至终不进入备份。

### 21.6 支持性声明

首版正式验收以 Linux 服务部署和项目声明的本地环境为准。其他操作系统、数据库版本、存储后端和执行器必须分别列出 verified/unverified 状态，不把“Python 理论上能运行”当成已经验证。

---

<a id="s22"></a>

## 22. 持久数据模型与事务要求

### 22.1 最小表族

| 表族 | 关键内容 | 关键约束 |
|---|---|---|
| `packages` / `package_files` | 包身份、清单、内容地址 | digest 唯一；同 namespace/name/version 不覆盖不同内容 |
| `binding_revisions` | 脱敏配置、Descriptor 快照、摘要 | 不可变 revision |
| `deployments` | 包、Binding、Policy、执行计划、active 状态 | 内容不可变；乐观版本控制 |
| `runs` | 输入引用、status、control_mode、deadline、version | namespace 过滤；终态单调 |
| `scopes` | 父 invocation、workflow、分支/轮次 | 父引用 + 激活路径唯一 |
| `invocations` | node、scope、状态、输入输出、错误 | scope + node_id 唯一 |
| `attempts` | invocation、attempt_no、dispatch/effect key、外部引用 | invocation + attempt_no 唯一；dispatch_key 唯一 |
| `decisions` | switch 选择、循环判断、计划中的控制决定 | transition_key 唯一 |
| `human_requests` / `human_decisions` | 主题、版本、截止时间、授权决定 | 每请求最多一个最终决定 |
| `artifacts` / `artifact_links` | 内容、版本、敏感级别和关联 | 内容存储完成后才登记可读 |
| `run_events` | seq、type、actor、payload | run_id + seq 唯一 |
| `command_receipts` | Idempotency-Key、请求摘要、结果 | namespace + subject + operation + key 唯一 |
| `inbox` | 认证后的外部观察 | executor + external_id + revision 去重 |
| `outbox` / `waits` | 待发送意图、等待、定时器 | 语义 action key 唯一 |
| `eval_runs` / `eval_cases` | 数据集、版本、结果和门禁 | 样本不因失败而被移除 |
| 后端 Checkpoint 表 | LangGraph saver 的存储 | 由 backend 模块管理，非公共查询 API |

scope + node_id 唯一依赖第 7 章的同级无环约束；循环创建子 scope，不复用同一 scope 中的节点调用。

### 22.2 必须原子提交的组合

Run 创建 + 命令回执 + 初始事件 + 唤醒；Attempt 创建 + 输入快照 + submit outbox；外部终态记录 + 输出校验结论 + 节点事件 + 下游唤醒；人工决定 + 版本推进 + 事件 + 唤醒；控制意图 + 命令回执 + 取消/暂停派生意图。

输出校验如果依赖大型 Artifact，可先验证并保存验证报告，再在事务中检查相关摘要没有变化。禁止在数据库长事务中执行模型调用或等待人工。

### 22.3 查询与并发

所有查询经 namespace 和资源级权限过滤，不允许“先查全量再在浏览器隐藏”。列表必须游标分页，默认 50、最大 200。事件与大日志使用独立分页，不塞进 Run 列表。

状态更新使用 expected version 或行级锁；外部事件处理、用户取消和 Worker 推进发生竞争时必须有确定的提交顺序。不依赖前端刷新速度保证一致性。

---

<a id="s23"></a>

## 23. 仓库、模块与开发约束

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
│   └── embedded-ui/
├── tests/
│   ├── protocol/
│   ├── conformance/
│   ├── integration/
│   ├── fault_injection/
│   └── e2e/
├── deploy/
├── docs/adr/
├── THIRD_PARTY_NOTICES.md
└── REFERENCES.md
```

初期一个 Python distribution 足够；目录划分表示依赖边界，不要求发布十几个独立包。UI、Client 可以独立构建，避免将 Python 运行时强加给前端集成方。

### 23.2 模块依赖方向

protocol 不依赖 API/Runtime/backend；compiler 只依赖 protocol 与注册能力接口；runtime 依赖自己的 backend/adapter 接口；LangGraph 实现依赖 runtime 接口，而不是让 protocol 导入 LangGraph。

API、CLI、Python SDK 使用同一 application 层。任何直接写业务表绕过 application 命令的实现都不得合并。

### 23.3 工程质量门槛

Python 启用类型检查和格式/静态检查；TypeScript 使用 strict。公共接口必须包含类型、错误语义和至少一个成功/失败测试。Schema 与客户端类型通过 CI 校验一致。

每个行为测试引用本文 requirement 或 acceptance ID。禁止将 Mock 链路、真实 Adapter 链路和真实业务验收混成一个绿色“全部通过”。测试报告必须区分三者。

### 23.4 参考代码与许可证

React Flow、LangGraph、Langflow、Sim、Langfuse、Temporal 等可以作为依赖或设计参考，但不整体 Fork 其平台成为永久核心。复制源码前记录来源文件、commit、许可证、修改内容和对应 NOTICE。

ELK.js 当前许可证为 EPL-2.0；Langfuse 的部分企业目录采用独立许可，不能笼统视为全部同一许可。[E10][E11] 实际发版必须按锁定依赖与复制文件检查，本文不替代对具体分发物的许可核查。

自有代码的开源许可不在本次用户要求中预设为已授权；正式公开发布前由权利人确认。该发布事项不阻止内部开发，不得擅自为原有或第三方代码改变许可。

---

<a id="s24"></a>

## 24. 实施阶段、职责与进入条件

按下列顺序开发，不按“先把所有页面做完”排序。每个阶段完成后应有独立可演示结果。

| 阶段 | 主要工作 | 完成证据 |
|---|---|---|
| P0 协议与骨架 | 工程初始化、锁依赖、资源 Schema、ValueExpr/Predicate、appendix 样例导入、数据库迁移、Auth/命令封装 | validate 能定位错误；样例和反例进 CI；无业务执行副作用 |
| P1 单次交付 | LangGraph 后端、持久 Run/Attempt、builtin、HTTP Job、Human、顺序/switch、最小 CLI | 程序→外部执行→人工→结果可以真实贯通；关闭 Web 不影响执行 |
| P2 恢复与控制 | outbox/inbox、幂等、轮询、超时、暂停/取消/核对、故障注入 | 创建响应丢失、Worker 重启、审批重复不重复业务执行 |
| P3 可交付与可嵌入 | Package 构建、两套 Binding、Deployment 固定、Inspector/UI SDK | 同包不改定义切换实现；独立 UI 和嵌入示例均可操作 |
| P4 组合与验收 | nested/parallel/repeat、第二场景、Eval/基线、版本门禁、安全测试 | 全部 core 特性一致性测试通过；两类业务样例能解释全过程 |
| V0.1 Release Gate | 完整回归、备份恢复、真实 Adapter 验证、第三方声明、已知限制 | 第 25 章全部 MUST 验收；支持矩阵和报告随版本发布 |

编译器/Runtime 负责人负责状态语义和故障测试；Adapter 负责人负责外部契约与副作用安全；UI 负责人负责由事实驱动的状态与可操作性；发布负责人负责依赖锁定、部署恢复、权限与版本门禁。这些是职责，不假定团队已经具备对应人数。

不得先实现自动分工、模型路由、向量记忆或市场分发，再补派发去重、人工决定与取消确认。

---

<a id="s25"></a>

## 25. 验收清单与完成定义

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

### 25.2 验证样例组合

必须维护两类参考 Preset：内容交付（生产→验证→审阅）与数据质量处理（并行检查→有界修正→汇总）。它们用于证明通用性，不定义项目只服务这些场景。

每类至少有确定性 fixture。至少一类再绑定真实 Agent、远程服务或实际本地执行器，不能用全部 Mock 证明外部接入已经成立。未获得真实凭据时如实标记该验收尚未完成，不阻止继续其他开发工作，但不能发布为全部通过。

### 25.3 性能验证目标

建立固定环境与样本，测试 100 个静态节点的 Graph、20 个同时等待的 Run 和 10,000 条分页事件。首屏可交互目标为 2 秒以内；本地已提交控制事件到 UI 可见目标为 1 秒以内。测试必须注明机器、网络和数据规模，这些是优化目标而不是当前实测承诺。

P0—P4 优先保证正确性与可解释性，不以吞掉事件、提前标成功或省略授权换取漂亮耗时。

### 25.4 完成定义

只有在协议样例、负例、故障注入、权限、部署恢复、嵌入 UI、评测门禁和真实执行证据均满足要求后，版本才可以标为 V0.1。

“页面已经画出来”“可以运行一次”“日志看起来正常”“单元测试通过”都不单独构成完成。

---

<a id="s26"></a>

## 26. 后续演进边界

V0.2 之后按真实需求考虑：额外 Adapter 和 MCP/A2A、完整结构化 Graph Diff、外部 Eval 后端、更多存储、分布式 Worker、第二运行后端、受控发布自动化、Memory 实验与生态注册。

任何新后端必须公开支持的 feature set，并运行同一 conformance suite。任何新 Adapter 必须说明幂等、取消、结果核对和观测能力；不能仅展示一个产品 Logo 即称支持。

任何新增核心字段必须至少用两类场景说明必要性；业务专有字段优先放入节点 payload、Capability 或扩展中。增加“更自由”的能力不能取消已有的权限、版本、审计和恢复边界。

**项目长期的核心资产是契约、一致性测试、可交付包、可靠适配经验和验收闭环；不是某个框架内部对象、一个特定平台或一张图。**

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

通用 HTTP 示例执行器必须使用自己的持久表，将 dispatchKey 与 inputDigest 原子绑定；重复 submit 返回同一 executionRef；测试开关可在“创建后响应前”断开连接，用于 AC-09。

它至少提供 accepted→running→succeeded、明确失败、延迟取消确认、unknown、重复 revision、相同 revision 冲突、输出 Schema 不合法等可控行为。该示例只验证契约，不代表某个实际模型或远程服务已经具备同样保证。

---

<a id="appendix-b"></a>

## 附录 B. 一致性校验与首日施工清单

### B.1 首日需要产生的文件和测试

在 P0 中创建资源 Schema、ValueExpr/Predicate 类型、附录 A 的真实样例文件，以及至少以下测试：合法包、缺失 slot、重复 YAML 键、悬空边、同级环、缺失数据引用、无默认 switch、非法 repeat 上限、未实现 requiredFeature、私密配置误入归档。

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

ExecutionPlan 必须包括 plan_version、package_digest、binding_digest、workflow_id、输入输出 Schema 摘要、全部节点的规范化字段、显式默认值、边/子流程关系、source_map、required_features 和 compiled_plan_digest。

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

## 附录 C. 来源、修订性质与外部参考

### C.1 材料来源与本次决定

[S1] 用户提供《可移植智能工作流框架 V0.1 初始架构方案》：保留其统一黑盒节点、Specification/Binding 分离、State/Memory/Context 区分、Package、Git-native、Inspector、Eval 和可选语义通信的术语与方向。

[S2] 用户提供《可移植智能工作流框架：技术与参考选型文档 V0.1》：保留 React/React Flow/ELK、Python/LangGraph、FastAPI/Pydantic、OTel、可嵌入 UI、选择性复用而非整体 Fork 的主要路线。

本次新增并冻结的设计决定：资源身份与版本规则、具体 YAML/JSON 载体、控制流子集、统一 Adapter 生命周期、重试/核对/取消语义、权限交集、审批主题、持久意图与后端重入约束、部署模型、CLI/API、数据表族、资源上限和验收门禁。这些是为实现 V0.1 作出的规范决定，不是原草案中已经实现或外部资料已经证明的事实。

本次范围调整：可移植部署、最小评测、Package 与可嵌入 UI 进入 V0.1；Langfuse 改为可选；完整 Memory、自动调优、额外 Runtime 与复杂 Graph Diff 后置。通用架构不依赖任何具体试验宿主。

### C.2 外部资料

以下资料于 2026-09-19 核查，只支撑正文中标注的第三方能力、协议或许可事实；不替代本文的项目决策。官方文档后续变化不自动改变本规范或锁文件。

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

### C.3 开始开发时的最终检查

先落实协议、最小交付链和恢复测试，再扩大组件数量。不能用另一个产品的内部模型代替本规范，也不能为了让某个样例顺利运行，绕过授权、审批、状态核对或版本约束。

**V0.1 要交付的是：同一份工作流定义，通过显式 Binding 在不同环境中组织不同执行者；运行有事实，失败有证据，变更有验证，结果能交付。**
