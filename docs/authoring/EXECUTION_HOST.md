# 可信本地执行宿主

W02 提供 Linux loopback HTTP Job 服务端，运行操作者安装的固定程序；其他系统未验证。
这不是沙箱、认证公网服务或第二个 Workflow Runtime。执行程序拥有当前用户权限；
不应配置不可信代码。网络提交不能指定可执行程序或环境变量。
写请求必须 application/json；Host 必须是实际绑定的 IPv4 地址与端口，Origin 若存在必须同源，
以阻止浏览器跨站提交和 DNS rebinding。未提供 Origin 的本地客户端可用；这不是用户认证。
请求体上限 256 KiB，header/body 读取共享绝对 5 秒时限，禁止分块编码。

从仓库根目录恢复环境并启动示例（`uv` 是仓库环境中安装的工具）：

```bash
uv sync --locked
uv run --locked python -m multiverse_workflow.execution_host \
  --trusted-loopback --database .multiverse/host/host.db --root .multiverse/host/jobs \
  --executor-ref example.remote-content.v1 --port 8790 \
  --capability content.produce@1 --capability content.review@1 -- \
  "$PWD/.venv/bin/python" "$PWD/examples/execution-host/deterministic_program.py"
```

示例 Binding 使用 `secretRefs: {}`；Runtime 发送的 `local-grant` 仅是开发模式标记，
不构成凭据或权限证明。可信 loopback 宿主不验证用户身份，不应创建虚假的 Secret 引用。

宿主默认 namespace 为 `local`。显式非 loopback 地址会被拒绝；当前参考实现只支持 IPv4。
SQLite 数据库及相邻 `.lock` 文件对应一个活宿主，第二进程拒绝启动。
不要在两个数据库间复用任务工作根目录，不要在运行中更换程序或 namespace。

在另一终端先运行真实本地合约测试，再将目录样例复制为操作者配置。以下声明仅针对
确定性示例及本机实测结果，不代表任意远端执行器得到验证。
登记是受信任操作者根据测试证据作出的声明；此宿主必须标记 `permissionLevel: trusted_local`，
不能继承远端目录样例的 `enforced`。`supportsCancel` 只描述宿主取消接口，
不代表 Runtime 完整取消分发已接线；后者仍由 W16 负责。

```bash
uv run --locked pytest tests/execution_host tests/runtime/test_http_job.py tests/runtime/test_http_job_runtime.py tests/runtime/test_http_artifact_transfer.py -q
uv run --locked python - <<'PY'
import json
import shutil
from pathlib import Path
root = Path('.multiverse/host-registry')
shutil.copytree('examples/executor-catalog', root, dirs_exist_ok=True)
path = root / 'executor-registration.json'
catalog = json.loads(path.read_text())
for item in catalog['executors']:
    if item['executorRef'] == 'example.remote-content.v1':
        item.update(installed=True, available=True, verified=True, permissionLevel='trusted_local')
        item['verificationEvidence'] = {
            'kind': 'operator-attestation', 'reference': 'tests/execution_host',
            'environment': 'trusted-loopback Linux deterministic program',
            'executorVersion': '1.0.0',
            'cases': ['real subprocess, crash recovery, owned-group cancel, artifact import']}
path.write_text(json.dumps(catalog, indent=2) + '\n')
PY
uv run --locked mverse preflight presets/content-delivery \
  --binding examples/bindings/content-execution-host.yaml --registry .multiverse/host-registry --json
uv run --locked mverse run presets/content-delivery \
  --binding examples/bindings/content-execution-host.yaml --registry .multiverse/host-registry \
  --db .multiverse/host-runtime.db --input examples/execution-host/input.json
```

继续启动同一配置的 Worker（到达人工审核后可按 Ctrl-C 停止轮询）：

```bash
uv run --locked mverse worker presets/content-delivery \
  --binding examples/bindings/content-execution-host.yaml --registry .multiverse/host-registry \
  --db .multiverse/host-runtime.db
```

执行是持久等待：HTTP submit 返回接受并不意味着完成；Worker 轮询相同 executionRef。
标准客户端可以调用 `describe/submit/lookup/observe/cancel/fetch_artifacts`。
宿主进程断开或重启后，已保存终态/产物仍可查询；没有终态的执行进入 unknown，
即使 PID 不存在也不自动再次运行。没有原生恢复/接管功能，应由操作者核对真实副作用。

程序 stdin 为标准 ExecutionRequest。stdout 必须是一个有限 JSON 对象：

```json
{"output":{"text":"result","artifact_refs":[]},"artifacts":[{"path":"result.txt","name":"result.txt","mediaType":"text/plain"}]}
```

`artifacts` 可省略；`path` 只允许任务 cwd 下的单个普通文件名，不允许子目录、符号链接或
绝对路径。宿主冻结产物字节后公布终态。Runtime 从固定同源 content 端点取字节，验证
namespace、执行身份、版本、大小和 SHA-256，再按来源身份幂等登记。
只有 Runtime 返回的 ArtifactRef 才可交给下游；宿主路径/URL/原始 blob ID 都不是引用。

默认 stdout 上限 256 KiB、stderr 上限 64 KiB、运行时限 30 秒（`--timeout` 可调整，
最大 3600 秒）。两路并行读取，超限失败并终止任务拥有的进程组。日志仅写任务专属
`stderr.log`，不混入 JSON 或 HTTP 错误响应；不继承操作者完整环境，仅提供 PATH、LANG、
任务 HOME。仍须保证受信任程序不主动输出秘密。产物每件最多 1 MiB、最多 8 件、合计 4 MiB。
内部事件按 execution 持久记录最近 32 个观察，cursor 为 revision；不收集无界日志事件。
GET observe 返回最新固定快照，可用 cursor 判断变化，不提供流式事件订阅。

取消端点先保存 commandId，再向当前宿主持有身份的任务专属进程组请求停止，声明
`best_effort`。重复取消不改变已确定终态；停止进程不代表撤销已发生的文件/网络副作用。
进程主动逃离进程组不在保证范围。重启后不会仅凭历史 PID 发信号。
当前 Runtime `cancel` 尚未自动派发宿主取消；完整控制意图→取消分发与竞争保证归 W16。
此版本新增观察导入路径会检查运行控制状态，取消后不得以迟到成功启动下游。
