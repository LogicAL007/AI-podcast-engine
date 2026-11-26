// What every 3D character shares: the control the page drives it with, the floor shadow, and the
// pointer-following, drag-spin and tap-reaction helpers. Used by BotScene and ToyBot.
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef, type RefObject } from "react";
import {
  CanvasTexture,
  type Mesh,
  type MeshBasicMaterial,
  type Object3D,
} from "three";

import type { Avatar } from "./avatar";
import type { BotMode } from "./botMode";

/** What the page tells a bot: where the pointer is, hover, drag spin, taps and speech. */
export interface BotControl {
  lookX: number; // -1 (far left of the screen) .. 1 (far right)
  lookY: number; // -1 (bottom) .. 1 (top)
  hovering: boolean;
  spin: number; // radians a second, from a drag; eases off by itself
  pokes: number; // goes up by one on each tap; the bot reacts to every new value
  talk: number; // 0 (quiet) .. 1 (mouth wide open), while it speaks
}

export function newControl(): BotControl {
  return { lookX: 0, lookY: 0, hovering: false, spin: 0, pokes: 0, talk: 0 };
}

export interface CharacterProps {
  mode: BotMode;
  still: boolean;
  avatar: Avatar;
  control: RefObject<BotControl>;
}

export const REACTION_SECONDS = 1.2;

export function easeOut(p: number): number {
  return 1 - (1 - p) ** 3;
}

/** A soft round shadow drawn once on a small canvas; cheaper than a shadow pass, and it ignores
 * the sparkles, which a contact-shadow camera would smear into a grey box. */
function shadowTexture(): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const glow = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    glow.addColorStop(0, "rgba(68, 28, 10, 0.55)");
    glow.addColorStop(1, "rgba(68, 28, 10, 0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, 64, 64);
  }
  return new CanvasTexture(canvas);
}

/** The floor shadow: it shrinks and fades as the bot rises. */
export function Shadow({ target }: { target: RefObject<Object3D | null> }) {
  const mesh = useRef<Mesh>(null);
  const material = useRef<MeshBasicMaterial>(null);
  const map = useMemo(shadowTexture, []);
  useFrame(() => {
    if (!mesh.current || !material.current || !target.current) return;
    const lift = Math.max(0, target.current.position.y);
    mesh.current.scale.setScalar(1 - lift * 0.9);
    material.current.opacity = 0.9 - lift * 1.6;
  });
  return (
    <mesh ref={mesh} position={[0, -0.97, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[1.3, 1.3]} />
      <meshBasicMaterial
        ref={material}
        map={map}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}

/** Pointer following and drag spin, shared by every character; call once per frame. */
export function useMotion(control: RefObject<BotControl>, still: boolean) {
  const look = useRef({ x: 0, y: 0 });
  const spin = useRef(0);
  return (delta: number) => {
    const c = control.current;
    const ease = Math.min(1, delta * 6);
    look.current.x += ((still ? 0 : c.lookX) - look.current.x) * ease;
    look.current.y += ((still ? 0 : c.lookY) - look.current.y) * ease;
    spin.current += c.spin * delta;
    c.spin *= 0.04 ** delta; // a flick keeps turning, then slows to a stop
    return { lookX: look.current.x, lookY: look.current.y, spin: spin.current };
  };
}

/** Taps: the time of the latest one, so a character can play out its reaction. */
export function useReaction(control: RefObject<BotControl>) {
  const seen = useRef(control.current.pokes);
  const start = useRef(-10);
  return (now: number) => {
    const fresh = control.current.pokes !== seen.current;
    if (fresh) {
      seen.current = control.current.pokes;
      start.current = now;
    }
    return { fresh, since: now - start.current };
  };
}
