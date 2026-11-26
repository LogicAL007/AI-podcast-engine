import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError, API_BASE } from "../../api/client";
import {
  useCreateSpeech,
  useSpeechClip,
  useSpeechEngine,
  useVoices,
} from "../../api/queries";
import type { SpeechCreate, SpeechVoice, VoiceEffects } from "../../api/types";
import { useAssistant } from "../../bots/assistant";
import { messageOf } from "../../components/Alert";
import { Button } from "../../components/Button";
import { SelectField, TextArea } from "../../components/Field";
import { EffectPicker, NATURAL } from "./effects";
import { clock, useClipPlayer } from "./playback";
import { VoiceOctagon, type OctagonState } from "./VoiceOctagon";

const OFFLINE_AFTER_MS = 20_000;
const STYLES: Record<string, string> = {
  neutral: "Neutral",
  warm: "Warm",
  curious: "Curious",
  excited: "Excited",
  thoughtful: "Thoughtful",
  amused: "Amused",
  serious: "Serious",
};

/** The voice picker's value ("recorded:<id>" or "engine:<host>") as a voice. */
export function voiceOf(key: string): SpeechVoice {
  const [kind, value] = key.split(":");
  return kind === "recorded"
    ? { kind: "recorded", voice_id: value }
    : { kind: "engine", host: value as "Alex" };
}

