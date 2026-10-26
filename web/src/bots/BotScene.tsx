// The assistant bots, drawn with React Three Fiber, in the look each person chose (bots/avatar.ts):
//
// * Pod: a floating podcast bot built from primitives (nothing to download).
// * Rex: "RobotExpressive" (CC0, Tomás Laulhé / Quaternius; public/bots/LICENSE.md), a rigged
//   robot with 14 animations and three facial expressions, recoloured to the chosen colour.
//
// Both follow the pointer, can be dragged to spin, and react to a tap; the page drives that
// through a BotControl. Loaded lazily: three.js only reaches pages that show a bot.
import {
  RoundedBox,
  Sparkles,
  useAnimations,
  useGLTF,
} from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Suspense, useEffect, useMemo, useRef, type RefObject } from "react";
import {
  CanvasTexture,
  Color,
  LoopOnce,
  LoopRepeat,
  Quaternion,
  Vector3,
  type AnimationAction,
  type Bone,
  type Group,
  type Mesh,
  type MeshBasicMaterial,
  type MeshStandardMaterial,
  type Object3D,
  type Points,
} from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import { COLORS, DEFAULT_AVATAR, GLOWS, type Avatar } from "./avatar";
import type { BotMode } from "./botMode";

export const ROBOT_URL = "/bots/robot-expressive.glb";
// The model is plain glTF. drei would otherwise set up the Draco and Meshopt decoders, which
// compile WebAssembly: the site's security policy (rightly) does not allow that.
const USE_DRACO = false;
const USE_MESHOPT = false;

/** What the page tells a bot: where the pointer is, hover, drag spin, and taps. */
export interface BotControl {
  lookX: number; // -1 (far left of the screen) .. 1 (far right)
  lookY: number; // -1 (bottom) .. 1 (top)
  hovering: boolean;
  spin: number; // radians a second, from a drag; eases off by itself
  pokes: number; // goes up by one on each tap; the bot reacts to every new value
}

export function newControl(): BotControl {
  return { lookX: 0, lookY: 0, hovering: false, spin: 0, pokes: 0 };
}

const ACCENT = "#c2410c";
const REACTION_SECONDS = 1.2;

