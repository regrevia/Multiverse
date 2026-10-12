import { describe, expect, it } from "vitest";
import { eventTone, runtimeEventDisplay } from "./App";
import type { RuntimeEvent } from "./runtime/client";

const runtimeEvent = (type: string, payload: Record<string, unknown>): RuntimeEvent => ({
  seq: 1,
  type,
  occurredAt: "2026-10-12T00:00:00Z",
  scopeId: null,
  invocationId: null,
  attemptId: null,
  payload,
});

describe("runtime event display", () => {
  it("expands Codex diagnostics and preserves structured JSON", () => {
    const display = runtimeEventDisplay(
      runtimeEvent("agent.model.failed", { stderr: "denied", turnId: "turn-1" }),
    );
    expect(display.expandable).toBe(true);
    expect(display.payload).toContain('"turnId": "turn-1"');
  });

  it("keeps ordinary lifecycle events collapsed without payload rendering", () => {
    const display = runtimeEventDisplay(runtimeEvent("run.updated", { status: "running" }));
    expect(display).toEqual({ expandable: false, payload: null });
    expect(eventTone("run.created")).toBe("active");
  });

  it("returns a safe fallback for unserializable diagnostic payloads", () => {
    const circular: Record<string, unknown> = {};
    circular.self = circular;
    expect(runtimeEventDisplay(runtimeEvent("agent.model.event", circular))).toEqual({
      expandable: true,
      payload: "[无法序列化事件详情]",
    });
  });
});
