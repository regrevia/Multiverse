import { describe, expect, it } from "vitest";
import { applyAgentPatch, demoGraph, visibleGraph } from "./model";

describe("audit graph model", () => {
  it("keeps stable domain ids while collapsing a group", () => {
    const collapsed = visibleGraph(demoGraph, new Set(["production"]));
    const expanded = visibleGraph(demoGraph, new Set());

    expect(collapsed.nodes.map((node) => node.id)).toContain("production");
    expect(collapsed.nodes.map((node) => node.id)).not.toContain("produce");
    expect(expanded.nodes.map((node) => node.id)).toContain("produce");
    expect(expanded.edges.every((edge) => edge.id.length > 0)).toBe(true);
  });

  it("applies only safe live agent patch fields", () => {
    const result = applyAgentPatch(demoGraph, {
      nodeId: "refine",
      title: "Refine deliverable",
      status: "running",
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.graph.nodes.find((node) => node.id === "refine")?.title).toBe(
        "Refine deliverable",
      );
      expect(result.graph.nodes.find((node) => node.id === "refine")?.status).toBe(
        "running",
      );
    }
  });

  it("rejects a patch that targets an unknown node", () => {
    const result = applyAgentPatch(demoGraph, {
      nodeId: "missing",
      title: "Should not apply",
    });

    expect(result.ok).toBe(false);
  });
});
