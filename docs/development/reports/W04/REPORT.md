# W04: 首条真实人机协作闭环

日期：2026-09-30
当前源码基线：`86c67dbe704b0c054063659ee53efbe53d619187`
依赖：W03（远端完成并通过 `scripts/milestones.py check W03 --phase remote`）
状态：**blocked，等待一次获授权真人通过当前 Inspector 提交真实 approve 或 reject**

## 当前实现与门禁

W04 复用 Runtime HTTP API、Ledger、HumanRequest、Artifact 登记和 Inspector。当前代码/自动化已验证真实 Codex producer → 程序 verifier → 业务 HumanRequest → approve/reject 终态；决定绑定授权主体、subjectDigest、expectedVersion 和幂等键。Inspector 使用 Runtime 实时投影，可刷新后重建同一 Run。

当前快照门禁：

- 完整 Python：`523 passed, 12 skipped`，日志 `final-tests/python-full.log`
- 服务 e2e：`1 passed`，日志 `final-tests/service-e2e.log`
- Inspector：`33 passed`，日志 `final-tests/frontend-tests.log`
- Inspector 生产构建：成功，日志 `final-tests/frontend-build.log`
- npm clean install：成功，日志 `final-tests/npm-ci.log`
- Node/npm：`20.20.2` / `11.13.0`，匹配项目 `.nvmrc`
- Ruff：通过，日志 `final-tests/ruff.log`
- mypy：37 个源码文件通过，日志 `final-tests/mypy.log`
- `git diff --check`：通过，日志 `final-tests/diff-check.log`

## 当前快照 Live 证据

Live 命令及逐项输出保存在 `final-tests/live-coding-delivery-matrix.log`。

- **Codex → verifier → approve → succeeded**
  - Run：`run_58c1226afa104123a59ca5f6ad0f4cb1`
  - HumanRequest：`human_03ef894e953740168b52221b233b49d8`
  - Decision：`decision_724b2e2a690c4fb193be24196594b13d`
  - Actor：`example-reviewer`
  - `expectedVersion=1`，决策后 `request_version=2`
  - Artifact：`artifact_59cccea8d1c14f78a324bbd8d7780ead`
  - Artifact digest：`sha256:1ba13269d5e0dfe6a21e765ef0e19cad50af96341a8142aebb48a55c11bdb8ee`
  - 4 个 Attempt 均关联同一 Run；最终状态 `succeeded`。

- **Codex → verifier → reject → failed**
  - Run：`run_21d33a9e7d914d398c2032bb6bc08306`
  - HumanRequest：`human_9779a55438034cda8abbc2aea919f2e2`
  - Decision：`decision_33ff097b793243f9aea26886ebb88046`
  - Actor：`example-reviewer`
  - Subject digest：`sha256:930a407cfd49a02a1f2c7e35967ec142a3370ea38e9a8b3b536ea21c816dd79a`
  - `expectedVersion=1`，decision request version `2`
  - Run 终态错误：`DELIVERABLE_REJECTED`；重复相同幂等键不重复推进。

- **Runtime restart → approve → succeeded**
  - Run：`run_cd50b0a48fd545ae9dca5fb1162732e7`
  - Request：`human_ee04f327fb9b470d8ee84eeb7880a550`
  - Decision：`decision_71b926d4a50b47038149291e675b5fdc`
  - 恢复同一 request；最终 Attempt 数 `4`、Artifact 数 `1`。

- **Worker stop → Worker restart → durable continuation → succeeded**
  - Run：`run_e3a5ae1021bf40edb17c22bf7acb6a65`
  - Request：`human_beba7c28d79a452e8f2b8fc3dec28688`
  - Decision：`decision_d1f41e8cf4e64a4fbd9a1f13094239c1`
  - 第一 Worker 显式 `stop_event` 停止并关闭；决定以 `resume=False` 持久化；第二 Worker 经 `run_forever` 消费 durable continuation 并完成 Run。
  - Actor：`example-reviewer`；Subject digest：
    `sha256:2e3e7b376379ca42c1e19ca83eacca3c2b68013f997c1cc7b3726e19213d93d9`
  - `expectedVersion=1`；最终 Attempt 数 `4`、Artifact 数 `1`；重复决定不再推进。

## Inspector Reopen

浏览器现场记录见 [INSPECTOR_REOPEN.md](INSPECTOR_REOPEN.md)，截图及 SHA256 见该记录和 `assets/inspector-runtime-reopen.png`。

- Runtime：`http://127.0.0.1:8788`
- Inspector：`http://127.0.0.1:4173`
- Run：`run_66907af31bb04a6f8d1bc5336f6c04a5`
- Runtime API 与 Inspector 均显示 Run `succeeded`、节点 `complete`、事件序号 `40` 和真实 Artifact。
- 刷新后仍从 Runtime 重建同一 projection；页面明确显示 Runtime 实时连接和 Runtime 台账只读事实，无 demo fallback。
- 浏览器 token 未写入 URL 或持久 localStorage，且未写入仓库报告。

## 尚未满足的完成条件

上述 approve/reject 都是 live Codex 自动化测试使用授权测试主体 `example-reviewer` 通过 Runtime API 提交，不是由实际操作者在 Inspector 亲自操作。工作包规划明确要求实际演示的决定由获授权真人完成；作者 Agent 不代批。

因此 W04 **保持 blocked/pending，不能标记 completed**，直至获授权真人通过 Inspector 对一个真实待办作出 approve 或 reject，并由 Runtime 投影验证对应 Decision、Run 终态和 exactly-once 计数。其余自动化/live 证据不替代该动作。此本地 trusted-local 证据也不表示多租户身份认证或生产浏览器凭据存储已完成。
