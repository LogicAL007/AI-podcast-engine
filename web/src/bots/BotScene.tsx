// The assistant bots, drawn with React Three Fiber, in the look each person chose (bots/avatar.ts),
// lit like a collectible vinyl toy on a photo set:
//
// * Toy: the build-your-own bot (ToyBot.tsx), assembled from the parts the person picked.
// * Pod: a floating podcast bot built from primitives (nothing to download).
// * Rex: "RobotExpressive" (CC0, Tomás Laulhé / Quaternius; public/bots/LICENSE.md), a rigged
//   robot with 14 animations and three facial expressions, recoloured to the chosen colour.
//
// Reflections come from a small studio of light panels rendered once into an environment map
// (no image is downloaded), and lit parts bloom softly. Weak devices, or any that cannot keep up,
// get a lighter version without the bloom. Every character follows the pointer, can be dragged
// to spin, and reacts to a tap; the page drives that through a BotControl. Loaded lazily:
// three.js only reaches pages that show a bot.
import {
  Environment,
  Lightformer,
  PerformanceMonitor,
  RoundedBox,
  Sparkles,
  useAnimations,
  useGLTF,
} from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import {
  Color,
  LoopOnce,
  LoopRepeat,
  MeshPhysicalMaterial,
  Quaternion,
  Vector3,
  type AnimationAction,
  type Bone,
  type Group,
  type Mesh,
  type MeshStandardMaterial,
  type Object3D,
  type Points,
} from "three";
import { clone as cloneSkinned } from "three/examples/jsm/utils/SkeletonUtils.js";

import {
  accentHex,
  bodyHex,
  DEFAULT_AVATAR,
  faceHex,
  glowHex,
  type Avatar,
} from "./avatar";
import type { BotMode } from "./botMode";
import {
  Glow,
  HatPart,
  HeadExtra,
  Mic,
  NeckPart,
  Shell,
  shellProps,
  type HeadFit,
} from "./parts";
import {
  easeOut,
  newControl,
  REACTION_SECONDS,
  Shadow,
  useMotion,
  useReaction,
  type BotControl,
  type CharacterProps,
} from "./sceneKit";
import { ToyBot } from "./ToyBot";

export { newControl, type BotControl } from "./sceneKit";

export const ROBOT_URL = "/bots/robot-expressive.glb";
// The model is plain glTF. drei would otherwise set up the Draco and Meshopt decoders, which
// compile WebAssembly: the site's security policy (rightly) does not allow that.
const USE_DRACO = false;
const USE_MESHOPT = false;

const POD_FIT: HeadFit = { unit: 0.49, top: 0.42, faceZ: 0.49, faceY: -0.02 };

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
  const shell = bodyHex(avatar);
  const glow = glowHex(avatar);
  const accent = accentHex(avatar);
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

  const visor = faceHex(avatar);
  return (
    <>
      <Shadow target={root} />
      <group ref={root}>
        <mesh position={[0, -0.38, 0]}>
          <capsuleGeometry args={[0.36, 0.22, 10, 32]} />
          <Shell color={shell} finish={avatar.finish} />
        </mesh>
        {avatar.neck === "none" ? (
          <mesh position={[0, -0.32, 0.37]}>
            <circleGeometry args={[0.09, 32]} />
            <Glow color={glow} intensity={1.2} pulse />
          </mesh>
        ) : (
          <group position={[0, -0.05, avatar.neck === "scarf" ? 0 : 0.31]}>
            <NeckPart
              kind={avatar.neck}
              glow={glow}
              accent={accent}
              unit={0.46}
            />
          </group>
        )}
        <group ref={head} position={[0, 0.34, 0]}>
          <mesh scale={[1.12, 0.92, 1]}>
            <sphereGeometry args={[0.46, 48, 48]} />
            <Shell color={shell} finish={avatar.finish} />
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
          <HatPart
            kind={avatar.hat}
            glow={glow}
            accent={accent}
            fit={POD_FIT}
          />
          <HeadExtra
            kind={avatar.extra}
            glow={glow}
            accent={accent}
            shell={shell}
            finish={avatar.finish}
            fit={POD_FIT}
          />
        </group>
        {[handL, handR].map((hand, i) => (
          <mesh key={i} ref={hand} position={[i ? 0.62 : -0.62, -0.18, 0]}>
            <sphereGeometry args={[0.1, 24, 24]} />
            <Shell color={shell} finish={avatar.finish} />
            {i === 1 && avatar.extra === "mic" ? (
              <group position={[0.02, 0.12, 0.08]}>
                <Mic glow={glow} unit={0.5} />
              </group>
            ) : null}
          </mesh>
        ))}
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
  faceForward: 0.3,
  tieUp: 0.02,
  tieForward: 0.2,
};
const REX_FIT: HeadFit = {
  unit: REX_TUNING.headHalfWidth,
  top: REX_TUNING.headTop,
  faceZ: REX_TUNING.faceForward,
  faceY: 0.02,
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
  const held = useRef<Group>(null);
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
      // The body becomes a physical material, so it can take any finish (clearcoat, sheen...).
      const original = mesh.material as MeshStandardMaterial;
      materials[original.name] ??=
        original.name === "Main"
          ? new MeshPhysicalMaterial({ name: "Main", color: original.color })
          : original.clone();
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
      hand: findBone(model, "HandR"),
    };
  }, [model]);

  const shell = bodyHex(avatar);
  const glow = glowHex(avatar);
  const accent = accentHex(avatar);
  useEffect(() => {
    const main = parts.materials.Main;
    if (main) {
      Object.assign(main, shellProps(avatar.finish));
      main.color.set(shell);
      main.needsUpdate = true;
    }
    const screen = parts.materials.Black;
    if (screen) {
      screen.emissive.set(glow);
      screen.emissiveIntensity = 0.5; // its eyes and brows take the glow colour
    }
    invalidate();
  }, [parts, shell, glow, avatar.finish, invalidate]);

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
    if (held.current && parts.hand) {
      parts.hand.getWorldPosition(where.v);
      parts.hand.getWorldQuaternion(where.q);
      held.current.position.copy(where.v);
      held.current.quaternion.copy(where.q);
    }
  });

  return (
    <>
      <Shadow target={root} />
      <group ref={root}>
        <primitive object={model} />
      </group>
      <group ref={hat}>
        <group position={[0, REX_TUNING.headCentre, 0]}>
          <HatPart
            kind={avatar.hat}
            glow={glow}
            accent={accent}
            fit={REX_FIT}
          />
          <HeadExtra
            kind={avatar.extra === "mic" ? "none" : avatar.extra}
            glow={glow}
            accent={accent}
            shell={shell}
            finish={avatar.finish}
            fit={REX_FIT}
          />
        </group>
      </group>
      <group ref={tie}>
        <group
          position={[
            0,
            REX_TUNING.tieUp,
            avatar.neck === "scarf" ? 0 : REX_TUNING.tieForward,
          ]}
        >
          <NeckPart kind={avatar.neck} glow={glow} accent={accent} unit={0.3} />
        </group>
      </group>
      {avatar.extra === "mic" ? (
        <group ref={held}>
          <Mic glow={glow} unit={0.32} />
        </group>
      ) : null}
    </>
  );
}

