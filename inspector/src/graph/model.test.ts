import { describe, expect, it } from "vitest";
import { applyAgentPatch, artifactsForNode, demoGraph, visibleGraph } from "./model";

describe("audit graph model", () => {
  it("keeps stable domain ids while collapsing a group", () => {
    const collapsed = visibleGraph(demoGraph, new Set(["production"]));
    const expanded = visibleGraph(demoGraph, new Set());

    expect(collapsed.nodes.map((node) => node.id)).toContain("production");
    expect(collapsed.nodes.map((node) => node.id)).not.toContain("produce");
    expect(expanded.nodes.map((node) => node.id)).toContain("produce");
    expect(expanded.edges.every((edge) => edge.id.length > 0)).toBe(true);
  });

  it("shows declared data dependencies for the selected demo node", () => {
    const node = demoGraph.nodes.find((item) => item.id === "produce")!;

    expect(node.dataSources).toEqual(["工作流输入"]);
    expect(node.dataTargets).toContain("细化交付物");
  });

  it("summarizes nested participants and blocked members when collapsing a group", () => {
    const graph = structuredClone(demoGraph);
    graph.nodes.find((node) => node.id === "produce")!.execution = {
      participantType: "program",
      adapter: "builtin",
      executorRef: "example.content-fixture.v1",
      location: "runtime",
      target: "Multiverse Runtime",
    };
    graph.nodes.find((node) => node.id === "refine")!.status = "failed";

    const collapsed = visibleGraph(graph, new Set(["production"]));
    const group = collapsed.nodes.find((node) => node.id === "production");

    expect(group?.detail).toContain("1 Agent");
    expect(group?.detail).toContain("1 个节点失败");
    expect(group?.status).toBe("failed");
    expect(group?.input).toBe("接口未投影");
    expect(group?.output).toBe("接口未投影");
    expect(group?.width).toBeLessThanOrEqual(320);
    expect(group?.height).toBeLessThanOrEqual(120);
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

  it("filters artifacts to the selected scope members instead of the whole run", () => {
    const graph = structuredClone(demoGraph);
    graph.nodes.find((node) => node.id === "produce")!.invocationId = "inv-produce";
    graph.nodes.find((node) => node.id === "refine")!.invocationId = "inv-refine";
    const artifacts = [
      { id: "inside-a", invocationId: "inv-produce" },
      { id: "inside-b", invocationId: "inv-refine" },
      { id: "outside", invocationId: "inv-other" },
      { id: "unscoped", invocationId: null },
    ];
    const group = visibleGraph(graph, new Set(["production"]))
      .nodes.find((node) => node.id === "production")!;

    expect(artifactsForNode(group, artifacts).map((artifact) => artifact.id)).toEqual([
      "inside-a",
      "inside-b",
    ]);
  });
});
