import { useCallback, useEffect, useState } from "react";

import { useRememberedFlag } from "../hooks/useRememberedFlag";

// How the companion behaves, remembered in this browser (like the rest of the companion's
// per-device choices). Storage can be missing or blocked: then the defaults apply.

/** Turning the companion off everywhere (from the Companion page). */
export const ASSISTANT_OFF = "pe.assistant.off";
/** Answers read out loud. */
export const SPEAK_REPLIES = "pe.assistant.speak";

export type Chattiness = "quiet" | "helpful" | "chatty";
export type Corner = "right" | "left";

const KEYS = {
  chattiness: "pe.james.chattiness",
  corner: "pe.james.corner",
  snooze: "pe.james.snooze",
} as const;
const CHANGED = "pe-value-changed";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the value lasts until the page reloads.
  }
  window.dispatchEvent(new CustomEvent(CHANGED, { detail: { key, value } }));
}

function useRememberedValue(
  key: string,
): [string | null, (value: string | null) => void] {
  const [value, setValue] = useState(() => read(key));
  useEffect(() => {
    const follow = (event: Event) => {
      const { detail } = event as CustomEvent<{
        key: string;
        value: string | null;
      }>;
      if (detail.key === key) setValue(detail.value);
    };
    window.addEventListener(CHANGED, follow);
    return () => window.removeEventListener(CHANGED, follow);
  }, [key]);
  const set = useCallback(
    (next: string | null) => {
      setValue(next);
      write(key, next);
    },
    [key],
  );
  return [value, set];
}

/** The end of today, local time: "rest of today" snoozes until then. */
export function endOfToday(now = new Date()): number {
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  return end.getTime();
}

export function useJamesSettings() {
  const [chattiness, setChattiness] = useRememberedValue(KEYS.chattiness);
  const [corner, setCorner] = useRememberedValue(KEYS.corner);
  const [snooze, setSnooze] = useRememberedValue(KEYS.snooze);
  const [off, setOff] = useRememberedFlag(ASSISTANT_OFF);
  const [speakReplies, setSpeakReplies] = useRememberedFlag(SPEAK_REPLIES);
  const snoozedUntil = Number(snooze) || 0;
  const [now, setNow] = useState(() => Date.now());

  // A snooze ends by itself: check again when it should be over.
  useEffect(() => {
    if (snoozedUntil <= Date.now()) return;
    const timer = window.setTimeout(
      () => setNow(Date.now()),
      snoozedUntil - Date.now() + 50,
    );
    return () => window.clearTimeout(timer);
  }, [snoozedUntil]);

  return {
    chattiness: (chattiness as Chattiness | null) ?? "helpful",
    setChattiness: (value: Chattiness) => setChattiness(value),
    corner: (corner as Corner | null) ?? "right",
    setCorner: (value: Corner) => setCorner(value),
    snoozedUntil: snoozedUntil > now ? snoozedUntil : 0,
    snoozeUntil: (until: number | null) => {
      setNow(Date.now());
      setSnooze(until ? String(until) : null);
    },
    off,
    setOff,
    speakReplies,
    setSpeakReplies,
  };
}
