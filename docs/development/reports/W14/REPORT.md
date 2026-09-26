# W14：v1 发布契约、需求追踪与支持范围冻结

基线4a4cf9225e22a2539f83afd3e9907bc14861a1bc；W01实现及完成回执均远端核对。独立工作树/home/aied/tanyicheng/multiverse/.multiverse/worktrees/w14，分支work/w14-release；w14_release_contract（gpt-6-sol/medium）独占实现，主Agent管理STATE、串行整合、最终验收、独立审阅、推送。未完成实现/门禁前不标完成。

主Agent实现期检查：要求部署profile标识/摘要严格拒绝尾随换行（复用W01已发现的跨Schema边界）；personal profile不能永久强制trusted-local，应允许显式选择enforced而不声称隔离已实现，team必须enforced。已返给实现者补Schema/正负例及支持矩阵说明，正式独立review仍在最终测试之后进行。

## 实现结果与范围

主Agent从已冻结work/w14-release精确整合8文件，逐一字节核对一致。新增支持矩阵、逐条验收账、部署profile Schema及两份release契约测试；更新README、唯一规范和根规划责任映射。222原ID+16新V1门槛全pending，未把基线单元测试当作完整v1验收。

正式v1弃用期为90天且两个minor，自正式发布生效，不回溯0.1预览；软件仍0.1.0，线级仍multiverse/v0.1。区分资源/HTTP Job/API/CLI/事件/SDK面。未实现完整导入/过期客户端/SDK协商保留可执行后续设计，未假造通过。

profile只声明形状，personal显式trusted-local或enforced，team enforced；offline外网禁止和资源清单不等于已部署。Node24/pnpm目标与当前Node20/npm/Python3.14开发事实分开；未实测矩阵未宣称supported。

责任闭包调整：AC-01→W24；AC-17/18/19→W16；AC-29→W17；G-19/SUP-23→W20；LH-13及V1-10最终汇合→W29；原owner保留contributors。范围与222ID未缩减，STATE依赖无新增边。

实现者在独立venv定向release 60 passed；主整合后的完整门禁及独立review记录才是本包最终批准依据。支持矩阵绑定W01基线，后续W02合入必须按实际能力更新，不能用该表推定未来已验证。

主整合全量：Python375 passed（含release60）、前端27 passed，uv/npmci/ruff/mypy/build/plan/只读CLI/diff全部通过，无skip。最终快照3aa0cdb6d392e310063e6553af558e879dbc0e5d5c58ffd9ca8efc94943de3e9，204文件，测试前后不变。进入实际独立审阅。

第一轮独立审阅P2 RDI责任闭包遗漏已返工：RDI-01最终owner W13，contributors W01/W02/W03/W04/W05A/W05B；RDI-02最终owner W24，contributors W01/W13/W16。同步规划理由与测试线索，新增4回归拒绝退回W01或清空必要贡献者绕过。原树64定向通过，主精确同步3文件后重验。

返工后主全量final-tests-r2：379 Python/27前端通过，其余门禁全0无skip，产品快照9799fc39de0a1562ee2fcda410e002a04533e2fefc13845ce4fe850137892369前后不变；调用原reviewer复审。

独立复审approved，P2 W14-R1关闭，独立64项通过；主验收采用r2完整379/27及冻结摘要。该包仅冻结契约和追踪，238项真实最终验收仍pending。推送完成信息在独立回执追加，不改本报告。
