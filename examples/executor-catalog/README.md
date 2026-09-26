# 显式受信任目录示例

本目录列出完整的默认实现，供操作者复制后审核；HTTP 示例仍未安装/可用/验证。
`verificationEvidence` 是示例中的操作者证据描述，不是加载器执行了测试的证明。
修改 schema 文件后必须重新计算原始文件字节 SHA256 并更新 configSchemaDigest。
不要把普通工作流包提供的注册文件作为可信管理配置加载。

```bash
mverse capabilities --registry examples/executor-catalog --executor local.process.v1 --json
mverse preflight presets/content-delivery --binding examples/bindings/content-local.yaml --registry examples/executor-catalog --json
```

`--registry DIRECTORY` 同样适用于 validate/run/serve/worker/sweep/resume/rerun/decide。
不提供时使用默认目录。显式目录完全替换默认目录；要保留某个内建执行器必须列出它。
`capabilities --executor REF --json` 保持 executors 数组 envelope，仅返回匹配项；未知引用为
EXECUTOR_UNRESOLVED，目录错误为 CATALOG_INVALID。

修复 Binding：先查询对应执行器的 configSchema；按 properties/required 填写 config，再运行
preflight。local_process 必须有非空字符串数组 command（允许纯空白参数），timeoutSeconds 为正数；HTTP Job
必须有 HTTP(S) baseUrl。人类/内建/Ollama 的实际字段均在 Schema 内，未知字段会被拒绝。
目录附加 Schema 与后端 Schema 共同生效。configSchemaDigest 对应引用文件原始字节，
effectiveConfigSchemaDigest 对应输出的有效 configSchema 按键排序、无空白 JSON 摘要。
W01 不支持配置 Schema 的 $ref/$dynamicRef/$id（包括本地片段）。

例如 `timeoutSeconds: 0` 的诊断 pointer 指向该 config 字段，expected 给出 exclusiveMinimum 0；
将其改为正数并重新 preflight。actual 仅含类型/脱敏占位，不输出配置中的 Secret。
配置合法不证明连接、凭据、授权或隔离可用。只有全部调用的配置检查完成后报告才将 executor-config 列入 checked；目录撤销或未解析执行器等跳过路径仍列入 notChecked。

`builtin.human-input.v1` 兼容旧 Binding 的 `requestType: input` 与 `choices: []`；
不接受其他 requestType 或非空 choices。旧 `requireCommentFor` 字符串数组保留为 deprecated
兼容字段，在 input 请求中无作用，不增加审批或必须评论的语义。

已构造实例保持同一描述快照。目录文件变更/删除会阻止其后新 Run 的注册预检，需要显式重启/重载；
它不会取消已经启动的任务，也不提供持续热撤销授权。local_process 是可信本地命令执行，不是沙箱。
