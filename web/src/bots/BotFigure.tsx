import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { canUseWebGL, useReducedMotion } from "../visual/motion";
import { useAvatar, type Avatar } from "./avatar";
import type { BotControl } from "./BotScene";
import type { BotMode } from "./botMode";

// three.js is large: it is fetched when the browser is next idle after sign-in (preloadBots), or
// when a bot is first shown, whichever comes first.
const loadBotScene = () => import("./BotScene");
const BotScene = lazy(loadBotScene);

/** Fetch the bots' 3D code (and the robot model) in the background, so a bot never waits. */
export function preloadBots(): () => void {
  if (!canUseWebGL()) return () => {};
  const load = () =>
    void loadBotScene()
      .then((scene) => scene.preloadRobot())
      .catch(() => {});
  if (typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(load, { timeout: 5000 });
    return () => window.cancelIdleCallback(handle);
  }
  const handle = window.setTimeout(load, 2000);
  return () => window.clearTimeout(handle);
}

export function defaultQuips(name: string): string[] {
  return [
    `Hi! I'm ${name}.`,
    "Beep boop! Tap me again.",
    "Drag me sideways to spin me round.",
    "Every line in your episode comes from a source.",
    "I check each claim before a word is voiced.",
    "Ready when you are!",
  ];
}

function clamp(value: number): number {
  return Math.max(-1, Math.min(1, value));
}

/**
 * The 3D bot in the person's chosen look, or a soft glow while its code loads or where WebGL is
 * missing. With `interactive`, it is a control: it watches the pointer, its eyes widen on hover,
 * a sideways drag spins it, and a tap (or Enter or Space) makes it react and say something, which
 * screen readers hear. Without it, the bot is decoration.
 */
export function BotFigure({
  mode,
  avatar,
  interactive = false,
  quips,
}: {
  mode: BotMode;
  avatar?: Avatar;
  interactive?: boolean;
  quips?: string[];
}) {
  const mine = useAvatar();
  const bot = avatar ?? mine;
  const reduced = useReducedMotion();
  const [webgl] = useState(canUseWebGL);
  const control = useRef<BotControl>({
    lookX: 0,
    lookY: 0,
    hovering: false,
    spin: 0,
    pokes: 0,
  });
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; moved: number; at: number } | null>(null);
  const said = useRef(0);
  const [bubble, setBubble] = useState<string | null>(null);

  // Follow the pointer anywhere on the page, not only over the bot.
  useEffect(() => {
    if (!interactive || reduced) return;
    const onMove = (event: PointerEvent) => {
      const box = stage.current?.getBoundingClientRect();
      if (!box) return;
      control.current.lookX = clamp(
        (event.clientX - (box.left + box.width / 2)) / (window.innerWidth / 2),
      );
      control.current.lookY = clamp(
        -(event.clientY - (box.top + box.height / 2)) /
          (window.innerHeight / 2),
      );
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, [interactive, reduced]);

  useEffect(() => {
    if (!bubble) return;
    const timer = window.setTimeout(() => setBubble(null), 2800);
    return () => window.clearTimeout(timer);
  }, [bubble]);

  function poke() {
    control.current.pokes += 1;
    const lines = quips ?? defaultQuips(bot.name);
    setBubble(lines[said.current++ % lines.length]);
  }

  function onPointerMove(event: ReactPointerEvent) {
    const held = drag.current;
    if (!held) return;
    const dx = event.clientX - held.x;
    const now = performance.now();
    held.moved += Math.abs(dx);
    held.x = event.clientX;
    if (!reduced)
      control.current.spin =
        (dx / (Math.max(16, now - held.at) / 1000)) * 0.012;
    held.at = now;
  }

  const scene = webgl ? (
    <Suspense fallback={<div className="dock-bot-placeholder" />}>
      <BotScene mode={mode} still={reduced} avatar={bot} control={control} />
    </Suspense>
  ) : (
    <div className="dock-bot-placeholder" />
  );
  if (!interactive) return scene;
  return (
    <div
      ref={stage}
      className="bot-stage"
      role="button"
      tabIndex={0}
      aria-label={`${bot.name}, your assistant. Press to say hi.`}
      onPointerEnter={() => {
        control.current.hovering = true;
      }}
      onPointerLeave={() => {
        control.current.hovering = false;
        drag.current = null;
      }}
      onPointerDown={(event) => {
        drag.current = { x: event.clientX, moved: 0, at: performance.now() };
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={onPointerMove}
      onPointerUp={() => {
        const held = drag.current;
        drag.current = null;
        if (held && held.moved < 6) poke(); // a tap, not a drag
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          poke();
        }
      }}
    >
      {scene}
      {bubble ? (
        <span className="bot-bubble" role="status">
          {bubble}
        </span>
      ) : null}
    </div>
  );
}
