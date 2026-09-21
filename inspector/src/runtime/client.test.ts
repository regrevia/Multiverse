import { describe, expect, it, vi } from "vitest";
import {
  RuntimeClient,
  mergeRuntimeEvents,
  parseSseText,
  type RuntimeEvent,
} from "./client";

const event = (seq: number): RuntimeEvent => ({
  seq,
  type: seq === 1 ? "run.created" : "run.updated",
  occurredAt: `2026-09-21T00:00:0${seq}Z`,
  scopeId: null,
  invocationId: null,
  attemptId: null,
  payload: { customer_id: `value-${seq}`, customerId: `value-${seq}` },
});

describe("runtime client", () => {
  it("parses multiline SSE data and ignores keepalive comments", () => {
    expect(
      parseSseText(
        ": keepalive\n\nid: 7\nevent: run.updated\ndata: {\"seq\":7,\ndata: \"type\":\"run.updated\"}\n\n",
      ),
    ).toEqual([
      {
        id: "7",
        event: "run.updated",
        data: '{"seq":7,\n"type":"run.updated"}',
      },
    ]);
  });

  it("deduplicates and orders events by sequence without changing business payload keys", () => {
    expect(mergeRuntimeEvents([event(2)], [event(1), event(2), event(3)])).toEqual({
      events: [event(1), event(2), event(3)],
      lastSeq: 3,
    });
  });

  it("sends bearer authorization and preserves the runtime URL path", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "run_123", status: "waiting" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new RuntimeClient(
      {
        baseUrl: "http://127.0.0.1:8080/",
        namespace: "local",
        runId: "run_123",
        token: "secret-token",
      },
      fetchImpl,
    );

    await client.getRun();

    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8080/api/v1/namespaces/local/runs/run_123");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret-token");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("reports non-2xx runtime errors with the server error code", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: "CURSOR_EXPIRED", message: "reload snapshot" },
          requestId: "req_1",
        }),
        {
          status: 409,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    const client = new RuntimeClient(
      { baseUrl: "http://runtime", namespace: "local", runId: "run_123", token: "token" },
      fetchImpl,
    );

    await expect(client.getRun()).rejects.toMatchObject({
      status: 409,
      code: "CURSOR_EXPIRED",
      message: "reload snapshot",
    });
  });

  it("lists human requests with their frozen input and submits the same versioned decision", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            requests: [
              {
                id: "human_1",
                runId: "run_123",
                scopeId: "scope_1",
                invocationId: "inv_1",
                requestType: "review",
                title: "Human review",
                instructions: "Review the deliverable.",
                input: { deliverable: { text: "Draft" } },
                inputDigest: "sha256:input",
                subjectDigest: "sha256:subject",
                choices: ["approve", "reject"],
                decisionSchema: { type: "object" },
                authorizedSubjects: ["reviewer"],
                createdAt: "2026-09-20T00:00:00Z",
                expiresAt: "2026-09-21T00:00:00Z",
                version: 1,
                status: "pending",
                decisionId: null,
                updatedAt: null,
              },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            requestId: "cmd_1",
            status: "completed",
            resourceId: "run_123",
            operation: "human-request.decide",
            resourceVersion: 2,
          }),
          { status: 202, headers: { "content-type": "application/json" } },
        ),
      );
    const client = new RuntimeClient(
      { baseUrl: "http://runtime/", namespace: "local", runId: "run_123", token: "token" },
      fetchImpl,
    );

    const result = await client.listHumanRequests();
    const receipt = await client.submitHumanDecision(
      "human_1",
      {
        expectedVersion: result.requests[0]?.version ?? 0,
        subjectDigest: result.requests[0]?.subjectDigest ?? "",
        choice: "approve",
        comment: "Approved from Inspector.",
      },
      "inspector-decision-1",
    );

    expect(result.requests[0]?.input).toEqual({ deliverable: { text: "Draft" } });
    expect(receipt.operation).toBe("human-request.decide");
    const [url, init] = fetchImpl.mock.calls[1] ?? [];
    expect(url).toBe(
      "http://runtime/api/v1/namespaces/local/human-requests/human_1/decisions",
    );
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token");
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe("inspector-decision-1");
    expect(JSON.parse(String(init?.body))).toEqual({
      expectedVersion: 1,
      subjectDigest: "sha256:subject",
      choice: "approve",
      comment: "Approved from Inspector.",
    });
  });

  it("reads artifact metadata and preserves content response headers", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "artifact_123",
            namespace: "local",
            runId: "run_123",
            invocationId: "inv_1",
            name: "release.md",
            mediaType: "text/markdown",
            sizeBytes: 15,
            digest: "sha256:artifact",
            status: "ready",
            createdAt: "2026-09-21T00:00:00Z",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response("# Release\n", {
          status: 200,
          headers: {
            "content-type": "text/markdown",
            etag: '"sha256:artifact"',
          },
        }),
      );
    const client = new RuntimeClient(
      { baseUrl: "http://runtime/", namespace: "local", runId: "run_123", token: "token" },
      fetchImpl,
    );

    const metadata = await client.getArtifact("artifact_123");
    const content = await client.getArtifactContent("artifact_123");

    expect(metadata).toMatchObject({
      id: "artifact_123",
      namespace: "local",
      runId: "run_123",
      digest: "sha256:artifact",
      status: "ready",
    });
    expect(await content.text()).toBe("# Release\n");
    expect(content.headers.get("content-type")).toBe("text/markdown");
    expect(content.headers.get("etag")).toBe('"sha256:artifact"');

    const [metadataUrl, metadataInit] = fetchImpl.mock.calls[0] ?? [];
    expect(metadataUrl).toBe(
      "http://runtime/api/v1/namespaces/local/artifacts/artifact_123",
    );
    expect(new Headers(metadataInit?.headers).get("Authorization")).toBe("Bearer token");
    const [contentUrl, contentInit] = fetchImpl.mock.calls[1] ?? [];
    expect(contentUrl).toBe(
      "http://runtime/api/v1/namespaces/local/artifacts/artifact_123/content",
    );
    expect(new Headers(contentInit?.headers).get("Authorization")).toBe("Bearer token");
    expect(new Headers(contentInit?.headers).get("Accept")).toBe("*/*");
  });

  it("reads invocation details, one human request, and graph artifacts", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            invocations: [
              {
                id: "inv_1",
                runId: "run_123",
                scopeId: "scope_1",
                nodeId: "produce",
                status: "succeeded",
                input: { goal: "write a release note" },
                inputDigest: "sha256:input",
                output: { text: "Draft", artifact_refs: [] },
                error: null,
                version: 2,
                createdAt: "2026-09-21T00:00:00Z",
                updatedAt: "2026-09-21T00:00:01Z",
                attempts: [],
              },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "inv_1",
            runId: "run_123",
            scopeId: "scope_1",
            nodeId: "produce",
            status: "succeeded",
            input: { goal: "write a release note" },
            inputDigest: "sha256:input",
            output: { text: "Draft", artifact_refs: [] },
            error: null,
            version: 2,
            createdAt: "2026-09-21T00:00:00Z",
            updatedAt: "2026-09-21T00:00:01Z",
            attempts: [],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "human_1",
            runId: "run_123",
            scopeId: "scope_1",
            invocationId: "inv_1",
            requestType: "review",
            title: "Human review",
            instructions: "Review the deliverable.",
            input: { deliverable: { text: "Draft" } },
            inputDigest: "sha256:input",
            subjectDigest: "sha256:subject",
            choices: ["approve", "reject"],
            decisionSchema: { type: "object" },
            authorizedSubjects: ["reviewer"],
            createdAt: "2026-09-21T00:00:00Z",
            expiresAt: "2026-09-22T00:00:00Z",
            version: 1,
            status: "pending",
            decisionId: null,
            updatedAt: null,
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            protocolVersion: "multiverse/v0.1",
            run: {
              id: "run_123",
              deploymentId: "deployment_local",
              workflowId: "delivery",
              packageDigest: "sha256:package",
              bindingDigest: null,
              status: "waiting",
              controlMode: "running",
              currentScopeId: "scope_1",
              currentNodeId: "review",
              currentInvocationId: "inv_1",
              version: 4,
              deadlineAt: "2026-09-22T00:00:00Z",
              createdAt: "2026-09-21T00:00:00Z",
              updatedAt: "2026-09-21T00:00:01Z",
              rerunOf: null,
              rerunReason: null,
            },
            scopes: [],
            nodes: [],
            edges: [],
            events: [],
            humanRequests: [],
            artifacts: [
              {
                id: "artifact_1",
                invocationId: "inv_1",
                name: "release.md",
                mediaType: "text/markdown",
                sizeBytes: 8,
                digest: "sha256:artifact",
                status: "ready",
                createdAt: "2026-09-21T00:00:01Z",
              },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );
    const client = new RuntimeClient(
      { baseUrl: "http://runtime", namespace: "local", runId: "run_123", token: "token" },
      fetchImpl,
    );

    const listed = await client.listInvocations({ scopeId: "scope_1" });
    const detail = await client.getInvocation("inv_1");
    const request = await client.getHumanRequest("human_1");
    const artifacts = await client.listArtifacts();

    expect(listed.invocations[0]?.input).toEqual({ goal: "write a release note" });
    expect(detail.output).toEqual({ text: "Draft", artifact_refs: [] });
    expect(request.subjectDigest).toBe("sha256:subject");
    expect(artifacts[0]?.id).toBe("artifact_1");

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(
      "http://runtime/api/v1/namespaces/local/runs/run_123/invocations?scopeId=scope_1",
    );
    expect(fetchImpl.mock.calls[1]?.[0]).toBe(
      "http://runtime/api/v1/namespaces/local/invocations/inv_1",
    );
    expect(fetchImpl.mock.calls[2]?.[0]).toBe(
      "http://runtime/api/v1/namespaces/local/human-requests/human_1",
    );
    expect(fetchImpl.mock.calls[3]?.[0]).toBe(
      "http://runtime/api/v1/namespaces/local/runs/run_123/graph",
    );
  });
});
