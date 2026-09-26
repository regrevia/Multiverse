from __future__ import annotations

import argparse
from pathlib import Path

from multiverse_workflow.execution_host.backend import ProcessConfig
from multiverse_workflow.execution_host.service import ExecutionHost, create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Trusted loopback HTTP Job host (Linux)")
    parser.add_argument("--trusted-loopback", required=True, action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--executor-ref", default="example.execution-host.v1")
    parser.add_argument("--namespace", default="local")
    parser.add_argument(
        "--capability", action="append", help="Operator-declared capability; repeatable"
    )
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Operator-installed absolute executable and fixed arguments after --",
    )
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    config = ProcessConfig(
        tuple(command),
        executor_ref=args.executor_ref,
        namespace=args.namespace,
        timeout_seconds=args.timeout,
        capabilities=tuple(args.capability or ["content.produce@1"]),
    )
    host = ExecutionHost(args.database, args.root, config)
    try:
        server = create_server(host, address=args.host, port=args.port)
        print(
            f"Trusted loopback execution host: http://{args.host}:{server.server_port}", flush=True
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        host.close()


if __name__ == "__main__":
    main()