function untilLabel(retryAfter: number | null): string {
  if (!retryAfter) return "Try again later";
  const at = new Date(Date.now() + retryAfter * 1000);
  return `Try again at ${at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

/** The Type to speech tab: type a line, hear it in one of your voices with an effect. */
export function SpeakPage() {
  const [params] = useSearchParams();
  const engine = useSpeechEngine();
  const voices = useVoices();
  const create = useCreateSpeech();

  const [text, setText] = useState("");
  const [voice, setVoice] = useState("");
  const [style, setStyle] = useState("neutral");
  const [effects, setEffects] = useState<VoiceEffects>(NATURAL);
  const [clipId, setClipId] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [lastRequest, setLastRequest] = useState<SpeechCreate | null>(null);
  const clip = useSpeechClip(clipId);
  const ready = clip.data?.status === "done" ? (clip.data.audio ?? null) : null;
  const player = useClipPlayer(ready, true);

  const recorded = engine.data?.recorded_voices
    ? (voices.data?.items ?? [])
    : [];
  const options = [
    ...recorded.map((v) => ({
      value: `recorded:${v.voice_id}`,
      label: v.name,
    })),
    ...(engine.data?.engine_voices ?? []).map((v) => ({
      value: `engine:${v.host}`,
      label: v.host,
    })),
  ];
  const wanted = params.get("voice");

  // The voice from "Try it", else the first one there is.
  useEffect(() => {
    if (voice || options.length === 0) return;
    const preferred = wanted ? `recorded:${wanted}` : "";
    setVoice(
      options.some((o) => o.value === preferred) ? preferred : options[0].value,
    );
  }, [options, voice, wanted]);

  // A clip still queued after 20 s means the voice engine is not running.
  const status = clip.data?.status;
  useEffect(() => {
    setOffline(false);
    if (status !== "queued") return;
    const timer = window.setTimeout(() => setOffline(true), OFFLINE_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [status, clipId]);

  useAssistant({
    page: "voices",
    key: "speak",
    moment: "voices",
    mode: "greeting",
    line: "Type a line and hear it in your voice.",
    hint: "Pick a voice, a style and an effect, then Speak. Effects never use quota.",
    questions: ["Do effects use my quota?"],
  });

  function send(request: SpeechCreate) {
    setLastRequest(request);
    create.mutate(request, { onSuccess: (made) => setClipId(made.clip_id) });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || !voice) return;
    send({
      text,
      voice: voiceOf(voice),
      delivery: style as SpeechCreate["delivery"],
      effects,
    });
  }

  const limited =
    create.error instanceof ApiError && create.error.status === 429
      ? create.error
      : null;
  let state: OctagonState = "idle";
  let heading = "Output";
  let note: string | null = "Your clip plays here";
  if (create.isPending || status === "queued" || status === "working") {
    state = offline ? "off" : "waiting";
    heading = offline ? "Engine offline" : "Preparing";
    note = offline ? "Starts when it's back" : "Preparing the voice…";
  } else if (limited) {
    state = "off";
    heading = "Limit reached";
    note = untilLabel(limited.retryAfter);
  } else if (create.error || status === "failed") {
    state = "error";
    heading = "Couldn't create";
    note = create.error ? messageOf(create.error) : (clip.data?.error ?? null);
  } else if (ready) {
    state = player.playing ? "speaking" : "idle";
    heading = player.playing ? "Speaking" : "Ready";
    note = null;
  }

  const max = engine.data?.max_characters ?? 600;
  return (
    <div className="speak-layout">
      <form className="card stack speak-form" onSubmit={submit}>
        <TextArea
          label="Text"
          value={text}
          maxLength={max}
          rows={4}
          required
          hint={`${text.length} / ${max}`}
          onChange={(event) => setText(event.target.value)}
        />
        <div className="speak-row">
          <SelectField
            label="Voice"
            value={voice}
            options={options}
            disabled={options.length === 0}
            onChange={(event) => setVoice(event.target.value)}
          />
          <SelectField
            label="Style"
            value={style}
            options={(engine.data?.deliveries ?? ["neutral"]).map((d) => ({
              value: d,
              label: STYLES[d] ?? d,
            }))}
            onChange={(event) => setStyle(event.target.value)}
          />
        </div>
        {engine.data?.recorded_voices && voices.data?.total === 0 ? (
          <p className="muted studio-meta">
            No recorded voices yet. <Link to="/voices/new">Add voice</Link>
          </p>
        ) : null}
        <EffectPicker value={effects} onChange={setEffects} />
        <div className="row speak-submit">
          <Button
            type="submit"
            busy={create.isPending}
            disabled={!text.trim() || !voice}
          >
            Speak
          </Button>
          {engine.data?.uses_quota && engine.data.clips_left_today != null ? (
            <span className="muted studio-meta">
              {engine.data.clips_left_today} left today
            </span>
          ) : null}
        </div>
      </form>

      <section
        className="card speak-output"
        aria-labelledby="speak-output-heading"
      >
        <div className="speak-output-head">
          <h2 id="speak-output-heading" className="studio-label">
            {heading}
          </h2>
          {ready ? (
            <span className="muted studio-meta">
              {clock(player.time)} / {clock(player.duration)}
            </span>
          ) : null}
        </div>
        <VoiceOctagon state={state} level={player.level} />
        <div aria-live="polite" className="speak-note">
          {note ? (
            <p className={state === "error" ? "field-error" : "muted"}>
              {note}
            </p>
          ) : null}
        </div>
        {state === "error" && lastRequest ? (
          <Button onClick={() => send(lastRequest)}>Try again</Button>
        ) : null}
        {ready ? (
          <div className="stack speak-controls">
            <div className="row">
              <button
                type="button"
                className="round-button"
                aria-label={player.playing ? "Pause" : "Play"}
                onClick={player.toggle}
              >
                {player.playing ? (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    aria-hidden="true"
                  >
                    <path
                      d="M4 2.5v9M10 2.5v9"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                    />
                  </svg>
                ) : (
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    aria-hidden="true"
                  >
                    <path d="M4 2.5v9l7-4.5z" fill="currentColor" />
                  </svg>
                )}
              </button>
              <a
                className="btn btn-secondary"
                href={`${API_BASE}${ready}?download=true`}
              >
                Download
              </a>
            </div>
            <Link
              to="/voices/show-sound"
              state={{ use: { voice, effects } }}
              className="speak-use"
            >
              Use in Show sound
            </Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
