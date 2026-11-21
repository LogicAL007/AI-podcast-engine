import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import {
  useCreateSpeech,
  useEpisodeAction,
  useMusic,
  useShow,
  useShowEpisodes,
  useShows,
  useSpeechClip,
  useUpdateShow,
  useVoices,
} from "../../api/queries";
import type {
  MusicTrackRead,
  ShowRead,
  ShowUpdate,
  VoiceEffects,
  VoiceRead,
} from "../../api/types";
import { useAssistant } from "../../bots/assistant";
import { Alert, ErrorAlert, messageOf } from "../../components/Alert";
import { Button, LinkButton } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { SelectField } from "../../components/Field";
import { Skeleton } from "../../components/Skeleton";
import { HOST_NAMES } from "../shows/showValues";
import { EffectPicker, effectName, full, isNatural } from "./effects";
import { PlayButton } from "./MusicTab";
import { useClipPlayer, useTrackPlayer } from "./playback";
import { VoiceOctagon, type OctagonState } from "./VoiceOctagon";

type Slot = "intro" | "sting" | "bed" | "outro";
const SLOTS: { slot: Slot; label: string; none: string }[] = [
  { slot: "intro", label: "Intro", none: "Default chime" },
  { slot: "sting", label: "Between segments", none: "A short pause" },
  { slot: "bed", label: "Background", none: "None" },
  { slot: "outro", label: "Outro", none: "Default chime" },
];
const LEVELS = [
  { value: "-26", label: "Quiet" },
  { value: "-22", label: "Medium" },
  { value: "-18", label: "Present" },
];

interface Sound {
  voices: Record<string, string>; // host -> recorded voice id, "" = built-in
  effects: Record<string, VoiceEffects>;
  music: Record<Slot, string> & { level: number };
}

/** What "Use in Show sound" (Type to speech) carries over. */
interface Carried {
  voice: string; // "recorded:<id>" or "engine:<host>"
  effects: VoiceEffects;
}

function soundOf(show: ShowRead): Sound {
  return {
    voices: Object.fromEntries(Object.entries(show.host_voices ?? {})),
    effects: Object.fromEntries(
      Object.entries(show.host_effects ?? {}).map(([host, fx]) => [
        host,
        full(fx),
      ]),
    ),
    music: {
      intro: show.music?.intro ?? "",
      sting: show.music?.sting ?? "",
      bed: show.music?.bed ?? "",
      outro: show.music?.outro ?? "",
      level: show.music?.bed_level_db ?? -22,
    },
  };
}

function bodyOf(sound: Sound, hosts: string[]): ShowUpdate {
  return {
    host_voices: Object.fromEntries(
      Object.entries(sound.voices).filter(
        ([host, id]) => id && hosts.includes(host),
      ),
    ),
    host_effects: Object.fromEntries(
      Object.entries(sound.effects).filter(
        ([host, fx]) => !isNatural(fx) && hosts.includes(host),
      ),
    ),
    music: {
      intro: sound.music.intro || null,
      sting: sound.music.sting || null,
      bed: sound.music.bed || null,
      outro: sound.music.outro || null,
      bed_level_db: sound.music.level,
    },
  };
}

/** What changed, as "Alex: Deep broadcast" lines, for the remix question. */
export function changesBetween(
  before: Sound,
  after: Sound,
  hosts: string[],
  voices: VoiceRead[],
  tracks: MusicTrackRead[],
): string[] {
  const voiceName = (id: string) =>
    id
      ? (voices.find((v) => v.voice_id === id)?.name ?? "Recorded voice")
      : "Built-in voice";
  const trackName = (id: string, none: string) =>
    id ? (tracks.find((t) => t.track_id === id)?.name ?? "A track") : none;
  const lines: string[] = [];
  for (const host of hosts) {
    if ((before.voices[host] ?? "") !== (after.voices[host] ?? ""))
      lines.push(`${host}: ${voiceName(after.voices[host] ?? "")}`);
    const a = full(before.effects[host]);
    const b = full(after.effects[host]);
    if (
      a.deepen !== b.deepen ||
      a.warmth !== b.warmth ||
      a.broadcast !== b.broadcast
    )
      lines.push(`${host}: ${effectName(b)}`);
  }
  for (const { slot, label, none } of SLOTS)
    if (before.music[slot] !== after.music[slot])
      lines.push(`${label}: ${trackName(after.music[slot], none)}`);
  if (before.music.level !== after.music.level)
    lines.push(
      `Background level: ${LEVELS.find((l) => l.value === String(after.music.level))?.label ?? after.music.level}`,
    );
  return lines;
}

