// Parts every bot can wear, and the shell finishes, shared by the Toy, Pod and Rex (BotScene).
// Everything is built from primitives: nothing is downloaded. Sizes are given relative to the
// head they sit on (HeadFit), so one hat fits a small sphere and a wide TV screen alike.
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { MeshStandardMaterial } from "three";

import type { Avatar } from "./avatar";

/** Where things go on a head, in its own coordinates (its centre at 0). */
export interface HeadFit {
  unit: number; // half its width
  top: number; // height of its crown
  faceZ: number; // the front of its face plate
  faceY: number; // the height of its eyes
}

const GOLD = "#f2c14e";
const DARK = "#2a2522";

/** The look of each finish: what makes a shell read as vinyl, chalk, metal or pearl. */
export function shellProps(finish: Avatar["finish"]) {
  switch (finish) {
    case "matte":
      return {
        roughness: 0.78,
        metalness: 0,
        clearcoat: 0,
        sheen: 0.4,
        sheenRoughness: 0.8,
      };
    case "metallic":
      return {
        roughness: 0.32,
        metalness: 0.85,
        clearcoat: 0.5,
        clearcoatRoughness: 0.2,
      };
    case "pearlescent":
      return {
        roughness: 0.22,
        metalness: 0.05,
        clearcoat: 1,
        clearcoatRoughness: 0.05,
        iridescence: 0.9,
        iridescenceIOR: 1.35,
        iridescenceThicknessRange: [180, 520] as [number, number],
      };
    default:
      return {
        roughness: 0.2,
        metalness: 0,
        clearcoat: 1,
        clearcoatRoughness: 0.04,
      };
  }
}

/** A shell-coloured part in the chosen finish. */
export function Shell({
  color,
  finish,
}: {
  color: string;
  finish: Avatar["finish"];
}) {
  return <meshPhysicalMaterial color={color} {...shellProps(finish)} />;
}

/** A small glossy part in a fixed colour (trim, outfits). */
function Trim({ color, metal = false }: { color: string; metal?: boolean }) {
  return (
    <meshPhysicalMaterial
      color={color}
      roughness={metal ? 0.25 : 0.35}
      metalness={metal ? 0.9 : 0}
      clearcoat={metal ? 0.3 : 0.8}
      clearcoatRoughness={0.1}
    />
  );
}

/** A lit part in the glow colour: bright enough for the bloom to catch it. */
export function Glow({
  color,
  intensity = 2,
  pulse = false,
}: {
  color: string;
  intensity?: number;
  pulse?: boolean;
}) {
  const material = useRef<MeshStandardMaterial>(null);
  useFrame((state) => {
    if (pulse && material.current)
      material.current.emissiveIntensity =
        intensity + Math.sin(state.clock.elapsedTime * 4) * intensity * 0.4;
  });
  return (
    <meshStandardMaterial
      ref={material}
      color={color}
      emissive={color}
      emissiveIntensity={intensity}
      toneMapped={false}
    />
  );
}

