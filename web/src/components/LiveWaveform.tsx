import { useEffect, useRef } from "react";

const HISTORY = 160; // bars across the meter

/** The microphone's level as it records, scrolling right to left: you can see yourself speak. */
export function LiveWaveform({ analyser }: { analyser: AnalyserNode | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext("2d");
    if (!element || !ctx || !analyser) return;
    const levels: number[] = Array.from({ length: HISTORY }, () => 0);
    const data = new Uint8Array(analyser.fftSize);
    const accent =
      getComputedStyle(element).getPropertyValue("--color-accent").trim() ||
      "#c2410c";
    let frame = 0;
    const draw = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const value of data) sum += ((value - 128) / 128) ** 2;
      levels.push(Math.min(1, Math.sqrt(sum / data.length) * 4));
      levels.shift();
      const scale = window.devicePixelRatio || 1;
      const width = element.clientWidth * scale;
      const height = element.clientHeight * scale;
      if (element.width !== width || element.height !== height) {
        element.width = width;
        element.height = height;
      }
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = accent;
      const step = width / HISTORY;
      levels.forEach((level, i) => {
        const bar = Math.max(2 * scale, level * height);
        ctx.fillRect(
          i * step,
          (height - bar) / 2,
          Math.max(1, step - 2 * scale),
          bar,
        );
      });
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [analyser]);

  return <canvas ref={canvas} className="live-waveform" aria-hidden="true" />;
}