/** One host's Preview: they say a line in their voice with their effect. */
function HostPreview({
  host,
  voiceId,
  effects,
}: {
  host: string;
  voiceId: string;
  effects: VoiceEffects;
}) {
  const create = useCreateSpeech();
  const [clipId, setClipId] = useState<string | null>(null);
  const [made, setMade] = useState("");
  const clip = useSpeechClip(clipId);
  const ready = clip.data?.status === "done" ? (clip.data.audio ?? null) : null;
  const player = useClipPlayer(ready, true);
  const settings = JSON.stringify([voiceId, effects]);
  const waiting =
    create.isPending ||
    clip.data?.status === "queued" ||
    clip.data?.status === "working";
  const failed = create.error || clip.data?.status === "failed";
  const state: OctagonState = waiting
    ? "waiting"
    : player.playing
      ? "speaking"
      : failed
        ? "error"
        : "idle";

  function preview() {
    if (ready && made === settings) return player.toggle(); // same settings: play it again
    setMade(settings);
    create.mutate(
      {
        text: `Hi, I'm ${host}. This is how I'll sound on the show.`,
        voice: voiceId
          ? { kind: "recorded", voice_id: voiceId }
          : { kind: "engine", host: host as "Alex" },
        delivery: "neutral",
        effects,
      },
      { onSuccess: (clipMade) => setClipId(clipMade.clip_id) },
    );
  }

  return (
    <div className="host-preview">
      <VoiceOctagon
        state={state}
        level={player.level}
        size={36}
        label={`${host}'s preview`}
      />
      <Button variant="secondary" busy={waiting} onClick={preview}>
        {player.playing ? "Pause" : "Preview"}
      </Button>
      <span className="sr-only" aria-live="polite">
        {waiting ? "Preparing the preview" : failed ? "The preview failed" : ""}
      </span>
      {failed ? (
        <span className="field-error studio-meta">
          {create.error
            ? messageOf(create.error)
            : (clip.data?.error ?? "Failed")}
        </span>
      ) : null}
    </div>
  );
}

