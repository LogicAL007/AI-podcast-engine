import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { useAskAssistant } from "../api/queries";
import type { AssistantAnswer } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useRememberedFlag } from "../hooks/useRememberedFlag";
import {
  useAssistantState,
  type AssistantPage,
  type BotAction,
  type Nudge,
  type PageAssist,
} from "./assistant";
import { useAvatar } from "./avatar";
import { AvatarFace, type FaceMood } from "./AvatarFace";
import { useJamesSettings } from "./jamesSettings";
import { canSpeak, speak } from "./speech";
import { Tour } from "./Tour";
import { useSpeechInput } from "./voiceInput";

const NUDGE_MS = 8000;
const TYPING_RETRY_MS = 1000;

const PLACES: Record<AssistantPage, string> = {
  welcome: "getting started",
  shows: "your shows",
  new_show: "a new show",
  show: "this show",
  episode: "this episode",
  voices: "the Voice studio",
  new_voice: "a new voice",
  companion: "your companion",
  other: "this page",
};

function prefersStill(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function typing(): boolean {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  return (
    el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)
  );
}

/** What makes the face feel alive at rest: it blinks now and then, and its eyes follow the
 * pointer. Holds still for reduced motion. */
function useAlive(target: RefObject<HTMLElement | null>) {
  const [blink, setBlink] = useState(false);
  const [gaze, setGaze] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (prefersStill()) return;
    let timer = 0;
    const next = () => {
      timer = window.setTimeout(
        () => {
          setBlink(true);
          window.setTimeout(() => setBlink(false), 140);
          next();
        },
        2500 + Math.random() * 3500,
      );
    };
    next();
    let frame = 0;
    const follow = (event: PointerEvent) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const box = target.current?.getBoundingClientRect();
        if (!box) return;
        const clamp = (v: number) => Math.max(-1, Math.min(1, v));
        setGaze({
          x: clamp((event.clientX - (box.left + box.width / 2)) / 420),
          y: clamp((event.clientY - (box.top + box.height / 2)) / 320),
        });
      });
    };
    window.addEventListener("pointermove", follow);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointermove", follow);
      cancelAnimationFrame(frame);
    };
  }, [target]);

  return { blink, gaze };
}

interface Message {
  from: "me" | "james";
  text: string;
  actions?: BotAction[];
}

/** The conversation with James about the page you are on, typed or spoken. */
function useConversation(
  assist: PageAssist,
  resolve: (id: string) => BotAction | undefined,
  onAnswer: (text: string) => void,
) {
  const ask = useAskAssistant();
  const [messages, setMessages] = useState<Message[]>([]);
  const [left, setLeft] = useState<number | null>(null);

  const send = useCallback(
    (question: string) => {
      const text = question.trim();
      if (!text || ask.isPending) return;
      setMessages((m) => [...m, { from: "me", text }]);
      ask.mutate(
        {
          question: text,
          page: assist.page,
          episode_id: assist.episodeId ?? null,
          show_id: assist.showId ?? null,
        },
        {
          onSuccess: (answer: AssistantAnswer) => {
            const actions = answer.actions
              .map((id) => resolve(id))
              .filter((a): a is BotAction => a !== undefined);
            setMessages((m) => [
              ...m,
              { from: "james", text: answer.answer, actions },
            ]);
            setLeft(answer.remaining);
            onAnswer(answer.answer);
          },
          onError: (error) => {
            const reply =
              error instanceof ApiError && error.status === 429
                ? "That's all my questions for this hour. Ask me again a little later."
                : "Sorry, I couldn't answer just now. Try again in a moment.";
            setMessages((m) => [...m, { from: "james", text: reply }]);
            onAnswer(reply);
          },
        },
      );
    },
    [ask, assist.page, assist.episodeId, assist.showId, resolve, onAnswer],
  );

  return { messages, send, thinking: ask.isPending, left };
}

