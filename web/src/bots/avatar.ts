// The assistant bot each person chooses: which character, its name, its colours and what it
// wears. Only these choices are stored (on the account); the bot itself is drawn here.
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { keys } from "../api/queries";
import type { Avatar, CurrentUser } from "../api/types";
import { useMaybeUser } from "../auth/AuthProvider";

export type { Avatar };

export const DEFAULT_AVATAR: Avatar = {
  character: "pod",
  name: "Scout",
  color: "pearl",
  glow: "amber",
  accessory: "antenna",
};

export const CHARACTERS: {
  value: Avatar["character"];
  label: string;
  about: string;
}[] = [
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

/** Body colours: light enough that the dark visor and outlines stay clear, plus one dark. */
export const COLORS: Record<Avatar["color"], { label: string; hex: string }> = {
  pearl: { label: "Pearl", hex: "#f7f3ee" },
  peach: { label: "Peach", hex: "#ffc9a8" },
  mint: { label: "Mint", hex: "#bfe9d4" },
  sky: { label: "Sky", hex: "#c4dafc" },
  graphite: { label: "Graphite", hex: "#5f5852" },
};

export const GLOWS: Record<Avatar["glow"], { label: string; hex: string }> = {
  amber: { label: "Amber", hex: "#ff8a3d" },
  gold: { label: "Gold", hex: "#f5b041" },
  cyan: { label: "Cyan", hex: "#4fd8ff" },
  lime: { label: "Lime", hex: "#9be15d" },
  pink: { label: "Pink", hex: "#ff6fae" },
};

export const ACCESSORIES: { value: Avatar["accessory"]; label: string }[] = [
  { value: "antenna", label: "Antenna" },
  { value: "headphones", label: "Headphones" },
  { value: "bowtie", label: "Bow tie" },
  { value: "none", label: "Nothing" },
];

/** A random but always valid bot, for "Surprise me". The name is kept. */
export function surprise(
  current: Avatar,
  pick: <T>(items: T[]) => T = randomItem,
): Avatar {
  return {
    ...current,
    character: pick(CHARACTERS).value,
    color: pick(Object.keys(COLORS) as Avatar["color"][]),
    glow: pick(Object.keys(GLOWS) as Avatar["glow"][]),
    accessory: pick(ACCESSORIES).value,
  };
}

function randomItem<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

/** The signed-in person's bot, or the default one until they choose. */
export function useAvatar(): Avatar {
  const user = useMaybeUser();
  return { ...DEFAULT_AVATAR, ...(user?.avatar ?? {}) } as Avatar;
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
