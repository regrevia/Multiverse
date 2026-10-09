import { describe, expect, it } from "vitest";
import { demoGraph, visibleGraph } from "./model";
import {
  fitGraphToViewport,
  preserveGraphPositions,
  resolveGraphPosition,
  routeGraphEdge,
  translatePositions,
} from "./layout";

describe("local graph layout", () => {
  it("centers the complete graph inside the viewport at a readable scale", () => {
    expect(
      fitGraphToViewport(
        [
          { x: 20, y: 50, width: 100, height: 60 },
          { x: 220, y: 150, width: 200, height: 100 },
        ],
        { width: 800, height: 500 },
      ),
    ).toEqual({
      zoom: 1.2,
      pan: { x: 136, y: 70 },
    });
  });

  it("scales larger graphs to fit while keeping their outer padding", () => {
    expect(
      fitGraphToViewport(
        [{ x: 0, y: 0, width: 1000, height: 700 }],
        { width: 500, height: 400 },
      ),
    ).toEqual({
      zoom: 0.42,
      pan: { x: 40, y: 53 },
    });
  });

  it("keeps the workflow readable when its scope is represented by a compact collapsed node", () => {
    const fit = fitGraphToViewport(
      [
        { x: 40, y: 25, width: 258, height: 134 },
        { x: 40, y: 185, width: 304, height: 116 },
        { x: 710, y: 235, width: 258, height: 134 },
        { x: 710, y: 375, width: 258, height: 134 },
        { x: 710, y: 515, width: 258, height: 134 },
      ],
      { width: 1015, height: 620 },
    );

    expect(fit?.zoom).toBeGreaterThanOrEqual(0.85);
  });

  it("keeps the default workflow readable in a 1280 by 720 desktop window", () => {
    const nodes = visibleGraph(demoGraph, new Set(["production"])).nodes;
    const fit = fitGraphToViewport(nodes, { width: 845, height: 475 }, 24);

    expect(fit?.zoom).toBeGreaterThanOrEqual(0.78);
  });

  it("routes edges through the nearest facing ports for horizontal and vertical neighbors", () => {
    expect(
      routeGraphEdge(
        { x: 40, y: 20, width: 258, height: 134 },
        { x: 40, y: 180, width: 304, height: 116 },
      ),
    ).toEqual({
      path: "M 169 154 C 169 178, 192 156, 192 180",
      direction: "vertical",
    });
    expect(
      routeGraphEdge(
        { x: 670, y: 180, width: 258, height: 134 },
        { x: 670, y: 340, width: 258, height: 134 },
      ),
    ).toMatchObject({
      path: "M 799 314 C 799 338, 799 316, 799 340",
      direction: "vertical",
    });
  });

  it("keeps the default collapsed workflow on horizontal ports when nodes share a row", () => {
    const visible = visibleGraph(demoGraph, new Set(["production"]));
    const byId = new Map(visible.nodes.map((node) => [node.id, node]));
    const horizontalEdges = visible.edges.filter((edge) =>
      [
        ["production", "verify"],
        ["verify", "review"],
      ].some(([from, to]) => edge.from === from && edge.to === to),
    );

    expect(horizontalEdges).toHaveLength(2);
    horizontalEdges.forEach((edge) => {
      const from = byId.get(edge.from)!;
      const to = byId.get(edge.to)!;
      const route = routeGraphEdge(from, to);
      expect(route.direction).toBe("horizontal");
      expect(route.path.startsWith(`M ${from.x + from.width} `)).toBe(true);
      expect(route.path.endsWith(` ${to.x} ${to.y + to.height / 2}`)).toBe(true);
    });
  });

  it("keeps fitting very wide layouts after nodes have been dragged far apart", () => {
    expect(
      fitGraphToViewport(
        [{ x: -2400, y: 0, width: 4000, height: 2400 }],
        { width: 500, height: 400 },
      ),
    ).toEqual({
      zoom: 0.105,
      pan: { x: 292, y: 74 },
    });
  });

  it("uses the locally dragged position when focusing a graph item", () => {
    expect(
      resolveGraphPosition(
        { id: "node-a", x: 20, y: 30, width: 100, height: 80 },
        { "node-a": { x: 420, y: 260 } },
      ),
    ).toEqual({ x: 420, y: 260 });
  });

  it("does not calculate a fit for an empty or unusable viewport", () => {
    expect(fitGraphToViewport([], { width: 800, height: 500 })).toBeNull();
    expect(
      fitGraphToViewport([{ x: 0, y: 0, width: 100, height: 100 }], { width: 0, height: 0 }),
    ).toBeNull();
  });

  it("moves a scope and all of its members by the same local delta", () => {
    const positions = translatePositions(
      {
        scope: { x: 40, y: 132 },
        "scope:produce": { x: 62, y: 154 },
        "scope:review": { x: 270, y: 154 },
      },
      ["scope", "scope:produce", "scope:review"],
      { x: 80, y: -24 },
    );

    expect(positions.scope).toEqual({ x: 120, y: 108 });
    expect(positions["scope:produce"]).toEqual({ x: 142, y: 130 });
    expect(positions["scope:review"]).toEqual({ x: 350, y: 130 });
  });

  it("keeps user positions when a fresh runtime projection replaces node facts", () => {
    const current = {
      nodes: [{ id: "node-a", x: 90, y: 120 }],
      groups: [{ id: "scope", x: 40, y: 80 }],
    };
    const next = {
      nodes: [{ id: "node-a", x: 10, y: 20 }, { id: "node-b", x: 30, y: 40 }],
      groups: [{ id: "scope", x: 0, y: 0 }],
    };

    expect(preserveGraphPositions(current, next, { "node-a": { x: 220, y: 240 } })).toEqual({
      nodes: [
        { id: "node-a", x: 220, y: 240 },
        { id: "node-b", x: 30, y: 40 },
      ],
      groups: [{ id: "scope", x: 40, y: 80 }],
    });
  });
});