/** The photo set: a key light, a warm rim light from behind, and soft panels for reflections. */
function Studio({ high }: { high: boolean }) {
  return (
    <>
      <ambientLight intensity={0.35} />
      <directionalLight position={[2.5, 3, 4]} intensity={2} />
      <pointLight position={[-2.5, 1.5, -2]} intensity={7} color="#fb923c" />
      <pointLight position={[2.2, -0.5, -1.5]} intensity={3} color="#93c5fd" />
      <Environment resolution={high ? 256 : 64} frames={1}>
        <Lightformer
          form="rect"
          intensity={3}
          position={[0, 3, 2]}
          rotation-x={Math.PI / 2}
          scale={[4, 1.4, 1]}
        />
        <Lightformer
          form="rect"
          intensity={2}
          position={[-3, 1, 1]}
          rotation-y={Math.PI / 2}
          scale={[2.5, 3, 1]}
        />
        <Lightformer
          form="rect"
          intensity={1.4}
          color="#ffe4d1"
          position={[3, 0.5, 1]}
          rotation-y={-Math.PI / 2}
          scale={[2.5, 3, 1]}
        />
        <Lightformer
          form="ring"
          intensity={2.5}
          color="#fb923c"
          position={[0, 1, -3]}
          scale={2}
        />
      </Environment>
    </>
  );
}

export type Quality = "high" | "low";

/** High for most screens; low for phones, small CPUs and data savers, and for any device that
 * cannot keep up (PerformanceMonitor drops it after a few slow seconds). */
export function initialQuality(): Quality {
  if (typeof window === "undefined") return "high";
  const coarse = window.matchMedia?.("(pointer: coarse)").matches ?? false;
  const cores = navigator.hardwareConcurrency ?? 8;
  const saveData = (navigator as { connection?: { saveData?: boolean } })
    .connection?.saveData;
  return coarse || cores <= 4 || saveData ? "low" : "high";
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
  const [quality, setQuality] = useState<Quality>(initialQuality);
  const high = quality === "high";
  const Character =
    avatar.character === "rex"
      ? Rex
      : avatar.character === "pod"
        ? Pod
        : ToyBot;
  return (
    <Canvas
      className="bot-canvas"
      data-quality={quality}
      dpr={high ? [1, 2] : [1, 1.25]}
      camera={{ position: [0, 0.15, 4.4], fov: 32 }}
      gl={{ antialias: true, alpha: true }}
      frameloop={still ? "demand" : "always"}
    >
      <PerformanceMonitor flipflops={1} onDecline={() => setQuality("low")} />
      <Studio high={high} />
      <Suspense fallback={null}>
        <Character mode={mode} still={still} avatar={avatar} control={ctl} />
      </Suspense>
      {high ? (
        <EffectComposer multisampling={4}>
          <Bloom
            mipmapBlur
            luminanceThreshold={1}
            intensity={0.55}
            radius={0.55}
          />
        </EffectComposer>
      ) : null}
    </Canvas>
  );
}

/** Start fetching the robot model early (it is small, but it should be ready when shown). */
export function preloadRobot(): void {
  useGLTF.preload(ROBOT_URL, USE_DRACO, USE_MESHOPT);
}
