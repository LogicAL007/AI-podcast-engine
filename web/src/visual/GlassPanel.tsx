import LiquidGlass from "liquid-glass-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useReducedMotion } from "./motion";

/**
 * A panel on liquid glass. liquid-glass-react centres itself absolutely and sizes itself to its
 * children, so here it is a layer: the panel measures its own box, draws the glass that size
 * underneath, and keeps its real content (forms, buttons) on top, outside the refraction.
 */
export function GlassPanel({
  children,
  radius = 24,
  className = "",
}: {
  children: ReactNode;
  radius?: number;
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const reduced = useReducedMotion();

  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    // The padding box, not contentRect: the glass covers the panel's padding too.
    const observer = new ResizeObserver(() => {
      setSize({ width: element.clientWidth, height: element.clientHeight });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={box}
      className={`glass-panel ${className}`}
      style={{ borderRadius: radius }}
    >
      {size.width > 0 ? (
        <div className="glass-layer" aria-hidden="true">
          <LiquidGlass
            cornerRadius={radius}
            padding="0px"
            displacementScale={reduced ? 0 : 64}
            blurAmount={0.08}
            saturation={140}
            aberrationIntensity={reduced ? 0 : 2}
            elasticity={0}
            mode="standard"
            style={{ position: "absolute", top: "50%", left: "50%" }}
          >
            <div style={{ width: size.width, height: size.height }} />
          </LiquidGlass>
        </div>
      ) : null}
      <div className="glass-content">{children}</div>
    </div>
  );
}
