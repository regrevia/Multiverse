import { describe, expect, it } from "vitest";
import {
  mapRuntimeProjection,
  parseRuntimeProjection,
  parseRuntimeViewSnapshot,
} from "./runtime";

const snapshot = {
  protocolVersion: "multiverse/v0.1",
  run: {
    id: "run_123",
    deploymentId: "deployment_123",
    workflowId: "delivery",
    packageDigest: "sha256:package",
    bindingDigest: "sha256:binding",
    status: "waiting",
    controlMode: "run",
    currentScopeId: "scope_root",
    currentNodeId: "review",
    currentInvocationId: null,
    version: 7,
    deadlineAt: "2026-09-21T00:00:00Z",
    createdAt: "2026-09-20T00:00:00Z",
    updatedAt: "2026-09-20T00:01:00Z",
    rerunOf: null,
    rerunReason: null,
  },
  scopes: [
    {
      id: "scope_root",
      workflowId: "delivery",
      parentScopeId: null,
      parentInvocationId: null,
      path: ["root"],
      inputDigest: "sha256:input",
      status: "active",
    },
  ],
  nodes: [
    {
      id: "scope_root:produce",
      scopeId: "scope_root",
      nodeId: "produce",
      title: "Produce deliverable",
      type: "call",
      status: "succeeded",
      invocation: {
        id: "inv_produce",
        status: "succeeded",
        inputDigest: "sha256:produce-input",
        version: 2,
        createdAt: "2026-09-20T00:00:00Z",
        updatedAt: "2026-09-20T00:00:01Z",
        hasOutput: true,
        error: null,
      },
      latestAttempt: {
        id: "attempt_produce",
        attemptNo: 1,
        status: "succeeded",
        version: 1,
        inputDigest: "sha256:produce-input",
        externalRef: null,
        createdAt: "2026-09-20T00:00:00Z",
        updatedAt: "2026-09-20T00:00:01Z",
        hasOutput: true,
        error: null,
      },
      attempts: [],
    },
    {
      id: "scope_root:review",
      scopeId: "scope_root",
      nodeId: "review",
      title: "Human review",
      type: "human",
      status: "waiting",
      invocation: {
        id: "inv_review",
        status: "waiting",
        inputDigest: "sha256:review-input",
        version: 2,
        createdAt: "2026-09-20T00:00:02Z",
        updatedAt: "2026-09-20T00:00:02Z",
        hasOutput: false,
        error: null,
      },
      latestAttempt: {
        id: "attempt_review",
        attemptNo: 1,
        status: "waiting",
        version: 1,
        inputDigest: "sha256:review-input",
        externalRef: null,
        createdAt: "2026-09-20T00:00:02Z",
        updatedAt: "2026-09-20T00:00:02Z",
        hasOutput: false,
        error: null,
      },
      attempts: [],
    },
  ],
  edges: [
    {
      id: "scope_root:produce->review",
      scopeId: "scope_root",
      from: "scope_root:produce",
      to: "scope_root:review",
      kind: "control",
    },
  ],
  events: [
    {
      seq: 1,
      type: "human.created",
      occurredAt: "2026-09-20T00:00:02Z",
      scopeId: "scope_root",
      invocationId: "inv_review",
      attemptId: "attempt_review",
      payload: { requestId: "human_123", status: "pending" },
    },
  ],
  humanRequests: [
    {
      id: "human_123",
      scopeId: "scope_root",
      invocationId: "inv_review",
      requestType: "review",
      title: "Human review",
      subjectDigest: "sha256:subject",
      choices: ["approve", "reject"],
      expiresAt: "2026-09-21T00:00:00Z",
      version: 1,
      status: "pending",
    },
  ],
  artifacts: [
    {
      id: "artifact_123",
      invocationId: "inv_produce",
      name: "deliverable.md",
      mediaType: "text/markdown",
      sizeBytes: 24,
      digest: "sha256:artifact",
      status: "ready",
      createdAt: "2026-09-20T00:00:01Z",
    },
  ],
};

