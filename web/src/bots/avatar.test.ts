import { describe, expect, it } from "vitest";

import {
  ACCESSORIES,
  CHARACTERS,
  COLORS,
  DEFAULT_AVATAR,
  GLOWS,
  surprise,
} from "./avatar";

describe("bot choices", () => {
  it("surprises with a valid look and keeps the name", () => {
    let i = 0;
    const pick = <T>(items: T[]): T => items[i++ % items.length];
    const bot = surprise({ ...DEFAULT_AVATAR, name: "Pip" }, pick);
    expect(bot.name).toBe("Pip");
    expect(CHARACTERS.map((c) => c.value)).toContain(bot.character);
    expect(Object.keys(COLORS)).toContain(bot.color);
    expect(Object.keys(GLOWS)).toContain(bot.glow);
    expect(ACCESSORIES.map((a) => a.value)).toContain(bot.accessory);
  });
});
