# Inspector 单工作流工作台优化

日期：2026-10-08
状态：`approved_bounded_checkpoint`
分支：`dev`

## 范围

将 Inspector 收敛为当前单个工作流的工作台，而不是全局管理平台：

- 移除左侧工作流/运行全局导航和模板复制引导弹窗。
- 顶部显示当前工作流与来源，提供 Runtime 快照导入、运行视图导出和 Runtime 连接。
- 主区保留流程图、运行状态、人工任务入口、最近证据与节点操作。
- 保留右侧节点审计、人工决定和智能体编辑面板。
- 导出 `multiverse-view/v0.1`；允许重新导入并恢复图、运行证据和节点布局。
- Runtime 连接成功后显示实际 workflow 来源。
- 画布尺寸变化时重新适配；节点选择或实时投影更新不重置用户的缩放和平移。

## 验收边界

- 当前“导入快照”接受 Runtime projection JSON 和 Multiverse 运行视图 JSON。
- 当前不接受可执行 Workflow Package 的 `.multiverse.json` 定义文件；不声称已完成单文件工作流定义导入、环境 Binding 自动配置、Run 创建或 Runtime 自动启动。
- “导出视图”导出的是运行视图与审计事实，不是可执行工作流定义。
- 移动端首先聚焦当前活动节点；完整画布可通过现有画布平移/缩放操作浏览。
- 该 bounded checkpoint 不代表 W13/W20 或其他工作包完成，不修改 `STATE.json` 中各工作包状态。

## 验证

- `cd inspector && npm run test:run`：`37 passed`。
- `cd inspector && npm run build`：通过。
- `git diff --check`：通过。
- `node /Users/apple/.agents/skills/impeccable/scripts/detect.mjs --json inspector/src/App.tsx inspector/src/styles.css inspector/src/graph/runtime.ts inspector/src/graph/runtime.test.ts inspector/index.html`：检测器因缺少 `htmlparser2`、`css-select`、`css-tree`、`domutils` 降级到 regex fallback，返回 `[]`；该结果不包含 computed contrast 审计。
- Playwright：桌面 `1440x900` 与移动端 `390x844` 页面已检查；点击其他节点后画布变换保持不变。
- Playwright 实际导出 `content-delivery-view.json`，再经文件选择器导入该文件成功；工作流图、节点详情和来源名称恢复。导出文件为本地浏览器临时产物，未纳入 Git。
- 截图：`output/playwright/desktop-final.png`、`output/playwright/mobile-final.png`。

## 独立审阅

- Reviewer：`01a11a35-5072-7990-9b1f-27702f445b40`
- 最终结论：`approved`
- 最终复审确认签名来源：view snapshot 严格解析、Runtime 来源标识、稳定 ResizeObserver 和非法 edge label 拒绝。
- 最终复审 reviewer 未重新运行测试/build；上述最终测试结果由主 Agent 在最终代码快照上运行并记录。
- 审阅代码文件 SHA256：
  - `inspector/index.html`: `f6ad6dceae0006524bb9b4c7bd3073eb295543c4bed6421f9bb661b0921fd0d6`
  - `inspector/src/App.tsx`: `794f720f49de50936ef34852e6c938886faf806710928face4e5d3cf23ee3536`
  - `inspector/src/styles.css`: `1efa60f42c5620008989a33ca9dce998a5f4f2f83a97ac64364351b03b9d7d28`
  - `inspector/src/graph/runtime.ts`: `9066baffd9e425b6e27340f4d0574602f7d2c301f2a5604ea580f88dffeb53f3`
  - `inspector/src/graph/runtime.test.ts`: `7e0b70e1bb0d45c075e19cac093984af2dbe95d08d947e0a3d2147fc4a158fdb`

## 远端

实现提交：`a3ec0eb96974935832ff018c89b895dfc0f77617`。

状态：`push_pending`。`git push origin HEAD:dev` 和
`git ls-remote origin refs/heads/dev` 均以 exit code 128 失败，错误为
`Connection closed by 127.0.0.1 port 7897`。远端提交未核验，本地提交不代表已同步。
