import { describe, expect, it } from "vitest";

import { encodeWav, formatTime, peaks, VOICE_RATE } from "./wav";

describe("voice audio", () => {
  it("writes a 24 kHz mono 16-bit WAV the server accepts", async () => {
    const wav = encodeWav(new Float32Array([0, 0.5, -0.5, 1, -1]));
    const view = new DataView(await wav.arrayBuffer());
    const text = (at: number) =>
      String.fromCharCode(...new Uint8Array(view.buffer, at, 4));
    expect(text(0)).toBe("RIFF");
    expect(text(8)).toBe("WAVE");
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(VOICE_RATE);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(10); // 5 samples x 2 bytes
    expect(view.getInt16(44 + 3 * 2, true)).toBe(32767);
    expect(view.getInt16(44 + 4 * 2, true)).toBe(-32768);
  });

  it("finds the loudest point per bar, scaled to the loudest bar", () => {
    const samples = new Float32Array([0.1, -0.2, 0.05, 0.4, 0, 0]);
    expect(peaks(samples, 3)).toEqual([0.5, 1, 0]);
  });

  it("shows times as minutes and seconds", () => {
    expect(formatTime(0)).toBe("0:00");
    expect(formatTime(75.9)).toBe("1:15");
  });
});
