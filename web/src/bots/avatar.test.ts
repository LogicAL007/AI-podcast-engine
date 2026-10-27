import { describe, expect, it } from "vitest";

import {
  BODIES,
  CHARACTERS,
  COLORS,
  complete,
  contrast,
  DEFAULT_AVATAR,
  GLOWS,
  HATS,
  hexOf,
  surprise,
} from "./avatar";

describe("bot choices", () => {
  it("surprises with a valid look and keeps the name, personality and voice", () => {
    let i = 0;
    const pick = <T>(items: T[]): T => items[i++ % items.length];
    const mine = {
      ...DEFAULT_AVATAR,
      name: "Pip",
      personality: "witty" as const,
    };
    const bot = surprise(mine, pick);
    expect(bot.name).toBe("Pip");
    expect(bot.personality).toBe("witty");
    expect(bot.voice).toEqual(mine.voice);
    expect(CHARACTERS.map((c) => c.value)).toContain(bot.character);
    expect(Object.keys(COLORS)).toContain(bot.color);
    expect(Object.keys(GLOWS)).toContain(bot.glow);
    expect(BODIES.map((b) => b.value)).toContain(bot.body);
    expect(HATS.map((h) => h.value)).toContain(bot.hat);
  });

  it("takes presets by name and any other colour as #rrggbb", () => {
    expect(hexOf("mint", COLORS, "#000000")).toBe("#bfe9d4");
    expect(hexOf("#A3E4D7", COLORS, "#000000")).toBe("#a3e4d7");
    expect(hexOf("unknown", COLORS, "#000000")).toBe("#000000");
  });

  it("measures contrast the WCAG way", () => {
    expect(contrast("#ffffff", "#000000")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#777777")).toBeCloseTo(1, 5);
  });

  it("fills in parts an older bot never chose", () => {
    const old = complete({ character: "rex", name: "Rex" } as never);
    expect(old.body).toBe("round");
    expect(old.voice.rate).toBe(1);
    expect(complete(null)).toEqual(DEFAULT_AVATAR);
  });
});
