import { describe, expect, it } from "vitest";
import {
  buildHumanInputDecision,
  coerceHumanField,
  createHumanDecisionIdempotencyKey,
  getHumanInputFields,
  type HumanField,
} from "./human";

describe("human input schema helpers", () => {
  it("extracts object fields and required markers from a decision schema", () => {
    expect(
      getHumanInputFields({
        type: "object",
        required: ["summary"],
        properties: {
          summary: { type: "string", title: "变更说明" },
          approved: { type: "boolean" },
        },
      }),
    ).toEqual([
      {
        name: "summary",
        title: "变更说明",
        description: undefined,
        type: "string",
        required: true,
        itemsType: undefined,
      },
      {
        name: "approved",
        title: "approved",
        description: undefined,
        type: "boolean",
        required: false,
        itemsType: undefined,
      },
    ]);
  });

  it("coerces structured form values without requiring JSON editing", () => {
    const fields: HumanField[] = [
      {
        name: "count",
        title: "数量",
        description: undefined,
        type: "integer",
        required: true,
        itemsType: undefined,
      },
      {
        name: "artifact_refs",
        title: "产物",
        description: undefined,
        type: "array",
        required: true,
        itemsType: "string",
      },
      {
        name: "approved",
        title: "批准",
        description: undefined,
        type: "boolean",
        required: false,
        itemsType: undefined,
      },
    ];

    expect(coerceHumanField(fields[0], "3")).toBe(3);
    expect(coerceHumanField(fields[1], "artifact_1\nartifact_2")).toEqual([
      "artifact_1",
      "artifact_2",
    ]);
    expect(coerceHumanField(fields[2], "true")).toBe(true);
  });

  it("rejects unsupported input schemas instead of falling back to JSON", () => {
    expect(
      getHumanInputFields({
        type: "object",
        properties: { nested: { type: "object" } },
      }),
    ).toBeNull();
  });

  it("builds a business decision while omitting optional blank fields", () => {
    const fields: HumanField[] = [
      {
        name: "summary",
        title: "说明",
        description: undefined,
        type: "string",
        required: true,
        itemsType: undefined,
      },
      {
        name: "artifact_refs",
        title: "产物",
        description: undefined,
        type: "array",
        required: true,
        itemsType: "string",
      },
      {
        name: "approved",
        title: "批准",
        description: undefined,
        type: "boolean",
        required: false,
        itemsType: undefined,
      },
    ];

    expect(
      buildHumanInputDecision(fields, {
        summary: "已完成",
        artifact_refs: "artifact_1\nartifact_2",
        approved: "",
      }),
    ).toEqual({
      decision: {
        summary: "已完成",
        artifact_refs: ["artifact_1", "artifact_2"],
      },
      errors: [],
    });
  });

  it("uses a stable idempotency key for retries of the same decision", () => {
    const first = createHumanDecisionIdempotencyKey("request-1", 2, {
      decision: { summary: "done" },
      comment: "",
    });
    const retry = createHumanDecisionIdempotencyKey("request-1", 2, {
      decision: { summary: "done" },
      comment: "",
    });
    const changed = createHumanDecisionIdempotencyKey("request-1", 2, {
      decision: { summary: "changed" },
      comment: "",
    });

    expect(retry).toBe(first);
    expect(changed).not.toBe(first);
  });
});