function easeOut(p: number): number {
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
function Shadow({ target }: { target: RefObject<Object3D | null> }) {
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

/** Pointer following and drag spin, shared by both characters; call once per frame. */
function useMotion(control: RefObject<BotControl>, still: boolean) {
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
function useReaction(control: RefObject<BotControl>) {
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

// ---- accessories ------------------------------------------------------------------------------

/** What a bot wears on its head, lit in the glow colour. `unit` is the head's half-width and
 * `top` the height of its crown above the head's centre (a wide, flat head has a small top). */
function HeadAccessory({
  kind,
  glow,
  unit,
  top,
}: {
  kind: Avatar["accessory"];
  glow: string;
  unit: number;
  top: number;
}) {
  const tip = useRef<MeshStandardMaterial>(null);
  useFrame((state) => {
    if (tip.current)
      tip.current.emissiveIntensity =
        1.4 + Math.sin(state.clock.elapsedTime * 4) * 0.8;
  });
  if (kind === "antenna") {
    return (
      <group>
        <mesh position={[0, top + unit * 0.12, 0]}>
          <cylinderGeometry
            args={[unit * 0.028, unit * 0.028, unit * 0.4, 12]}
          />
          <meshStandardMaterial color="#d6d3d1" />
        </mesh>
        <mesh position={[0, top + unit * 0.36, 0]}>
          <sphereGeometry args={[unit * 0.11, 24, 24]} />
          <meshStandardMaterial
            ref={tip}
            color={glow}
            emissive={glow}
            emissiveIntensity={1.4}
            toneMapped={false}
          />
        </mesh>
      </group>
    );
  }
  if (kind === "headphones") {
    const r = unit * 1.08;
    return (
      <group>
        {/* The band hugs the crown: an arc as wide as the head, squashed to its height. */}
        <mesh position={[0, unit * 0.05, 0]} scale={[1, (top * 1.15) / r, 1]}>
          <torusGeometry args={[r, unit * 0.07, 12, 48, Math.PI]} />
          <meshStandardMaterial color="#2a2522" roughness={0.4} />
        </mesh>
        {[-1, 1].map((side) => (
          <group
            key={side}
            position={[side * r, unit * 0.02, 0]}
            rotation={[0, 0, Math.PI / 2]}
          >
            <mesh>
              <cylinderGeometry
                args={[unit * 0.26, unit * 0.26, unit * 0.18, 32]}
              />
              <meshStandardMaterial color="#2a2522" roughness={0.35} />
            </mesh>
            <mesh
              position={[0, side * unit * 0.095, 0]}
              rotation={[Math.PI / 2, 0, 0]}
            >
              <torusGeometry args={[unit * 0.17, unit * 0.025, 8, 32]} />
              <meshStandardMaterial
                color={glow}
                emissive={glow}
                emissiveIntensity={1.6}
                toneMapped={false}
              />
            </mesh>
          </group>
        ))}
      </group>
    );
  }
  return null;
}

function BowTie({ glow, unit }: { glow: string; unit: number }) {
  return (
    <group>
      {[-1, 1].map((side) => (
        <mesh
          key={side}
          position={[side * unit * 0.16, 0, 0]}
          rotation={[0, 0, (-side * Math.PI) / 2]}
        >
          <coneGeometry args={[unit * 0.15, unit * 0.28, 4]} />
          <meshStandardMaterial color={ACCENT} roughness={0.5} />
        </mesh>
      ))}
      <mesh>
        <sphereGeometry args={[unit * 0.07, 16, 16]} />
        <meshStandardMaterial
          color={glow}
          emissive={glow}
          emissiveIntensity={1.2}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

interface CharacterProps {
  mode: BotMode;
  still: boolean;
  avatar: Avatar;
  control: RefObject<BotControl>;
}

// ---- Pod -------------------------------------------------------------------------------------

function Pod({ mode, still, avatar, control }: CharacterProps) {
  const root = useRef<Group>(null);
  const head = useRef<Group>(null);
  const eyes = useRef<Group>(null);
  const handL = useRef<Mesh>(null);
  const handR = useRef<Mesh>(null);
  const ring = useRef<Mesh>(null);
  const sparkles = useRef<Points>(null);
  const motion = useMotion(control, still);
  const reaction = useReaction(control);
  const shell = COLORS[avatar.color].hex;
  const glow = GLOWS[avatar.glow].hex;
  const eyeColour = useMemo(() => new Color(glow), [glow]);

  useFrame((state, delta) => {
    if (
      !root.current ||
      !head.current ||
      !eyes.current ||
      !handL.current ||
      !handR.current
    )
      return;
    const t = still ? 0.8 : state.clock.elapsedTime;
    const { since } = reaction(state.clock.elapsedTime);
    const reacting = !still && since < REACTION_SECONDS;
    const p = Math.min(1, since / REACTION_SECONDS);
    const c = control.current;

    // Eyes: a blink every few seconds; happy and squinting eyes are flatter, and they widen
    // when you hover over the bot.
    const open = t % 3.4 < 0.12 ? 0.12 : 1;
    let shape =
      mode === "celebrating"
        ? 0.38
        : mode === "reviewing"
          ? 0.55
          : mode === "greeting"
            ? 0.7
            : 1;
    if (reacting) shape = 0.38;
    else if (c.hovering) shape = Math.max(shape, 1.2);
    eyes.current.scale.y = open * shape;
    eyes.current.position.set(0, -0.02, 0.5);
    head.current.rotation.set(0, 0, 0);

    if (mode === "working") {
      // Hovering, scanning side to side, hands tapping away.
      root.current.position.y = Math.sin(t * 2) * 0.06;
      root.current.rotation.y = Math.sin(t * 0.6) * 0.15;
      head.current.rotation.y = Math.sin(t * 1.6) * 0.35;
      eyes.current.position.x = Math.sin(t * 1.6) * 0.04;
      handL.current.position.set(
        -0.62,
        -0.18 + Math.abs(Math.sin(t * 9)) * 0.08,
        0,
      );
      handR.current.position.set(
        0.62,
        -0.18 + Math.abs(Math.cos(t * 9)) * 0.08,
        0,
      );
    } else if (mode === "reviewing") {
      // A thoughtful head tilt and a scan ring sweeping up and down.
      root.current.position.y = Math.sin(t * 1.4) * 0.04;
      root.current.rotation.y = 0;
      head.current.rotation.y = Math.sin(t * 0.7) * 0.12;
      head.current.rotation.z = 0.14 + Math.sin(t * 0.9) * 0.05;
      handL.current.position.set(-0.6, -0.2, 0.1);
      handR.current.position.set(0.48, 0.2 + Math.sin(t * 1.4) * 0.04, 0.38); // chin-scratching
    } else if (mode === "greeting") {
      // A friendly hello: a gentle bob, a curious head tilt and one hand waving high.
      root.current.position.y = Math.sin(t * 1.6) * 0.05;
      root.current.rotation.y = Math.sin(t * 0.5) * 0.1;
      head.current.rotation.y = 0.15;
      head.current.rotation.z = 0.1 + Math.sin(t * 1.2) * 0.04;
      handL.current.position.set(-0.6, -0.2, 0.1);
      handR.current.position.set(0.66 + Math.sin(t * 7) * 0.08, 0.5, 0.15);
    } else {
      // Bouncing, spinning, both hands up and waving.
      root.current.position.y = Math.abs(Math.sin(t * 4)) * 0.22;
      root.current.rotation.y = still ? 0 : t * 2.2;
      head.current.rotation.z = Math.sin(t * 8) * 0.08;
      handL.current.position.set(-0.62, 0.42 + Math.sin(t * 9) * 0.08, 0);
      handR.current.position.set(0.62, 0.42 + Math.cos(t * 9) * 0.08, 0);
    }

    // It looks where you are, and keeps turning after a drag.
    const { lookX, lookY, spin } = motion(delta);
    head.current.rotation.y += lookX * 0.5;
    head.current.rotation.x = -lookY * 0.3;
    eyes.current.position.x += lookX * 0.05;
    eyes.current.position.y += lookY * 0.03;
    root.current.rotation.y += spin;

    // A tap: a hop, a full twirl and both hands up.
    if (reacting) {
      const hop = Math.sin(Math.PI * p);
      root.current.position.y += hop * 0.35;
      root.current.rotation.y += easeOut(p) * Math.PI * 2;
      handL.current.position.y += hop * 0.5;
      handR.current.position.y += hop * 0.5;
    }
    if (ring.current) {
      ring.current.visible = mode === "reviewing";
      ring.current.position.y = 0.15 + Math.sin(t * 1.8) * 0.42;
    }
    if (sparkles.current)
      sparkles.current.visible = !still && (mode === "celebrating" || reacting);
  });

  const visor = avatar.color === "graphite" ? "#0d0b0a" : "#17120f";
  return (
    <>
      <Shadow target={root} />
      <group ref={root}>
        <mesh position={[0, -0.38, 0]}>
          <capsuleGeometry args={[0.36, 0.22, 10, 32]} />
          <meshPhysicalMaterial
            color={shell}
            roughness={0.25}
            clearcoat={1}
            clearcoatRoughness={0.08}
          />
        </mesh>
        {avatar.accessory === "bowtie" ? (
          <group position={[0, -0.05, 0.31]}>
            <BowTie glow={glow} unit={0.46} />
          </group>
        ) : (
          <mesh position={[0, -0.32, 0.33]}>
            <circleGeometry args={[0.09, 32]} />
            <meshStandardMaterial
              color={glow}
              emissive={glow}
              emissiveIntensity={0.6}
            />
          </mesh>
        )}
        <group ref={head} position={[0, 0.34, 0]}>
          <mesh scale={[1.12, 0.92, 1]}>
            <sphereGeometry args={[0.46, 48, 48]} />
            <meshPhysicalMaterial
              color={shell}
              roughness={0.2}
              clearcoat={1}
              clearcoatRoughness={0.06}
            />
          </mesh>
          <RoundedBox
            args={[0.74, 0.38, 0.2]}
            radius={0.12}
            smoothness={6}
            position={[0, -0.02, 0.39]}
          >
            <meshPhysicalMaterial
              color={visor}
              roughness={0.15}
              clearcoat={1}
            />
          </RoundedBox>
          <group ref={eyes} position={[0, -0.02, 0.5]}>
            {[-0.15, 0.15].map((x) => (
              <mesh key={x} position={[x, 0, 0]}>
                <capsuleGeometry args={[0.045, 0.1, 6, 16]} />
                <meshStandardMaterial
                  color={eyeColour}
                  emissive={eyeColour}
                  emissiveIntensity={2.2}
                  toneMapped={false}
                />
              </mesh>
            ))}
          </group>
          <HeadAccessory
            kind={avatar.accessory}
            glow={glow}
            unit={0.49}
            top={0.42}
          />
        </group>
        {[handL, handR].map((hand, i) => (
          <mesh key={i} ref={hand} position={[i ? 0.62 : -0.62, -0.18, 0]}>
            <sphereGeometry args={[0.1, 24, 24]} />
            <meshPhysicalMaterial
              color={shell}
              roughness={0.25}
              clearcoat={1}
            />
          </mesh>
        ))}
        <mesh ref={ring} rotation={[Math.PI / 2, 0, 0]} visible={false}>
          <torusGeometry args={[0.72, 0.008, 8, 64]} />
          <meshStandardMaterial
            color="#f5b041"
            emissive="#f5b041"
            emissiveIntensity={2}
            transparent
            opacity={0.8}
            toneMapped={false}
          />
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

// ---- Rex -------------------------------------------------------------------------------------

/** The clip each moment plays on a loop, and the gestures a tap cycles through. */
const BASE_CLIP: Record<BotMode, string> = {
  working: "Walking",
  reviewing: "Idle",
  celebrating: "Dance",
  greeting: "Wave",
};
const GESTURES = ["Wave", "ThumbsUp", "Yes", "Jump"];
const REX_HEIGHT = 1.85;
const REX_MODEL_HEIGHT = 4.46; // the robot's height in the file's units, feet at 0
/** Where Rex's accessories sit relative to its bones, in scene units (checked by eye). */
const REX_TUNING = {
  headCentre: 0.27,
  headHalfWidth: 0.52,
  headTop: 0.3,
  tieUp: 0.02,
  tieForward: 0.2,
};

function findBone(model: Object3D, name: string): Bone | undefined {
  let found: Bone | undefined;
  model.traverse((node) => {
    if (!found && (node as Bone).isBone && node.name === name)
      found = node as Bone;
  });
  return found;
}

function Rex({ mode, still, avatar, control }: CharacterProps) {
  const root = useRef<Group>(null);
  const hat = useRef<Group>(null);
  const tie = useRef<Group>(null);
  const motion = useMotion(control, still);
  const reaction = useReaction(control);
  const invalidate = useThree((state) => state.invalidate);
  const { scene, animations } = useGLTF(ROBOT_URL, USE_DRACO, USE_MESHOPT);

  // Each bot on screen gets its own copy (and its own materials), scaled to stand on the floor.
  // The size is measured once from the file (REX_MODEL_HEIGHT): a bounding box taken before the
  // skeleton's first update is distorted by the bones' 100x scale.
  const model = useMemo(() => {
    const copy = cloneSkinned(scene) as Group;
    copy.scale.setScalar(REX_HEIGHT / REX_MODEL_HEIGHT);
    copy.position.set(0, -0.95, 0);
    return copy;
  }, [scene]);

  const parts = useMemo(() => {
    const materials: Record<string, MeshStandardMaterial> = {};
    let face: Mesh | undefined;
    model.traverse((node) => {
      const mesh = node as Mesh;
      if (!mesh.isMesh) return;
      // Several meshes share each material (Main is the whole body), so each is copied once
      // and the copy shared again: recolouring it recolours this robot, and only this one.
      const original = mesh.material as MeshStandardMaterial;
      materials[original.name] ??= original.clone();
      mesh.material = materials[original.name];
      if (
        mesh.morphTargetDictionary &&
        "Surprised" in mesh.morphTargetDictionary
      )
        face = mesh;
    });
    return {
      materials,
      face,
      head: findBone(model, "Head"),
      neck: findBone(model, "Neck"),
    };
  }, [model]);

  useEffect(() => {
    parts.materials.Main?.color.set(COLORS[avatar.color].hex);
    const screen = parts.materials.Black;
    if (screen) {
      screen.emissive.set(GLOWS[avatar.glow].hex);
      screen.emissiveIntensity = 0.35; // its eyes and brows take the glow colour
    }
    invalidate();
  }, [parts, avatar.color, avatar.glow, invalidate]);

  const { actions, mixer } = useAnimations(animations, root);
  const current = useRef<AnimationAction | null>(null);
  const modeNow = useRef(mode);
  modeNow.current = mode;
  const gesture = useRef(0);

  const play = useMemo(
    () =>
      (name: string, once = false) => {
        const next = actions[name];
        if (!next) return;
        next.reset();
        next.setLoop(once ? LoopOnce : LoopRepeat, once ? 1 : Infinity);
        next.clampWhenFinished = once;
        if (current.current && current.current !== next)
          next.crossFadeFrom(current.current, 0.3, false);
        next.play();
        current.current = next;
      },
    [actions],
  );

  useEffect(() => {
    play(BASE_CLIP[mode]);
    if (still) {
      mixer.update(0.6); // hold a natural pose instead of the bind pose
      invalidate();
    }
  }, [mode, still, play, mixer, invalidate]);

  useEffect(() => {
    // After a one-off gesture, go back to the moment's loop.
    const back = (event: { action: AnimationAction }) => {
      if (event.action === current.current) play(BASE_CLIP[modeNow.current]);
    };
    mixer.addEventListener("finished", back);
    return () => mixer.removeEventListener("finished", back);
  }, [mixer, play]);

  const where = useMemo(() => ({ v: new Vector3(), q: new Quaternion() }), []);
  useFrame((state, delta) => {
    if (!root.current) return;
    const { fresh, since } = reaction(state.clock.elapsedTime);
    if (fresh && !still)
      play(GESTURES[gesture.current++ % GESTURES.length], true);
    const c = control.current;

    // Runs after the animation mixer (same component, registered later), so these add to it.
    const { lookX, lookY, spin } = motion(delta);
    root.current.rotation.y = spin;
    if (parts.head) {
      parts.head.rotation.y += lookX * 0.6;
      parts.head.rotation.x -= lookY * 0.35;
    }

    // A surprised face on a tap, a curious one on hover or while reviewing.
    const face = parts.face;
    const index = face?.morphTargetDictionary?.Surprised;
    if (face?.morphTargetInfluences && index !== undefined) {
      const target =
        !still && since < 0.7
          ? 1
          : c.hovering
            ? 0.45
            : mode === "reviewing"
              ? 0.2
              : 0;
      const now = face.morphTargetInfluences[index];
      face.morphTargetInfluences[index] =
        now + (target - now) * Math.min(1, delta * 8);
    }

    // Accessories ride on the head and neck bones.
    if (hat.current && parts.head) {
      parts.head.getWorldPosition(where.v);
      parts.head.getWorldQuaternion(where.q);
      hat.current.position.copy(where.v);
      hat.current.quaternion.copy(where.q);
    }
    if (tie.current && parts.neck) {
      parts.neck.getWorldPosition(where.v);
      parts.neck.getWorldQuaternion(where.q);
      tie.current.position.copy(where.v);
      tie.current.quaternion.copy(where.q);
    }
  });

  const glow = GLOWS[avatar.glow].hex;
  return (
    <>
      <Shadow target={root} />
      <group ref={root}>
        <primitive object={model} />
      </group>
      {avatar.accessory === "antenna" || avatar.accessory === "headphones" ? (
        <group ref={hat}>
          <group position={[0, REX_TUNING.headCentre, 0]}>
            <HeadAccessory
              kind={avatar.accessory}
              glow={glow}
              unit={REX_TUNING.headHalfWidth}
              top={REX_TUNING.headTop}
            />
          </group>
        </group>
      ) : null}
      {avatar.accessory === "bowtie" ? (
        <group ref={tie}>
          <group position={[0, REX_TUNING.tieUp, REX_TUNING.tieForward]}>
            <BowTie glow={glow} unit={0.3} />
          </group>
        </group>
      ) : null}
    </>
  );
}

export default function BotScene({
  mode,
  still = false,
  avatar = DEFAULT_AVATAR,
  control,
}: {
  mode: BotMode;
  still?: boolean;
  avatar?: Avatar;
  control?: RefObject<BotControl>;
}) {
  const own = useRef<BotControl>(newControl());
  const ctl = control ?? own;
  return (
    <Canvas
      className="bot-canvas"
      dpr={[1, 2]}
      camera={{ position: [0, 0.15, 4.4], fov: 32 }}
      gl={{ antialias: true, alpha: true }}
      frameloop={still ? "demand" : "always"}
    >
      <ambientLight intensity={0.8} />
      <directionalLight position={[2.5, 3, 4]} intensity={2.4} />
      <pointLight position={[-2.5, 1.5, -2]} intensity={6} color="#fb923c" />
      <Suspense fallback={null}>
        {avatar.character === "rex" ? (
          <Rex mode={mode} still={still} avatar={avatar} control={ctl} />
        ) : (
          <Pod mode={mode} still={still} avatar={avatar} control={ctl} />
        )}
      </Suspense>
    </Canvas>
  );
}

/** Start fetching the robot model early (it is small, but it should be ready when shown). */
export function preloadRobot(): void {
  useGLTF.preload(ROBOT_URL, USE_DRACO, USE_MESHOPT);
}