function ActionButtons({
  actions,
  onAction,
}: {
  actions: BotAction[];
  onAction: (action: BotAction) => void;
}) {
  if (!actions.length) return null;
  return (
    <div className="james-actions">
      {actions.map((action) => (
        <button
          key={action.id}
          type="button"
          className="choice-pill"
          onClick={() => onAction(action)}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}

const MicIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 20 20"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    aria-hidden="true"
  >
    <rect x="7.5" y="2.5" width="5" height="9" rx="2.5" />
    <path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" />
  </svg>
);

/** The side panel: what James is looking at, the conversation, and talking to him. */
function JamesPanel({
  assist,
  name,
  opening,
  standing,
  resolve,
  onAction,
  onTour,
  onClose,
  speakReplies,
  talk,
  setTalk,
}: {
  assist: PageAssist;
  name: string;
  opening: string;
  standing: BotAction[];
  resolve: (id: string) => BotAction | undefined;
  onAction: (action: BotAction) => void;
  onTour: (() => void) | null;
  onClose: () => void;
  speakReplies: boolean;
  talk: number;
  setTalk: (open: number) => void;
}) {
  const avatar = useAvatar();
  const titleId = useId();
  const inputId = useId();
  const [draft, setDraft] = useState("");
  const [voice, setVoice] = useState(false);
  const [spoken, setSpoken] = useState("");
  const stop = useRef<() => void>(() => {});
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  const onAnswer = useCallback(
    (text: string) => {
      stop.current();
      if ((voiceRef.current || speakReplies) && canSpeak())
        stop.current = speak(text, avatar.voice, setTalk);
      if (voiceRef.current) setSpoken(text);
    },
    [avatar.voice, speakReplies, setTalk],
  );
  const chat = useConversation(assist, resolve, onAnswer);
  const mic = useSpeechInput((text) => chat.send(text));

  useEffect(() => {
    input.current?.focus();
    return () => stop.current();
  }, []);
  useEffect(() => {
    log.current?.scrollTo?.({ top: log.current.scrollHeight });
  }, [chat.messages, chat.thinking]);

  function talkToJames() {
    stop.current();
    setTalk(0);
    setSpoken("");
    setVoice(true);
    mic.start();
  }

  function typeInstead() {
    mic.cancel();
    stop.current();
    setTalk(0);
    setVoice(false);
    requestAnimationFrame(() => input.current?.focus());
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    chat.send(draft);
    setDraft("");
  }

  const voiceMood: FaceMood = mic.listening
    ? "listening"
    : chat.thinking
      ? "working"
      : talk > 0
        ? "speaking"
        : "idle";

  return (
    <aside className="james-panel" aria-labelledby={titleId}>
      <header className="james-panel-head">
        <AvatarFace
          avatar={avatar}
          size={40}
          mood={talk > 0 ? "speaking" : "idle"}
          mouth={talk}
        />
        <div className="james-panel-title">
          <h2 id={titleId}>{name}</h2>
          <p className="muted">
            Looking at <b>{assist.context ?? PLACES[assist.page]}</b>
          </p>
        </div>
        <button
          type="button"
          className="james-icon-button"
          aria-label={`Close ${name} (Esc)`}
          onClick={onClose}
        >
          <svg width="14" height="14" viewBox="0 0 12 12" aria-hidden="true">
            <path
              d="M2 2l8 8M10 2l-8 8"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>

      {voice ? (
        <div className="james-voice">
          <div className={`james-voice-face james-voice-${voiceMood}`}>
            <AvatarFace
              avatar={avatar}
              size={168}
              mood={voiceMood}
              mouth={talk}
            />
          </div>
          <p className="james-voice-state" aria-live="polite">
            {mic.listening
              ? "Listening"
              : chat.thinking
                ? "Thinking"
                : talk > 0
                  ? "Speaking"
                  : mic.problem
                    ? mic.problem
                    : "Tap to talk"}
          </p>
          <p className="james-voice-words" aria-live="polite">
            {mic.listening || chat.thinking
              ? mic.heard
                ? `“${mic.heard}”`
                : ""
              : spoken}
          </p>
          {mic.listening ? (
            <button
              type="button"
              className="james-talk-button"
              aria-label="Stop listening"
              onClick={mic.stop}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 18 18"
                aria-hidden="true"
              >
                <rect
                  x="4"
                  y="4"
                  width="10"
                  height="10"
                  rx="2"
                  fill="currentColor"
                />
              </svg>
            </button>
          ) : (
            <button
              type="button"
              className="james-talk-button"
              aria-label={`Talk to ${name}`}
              disabled={chat.thinking}
              onClick={talkToJames}
            >
              <MicIcon />
            </button>
          )}
          <button type="button" className="link-button" onClick={typeInstead}>
            Type instead
          </button>
        </div>
      ) : (
        <>
          <div
            ref={log}
            className="james-log"
            role="log"
            aria-live="polite"
            aria-label={`Conversation with ${name}`}
          >
            <div className="james-message james-from-james">
              <span className="sr-only">{name}: </span>
              <p>{opening}</p>
              <ActionButtons
                actions={[
                  ...standing,
                  ...(onTour
                    ? [
                        {
                          id: "start_tour",
                          label: "Show me around",
                          run: onTour,
                        },
                      ]
                    : []),
                ]}
                onAction={onAction}
              />
            </div>
            {chat.messages.map((message, index) => (
              <div
                key={index}
                className={`james-message james-from-${message.from}`}
              >
                <span className="sr-only">
                  {message.from === "me" ? "You:" : `${name}:`}{" "}
                </span>
                <p>{message.text}</p>
                {message.actions?.length ? (
                  <div className="james-action-card">
                    <ActionButtons
                      actions={message.actions}
                      onAction={onAction}
                    />
                  </div>
                ) : null}
              </div>
            ))}
            {chat.thinking ? (
              <div
                className="james-message james-from-james"
                aria-label={`${name} is thinking`}
              >
                <span className="progress-dots" aria-hidden="true">
                  <span>.</span>
                  <span>.</span>
                  <span>.</span>
                </span>
              </div>
            ) : null}
          </div>
          {chat.messages.length === 0 && assist.questions?.length ? (
            <div className="james-suggestions" aria-label="Suggested questions">
              {assist.questions.slice(0, 3).map((question) => (
                <button
                  key={question}
                  type="button"
                  className="choice-pill"
                  onClick={() => chat.send(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          ) : null}
          <form className="james-composer" onSubmit={submit}>
            <label htmlFor={inputId} className="sr-only">
              Ask {name}
            </label>
            <input
              ref={input}
              id={inputId}
              value={draft}
              maxLength={500}
              placeholder={`Ask ${name}…`}
              autoComplete="off"
              onChange={(event) => setDraft(event.target.value)}
            />
            {mic.supported ? (
              <button
                type="button"
                className="james-icon-button james-mic"
                aria-label={`Talk to ${name}`}
                onClick={talkToJames}
              >
                <MicIcon />
              </button>
            ) : null}
            <button
              type="submit"
              className="james-icon-button james-send"
              aria-label="Send"
              disabled={!draft.trim() || chat.thinking}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M10 16V4M5 9l5-5 5 5" />
              </svg>
            </button>
          </form>
          {chat.left !== null ? (
            <p className="james-note muted">
              {chat.left} question{chat.left === 1 ? "" : "s"} left this hour
            </p>
          ) : null}
        </>
      )}
    </aside>
  );
}

/**
 * James, the companion, on every page that tells him what is going on (useAssistant). He rests
 * small in a corner (breathing, blinking, eyes on the pointer), says one short thing at a pause
 * (an episode finishing or failing, never while you type, at most once a visit), and opens a
 * side panel on a click or ⌘J for questions, typed or spoken. Actions are the page's own, and
 * anything that spends quota or cannot be undone asks first.
 */
export function James() {
  const state = useAssistantState();
  const assist = state?.assist ?? null;
  const avatar = useAvatar();
  const navigate = useNavigate();
  const settings = useJamesSettings();
  const button = useRef<HTMLButtonElement>(null);
  const alive = useAlive(button);
  const [open, setOpen] = useState(false);
  const [nudge, setNudge] = useState<Nudge | null>(null);
  const [talk, setTalk] = useState(0);
  const [touring, setTouring] = useState(false);
  const [asking, setAsking] = useState<BotAction | null>(null);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const [hintSeen, setHintSeen] = useRememberedFlag(
    `pe.hint.${assist?.moment ?? "none"}`,
  );
  const [, setToured] = useRememberedFlag(`pe.tour.${assist?.page ?? "none"}`);
  const baseline = useRef<{ key: string; id: string | undefined } | null>(null);
  const nudgedKey = useRef<string | null>(null);
  const hovering = useRef(false);
  const panelWasOpen = useRef(false);

  // ⌘J (Ctrl+J) opens and closes James anywhere; Escape closes him.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        setNudge(null);
        setOpen((current) => !current);
      } else if (event.key === "Escape") {
        setOpen(false);
        setNudge(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Closing the panel puts focus back on James.
  useEffect(() => {
    if (panelWasOpen.current && !open) button.current?.focus();
    panelWasOpen.current = open;
  }, [open]);

  // A new place: whatever is already so there is the baseline, not news.
  const key = assist?.key;
  const nudgeId = assist?.nudge?.id;
  const quiet =
    settings.off ||
    settings.chattiness === "quiet" ||
    settings.snoozedUntil > 0;
  useEffect(() => {
    if (!assist) return;
    if (!baseline.current || baseline.current.key !== assist.key) {
      baseline.current = { key: assist.key, id: nudgeId };
      nudgedKey.current = null;
      setNudge(null);
      // Chatty: a first-time tip on arrival, once.
      if (
        settings.chattiness === "chatty" &&
        assist.hint &&
        !hintSeen &&
        !quiet
      ) {
        const tip: Nudge = { id: `hint:${assist.moment}`, text: assist.hint };
        const timer = window.setTimeout(() => setNudge(tip), 1200);
        return () => window.clearTimeout(timer);
      }
      return;
    }
    if (!nudgeId || nudgeId === baseline.current.id) return;
    baseline.current.id = nudgeId;
    if (quiet || open || nudgedKey.current === assist.key || !assist.nudge)
      return;
    const news = assist.nudge;
    nudgedKey.current = assist.key;
    // Never while someone is typing: wait for them to stop.
    let timer = 0;
    const show = () => {
      if (typing()) timer = window.setTimeout(show, TYPING_RETRY_MS);
      else setNudge(news);
    };
    show();
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nudgeId]);

  // A nudge fades after a few seconds, unless the pointer or focus is on it.
  useEffect(() => {
    if (!nudge) return;
    const timer = window.setInterval(() => {
      if (!hovering.current) setNudge(null);
    }, NUDGE_MS);
    return () => window.clearInterval(timer);
  }, [nudge]);

  if (!assist || settings.off) return null;

  const pageActions = state?.actions.current ?? [];
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
  const startTour = assist.tour?.length
    ? () => {
        setOpen(false);
        setTouring(true);
      }
    : null;
  const resolve = (id: string): BotAction | undefined =>
    pageActions.find((a) => a.id === id) ??
    (id === "start_tour" && startTour
      ? { id, label: "Show me around", run: startTour }
      : everywhere.find((a) => a.id === id));

  async function run(action: BotAction) {
    setRunning(true);
    setFailure(null);
    const live =
      state?.actions.current.find((a) => a.id === action.id) ?? action;
    try {
      await live.run();
      setAsking(null);
    } catch (error) {
      setFailure(error);
      setOpen(true);
    } finally {
      setRunning(false);
    }
  }

  function choose(action: BotAction) {
    setNudge(null);
    if (action.confirm) {
      setFailure(null);
      setAsking(action);
    } else void run(action);
  }

  function openPanel() {
    setNudge(null);
    setOpen(true);
    if (assist?.hint) setHintSeen(true);
  }

  const working = assist.mode === "working" || assist.moment === "factcheck";
  const mood: FaceMood =
    settings.snoozedUntil > 0
      ? "sleeping"
      : talk > 0
        ? "speaking"
        : nudge?.tone === "problem"
          ? "concerned"
          : nudge?.tone === "good" || assist.mode === "celebrating"
            ? "happy"
            : working
              ? "working"
              : "idle";
  const opening = assist.hint && !hintSeen ? assist.hint : assist.line;
  const nudgeAction = nudge?.action ? resolve(nudge.action) : undefined;
  const corner = settings.corner === "left" ? "james-left" : "james-right";

  return (
    <div className={`james ${corner}`}>
      {open ? (
        <JamesPanel
          key={assist.key}
          assist={assist}
          name={avatar.name}
          opening={opening}
          standing={pageActions.filter((a) => !a.hidden)}
          resolve={resolve}
          onAction={choose}
          onTour={startTour}
          onClose={() => setOpen(false)}
          speakReplies={settings.speakReplies}
          talk={talk}
          setTalk={setTalk}
        />
      ) : null}

      {nudge && !open ? (
        <div
          className={`james-nudge${nudge.tone === "problem" ? " james-nudge-problem" : ""}`}
          role="status"
          onPointerEnter={() => (hovering.current = true)}
          onPointerLeave={() => (hovering.current = false)}
          onFocus={() => (hovering.current = true)}
          onBlur={() => (hovering.current = false)}
        >
          <div className="james-nudge-row">
            <button
              type="button"
              className="james-nudge-text"
              onClick={openPanel}
            >
              {nudge.text}
            </button>
            <button
              type="button"
              className="james-icon-button"
              aria-label="Dismiss"
              onClick={() => setNudge(null)}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 12 12"
                aria-hidden="true"
              >
                <path
                  d="M2 2l8 8M10 2l-8 8"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
          {nudgeAction ? (
            <div>
              <button
                type="button"
                className="btn btn-primary james-nudge-action"
                onClick={() => choose(nudgeAction)}
              >
                {nudgeAction.label}
              </button>
            </div>
          ) : null}
          <span className="james-nudge-timer" aria-hidden="true" />
        </div>
      ) : null}

      {failure && !asking && !open ? (
        <p className="james-error" role="alert">
          {failure instanceof Error
            ? failure.message
            : "That did not work. Try again."}
        </p>
      ) : null}

      <button
        ref={button}
        type="button"
        className={`james-button james-mood-${mood}`}
        aria-label={`${open ? "Close" : "Open"} ${avatar.name} (⌘J)`}
        aria-expanded={open}
        data-tip={`${avatar.name} · ⌘J`}
        onClick={() => (open ? setOpen(false) : openPanel())}
      >
        <span className="james-body">
          <AvatarFace
            avatar={avatar}
            size={60}
            gaze={mood === "sleeping" ? undefined : alive.gaze}
            blink={alive.blink}
            mood={mood}
            mouth={talk}
          />
        </span>
        {working ? <span className="james-ring" aria-hidden="true" /> : null}
      </button>

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
    </div>
  );
}