export function HatPart({
  kind,
  glow,
  accent,
  fit,
}: {
  kind: Avatar["hat"];
  glow: string;
  accent: string;
  fit: HeadFit;
}) {
  const { unit, top } = fit;
  switch (kind) {
    case "antenna":
      return (
        <group>
          <mesh position={[0, top + unit * 0.12, 0]}>
            <cylinderGeometry
              args={[unit * 0.028, unit * 0.028, unit * 0.4, 12]}
            />
            <Trim color="#d6d3d1" metal />
          </mesh>
          <mesh position={[0, top + unit * 0.36, 0]}>
            <sphereGeometry args={[unit * 0.11, 24, 24]} />
            <Glow color={glow} intensity={1.8} pulse />
          </mesh>
        </group>
      );
    case "headphones": {
      const r = unit * 1.08;
      return (
        <group>
          {/* The band hugs the crown: an arc as wide as the head, squashed to its height. */}
          <mesh position={[0, unit * 0.05, 0]} scale={[1, (top * 1.15) / r, 1]}>
            <torusGeometry args={[r, unit * 0.07, 12, 48, Math.PI]} />
            <Trim color={DARK} />
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
                <Trim color={accent} />
              </mesh>
              <mesh
                position={[0, side * unit * 0.095, 0]}
                rotation={[Math.PI / 2, 0, 0]}
              >
                <torusGeometry args={[unit * 0.17, unit * 0.025, 8, 32]} />
                <Glow color={glow} intensity={1.8} />
              </mesh>
            </group>
          ))}
        </group>
      );
    }
    case "cap":
      return (
        <group position={[0, top * 0.72, 0]} rotation={[-0.12, 0, 0]}>
          <mesh scale={[1, 0.62, 1]}>
            <sphereGeometry
              args={[unit * 0.86, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2]}
            />
            <Trim color={accent} />
          </mesh>
          <mesh position={[0, 0.005, unit * 0.82]} scale={[1, 1, 0.9]}>
            <cylinderGeometry
              args={[
                unit * 0.66,
                unit * 0.68,
                unit * 0.04,
                40,
                1,
                false,
                -Math.PI / 2,
                Math.PI,
              ]}
            />
            <Trim color={accent} />
          </mesh>
          <mesh position={[0, unit * 0.56, 0]}>
            <sphereGeometry args={[unit * 0.07, 16, 16]} />
            <Glow color={glow} intensity={1.4} />
          </mesh>
        </group>
      );
    case "beanie":
      return (
        <group position={[0, top * 0.62, 0]}>
          <mesh scale={[1, 0.85, 1]}>
            <sphereGeometry
              args={[unit * 0.92, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2]}
            />
            <meshPhysicalMaterial
              color={accent}
              roughness={0.85}
              sheen={1}
              sheenColor={accent}
            />
          </mesh>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[unit * 0.9, unit * 0.1, 12, 48]} />
            <meshPhysicalMaterial color={accent} roughness={0.9} sheen={1} />
          </mesh>
          <mesh position={[0, unit * 0.86, 0]}>
            <sphereGeometry args={[unit * 0.17, 20, 20]} />
            <meshPhysicalMaterial color="#fafaf9" roughness={1} sheen={1} />
          </mesh>
        </group>
      );
    case "crown":
      return (
        <group position={[0, top * 0.9, 0]}>
          <mesh>
            <cylinderGeometry
              args={[unit * 0.52, unit * 0.52, unit * 0.22, 40, 1, true]}
            />
            <meshPhysicalMaterial
              color={GOLD}
              metalness={1}
              roughness={0.22}
              side={2}
            />
          </mesh>
          {Array.from({ length: 6 }, (_, i) => {
            const a = (i / 6) * Math.PI * 2;
            return (
              <group key={i}>
                <mesh
                  position={[
                    Math.sin(a) * unit * 0.52,
                    unit * 0.2,
                    Math.cos(a) * unit * 0.52,
                  ]}
                >
                  <coneGeometry args={[unit * 0.09, unit * 0.2, 4]} />
                  <meshPhysicalMaterial
                    color={GOLD}
                    metalness={1}
                    roughness={0.22}
                  />
                </mesh>
                <mesh
                  position={[
                    Math.sin(a) * unit * 0.53,
                    0,
                    Math.cos(a) * unit * 0.53,
                  ]}
                >
                  <sphereGeometry args={[unit * 0.045, 12, 12]} />
                  <Glow color={i % 2 ? glow : accent} intensity={1.6} />
                </mesh>
              </group>
            );
          })}
        </group>
      );
    case "halo":
      return (
        <mesh
          position={[0, top + unit * 0.28, -unit * 0.05]}
          rotation={[Math.PI / 2 - 0.42, 0, 0]}
        >
          <torusGeometry args={[unit * 0.52, unit * 0.07, 16, 48]} />
          <Glow color={glow} intensity={2.4} pulse />
        </mesh>
      );
    default:
      return null;
  }
}

