import { MeshGradient } from "@paper-design/shaders-react";
import { useState } from "react";

import { canUseWebGL, useReducedMotion } from "./motion";

/** A slow, warm mesh gradient behind glass panels: the liquid glass needs something to bend.
 * Without WebGL it is a static gradient in the same colours. */
export function Backdrop() {
  const reduced = useReducedMotion();
  const [webgl] = useState(canUseWebGL);
  return (
    <div className="backdrop" aria-hidden="true">
      {webgl ? (
        <MeshGradient
          colors={["#fff7f0", "#fed7aa", "#fdba74", "#c2410c", "#fff1e8"]}
          distortion={0.8}
          swirl={0.35}
          speed={reduced ? 0 : 0.25}
          style={{ width: "100%", height: "100%" }}
        />
      ) : null}
    </div>
  );
}
