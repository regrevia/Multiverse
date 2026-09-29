import { describe, expect, it } from "vitest";
import {
  fitGraphToViewport,
  preserveGraphPositions,
  resolveGraphPosition,
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
