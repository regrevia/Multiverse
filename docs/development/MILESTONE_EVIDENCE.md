# 里程碑机器证据（W00）

`scripts/milestones.py` 是只读的一致性检查器，不执行测试、fetch、push或review。
它不能凭JSON证明真人操作、独立Agent身份或真实工具调用；负责人仍须实际调用工具，
保存脱敏回执，reviewer核对原始记录及验收覆盖。记录中的测试清单也不能替代规划规定的必需检查。

```bash
python scripts/milestones.py check-plan
python scripts/milestones.py next
python scripts/milestones.py snapshot
python scripts/milestones.py check W00 --phase pre-push
# 调用方在受控环境中先完成 git fetch origin dev 及远端核对：
python scripts/milestones.py check W00 --phase remote
```

所有结果为stdout JSON。退出码0表示该查询成功（`next`可能返回恢复或续推动作，
不代表已完成），1表示门禁拒绝/没有就绪包，2表示输入或文件/Git错误。
`check`省略phase时，completed使用remote，其余使用pre-push。
全局参数置于子命令之前：`--repo ROOT`、`--state PATH`和`--report EVIDENCE_JSON`。
repo默认脚本所在仓库；state默认`docs/development/STATE.json`；参数路径相对repo，
不得越出repo。`--report`只用于注入证据JSON，不是REPORT.md。

STATE每包`report`相对于STATE所在目录，例如`reports/W00/REPORT.md`。
可选`evidence`同样相对STATE目录；默认REPORT.md同目录的`EVIDENCE.json`。
其他证据引用和snapshot文件路径均相对于repo根。

## 快照和收尾顺序

`snapshot`返回`{ "ok": true, "snapshot": { "files": {...}, "digest": "..." } }`。
files包含全部Git跟踪文件及非忽略的未跟踪文件，含产品代码、Schema、文档、工具和测试；
每项为`{"sha256":"文件原始字节SHA256","mode":"100644"}`，可执行文件100755、符号链接120000
（摘要为链接目标文本）。删除以文件缺席表示。Git子模块不支持，遇到时拒绝。
digest是files按key排序、无空白JSON的UTF-8字节SHA256。

只有当前STATE文件和固定`docs/development/reports/`目录不进入摘要，避免状态/证据引用自身。
没有任意排除列表。禁止在reports内放实现、配置或验收脚本绕过快照；该目录仅存报告和回执。
忽略文件不会读取；凭据、真实数据库和私人评测必须按仓库规则排除，不上传到报告。

1. 修改实现、测试、Schema及文档，保存最终snapshot。任何后续被覆盖文件变化都要重新测试和review。
2. 实际运行规划规定检查，将结果、日志索引和snapshot digest填入tests。
3. 实际调用独立reviewer，将task ID、调用工具、回执引用、范围、限制和最终批准摘要填入reviews。
   修复后重新生成摘要、复测、调用原reviewer复审；reviews只放最终有效批准，历史轮次存报告附件。
4. 完成REPORT.md、EVIDENCE.json及其引用的脱敏回执文件。状态reviewing/ready_to_push/push_pending时
   `check ID --phase pre-push`可通过；此阶段不要求本包已推送，避免自身验收循环。所有依赖仍须远端完成。
5. 将实现和全部证据一起提交为C，正常推送并由调用方fetch/核对。STATE改completed并填
   `implementation_commit=C`，另建状态回执提交R并推送。STATE无须记录自身R的ID。
6. `check ID --phase remote`核对C是本地remote ref祖先、remote ref的STATE条目为相同completed/C/
   report/evidence/depends_on，以及实现C的文件树摘要与证据一致。REPORT.md、EVIDENCE.json和所有
   引用文件在C、当前工作树和remote ref必须同内容。之后允许后继包改变产品文件，不用当前工作树
   检验历史包快照。追加日志/推送回执放独立新文件，不改已绑定证据文件。

