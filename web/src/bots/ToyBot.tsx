// The Toy: the build-your-own bot, a collectible-style figure assembled from the parts the person
// chose (body, head, face, outfit), in their colours and finish. Its face is a glowing screen
// drawn by expressions.ts, so it can blink, look around, smile, think, gasp and talk.
import { RoundedBox, Sparkles } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  CanvasTexture,
  SRGBColorSpace,
  type Group,
  type Mesh,
  type Points,
} from "three";

import { accentHex, bodyHex, faceHex, glowHex, type Avatar } from "./avatar";
import type { BotMode } from "./botMode";
import {
  drawFace,
  FACE_SIZE,
  faceKey,
  type Expression,
  type FaceState,
} from "./expressions";
import {
  Glow,
  HatPart,
  HeadExtra,
  Mic,
  NeckPart,
  Shell,
  type HeadFit,
} from "./parts";
import {
  easeOut,
  REACTION_SECONDS,
  Shadow,
  useMotion,
  useReaction,
  type CharacterProps,
} from "./sceneKit";

/** Each body: where it sits, its half-width, the top of it (the neck), the front of its chest,
 * and how much higher the head goes on it. */
const BODIES: Record<
  Avatar["body"],
  {
    y: number;
    half: number;
    front: number;
    lift: number;
    feet: boolean;
    /** Where neckwear sits: its height, the body's front there, and its radius there. */
    neck: { y: number; z: number; r: number };
  }
> = {
  round: {
    y: -0.42,
    half: 0.42,
    front: 0.4,
    lift: 0,
    feet: true,
    neck: { y: -0.12, z: 0.26, r: 0.27 },
  },
  capsule: {
    y: -0.4,
    half: 0.36,
    front: 0.35,
    lift: 0.02,
    feet: false,
    neck: { y: -0.05, z: 0.27, r: 0.27 },
  },
  boxy: {
    y: -0.45,
    half: 0.39,
    front: 0.31,
    lift: -0.04,
    feet: true,
    neck: { y: -0.17, z: 0.31, r: 0.36 },
  },
  tall: {
    y: -0.32,
    half: 0.29,
    front: 0.28,
    lift: 0.12,
    feet: false,
    neck: { y: 0.04, z: 0.27, r: 0.27 },
  },
};

/** Each head: its fit for hats and glasses, and its dark face plate. */
const HEADS: Record<
  Avatar["head"],
  {
    fit: HeadFit;
    plate: { w: number; h: number; d: number; z: number; r: number };
  }
> = {
  sphere: {
    fit: { unit: 0.5, top: 0.44, faceZ: 0.472, faceY: -0.02 },
    plate: { w: 0.74, h: 0.42, d: 0.2, z: 0.37, r: 0.12 },
  },
  cube: {
    fit: { unit: 0.45, top: 0.39, faceZ: 0.432, faceY: 0 },
    plate: { w: 0.72, h: 0.52, d: 0.06, z: 0.4, r: 0.03 },
  },
  dome: {
    fit: { unit: 0.5, top: 0.45, faceZ: 0.502, faceY: -0.06 },
    plate: { w: 0.76, h: 0.38, d: 0.18, z: 0.41, r: 0.1 },
  },
  screen: {
    fit: { unit: 0.52, top: 0.38, faceZ: 0.232, faceY: 0 },
    plate: { w: 0.9, h: 0.6, d: 0.04, z: 0.21, r: 0.02 },
  },
};

const HEAD_Y = 0.36;

/** How each personality moves: how big, how fast, how much it tilts its head. */
const PERSONA: Record<
  Avatar["personality"],
  { amp: number; speed: number; tilt: number }
> = {
  cheerful: { amp: 1.25, speed: 1.15, tilt: 1 },
  calm: { amp: 0.55, speed: 0.7, tilt: 0.5 },
  witty: { amp: 1, speed: 1.05, tilt: 1.7 },
  formal: { amp: 0.4, speed: 0.85, tilt: 0.25 },
};

