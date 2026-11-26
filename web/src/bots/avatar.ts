// The assistant bot each person chooses: which character, its name, its colours and what it
// wears. Only these choices are stored (on the account); the bot itself is drawn here.
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { keys } from "../api/queries";
import type { Avatar, CurrentUser } from "../api/types";
import { useMaybeUser } from "../auth/AuthProvider";

export type { Avatar };

export const DEFAULT_AVATAR: Avatar = {
  character: "toy",
  name: "James",
  color: "pearl",
  accent: "#c2410c",
  glow: "amber",
  finish: "glossy",
  body: "round",
  head: "sphere",
  eyes: "dots",
  mouth: "smile",
  hat: "antenna",
  neck: "none",
  extra: "none",
  personality: "cheerful",
  voice: { engine: "browser", name: "", rate: 1, pitch: 1 },
};

/** A choice in the creator: its value, what it is called and (sometimes) a line about it. */
export interface Option<T extends string> {
  value: T;
  label: string;
  about?: string;
}

export const CHARACTERS: Option<Avatar["character"]>[] = [
  {
    value: "toy",
    label: "Toy",
    about: "Build your own: pick its body, head, face and outfit.",
  },
  {
    value: "pod",
    label: "Pod",
    about: "A floating podcast bot with a glowing visor.",
  },
  {
    value: "rex",
    label: "Rex",
    about: "A full-body robot that waves, dances and cheers.",
  },
];

/** Preset body colours: light enough that dark eyes and outlines stay clear, plus one dark. Any
 * other colour can be picked as #rrggbb. */
export const COLORS: Record<string, { label: string; hex: string }> = {
  pearl: { label: "Pearl", hex: "#f7f3ee" },
  peach: { label: "Peach", hex: "#ffc9a8" },
  mint: { label: "Mint", hex: "#bfe9d4" },
  sky: { label: "Sky", hex: "#c4dafc" },
  lilac: { label: "Lilac", hex: "#dcccf5" },
  lemon: { label: "Lemon", hex: "#fbeaa0" },
  graphite: { label: "Graphite", hex: "#5f5852" },
};

export const GLOWS: Record<string, { label: string; hex: string }> = {
  amber: { label: "Amber", hex: "#ff8a3d" },
  gold: { label: "Gold", hex: "#f5b041" },
  cyan: { label: "Cyan", hex: "#4fd8ff" },
  lime: { label: "Lime", hex: "#9be15d" },
  pink: { label: "Pink", hex: "#ff6fae" },
  violet: { label: "Violet", hex: "#a78bfa" },
};

export const ACCENTS: Record<string, { label: string; hex: string }> = {
  ember: { label: "Ember", hex: "#c2410c" },
  navy: { label: "Navy", hex: "#1e3a8a" },
  forest: { label: "Forest", hex: "#166534" },
  plum: { label: "Plum", hex: "#7e22ce" },
  rose: { label: "Rose", hex: "#be185d" },
  ink: { label: "Ink", hex: "#292524" },
};

export const FINISHES: Option<Avatar["finish"]>[] = [
  {
    value: "glossy",
    label: "Glossy",
    about: "Shiny vinyl, like a collectible toy",
  },
  { value: "matte", label: "Matte", about: "Soft and chalky" },
  { value: "metallic", label: "Metallic", about: "Brushed metal" },
  {
    value: "pearlescent",
    label: "Pearl",
    about: "Glossy with a colour-shifting sheen",
  },
];
export const BODIES: Option<Avatar["body"]>[] = [
  { value: "round", label: "Round" },
  { value: "capsule", label: "Capsule" },
  { value: "boxy", label: "Boxy" },
  { value: "tall", label: "Tall" },
];
export const HEADS: Option<Avatar["head"]>[] = [
  { value: "sphere", label: "Sphere" },
  { value: "cube", label: "Cube" },
  { value: "dome", label: "Dome" },
  { value: "screen", label: "Screen" },
];
export const EYES: Option<Avatar["eyes"]>[] = [
  { value: "dots", label: "Dots" },
  { value: "visor", label: "Visor" },
  { value: "pixel", label: "Pixel" },
  { value: "sleepy", label: "Sleepy" },
  { value: "star", label: "Stars" },
];
export const MOUTHS: Option<Avatar["mouth"]>[] = [
  { value: "smile", label: "Smile" },
  { value: "open", label: "Open" },
  { value: "line", label: "Line" },
  { value: "none", label: "None" },
];
export const HATS: Option<Avatar["hat"]>[] = [
  { value: "antenna", label: "Antenna" },
  { value: "headphones", label: "Headphones" },
  { value: "cap", label: "Cap" },
  { value: "beanie", label: "Beanie" },
  { value: "crown", label: "Crown" },
  { value: "halo", label: "Halo" },
  { value: "none", label: "Nothing" },
];
export const NECKS: Option<Avatar["neck"]>[] = [
  { value: "none", label: "Nothing" },
  { value: "bowtie", label: "Bow tie" },
  { value: "scarf", label: "Scarf" },
  { value: "medal", label: "Medal" },
];
export const EXTRAS: Option<Avatar["extra"]>[] = [
  { value: "none", label: "Nothing" },
  { value: "glasses", label: "Glasses" },
  { value: "mic", label: "Microphone" },
  { value: "ears", label: "Ears" },
];
export const PERSONALITIES: Option<Avatar["personality"]>[] = [
  {
    value: "cheerful",
    label: "Cheerful",
    about: "Bouncy, and says so with an exclamation mark",
  },
  { value: "calm", label: "Calm", about: "Floats gently and keeps it short" },
  { value: "witty", label: "Witty", about: "Fidgety, with a joke or two" },
  { value: "formal", label: "Formal", about: "Upright and precise" },
];

