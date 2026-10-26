import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EpisodeStatus } from "../api/types";
import { useDoneNotice } from "./useDoneNotice";

function watch(first: EpisodeStatus) {
  return renderHook(({ status }) => useDoneNotice(status, "Tides, episode 2"), {
    initialProps: { status: first },
  });
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    value: state,
    configurable: true,
  });
}

afterEach(() => {
  setVisibility("visible");
  vi.unstubAllGlobals();
  document.title = "Podcast Engine";
});

describe("done notice", () => {
  it("badges the tab title when a running episode finishes", () => {
    document.title = "Podcast Engine";
    const hook = watch("processing");
    hook.rerender({ status: "needs_review" });
    expect(document.title).toBe("✓ Ready for your review · Podcast Engine");
  });

  it("does nothing for an episode that was already finished when opened", () => {
    document.title = "Podcast Engine";
    watch("published");
    expect(document.title).toBe("Podcast Engine");
  });

  it("notifies in the background once allowed", () => {
    const shown: string[] = [];
    class FakeNotification {
      static permission = "granted";
      constructor(title: string) {
        shown.push(title);
      }
    }
    vi.stubGlobal("Notification", FakeNotification);
    setVisibility("hidden");
    const hook = watch("processing");
    hook.rerender({ status: "published" });
    expect(shown).toEqual(["Tides, episode 2: Published"]);
  });
});
