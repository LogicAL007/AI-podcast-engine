import { LiquidMetal } from "@paper-design/shaders-react";
import { Suspense, useState } from "react";

import { canUseWebGL, useReducedMotion } from "./motion";

/** The brand mark (four waveform bars) as flowing liquid metal, tinted dark orange.
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
      <svg
        width={size * 0.56}
        height={size * 0.56}
        viewBox="0 0 18 18"
        fill="currentColor"
      >
        <rect x="2" y="6" width="2" height="6" rx="1" />
        <rect x="6" y="3" width="2" height="12" rx="1" />
        <rect x="10" y="5" width="2" height="8" rx="1" />
        <rect x="14" y="7" width="2" height="4" rx="1" />
      </svg>
    </span>
  );
}