/** A preset's colour, or the colour itself when it is already #rrggbb. */
export function hexOf(
  colour: string,
  presets: Record<string, { hex: string }>,
  fallback: string,
): string {
  if (/^#[0-9a-f]{6}$/i.test(colour)) return colour.toLowerCase();
  return presets[colour]?.hex ?? fallback;
}

export const bodyHex = (avatar: Avatar) =>
  hexOf(avatar.color, COLORS, "#f7f3ee");
export const glowHex = (avatar: Avatar) => hexOf(avatar.glow, GLOWS, "#ff8a3d");
export const accentHex = (avatar: Avatar) =>
  hexOf(avatar.accent, ACCENTS, "#c2410c");

/** WCAG relative luminance of a #rrggbb colour. */
export function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** The face plate the eyes sit on: near-black, or lighter on a dark body so it still shows. */
export const faceHex = (avatar: Avatar) =>
  luminance(bodyHex(avatar)) < 0.12 ? "#0b0908" : "#17120f";

/** Fill in parts an older saved bot does not have. */
export function complete(avatar: Partial<Avatar> | null | undefined): Avatar {
  const done = {
    ...DEFAULT_AVATAR,
    ...(avatar ?? {}),
    voice: { ...DEFAULT_AVATAR.voice, ...(avatar?.voice ?? {}) },
  } as Avatar;
  // "Scout" was the default name before the companion became James: a bot never renamed is James.
  if (done.name === LEGACY_DEFAULT_NAME) done.name = DEFAULT_AVATAR.name;
  return done;
}

const LEGACY_DEFAULT_NAME = "Scout";

/** A random but always valid bot, for "Surprise me". The name, personality and voice are kept. */
export function surprise(
  current: Avatar,
  pick: <T>(items: T[]) => T = randomItem,
): Avatar {
  const values = <T extends string>(options: Option<T>[]) =>
    options.map((o) => o.value);
  return {
    ...current,
    character: pick(values(CHARACTERS)),
    color: pick(Object.keys(COLORS)),
    glow: pick(Object.keys(GLOWS)),
    accent: pick(Object.values(ACCENTS).map((a) => a.hex)),
    finish: pick(values(FINISHES)),
    body: pick(values(BODIES)),
    head: pick(values(HEADS)),
    eyes: pick(values(EYES)),
    mouth: pick(values(MOUTHS)),
    hat: pick(values(HATS)),
    neck: pick(values(NECKS)),
    extra: pick(values(EXTRAS)),
  };
}

function randomItem<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

/** The signed-in person's bot, or the default one until they choose. */
export function useAvatar(): Avatar {
  const user = useMaybeUser();
  return complete(user?.avatar);
}

/** Save a choice; the cached account updates at once, so every bot on screen changes with it. */
export function useSaveAvatar() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (avatar: Avatar) =>
      unwrap(await api.PUT("/v1/auth/me/avatar", { body: avatar })),
    onSuccess: (user: CurrentUser) => client.setQueryData(keys.me, user),
  });
}
