import { useEffect, useId, useRef } from "react";

import { octagonPath } from "../../visual/octagon";

export { octagonPath };

export type OctagonState = "idle" | "waiting" | "speaking" | "off" | "error";

const LABELS: Record<OctagonState, string> = {
  idle: "Voice, idle",
  waiting: "Voice, preparing",
  speaking: "Voice, speaking",
  off: "Voice engine offline",
  error: "Voice, failed",
};

function prefersStill(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * The voice octagon: brand orange, eight rounded corners. Idle, it breathes; waiting, it turns
 * slowly; speaking, its edges and glow follow `level()` (0 to 1, the voice's loudness now).
 * With reduced motion it stays still. It is drawn by setting the paths directly each frame,
 * so React does not re-render 60 times a second.
 */
export function VoiceOctagon({
  state,
  level,
  size = 220,
  label,
}: {
  state: OctagonState;
  level?: () => number;
  size?: number;
  label?: string;
}) {
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const glow = useRef<SVGPathElement>(null);
  const body = useRef<SVGPathElement>(null);
  const inner = useRef<SVGPathElement>(null);
  const gradient = useRef<SVGLinearGradientElement>(null);
  const levelRef = useRef(level);
  levelRef.current = level;

  useEffect(() => {
    let frame = 0;
    let smooth = 0;
    const start = performance.now();
    const draw = (t: number) => {
      let amp = 0.012;
      let rot = 0;
      let scale = 1 + 0.025 * Math.sin(t * 1.3);
      let glowOpacity = 0.35;
      if (state === "waiting") {
        amp = 0.018;
        rot = t * 0.5;
        scale = 0.96;
        glowOpacity = 0.2 + 0.1 * Math.sin(t * 2);
      } else if (state === "speaking") {
        const raw = levelRef.current?.() ?? 0;
        smooth += (raw - smooth) * 0.35; // follow the voice without jitter
        amp = 0.03 + 0.09 * smooth;
        rot = t * 0.18;
        scale = 1 + 0.05 * smooth;
        glowOpacity = 0.3 + 0.35 * smooth;
      } else if (state === "off" || state === "error") {
        amp = 0;
        scale = 0.96;
        glowOpacity = 0;
      }
      const r = 170 * scale;
      glow.current?.setAttribute(
        "d",
        octagonPath(260, 268, r * 1.08, t * 0.8 + 2, amp * 1.4, rot * 0.7),
      );
      glow.current?.setAttribute("opacity", glowOpacity.toFixed(2));
      body.current?.setAttribute("d", octagonPath(260, 260, r, t, amp, rot));
      inner.current?.setAttribute(
        "d",
        octagonPath(236, 232, r * 0.62, t * 1.3 + 1, amp * 1.2, rot + 0.39),
      );
      gradient.current?.setAttribute(
        "gradientTransform",
        `rotate(${((t * 24) % 360).toFixed(1)} 0.5 0.5)`,
      );
    };
    if (prefersStill() || state === "off" || state === "error") {
      draw(0);
      return;
    }
    const tick = (now: number) => {
      draw((now - start) / 1000);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [state]);

  const fill =
    state === "off"
      ? "#d6d3d1"
      : state === "error"
        ? "#fca5a5"
        : `url(#${id}-fill)`;
  const still = octagonPath(260, 260, 170);
  return (
    <svg
      className="voice-octagon"
      width={size}
      height={size}
      viewBox="0 0 520 520"
      role="img"
      aria-label={label ?? LABELS[state]}
    >
      <defs>
        <linearGradient
          ref={gradient}
          id={`${id}-fill`}
          x1="0"
          y1="0"
          x2="1"
          y2="1"
        >
          <stop offset="0" stopColor="#fed7aa" />
          <stop offset="0.35" stopColor="#fb923c" />
          <stop offset="0.72" stopColor="#c2410c" />
          <stop offset="1" stopColor="#7c2d12" />
        </linearGradient>
        <radialGradient id={`${id}-light`} cx="0.35" cy="0.3" r="0.6">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.75" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <filter id={`${id}-blur`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="22" />
        </filter>
      </defs>
      <path
        ref={glow}
        d={still}
        fill="#fb923c"
        opacity="0.35"
        filter={`url(#${id}-blur)`}
      />
      <path
        ref={body}
        d={still}
        fill={fill}
        opacity={state === "waiting" ? 0.75 : 1}
      />
      {state === "off" || state === "error" ? null : (
        <path ref={inner} d={still} fill={`url(#${id}-light)`} opacity="0.55" />
      )}
    </svg>
  );
}
