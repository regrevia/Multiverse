import { describe, expect, it } from "vitest";
import { mapRuntimeProjection, parseRuntimeProjection } from "./runtime";

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
    currentScopeId: "scope-root",
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
    expect(graph.updatedAt).toBe("2026-09-20T00:01:00Z");
    expect(graph.nodes.find((node) => node.id === "scope_root:review")?.status).toBe(
      "waiting",
    );
    expect(graph.groups[0]?.memberIds).toContain("scope_root:review");
    expect(graph.nodes.find((node) => node.id === "scope_root:produce")?.evidence).toContain(
      "产物 deliverable.md 已登记",
    );
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