const MODE_FACE: Record<BotMode, Expression> = {
  working: "focused",
  reviewing: "thinking",
  celebrating: "happy",
  greeting: "happy",
};

function HeadShell({
  head,
  shell,
  finish,
}: {
  head: Avatar["head"];
  shell: string;
  finish: Avatar["finish"];
}) {
  switch (head) {
    case "cube":
      return (
        <RoundedBox args={[0.9, 0.78, 0.78]} radius={0.2} smoothness={6}>
          <Shell color={shell} finish={finish} />
        </RoundedBox>
      );
    case "dome":
      return (
        <group>
          <mesh position={[0, -0.04, 0]}>
            <sphereGeometry
              args={[0.5, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2]}
            />
            <Shell color={shell} finish={finish} />
          </mesh>
          <mesh position={[0, -0.16, 0]}>
            <cylinderGeometry args={[0.5, 0.46, 0.24, 48]} />
            <Shell color={shell} finish={finish} />
          </mesh>
        </group>
      );
    case "screen":
      return (
        <RoundedBox args={[1.04, 0.76, 0.42]} radius={0.08} smoothness={5}>
          <Shell color={shell} finish={finish} />
        </RoundedBox>
      );
    default:
      return (
        <mesh scale={[1.1, 0.95, 1]}>
          <sphereGeometry args={[0.46, 48, 48]} />
          <Shell color={shell} finish={finish} />
        </mesh>
      );
  }
}

function BodyShell({
  body,
  shell,
  finish,
}: {
  body: Avatar["body"];
  shell: string;
  finish: Avatar["finish"];
}) {
  switch (body) {
    case "capsule":
      return (
        <mesh>
          <capsuleGeometry args={[0.36, 0.24, 12, 32]} />
          <Shell color={shell} finish={finish} />
        </mesh>
      );
    case "boxy":
      return (
        <RoundedBox args={[0.78, 0.66, 0.6]} radius={0.16} smoothness={6}>
          <Shell color={shell} finish={finish} />
        </RoundedBox>
      );
    case "tall":
      return (
        <mesh>
          <capsuleGeometry args={[0.28, 0.62, 12, 32]} />
          <Shell color={shell} finish={finish} />
        </mesh>
      );
    default:
      return (
        <mesh scale={[1, 0.92, 0.95]}>
          <sphereGeometry args={[0.42, 48, 48]} />
          <Shell color={shell} finish={finish} />
        </mesh>
      );
  }
}

