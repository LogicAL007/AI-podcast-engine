import { LiquidMetal } from "@paper-design/shaders-react";
import { Suspense, useState } from "react";

import { canUseWebGL, useReducedMotion } from "./motion";
import { octagonPath } from "./octagon";

/** The brand mark (the Oasis octagon) as flowing liquid metal, tinted dark orange.
 * A still orange copy of the mark sits underneath, so there is never a blank square while the
 * shader prepares its image; the metal fades in over it. Falls back to the flat mark without
 * WebGL, and holds still for reduced motion. */
export function LiquidLogo({ size = 32 }: { size?: number }) {
  const reduced = useReducedMotion();
  const [webgl] = useState(canUseWebGL);
  if (!webgl) {
    return <FlatMark size={size} />;
  }
  return (
    <span
      className="liquid-logo"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <span className="liquid-logo-still" />
      <Suspense fallback={null}>
        <LiquidMetal
          className="liquid-logo-metal"
          suspendWhenProcessingImage
          image="/logo-mark.svg"
          width={size}
          height={size}
          colorBack="#00000000"
          colorTint="#c2410c"
          repetition={2.6}
          softness={0.12}
          shiftRed={0.25}
          shiftBlue={0.25}
          distortion={0.08}
          contour={0.45}
          angle={70}
          speed={reduced ? 0 : 0.7}
          fit="contain"
          scale={0.9}
        />
      </Suspense>
    </span>
  );
}

export function FlatMark({ size = 32 }: { size?: number }) {
  return (
    <span
      className="brand-mark"
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <svg width={size} height={size} viewBox="0 0 32 32">
        <defs>
          <linearGradient id="oasis-flat" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#fdba74" />
            <stop offset="0.5" stopColor="#ea580c" />
            <stop offset="1" stopColor="#9a3412" />
          </linearGradient>
        </defs>
        <path d={octagonPath(16, 16, 15.6)} fill="url(#oasis-flat)" />
      </svg>
    </span>
  );
}
