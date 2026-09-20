import { describe, expect, it } from "vitest";
import { translatePositions } from "./layout";

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
});