export function ToyBot({ mode, still, avatar, control }: CharacterProps) {
  const root = useRef<Group>(null);
  const head = useRef<Group>(null);
  const handL = useRef<Group>(null);
  const handR = useRef<Group>(null);
  const ring = useRef<Mesh>(null);
  const sparkles = useRef<Points>(null);
  const motion = useMotion(control, still);
  const reaction = useReaction(control);

  const shell = bodyHex(avatar);
  const glow = glowHex(avatar);
  const accent = accentHex(avatar);
  const plateColour = faceHex(avatar);
  const body = BODIES[avatar.body];
  const headPart = HEADS[avatar.head];
  const persona = PERSONA[avatar.personality];
  const headY = HEAD_Y + body.lift;
  const handX = body.half + 0.2;

  // The face: a canvas the plate shows, redrawn only when what it shows changes.
  const face = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = FACE_SIZE;
    const texture = new CanvasTexture(canvas);
    texture.colorSpace = SRGBColorSpace;
    return { canvas, ctx: canvas.getContext("2d"), texture, key: "" };
  }, []);
  useEffect(() => () => face.texture.dispose(), [face]);
  const faceSize = {
    w: headPart.plate.w * 0.92,
    h: headPart.plate.h * 0.88,
  };

  useFrame((state, delta) => {
    if (!root.current || !head.current || !handL.current || !handR.current)
      return;
    const t = (still ? 0.8 : state.clock.elapsedTime) * persona.speed;
    const { since } = reaction(state.clock.elapsedTime);
    const reacting = !still && since < REACTION_SECONDS;
    const p = Math.min(1, since / REACTION_SECONDS);
    const c = control.current;
    const amp = persona.amp;
    head.current.rotation.set(0, 0, 0);

    if (mode === "working") {
      // Busy: a hover-bob, scanning side to side, hands tapping away.
      root.current.position.y = Math.sin(t * 2) * 0.05 * amp;
      root.current.rotation.y = Math.sin(t * 0.6) * 0.15;
      head.current.rotation.y = Math.sin(t * 1.6) * 0.3 * persona.tilt;
      handL.current.position.set(
        -handX,
        -0.2 + Math.abs(Math.sin(t * 9)) * 0.07 * amp,
        0.05,
      );
      handR.current.position.set(
        handX,
        -0.2 + Math.abs(Math.cos(t * 9)) * 0.07 * amp,
        0.05,
      );
    } else if (mode === "reviewing") {
      // Thoughtful: a head tilt, a scan ring, one hand at its chin.
      root.current.position.y = Math.sin(t * 1.4) * 0.035 * amp;
      root.current.rotation.y = 0;
      head.current.rotation.y = Math.sin(t * 0.7) * 0.12;
      head.current.rotation.z =
        (0.14 + Math.sin(t * 0.9) * 0.05) * persona.tilt;
      handL.current.position.set(-handX, -0.22, 0.1);
      handR.current.position.set(
        0.38,
        headY - 0.32 + Math.sin(t * 1.4) * 0.03,
        0.38,
      );
    } else if (mode === "greeting") {
      // Hello: a gentle bob, a curious tilt and one hand waving high.
      root.current.position.y = Math.sin(t * 1.6) * 0.05 * amp;
      root.current.rotation.y = Math.sin(t * 0.5) * 0.1;
      head.current.rotation.y = 0.15;
      head.current.rotation.z = (0.1 + Math.sin(t * 1.2) * 0.04) * persona.tilt;
      handL.current.position.set(-handX, -0.22, 0.1);
      handR.current.position.set(
        handX + 0.04 + Math.sin(t * 7) * 0.08 * amp,
        headY + 0.1,
        0.15,
      );
    } else {
      // Celebrating: bouncing, spinning, both hands up.
      root.current.position.y = Math.abs(Math.sin(t * 4)) * 0.2 * amp;
      root.current.rotation.y = still ? 0 : t * 2.2 * Math.min(1, amp);
      head.current.rotation.z = Math.sin(t * 8) * 0.08 * persona.tilt;
      handL.current.position.set(
        -handX,
        headY + 0.05 + Math.sin(t * 9) * 0.08,
        0,
      );
      handR.current.position.set(
        handX,
        headY + 0.05 + Math.cos(t * 9) * 0.08,
        0,
      );
    }

    // It looks where you are, and keeps turning after a drag.
    const { lookX, lookY, spin } = motion(delta);
    head.current.rotation.y += lookX * 0.5;
    head.current.rotation.x = -lookY * 0.3;
    root.current.rotation.y += spin;

    // A tap: a hop, a twirl and both hands up.
    if (reacting) {
      const hop = Math.sin(Math.PI * p);
      root.current.position.y += hop * 0.32;
      root.current.rotation.y += easeOut(p) * Math.PI * 2;
      handL.current.position.y += hop * 0.45;
      handR.current.position.y += hop * 0.45;
    }
    if (ring.current) {
      ring.current.visible = mode === "reviewing";
      ring.current.position.y = 0.1 + Math.sin(t * 1.8) * 0.42;
    }
    if (sparkles.current)
      sparkles.current.visible = !still && (mode === "celebrating" || reacting);

    // The face: blinks, expressions, eyes that follow you, a mouth that moves when it talks.
    const blinking = !still && state.clock.elapsedTime % 3.6 < 0.12;
    const expression: Expression = reacting
      ? "surprised"
      : c.hovering && mode !== "celebrating"
        ? "happy"
        : MODE_FACE[mode];
    const now: FaceState = {
      eyes: avatar.eyes,
      mouth: avatar.mouth,
      glow,
      plate: plateColour,
      expression,
      open: blinking ? 0.1 : c.hovering ? 1.15 : 1,
      lookX: lookX + (mode === "working" ? Math.sin(t * 1.6) * 0.4 : 0),
      lookY,
      talk: c.talk,
      aspect: faceSize.w / faceSize.h,
    };
    const key = faceKey(now);
    if (key !== face.key && face.ctx) {
      face.key = key;
      drawFace(face.ctx, now);
      face.texture.needsUpdate = true;
    }
  });

  const plate = headPart.plate;
  return (
    <>
      <Shadow target={root} />
      <group ref={root}>
        <group position={[0, body.y, 0]}>
          <BodyShell body={avatar.body} shell={shell} finish={avatar.finish} />
          {avatar.neck === "none" ? (
            <mesh position={[0, 0.04, body.front]}>
              <circleGeometry args={[0.07, 32]} />
              <Glow color={glow} intensity={1.2} pulse />
            </mesh>
          ) : null}
          {body.feet
            ? [-1, 1].map((side) => (
                <mesh
                  key={side}
                  position={[
                    side * body.half * 0.45,
                    -0.95 - body.y + 0.07,
                    0.05,
                  ]}
                  scale={[1, 0.55, 1.2]}
                >
                  <sphereGeometry args={[0.13, 24, 16]} />
                  <Shell color={shell} finish={avatar.finish} />
                </mesh>
              ))
            : null}
        </group>
        <group
          position={[0, body.neck.y, avatar.neck === "scarf" ? 0 : body.neck.z]}
        >
          <NeckPart
            kind={avatar.neck}
            glow={glow}
            accent={accent}
            unit={
              avatar.neck === "scarf"
                ? body.neck.r / 0.62 + 0.03
                : body.half + 0.1
            }
          />
        </group>
        <group ref={head} position={[0, headY, 0]}>
          <HeadShell head={avatar.head} shell={shell} finish={avatar.finish} />
          <RoundedBox
            args={[plate.w, plate.h, plate.d]}
            radius={plate.r}
            smoothness={5}
            position={[0, headPart.fit.faceY, plate.z]}
          >
            <meshPhysicalMaterial
              color={plateColour}
              roughness={0.12}
              clearcoat={1}
              clearcoatRoughness={0.03}
            />
          </RoundedBox>
          <mesh position={[0, headPart.fit.faceY, headPart.fit.faceZ]}>
            <planeGeometry args={[faceSize.w, faceSize.h]} />
            <meshStandardMaterial
              color="#000000"
              emissive="#ffffff"
              emissiveMap={face.texture}
              emissiveIntensity={1.7}
              roughness={0.15}
              toneMapped={false}
            />
          </mesh>
          <HatPart
            kind={avatar.hat}
            glow={glow}
            accent={accent}
            fit={headPart.fit}
          />
          <HeadExtra
            kind={avatar.extra}
            glow={glow}
            accent={accent}
            shell={shell}
            finish={avatar.finish}
            fit={headPart.fit}
          />
        </group>
        <group ref={handL} position={[-handX, -0.2, 0]}>
          <mesh>
            <sphereGeometry args={[0.1, 24, 24]} />
            <Shell color={shell} finish={avatar.finish} />
          </mesh>
        </group>
        <group ref={handR} position={[handX, -0.2, 0]}>
          <mesh>
            <sphereGeometry args={[0.1, 24, 24]} />
            <Shell color={shell} finish={avatar.finish} />
          </mesh>
          {avatar.extra === "mic" ? (
            <group position={[0.02, 0.12, 0.08]}>
              <Mic glow={glow} unit={0.5} />
            </group>
          ) : null}
        </group>
        <mesh ref={ring} rotation={[Math.PI / 2, 0, 0]} visible={false}>
          <torusGeometry args={[0.72, 0.008, 8, 64]} />
          <Glow color="#f5b041" intensity={2} />
        </mesh>
        {!still ? (
          <Sparkles
            ref={sparkles}
            count={28}
            scale={[2.2, 2, 1.2]}
            size={3}
            speed={0.6}
            color={glow}
            visible={false}
          />
        ) : null}
      </group>
    </>
  );
}