function SoundEditor({
  show,
  carried,
  onCarried,
}: {
  show: ShowRead;
  carried: Carried | null;
  onCarried: () => void;
}) {
  const voices = useVoices();
  const music = useMusic();
  const update = useUpdateShow(show.show_id);
  const episodes = useShowEpisodes(show.show_id, 0);
  const latest =
    episodes.data?.items.find((e) => e.status === "published") ?? null;
  const remix = useEpisodeAction(latest?.episode_id ?? "", "remix");
  const player = useTrackPlayer();
  const saved = useMemo(() => soundOf(show), [show]);
  const [sound, setSound] = useState<Sound>(saved);
  const [changes, setChanges] = useState<string[] | null>(null);
  const [done, setDone] = useState<"saved" | "remixing" | null>(null);
  const hosts = HOST_NAMES.slice(0, Math.max(1, Math.min(4, show.host_count)));
  const recorded = voices.data?.items ?? [];
  const tracks = music.data ?? [];

  function setHost(
    host: string,
    voice: string | undefined,
    effects: VoiceEffects | undefined,
  ) {
    setDone(null);
    setSound((current) => ({
      ...current,
      voices:
        voice === undefined
          ? current.voices
          : { ...current.voices, [host]: voice },
      effects:
        effects === undefined
          ? current.effects
          : { ...current.effects, [host]: effects },
    }));
  }

  function setMusic(patch: Partial<Sound["music"]>) {
    setDone(null);
    setSound((current) => ({
      ...current,
      music: { ...current.music, ...patch },
    }));
  }

  function apply(host: string) {
    if (!carried) return;
    const [kind, value] = carried.voice.split(":");
    setHost(host, kind === "recorded" ? value : "", carried.effects);
    onCarried();
  }

  function save() {
    const lines = changesBetween(saved, sound, hosts, recorded, tracks);
    update.mutate(bodyOf(sound, hosts), {
      onSuccess: () => {
        if (latest && lines.length) setChanges(lines);
        else setDone("saved");
      },
    });
  }

  const carriedVoice = carried
    ? carried.voice.startsWith("recorded:")
      ? (recorded.find((v) => `recorded:${v.voice_id}` === carried.voice)
          ?.name ?? "Recorded voice")
      : carried.voice.replace("engine:", "")
    : "";

  return (
    <div className="stack sound-editor">
      {carried ? (
        <div
          className="carried"
          role="region"
          aria-label="Use from Type to speech"
        >
          <span>
            Use <b>{carriedVoice}</b> · <b>{effectName(carried.effects)}</b> for
          </span>
          {hosts.map((host) => (
            <Button key={host} variant="secondary" onClick={() => apply(host)}>
              {host}
            </Button>
          ))}
          <button type="button" className="link-button" onClick={onCarried}>
            Dismiss
          </button>
        </div>
      ) : null}

      <section className="stack" aria-labelledby="hosts-heading">
        <h2 id="hosts-heading" className="studio-label">
          Hosts
        </h2>
        <div className="studio-grid">
          {hosts.map((host) => (
            <article
              key={host}
              className="card stack host-card"
              aria-label={host}
            >
              <div className="host-card-head">
                <h3 className="studio-card-title">{host}</h3>
                <HostPreview
                  host={host}
                  voiceId={sound.voices[host] ?? ""}
                  effects={full(sound.effects[host])}
                />
              </div>
              <SelectField
                label={`${host}'s voice`}
                value={sound.voices[host] ?? ""}
                onChange={(event) =>
                  setHost(host, event.target.value, undefined)
                }
                options={[
                  { value: "", label: "Built-in" },
                  ...recorded.map((v) => ({
                    value: v.voice_id,
                    label: v.name,
                  })),
                ]}
              />
              <EffectPicker
                label={`${host}'s effect`}
                value={full(sound.effects[host])}
                onChange={(effects) => setHost(host, undefined, effects)}
              />
            </article>
          ))}
        </div>
      </section>

      <section className="stack" aria-labelledby="music-heading">
        <h2 id="music-heading" className="studio-label">
          Music
        </h2>
        <div className="card sound-music">
          {SLOTS.map(({ slot, label, none }) => {
            const chosen = tracks.find((t) => t.track_id === sound.music[slot]);
            const fits = tracks.filter(
              (t) =>
                t.role === slot ||
                t.role === "any" ||
                t.track_id === sound.music[slot],
            );
            return (
              <div key={slot} className="sound-row">
                <SelectField
                  label={label}
                  value={sound.music[slot]}
                  onChange={(event) => setMusic({ [slot]: event.target.value })}
                  options={[
                    { value: "", label: none },
                    ...fits.map((t) => ({ value: t.track_id, label: t.name })),
                  ]}
                />
                {chosen ? (
                  <PlayButton
                    playing={player.playing === chosen.track_id}
                    name={chosen.name}
                    onClick={() => player.toggle(chosen.track_id, chosen.audio)}
                  />
                ) : (
                  <span
                    className="round-button-placeholder"
                    aria-hidden="true"
                  />
                )}
              </div>
            );
          })}
          <div className="sound-row">
            <SelectField
              label="Background level"
              value={String(sound.music.level)}
              disabled={!sound.music.bed}
              onChange={(event) =>
                setMusic({ level: Number(event.target.value) })
              }
              options={
                LEVELS.some((l) => l.value === String(sound.music.level))
                  ? LEVELS
                  : [
                      ...LEVELS,
                      {
                        value: String(sound.music.level),
                        label: `${sound.music.level} dB`,
                      },
                    ]
              }
            />
            <span className="round-button-placeholder" aria-hidden="true" />
          </div>
        </div>
      </section>

      <ErrorAlert error={update.error} />
      {done === "saved" ? (
        <Alert tone="success">Saved. New episodes use these settings.</Alert>
      ) : null}
      {done === "remixing" && latest ? (
        <Alert tone="success">
          Remixing.{" "}
          <Link to={`/episodes/${latest.episode_id}`}>Open the episode</Link> to
          hear it in about a minute.
        </Alert>
      ) : null}
      <div className="row">
        <Button busy={update.isPending} onClick={save}>
          Save
        </Button>
        <span className="muted studio-meta">
          New episodes use these settings
        </span>
      </div>

      <ConfirmDialog
        open={changes !== null}
        title="Saved. Remix the latest episode?"
        confirmLabel="Remix"
        busy={remix.isPending}
        error={remix.error}
        onClose={() => {
          setChanges(null);
          setDone("saved");
        }}
        onConfirm={() =>
          remix.mutate(undefined, {
            onSuccess: () => {
              setChanges(null);
              setDone("remixing");
            },
          })
        }
      >
        <ul className="change-list">
          {(changes ?? []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p>Episode {latest?.revision} · no voice quota used</p>
      </ConfirmDialog>
    </div>
  );
}

/** The Show sound tab: how one show sounds, its hosts' voices and effects, and its music. */
export function ShowSoundTab() {
  const shows = useShows(0);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const showId = params.get("show") ?? shows.data?.items[0]?.show_id ?? "";
  const show = useShow(showId);
  const carried = ((location.state as { use?: Carried } | null)?.use ??
    null) as Carried | null;

  useAssistant({
    page: "voices",
    key: "show-sound",
    moment: "voices",
    mode: "greeting",
    line: "Pick a show, then shape how its hosts sound.",
    hint: "Changes apply to new episodes. After saving you can remix the latest one; it uses no voice quota.",
    questions: ["What does Remix do?"],
  });

  if (shows.isPending) return <Skeleton label="Loading your shows" rows={2} />;
  if (shows.data?.total === 0)
    return (
      <EmptyState
        title="No shows yet"
        action={<LinkButton to="/shows/new">New show</LinkButton>}
      >
        Create a show, then set how it sounds here.
      </EmptyState>
    );
  return (
    <div className="stack">
      <div className="sound-show-picker">
        <SelectField
          label="Show"
          value={showId}
          onChange={(event) => setParams({ show: event.target.value })}
          options={(shows.data?.items ?? []).map((s) => ({
            value: s.show_id,
            label: s.topic,
          }))}
        />
      </div>
      <ErrorAlert error={shows.error ?? show.error} />
      {show.isPending ? <Skeleton label="Loading the show" rows={2} /> : null}
      {show.data ? (
        <SoundEditor
          key={show.data.show_id}
          show={show.data}
          carried={carried}
          onCarried={() =>
            navigate(`${location.pathname}${location.search}`, {
              replace: true,
              state: null,
            })
          }
        />
      ) : null}
    </div>
  );
}