describe("runtime projection mapper", () => {
  it("keeps runtime identities and waiting audit evidence", () => {
    const graph = mapRuntimeProjection(snapshot);

    expect(graph.runId).toBe("run_123");
    expect(graph.packageName).toBe("delivery");
    expect(graph.groups[0]?.title).toBe("delivery");
    expect(graph.groups[0]?.subtitle).toBe("流程 ID · 主流程 · active");
    expect(graph.updatedAt).toBe("2026-09-20T00:01:00Z");
    expect(graph.runVersion).toBe(7);
    expect(graph.controlMode).toBe("run");
    expect(graph.currentNodeId).toBe("scope_root:review");
    expect(graph.currentScopeId).toBe("scope_root");
    expect(graph.nodes.find((node) => node.id === "scope_root:review")?.status).toBe(
      "waiting",
    );
    expect(graph.groups[0]?.memberIds).toContain("scope_root:review");
    expect(graph.nodes.find((node) => node.id === "scope_root:produce")?.evidence).toContain(
      "产物 deliverable.md 已登记",
    );
  });

  it("labels each nested workflow scope with its own stable workflow ID", () => {
    const nested = structuredClone(snapshot) as Parameters<typeof mapRuntimeProjection>[0];
    nested.scopes.push({
      id: "scope_child",
      workflowId: "quality-check",
      parentScopeId: "scope_root",
      parentInvocationId: "inv_produce",
      path: ["root", "quality-check"],
      inputDigest: "sha256:child",
      status: "active",
    });

    const graph = mapRuntimeProjection(nested);

    expect(graph.groups.find((group) => group.id === "scope_child")).toMatchObject({
      title: "quality-check",
      subtitle: "流程 ID · 子流程 · quality-check · active",
      parentId: "scope_root",
    });
  });

  it("rejects JSON that is not a runtime projection", () => {
    expect(() => parseRuntimeProjection({ run: { id: "not-enough" } })).toThrow(
      "不是有效的 Runtime 运行快照",
    );
  });

  it("rejects the retired snake_case run shape instead of silently diverging", () => {
    const legacySnapshot = structuredClone(snapshot) as Record<string, unknown>;
    legacySnapshot.run = {
      id: "run_legacy",
      workflow_id: "delivery",
      package_digest: "sha256:package",
      binding_digest: null,
      status: "waiting",
      control_mode: "run",
      current_node_id: null,
      version: 1,
      deadline_at: "2026-09-21T00:00:00Z",
      created_at: "2026-09-20T00:00:00Z",
      updated_at: "2026-09-20T00:01:00Z",
      rerun_of: null,
      rerun_reason: null,
    };

    expect(() => parseRuntimeProjection(legacySnapshot)).toThrow(
      "不是有效的 Runtime 运行快照",
    );
  });

  it("keeps unknown and cancelled facts distinct from failed", () => {
    const next = structuredClone(snapshot);
    next.nodes[0].status = "unknown";
    next.nodes[1].status = "cancelled";
    const graph = mapRuntimeProjection(next);

    expect(graph.nodes.find((node) => node.id === "scope_root:produce")?.status).toBe(
      "unknown",
    );
    expect(graph.nodes.find((node) => node.id === "scope_root:review")?.status).toBe(
      "cancelled",
    );
  });

  it("keeps the invocation identity needed to target a HumanRequest", () => {
    const graph = mapRuntimeProjection(snapshot);

    expect(graph.nodes.find((node) => node.id === "scope_root:review")?.invocationId).toBe(
      "inv_review",
    );
  });
});

describe("runtime view snapshot", () => {
  it("parses an exported view snapshot with graph layout and run evidence", () => {
    const graph = mapRuntimeProjection(snapshot);
    const view = parseRuntimeViewSnapshot({
      format: "multiverse-view/v0.1",
      exportedAt: "2026-10-08T00:00:00Z",
      workflow: {
        name: graph.packageName,
        version: graph.packageVersion,
        runId: graph.runId,
      },
      graph,
      layout: { "scope_root:review": { x: 240, y: 180 } },
      events: snapshot.events,
      humanRequests: snapshot.humanRequests,
      artifacts: snapshot.artifacts,
    });

    expect(view.workflow.runId).toBe("run_123");
    expect(view.layout["scope_root:review"]).toEqual({ x: 240, y: 180 });
    expect(view.graph.nodes).toHaveLength(2);
  });

  it("rejects malformed graph positions and unsupported view versions", () => {
    const graph = mapRuntimeProjection(snapshot);
    const view = {
      format: "multiverse-view/v0.1",
      exportedAt: "2026-10-08T00:00:00Z",
      workflow: {
        name: graph.packageName,
        version: graph.packageVersion,
        runId: graph.runId,
      },
      graph,
      layout: { "scope_root:review": { x: "bad", y: 180 } },
      events: snapshot.events,
      humanRequests: snapshot.humanRequests,
      artifacts: snapshot.artifacts,
    };

    expect(() => parseRuntimeViewSnapshot(view)).toThrow("不是有效的 Multiverse 运行视图");
    expect(() =>
      parseRuntimeViewSnapshot({ ...view, format: "multiverse-view/v9" }),
    ).toThrow("不是有效的 Multiverse 运行视图");
  });

  it("rejects graph node states that the Inspector cannot render", () => {
    const graph = mapRuntimeProjection(snapshot);
    graph.nodes[0]!.status = "new-runtime-state" as typeof graph.nodes[number]["status"];
    const view = {
      format: "multiverse-view/v0.1",
      exportedAt: "2026-10-08T00:00:00Z",
      workflow: {
        name: graph.packageName,
        version: graph.packageVersion,
        runId: graph.runId,
      },
      graph,
      layout: {},
      events: snapshot.events,
      humanRequests: snapshot.humanRequests,
      artifacts: snapshot.artifacts,
    };

    expect(() => parseRuntimeViewSnapshot(view)).toThrow("不是有效的 Multiverse 运行视图");
  });

  it("rejects non-string edge labels before rendering", () => {
    const graph = mapRuntimeProjection(snapshot);
    graph.edges[0]!.label = { invalid: true } as unknown as string;
    const view = {
      format: "multiverse-view/v0.1",
      exportedAt: "2026-10-08T00:00:00Z",
      workflow: {
        name: graph.packageName,
        version: graph.packageVersion,
        runId: graph.runId,
      },
      graph,
      layout: {},
      events: snapshot.events,
      humanRequests: snapshot.humanRequests,
      artifacts: snapshot.artifacts,
    };

    expect(() => parseRuntimeViewSnapshot(view)).toThrow("不是有效的 Multiverse 运行视图");
  });
});
