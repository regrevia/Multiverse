# W05A: Claude 执行端适配

日期：2026-10-06
依赖：W03（已推送）
状态：`implementation_ready`，真实 cc-switch Runtime delivery 已通过。

## 交付范围

- Claude Code `--print` 的 `json` 与 `stream-json` 结构化适配。
- 强制无工具、无 session persistence、受控 permission mode 和安全参数。
- deadline、输出上限、cooperative stop、进程组清理和版本绑定。
- 统一 `execute_agent("claude", ...)`、Runtime Artifact、Observation 和 Runner 路由。
- `cc-switch` provider 配置继承：
  - 运行时读取 `~/.cc-switch/cc-switch.db`；
  - 只注入白名单环境变量；
  - 不持久化或回显 token；
  - Observation 记录非敏感 profile 来源和 model alias。

## 真实证据

Claude Code 版本：`2.1.197`。

命令：

```text
MULTIVERSE_RUN_CLAUDE_LIVE=1 \
uv run --python 3.12 --locked pytest -q -s \
tests/integration/test_claude_delivery_live.py
```

结果：`1 passed in 34.92s`

- Run：`run_8b54084e4df241b99ad3a57b5ebf922f`
- HumanRequest：`human_8cc14911ca8e426eb8f56fd777611e75`
- Artifact：`artifact_a87bba1345f54c0296f4d6131bdf8455`
- Artifact digest：`sha256:c43b0a091ccaa42e47b8860e689ca0593d27befda8f5ed2db381084822a87b54`
- 4 个 Attempt；最后一个进入真实人工待办。

直接 Claude probe 当前仍因认证条件不满足而 skip；不使用它替代上面的 cc-switch delivery 证据。

## 验证

- 定向适配器测试：`136 passed`
- 完整 Python：`562 passed, 15 skipped`
- Ruff：通过
- mypy：通过
- `git diff --check`：通过
- 实现快照清单：`final-tests/implementation-snapshot.sha256`
- 实现快照清单 SHA256：`641abda8556e0ff67854496d73860953e3c3f14be8f249c8d3633cace1aee4b9`
- 完整测试日志：`final-tests/python-full.log`
- Ruff 日志：`final-tests/ruff.log`
- mypy 日志：`final-tests/mypy.log`

## 限制

- 本轮只支持新建单次 Claude 调用；resume/fork、跨 CLI handoff 和身份/会话绑定属于 W06/W07。
- cc-switch 只提供运行时配置继承，不自动安装 Claude Code，也不绕过授权。
- 多租户身份、生产 Secret Provider 和沙箱不在本包范围。

## 独立审阅

最终 reviewer：`01a1114e-ad50-7131-bfb5-dff81ff76060`
状态：代码问题已关闭；最终状态回执将在实现提交和远端核对后补入。
