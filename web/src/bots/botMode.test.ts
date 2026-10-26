import { describe, expect, it } from "vitest";

import { botFor } from "./botMode";

describe("which bot helps", () => {
  it("works while an episode is being made", () => {
    expect(botFor("queued", null)?.mode).toBe("working");
    expect(botFor("processing", "voice")).toMatchObject({
      mode: "working",
      name: "Scout",
      line: "On it: voice.",
    });
  });
  it("reviews during the fact-check and while waiting for a person", () => {
    expect(botFor("processing", "factcheck")?.mode).toBe("reviewing");
    expect(botFor("needs_review", "factcheck")).toMatchObject({
      mode: "reviewing",
      name: "Checker",
    });
  });
  it("celebrates a published episode", () => {
    expect(botFor("published", null)).toMatchObject({
      mode: "celebrating",
      name: "Herald",
    });
  });
  it("stays out of the way when something went wrong or nothing changed", () => {
    for (const status of ["failed", "cancelled", "unchanged"] as const)
      expect(botFor(status, null)).toBeNull();
  });
});
