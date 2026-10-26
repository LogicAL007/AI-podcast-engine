import { describe, expect, it } from "vitest";

import { passwordProblem } from "./passwords";
import { readResetToken } from "./ResetPasswordPage";
import { EMPTY_SHOW, validateShow } from "./shows/showValues";

describe("reset link", () => {
  it("takes the token from the fragment", () => {
    expect(readResetToken("#token=prt_abcdefghijk")).toBe("prt_abcdefghijk");
  });
  it("ignores a missing or truncated token", () => {
    expect(readResetToken("")).toBeNull();
    expect(readResetToken("#token=short")).toBeNull();
    expect(readResetToken("#other=1")).toBeNull();
  });
});

describe("new passwords", () => {
  it("need 12 characters and a matching confirmation", () => {
    expect(passwordProblem("short", "short")).toMatch(/12/);
    expect(passwordProblem("a long passphrase", "a long passphrasE")).toMatch(
      /match/,
    );
    expect(
      passwordProblem("a long passphrase", "a long passphrase"),
    ).toBeNull();
  });
});

describe("show form", () => {
  it("builds the request from valid values", () => {
    const { body, errors } = validateShow({
      ...EMPTY_SHOW,
      topic: "  Tides and the moon ",
      sources: "https://example.org/a\n\n https://example.org/b ",
      review_before_voice: true,
    });
    expect(errors).toEqual({});
    expect(body).toMatchObject({
      topic: "Tides and the moon",
      sources: ["https://example.org/a", "https://example.org/b"],
      target_minutes: 7,
      host_count: 2,
      max_segments: 6,
      review_before_voice: true,
    });
  });

  it("reports every problem, with the API's limits", () => {
    const { body, errors } = validateShow({
      ...EMPTY_SHOW,
      topic: "ab",
      target_minutes: "45",
      host_count: "0",
      language: "English",
      max_segments: "2.5",
      sources: "example.org ftp://example.org/x",
    });
    expect(body).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(
      [
        "host_count",
        "language",
        "max_segments",
        "sources",
        "target_minutes",
        "topic",
      ].sort(),
    );
    expect(errors.sources).toContain("example.org");
  });
});
