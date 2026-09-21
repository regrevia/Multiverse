import { describe, expect, it } from "vitest";
import {
  buildHumanInputDecision,
  coerceHumanField,
  createHumanDecisionIdempotencyKey,
  getHumanInputFields,
  isArtifactReferenceField,
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

  it("rejects schemas whose required fields are missing from properties", () => {
    expect(
      getHumanInputFields({
        type: "object",
        required: ["artifact_refs"],
        properties: {},
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

  it("recognizes artifact reference arrays and rejects unregistered values", () => {
    const fields = getHumanInputFields({
      type: "object",
      properties: {
        artifact_refs: {
          type: "array",
          items: { type: "string" },
        },
      },
    });
    expect(fields).not.toBeNull();
    const field = fields?.[0];
    expect(field && isArtifactReferenceField(field)).toBe(true);
    expect(
      buildHumanInputDecision(
        fields ?? [],
        { artifact_refs: "artifact_ready\nartifact_missing" },
        { allowedValues: { artifact_refs: ["artifact_ready"] } },
      ),
    ).toEqual({
      decision: null,
      errors: ["artifact_refs 包含未登记或不可引用的产物"],
    });
  });

  it("enforces numeric boundaries from the decision schema", () => {
    const fields = getHumanInputFields({
      type: "object",
      properties: {
        score: { type: "number", minimum: -10, maximum: 10 },
        retries: { type: "integer", minimum: 1, maximum: 3 },
      },
    });
    expect(fields).toEqual([
      expect.objectContaining({ name: "score", minimum: -10, maximum: 10 }),
      expect.objectContaining({ name: "retries", minimum: 1, maximum: 3 }),
    ]);
    expect(
      buildHumanInputDecision(fields ?? [], { score: "11", retries: "0" }),
    ).toEqual({
      decision: null,
      errors: ["score 不能大于 10", "retries 不能小于 1"],
    });
  });

  it("rejects fractional integer values and invalid booleans", () => {
    const fields = getHumanInputFields({
      type: "object",
      required: ["count", "approved"],
      properties: {
        count: { type: "integer" },
        approved: { type: "boolean" },
      },
    });

    expect(
      buildHumanInputDecision(fields ?? [], { count: "3.5", approved: "maybe" }),
    ).toEqual({
      decision: null,
      errors: ["count 必须是有效数字", "approved 必须选择是或否"],
    });
  });
});
