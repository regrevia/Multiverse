# Agent 作者入口

你是 Workflow Package 的主要开发者。直接编辑文件，通过 CLI/Schema 检查；图形界面用于理解、审阅和辅助修改。运行 Agent、作者 Agent、真人审批者是不同角色。

先读本页。需要语义时按链接读取 [唯一规范](../spec/MULTIVERSE_SPEC.md) §6—9（契约）、§13（人工）、§20/30（编写和可移植性）；需要现有功能边界时读 [Authoring Guide](AUTHORING_GUIDE.md)。不要把规范的待实现行为当成当前功能。

## 发现、编辑、验证

在仓库根目录执行；使用锁文件安装的环境。以下均是已经实现的命令：

```bash
uv sync --locked
uv run mverse capabilities --json
uv run mverse validate presets/content-delivery \
  --binding examples/bindings/content-local.yaml --json
uv run mverse preflight presets/content-delivery \
  --binding examples/bindings/content-local.yaml --json
```

选择一个已有例子复制到**新的、不存在的目录**，保留原例子用于对照。先读 `manifest.yaml` 与节点引用的输入输出 Schema，再修改目标、节点和 Binding。顶层 Schema 在 `schemas/`；业务 Schema 放在包内，勿将业务专有字段添加进 Runtime。

- `presets/content-delivery`：产出 → 独立审阅 → 程序校验 → 人工决定。
- `presets/manual-input`：真人提交结构化结果与 Artifact。
- `examples/bindings/content-local.yaml`：确定性 fixture，不调用真实 Agent。
- `examples/bindings/content-ollama.yaml`：真实本地模型，需要实际可用的 Ollama 配置。
- `examples/bindings/content-remote.yaml`：远程能力声明例子；默认注册状态未安装/不可用/未验证，预检应失败。

## 使用机器结果修复

`validate` 检查声明契约。`preflight` 进一步检查同一个注册表快照中的安装、可用、验证状态，覆盖包内全部 Workflow。读取 `diagnostics[].code/file/pointer/suggestion`；注册状态问题还包含 `details.workflowId/nodeId/slot/source`，可直接定位需要修改的绑定及受影响节点。

`preflight` 的报告 Schema 为 [preflight-report.schema.json](../../schemas/preflight-report.schema.json)。`checked` 是已经运行的阶段，`notChecked` 是尚未检查的内容。`ok=true` 仅表示该检查子集通过：没有连接远端，没有检查任意配置、真实权限、沙箱或业务质量，也没有执行节点。退出码 0 通过、2 存在问题。

发现未绑定或不支持能力，报告缺口或选真实兼容执行器；不要编造 executorRef，不要把注册字段改成 true 作为“验证”，不要删掉验收、权限或人工节点来消除错误。包、Binding 或注册信息变化后重新检查。

## 授权试运行与证据

下面会执行本地 fixture 并写入运行数据库；先确保这在当前任务授权范围内。输入和数据库放在包目录外，避免改变包摘要。

```bash
mkdir -p .multiverse
printf '{"goal":"write a release note"}' > .multiverse/author-request.json
uv run mverse run presets/content-delivery \
  --binding examples/bindings/content-local.yaml \
  --input .multiverse/author-request.json \
  --db .multiverse/author-trial.db --json
```

读取返回的 Run ID，使用 `mverse inspect <run-id> --db .multiverse/author-trial.db --json` 获取状态与待办。遇到 HumanRequest，向有权主体呈现主题、证据和允许决定；作者 Agent 不冒充真人批准。

业务修改的交付材料包含：文件 diff、包/Binding 与计划摘要、Validate/预检结果、试验输入与结果、未验证集成、待绑定/待授权项。`git diff` 是当前文本审阅工具；完整语义 diff、Bundle 安装、Connector 和跨 CLI 会话切换仍未实现。

## 保持可移植

Workflow 只写逻辑 slot、Capability、输入输出和业务依赖。主机地址、真实账号、目录和凭据引用属于环境 Binding；Secret 明文不能进入包。换目标先换 Binding 并检查，避免改业务图迁就某个 CLI。

同一 Agent 可以有多个会话和执行位置；跨 CLI 默认通过授权任务材料和产物续接，不复制原生 session ID 后声称恢复。unknown 副作用必须核对，不能换执行器重试。会话切换目前是规范要求，当前 Runtime 尚无该 API。
