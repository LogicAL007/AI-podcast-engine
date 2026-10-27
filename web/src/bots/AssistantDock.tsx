import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { useRememberedFlag } from "../hooks/useRememberedFlag";
import { GlassPanel } from "../visual/GlassPanel";
import { useAssistantState, type BotAction } from "./assistant";
import { useAvatar } from "./avatar";
import { AvatarFace } from "./AvatarFace";
import { BotFigure } from "./BotFigure";
import { ChatPanel } from "./ChatPanel";
import { canSpeak, speak } from "./speech";
import { Tour } from "./Tour";

/** Turning the assistant off everywhere (from the Companion page) is remembered per device. */
export const ASSISTANT_OFF = "pe.assistant.off";

/**
 * The assistant, on every page that tells it what is going on (useAssistant): a floating glass
 * card with the bot, its line (or, the first time, a hint until "Got it"), buttons for the next
 * steps, a chat, a guided tour, and, when turned on, its voice. Closing it is remembered per
 * place, and a small bot button brings it back. Its actions are the page's own: anything that
 * spends quota or cannot be undone asks first.
 */
export function AssistantDock() {
  const state = useAssistantState();
  const assist = state?.assist ?? null;
  const avatar = useAvatar();
  const navigate = useNavigate();
  const [off] = useRememberedFlag(ASSISTANT_OFF);
  const [closed, setClosed] = useRememberedFlag(
    `pe.dock.closed.${assist?.key ?? "none"}`,
  );
  const [hintSeen, setHintSeen] = useRememberedFlag(
    `pe.hint.${assist?.moment ?? "none"}`,
  );
  const [, setToured] = useRememberedFlag(`pe.tour.${assist?.page ?? "none"}`);
  const [speaking, setSpeaking] = useRememberedFlag("pe.assistant.speak");
  const [chatting, setChatting] = useState(false);
  const [touring, setTouring] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [talk, setTalk] = useState(0);
  const [asking, setAsking] = useState<BotAction | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const stop = useRef<() => void>(() => {});

  // A new place starts with the chat folded away.
  const key = assist?.key;
  useEffect(() => {
    setChatting(false);
    setTouring(false);
  }, [key]);

  const say = useCallback(
    (text: string) => {
      stop.current();
      if (speaking && canSpeak())
        stop.current = speak(text, avatar.voice, setTalk);
    },
    [speaking, avatar.voice],
  );
  const showsHint = Boolean(assist?.hint) && !hintSeen;
  const text = assist
    ? showsHint
      ? (assist.hint as string)
      : assist.line
    : "";
  useEffect(() => {
    if (text && !closed && !off) say(text);
    return () => stop.current();
  }, [text, closed, off, say]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") stop.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!assist || off) return null;

  const pageActions = state?.actions.current ?? [];
  const tourAction: BotAction | null = assist.tour?.length
    ? { id: "start_tour", label: "Show me around", run: () => setTouring(true) }
    : null;
  const everywhere: BotAction[] = [
    { id: "new_show", label: "New show", run: () => navigate("/shows/new") },
    {
      id: "add_voice",
      label: "Add a voice",
      run: () => navigate("/voices/new"),
    },
    {
      id: "open_voices",
      label: "Voice studio",
      run: () => navigate("/voices"),
    },
    {
      id: "open_companion",
      label: "Customise me",
      run: () => navigate("/companion"),
    },
  ];
  const resolve = (id: string) =>
    pageActions.find((a) => a.id === id) ??
    (id === "start_tour"
      ? (tourAction ?? undefined)
      : everywhere.find((a) => a.id === id));

  async function run(action: BotAction) {
    setRunning(true);
    setFailure(null);
    // The page's latest version of the action (its mutation may have changed since this render).
    const live =
      state?.actions.current.find((a) => a.id === action.id) ?? action;
    try {
      await live.run();
      setAsking(null);
    } catch (error) {
      setFailure(error);
    } finally {
      setRunning(false);
    }
  }
  function choose(action: BotAction) {
    if (action.confirm) {
      setFailure(null);
      setAsking(action);
    } else void run(action);
  }

  if (closed) {
    return (
      <button
        type="button"
        className="dock-reopen"
        onClick={() => setClosed(false)}
        aria-label="Show the assistant"
      >
        <AvatarFace avatar={avatar} />
      </button>
    );
  }

  const buttons = [
    ...pageActions.filter((a) => !a.hidden),
    ...(tourAction ? [tourAction] : []),
  ];
  return (
    <aside
      className={chatting ? "assistant-dock dock-chatting" : "assistant-dock"}
      aria-label="Assistant"
    >
      <GlassPanel radius={26}>
        <div className="dock-inner">
          <div className="dock-bot">
            <BotFigure
              mode={thinking ? "reviewing" : assist.mode}
              interactive
              talk={talk}
            />
          </div>
          <div className="dock-text">
            <span className="dock-name" aria-hidden="true">
              {avatar.name}
            </span>
            {showsHint ? (
              <>
                <p className="dock-hint">{assist.hint}</p>
                <button
                  type="button"
                  className="link-button dock-got-it"
                  onClick={() => setHintSeen(true)}
                >
                  Got it
                </button>
              </>
            ) : (
              <span className="dock-line">{assist.line}</span>
            )}
            {buttons.length ? (
              <div className="dock-actions">
                {buttons.map((action) => (
                  <button
                    key={action.id}
                    type="button"
                    className="choice-pill"
                    onClick={() => choose(action)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            ) : null}
            {failure && !asking ? (
              <p className="dock-error" role="alert">
                {failure instanceof Error
                  ? failure.message
                  : "That did not work. Try again."}
              </p>
            ) : null}
            <div className="dock-tools">
              <button
                type="button"
                className="link-button"
                aria-expanded={chatting}
                onClick={() => setChatting(!chatting)}
              >
                {chatting ? "Hide chat" : `Ask ${avatar.name}`}
              </button>
              {canSpeak() ? (
                <button
                  type="button"
                  className="link-button"
                  aria-pressed={speaking}
                  onClick={() => {
                    if (speaking) stop.current();
                    setSpeaking(!speaking);
                  }}
                >
                  {speaking ? "Stop reading aloud" : "Read aloud"}
                </button>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            className="dock-close"
            onClick={() => {
              stop.current();
              setClosed(true);
            }}
            aria-label="Hide the assistant"
          >
            ×
          </button>
        </div>
        {chatting ? (
          <ChatPanel
            assist={assist}
            name={avatar.name}
            resolve={resolve}
            onAction={choose}
            onAnswer={say}
            onThinking={setThinking}
          />
        ) : null}
      </GlassPanel>
      {touring && assist.tour ? (
        <Tour
          steps={assist.tour}
          onClose={(finished) => {
            setTouring(false);
            if (finished) setToured(true);
          }}
        />
      ) : null}
      <ConfirmDialog
        open={asking !== null}
        title={asking?.confirm?.title ?? ""}
        confirmLabel={asking?.confirm?.confirmLabel ?? "OK"}
        danger={asking?.confirm?.danger}
        busy={running}
        error={failure}
        onClose={() => setAsking(null)}
        onConfirm={() => asking && void run(asking)}
      >
        {asking?.confirm?.body}
      </ConfirmDialog>
    </aside>
  );
}