远端检查只读取本地`refs/remotes/<push_policy.remote>/<push_policy.branch>`（默认origin/dev）。
它不确认该ref新鲜度，不发送网络请求，不能用陈旧ref代替实际fetch/ls-remote。
`next`优先续推实现/协调未到远端的完成回执，然后恢复到期外部验证、活动包，再按STATE顺序领取就绪包。
多个前台活动包返回协调错误，不擅自跳过。依赖仅在remote检查通过后解锁。
`check-plan`检查状态、依赖、重复ID/环，也检查completed的远端证据及waiting_external记录。

## EVIDENCE.json最小结构

下列摘要值和回执内容必须由实际执行产生；示例不构成验收证据。
每个必需检查有唯一test ID；required_tests不得为空，必须包含规划适用命令及本包验收。
全部tests记录（含非required项）均校验必填字段、日志文件引用、计数、退出码和快照摘要，
remote阶段还要求日志在C及远端保持同内容。全部记录的测试不能失败；required_tests中的每项
必须存在；必需live检查不能skip且必须有passed结果。
没有测试计数的工具（ruff/build等）可以用0/0/0，exit_code必须0。

```json
{
  "package_id": "W00",
  "snapshot": {"files": {"app.py": {"sha256": "ACTUAL_SHA256", "mode": "100644"}}, "digest": "ACTUAL_DIGEST"},
  "required_tests": ["python-full"],
  "tests": [{
    "id": "python-full", "command": "uv run --locked pytest -q", "cwd": ".",
    "tool_versions": {"python": "ACTUAL_VERSION", "pytest": "ACTUAL_VERSION"},
    "started_at": "2026-09-26T00:00:00Z", "exit_code": 0,
    "passed": 1, "failed": 0, "skipped": 0, "live": false,
    "log_ref": "docs/development/reports/W00/TESTS.md#python-full",
    "snapshot_digest": "ACTUAL_DIGEST"
  }],
  "acceptance": [{"id": "baseline", "status": "passed", "evidence_ref": "docs/development/reports/W00/ACCEPTANCE.md"}],
  "reviews": [{
    "task_id": "ACTUAL_REVIEWER_TASK_ID", "tool": "collaboration.spawn_agent",
    "record_ref": "docs/development/reports/W00/REVIEW.md#final-approval",
    "reviewer_role": "independent", "scope": ["actual reviewed paths"],
    "limitations": [], "blocking_findings": [], "verdict": "approved",
    "snapshot_digest": "ACTUAL_DIGEST"
  }]
}
```

引用必须指向仓库内真实非空文件；可附`#片段`索引（不验证片段语义）。原始敏感日志只留受控本地，
版本化脱敏摘要记录原日志位置、命令/退出码及实际工具回执标识。机器只核验文件存在及提交一致性，
不认证内容真实性。REPORT.md保留范围、基线、验收矩阵、修复复测、已知限制和完整索引。

## waiting_external

STATE包状态waiting_external时必须提供以下`background_validation`对象。source_commit必须存在于
本地Git对象库；next_check_at须含时区。隔离对象必须分别声明workspace/database/ports，workspace
不能为当前repo；这是声明一致性检查，操作者仍须验证资源确实隔离。无需数据库/端口可填明确的
`"not used"`，不可留空。到期的包优先恢复；未到期包允许其他无依赖就绪包继续，不解锁其下游。

```json
{
  "source_commit": "FIXED_COMMIT",
  "artifact_digests": {"candidate": "sha256:ACTUAL_DIGEST"},
  "isolated_environment": {"workspace": "/absolute/isolated/worktree", "database": "isolated-db", "ports": [9012]},
  "task_id": "ACTUAL_BACKGROUND_TASK", "log_ref": "controlled-local-log-location",
  "checkpoint": "last completed stage", "next_check_at": "2026-09-27T00:00:00Z",
  "resume_command": "actual resumable command"
}
```