/** Worn at the neck; `unit` is the body's half-width at the top. */
export function NeckPart({
  kind,
  glow,
  accent,
  unit,
}: {
  kind: Avatar["neck"];
  glow: string;
  accent: string;
  unit: number;
}) {
  switch (kind) {
    case "bowtie":
      return (
        <group>
          {[-1, 1].map((side) => (
            <mesh
              key={side}
              position={[side * unit * 0.16, 0, 0]}
              rotation={[0, 0, (-side * Math.PI) / 2]}
            >
              <coneGeometry args={[unit * 0.15, unit * 0.28, 4]} />
              <Trim color={accent} />
            </mesh>
          ))}
          <mesh>
            <sphereGeometry args={[unit * 0.07, 16, 16]} />
            <Glow color={glow} intensity={1.4} />
          </mesh>
        </group>
      );
    case "scarf":
      return (
        <group>
          <mesh rotation={[Math.PI / 2, 0, 0]} scale={[1, 0.9, 1]}>
            <torusGeometry args={[unit * 0.62, unit * 0.13, 14, 40]} />
            <meshPhysicalMaterial
              color={accent}
              roughness={0.9}
              sheen={1}
              sheenColor="#ffffff"
            />
          </mesh>
          <mesh
            position={[unit * 0.3, -unit * 0.28, unit * 0.62]}
            rotation={[0.2, 0, 0.18]}
          >
            <boxGeometry args={[unit * 0.22, unit * 0.5, unit * 0.08]} />
            <meshPhysicalMaterial color={accent} roughness={0.9} sheen={1} />
          </mesh>
        </group>
      );
    case "medal":
      return (
        <group>
          {[-1, 1].map((side) => (
            <mesh
              key={side}
              position={[side * unit * 0.12, -unit * 0.12, 0]}
              rotation={[0, 0, side * 0.35]}
            >
              <boxGeometry args={[unit * 0.1, unit * 0.3, unit * 0.02]} />
              <Trim color={accent} />
            </mesh>
          ))}
          <mesh
            position={[0, -unit * 0.32, 0.01]}
            rotation={[Math.PI / 2, 0, 0]}
          >
            <cylinderGeometry
              args={[unit * 0.13, unit * 0.13, unit * 0.04, 32]}
            />
            <meshPhysicalMaterial color={GOLD} metalness={1} roughness={0.2} />
          </mesh>
          <mesh position={[0, -unit * 0.32, unit * 0.035]}>
            <circleGeometry args={[unit * 0.06, 24]} />
            <Glow color={glow} intensity={1.4} />
          </mesh>
        </group>
      );
    default:
      return null;
  }
}

/** Glasses or ears: worn on the head. (The microphone is held: see Mic.) */
export function HeadExtra({
  kind,
  glow,
  accent,
  shell,
  finish,
  fit,
}: {
  kind: Avatar["extra"];
  glow: string;
  accent: string;
  shell: string;
  finish: Avatar["finish"];
  fit: HeadFit;
}) {
  const { unit, faceZ, faceY } = fit;
  if (kind === "glasses") {
    return (
      <group position={[0, faceY + unit * 0.02, faceZ + unit * 0.06]}>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * unit * 0.3, 0, 0]}>
            <torusGeometry args={[unit * 0.19, unit * 0.03, 10, 36]} />
            <Trim color={accent} />
          </mesh>
        ))}
        <mesh>
          <boxGeometry args={[unit * 0.24, unit * 0.04, unit * 0.04]} />
          <Trim color={accent} />
        </mesh>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * unit * 0.3, 0, -unit * 0.005]}>
            <circleGeometry args={[unit * 0.17, 32]} />
            <meshPhysicalMaterial
              color={glow}
              transparent
              opacity={0.18}
              roughness={0}
              transmission={0.4}
            />
          </mesh>
        ))}
      </group>
    );
  }
  if (kind === "ears") {
    return (
      <group>
        {[-1, 1].map((side) => (
          <group
            key={side}
            position={[side * unit * 0.62, fit.top * 0.78, 0]}
            rotation={[0, 0, -side * 0.35]}
          >
            <mesh>
              <coneGeometry args={[unit * 0.22, unit * 0.42, 24]} />
              <Shell color={shell} finish={finish} />
            </mesh>
            <mesh
              position={[0, -unit * 0.02, unit * 0.06]}
              scale={[0.6, 0.65, 0.5]}
            >
              <coneGeometry args={[unit * 0.22, unit * 0.42, 24]} />
              <Trim color={accent} />
            </mesh>
          </group>
        ))}
      </group>
    );
  }
  return null;
}

/** A handheld podcast microphone, its grille lit in the glow colour. */
export function Mic({ glow, unit }: { glow: string; unit: number }) {
  return (
    <group rotation={[0.5, 0, -0.3]}>
      <mesh position={[0, -unit * 0.25, 0]}>
        <cylinderGeometry args={[unit * 0.06, unit * 0.05, unit * 0.5, 16]} />
        <Trim color={DARK} />
      </mesh>
      <mesh position={[0, unit * 0.06, 0]}>
        <sphereGeometry args={[unit * 0.15, 24, 24]} />
        <meshPhysicalMaterial
          color="#d6d3d1"
          metalness={0.9}
          roughness={0.35}
        />
      </mesh>
      <mesh position={[0, -unit * 0.05, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[unit * 0.08, unit * 0.02, 8, 24]} />
        <Glow color={glow} intensity={1.6} />
      </mesh>
    </group>
  );
}
