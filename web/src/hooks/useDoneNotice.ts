import { useEffect, useRef, useState } from "react";

import type { EpisodeStatus } from "../api/types";

const RUNNING: EpisodeStatus[] = ["queued", "processing"];
const NOTICE: Partial<Record<EpisodeStatus, string>> = {
  needs_review: "Ready for your review",
  published: "Published",
  failed: "Stopped with an error",
};

export type NotifyPermission = NotificationPermission | "unsupported";

function permissionNow(): NotifyPermission {
  return typeof window !== "undefined" && "Notification" in window
    ? Notification.permission
    : "unsupported";
}

/**
 * Tells the creator when an episode they are watching finishes. The tab title gets a badge
 * until they look at the tab again, and, if they allowed it, a browser notification appears
 * while the tab is in the background. Nothing is asked until they press "Notify me".
 */
export function useDoneNotice(status: EpisodeStatus, title: string) {
  const previous = useRef(status);
  const [permission, setPermission] = useState<NotifyPermission>(permissionNow);

  useEffect(() => {
    const was = previous.current;
    previous.current = status;
    const notice = NOTICE[status];
    if (!notice || !RUNNING.includes(was)) return;

    const original = document.title;
    document.title = `✓ ${notice} · ${original}`;
    const restore = () => {
      if (document.visibilityState === "visible") document.title = original;
    };
    // Already looking at it: show the badge briefly; otherwise keep it until they come back.
    const timer =
      document.visibilityState === "visible"
        ? window.setTimeout(restore, 6000)
        : 0;
    document.addEventListener("visibilitychange", restore);

    if (
      permissionNow() === "granted" &&
      document.visibilityState === "hidden"
    ) {
      try {
        new Notification(`${title}: ${notice}`, {
          icon: "/logo-mark.svg",
          tag: title,
        });
      } catch {
        // Some browsers allow notifications only from a service worker; the title badge remains.
      }
    }
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", restore);
      document.title = original;
    };
  }, [status, title]);

  async function ask() {
    if (permissionNow() === "unsupported") return;
    setPermission(await Notification.requestPermission());
  }

  return { permission, ask };
}
