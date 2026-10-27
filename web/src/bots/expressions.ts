// The Toy bot's face: eyes and mouth drawn on a small canvas that the 3D face plate shows, glowing
// in the bot's glow colour. Drawing is cheap, and the face is redrawn only when what it shows
// changes (a blink, a new expression, the mouth moving while it talks), not on every frame.
import type { Avatar } from "./avatar";

export type Expression =
  "neutral" | "happy" | "thinking" | "surprised" | "sleepy" | "focused";

export interface FaceState {
  eyes: Avatar["eyes"];
  mouth: Avatar["mouth"];
  glow: string;
  plate: string;
  expression: Expression;
  /** 0 (shut) .. 1 (open) */
  open: number;
  /** -1 .. 1: where the eyes look */
  lookX: number;
  lookY: number;
  /** 0 .. 1: how far the mouth is open while talking; 0 when quiet */
  talk: number;
  /** Width over height of the face plate, so round eyes stay round. */
  aspect: number;
}

export const FACE_SIZE = 256;

/** A string that changes exactly when the drawing would, rounded so tiny motions do not count. */
export function faceKey(face: FaceState): string {
  const r = (n: number, steps: number) => Math.round(n * steps) / steps;
  return [
    face.eyes,
    face.mouth,
    face.glow,
    face.plate,
    face.expression,
    r(face.open, 6),
    r(face.lookX, 8),
    r(face.lookY, 8),
    r(face.talk, 4),
    r(face.aspect, 20),
  ].join("|");
}

function star(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  outer: number,
) {
  const inner = outer * 0.45;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const radius = i % 2 ? inner : outer;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    ctx.lineTo(x + Math.cos(angle) * radius, y + Math.sin(angle) * radius);
  }
  ctx.closePath();
  ctx.fill();
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

/** Draw the face onto a square canvas (the plate's texture is stretched to its aspect). */
export function drawFace(ctx: CanvasRenderingContext2D, face: FaceState) {
  const S = FACE_SIZE;
  ctx.clearRect(0, 0, S, S);
  ctx.fillStyle = face.plate;
  ctx.fillRect(0, 0, S, S);
  ctx.fillStyle = face.glow;
  ctx.strokeStyle = face.glow;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = face.glow;
  ctx.shadowBlur = 18;

  // The canvas is stretched sideways by `aspect`, so draw x squeezed to keep shapes round.
  ctx.save();
  ctx.scale(1 / face.aspect, 1);
  const W = S * face.aspect;
  const cx = W / 2 + face.lookX * W * 0.06;
  const eyeY = S * 0.42 - face.lookY * S * 0.06;
  const gap = Math.min(W * 0.2, S * 0.28);
  const happy = face.expression === "happy";
  const surprised = face.expression === "surprised";
  const thinking = face.expression === "thinking";
  const sleepy = face.eyes === "sleepy" || face.expression === "sleepy";
  const open = Math.max(0.08, face.open) * (surprised ? 1.25 : 1);
  ctx.lineWidth = S * 0.05;

  for (const side of [-1, 1]) {
    const x = cx + side * gap;
    // Thinking: one eye squints, as if working something out.
    const squint = thinking && side === 1 ? 0.45 : 1;
    if (happy && !surprised) {
      // Upturned arcs: ^ ^
      ctx.beginPath();
      ctx.arc(x, eyeY + S * 0.04, S * 0.075, Math.PI * 1.1, Math.PI * 1.9);
      ctx.stroke();
      continue;
    }
    switch (face.eyes) {
      case "visor": {
        const h = S * 0.09 * open * squint;
        roundedRect(ctx, x - S * 0.1, eyeY - h / 2, S * 0.2, h, h / 2);
        ctx.fill();
        break;
      }
      case "pixel": {
        const px = S * 0.045;
        const rows = Math.max(1, Math.round(3 * open * squint));
        for (let r = 0; r < rows; r++)
          for (let c = 0; c < 3; c++)
            ctx.fillRect(
              x - px * 1.5 + c * px + 1,
              eyeY - (rows * px) / 2 + r * px + 1,
              px - 2,
              px - 2,
            );
        break;
      }
      case "star":
        if (open < 0.3) {
          ctx.beginPath();
          ctx.moveTo(x - S * 0.06, eyeY);
          ctx.lineTo(x + S * 0.06, eyeY);
          ctx.stroke();
        } else star(ctx, x, eyeY, S * 0.085 * Math.min(1.2, open) * squint);
        break;
      default: {
        // dots and sleepy: an ellipse; sleepy ones are half-closed lids
        const rx = S * 0.055;
        const ry = S * 0.085 * open * squint * (sleepy ? 0.45 : 1);
        ctx.beginPath();
        ctx.ellipse(
          x,
          eyeY + (sleepy ? S * 0.02 : 0),
          rx,
          Math.max(ry, S * 0.012),
          0,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
    }
  }

  // The mouth: talking opens it in time with speech, whatever its resting style.
  const mouthY = S * 0.72;
  ctx.lineWidth = S * 0.04;
  if (face.talk > 0.05) {
    const h = S * (0.03 + face.talk * 0.09);
    roundedRect(ctx, cx - S * 0.07, mouthY - h / 2, S * 0.14, h, h / 2);
    ctx.fill();
  } else if (surprised) {
    ctx.beginPath();
    ctx.ellipse(cx, mouthY, S * 0.04, S * 0.05, 0, 0, Math.PI * 2);
    ctx.stroke();
  } else if (face.mouth === "smile" || happy) {
    ctx.beginPath();
    ctx.arc(
      cx,
      mouthY - S * 0.07,
      S * (happy ? 0.11 : 0.09),
      Math.PI * 0.2,
      Math.PI * 0.8,
    );
    ctx.stroke();
  } else if (face.mouth === "open") {
    ctx.beginPath();
    ctx.arc(cx, mouthY - S * 0.01, S * 0.06, 0, Math.PI);
    ctx.closePath();
    ctx.fill();
  } else if (face.mouth === "line" || thinking) {
    ctx.beginPath();
    ctx.moveTo(cx - S * 0.06, mouthY);
    ctx.lineTo(
      cx + S * (thinking ? 0.03 : 0.06),
      mouthY - (thinking ? S * 0.02 : 0),
    );
    ctx.stroke();
  }
  ctx.restore();
}
