import { describe, expect, it } from "vitest";
import { preserveGraphPositions, translatePositions } from "./layout";

describe("local graph layout", () => {
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
