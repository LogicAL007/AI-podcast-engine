// The Oasis octagon: the logo, and the Voice studio's voice visual, are this one shape.

/** A rounded octagon around (cx, cy). Each corner moves in and out by `amp` of the radius, on
 * its own phase, so the shape flows; `rot` turns it. Pure, so it can be tested. */
export function octagonPath(
  cx: number,
  cy: number,
  radius: number,
  t = 0,
  amp = 0,
  rot = 0,
): string {
  const corners: [number, number][] = [];
  for (let i = 0; i < 8; i++) {
    const angle = (Math.PI / 4) * i + Math.PI / 8 + rot;
    const wobble =
      amp *
      (0.55 * Math.sin(t * 1.9 + i * 1.7) + 0.45 * Math.sin(t * 3.1 + i * 2.6));
    const r = radius * (1 + wobble);
    corners.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
  }
  const k = 0.24; // how much of each edge is rounded into the corner
  const along = (p: [number, number], q: [number, number], f: number) => [
    p[0] + (q[0] - p[0]) * f,
    p[1] + (q[1] - p[1]) * f,
  ];
  const n = (v: number) => v.toFixed(1);
  let d = "";
  for (let i = 0; i < 8; i++) {
    const p = corners[i];
    const q = corners[(i + 1) % 8];
    const next = corners[(i + 2) % 8];
    const start = along(p, q, k);
    const end = along(p, q, 1 - k);
    const after = along(q, next, k);
    if (i === 0) d += `M${n(start[0])} ${n(start[1])}`;
    d += ` L${n(end[0])} ${n(end[1])} Q${n(q[0])} ${n(q[1])} ${n(after[0])} ${n(after[1])}`;
  }
  return `${d} Z`;
}
