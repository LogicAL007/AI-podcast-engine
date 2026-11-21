import { useState, type DragEvent, type FormEvent } from "react";

import { useDeleteMusic, useMusic, useUploadMusic } from "../../api/queries";
import type { MusicTrackRead } from "../../api/types";
import { decode, toVoiceWav } from "../../audio/wav";
import { useAssistant } from "../../bots/assistant";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { SelectField, TextField } from "../../components/Field";
import { Skeleton } from "../../components/Skeleton";
import { clock, useTrackPlayer } from "./playback";

const MAX_SECONDS = 360;
export const ROLE_LABELS: Record<MusicTrackRead["role"], string> = {
  bed: "Background",
  intro: "Intro",
  outro: "Outro",
  sting: "Sting",
  any: "Any",
};

export function PlayButton({
  playing,
  name,
  onClick,
}: {
  playing: boolean;
  name: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="round-button round-button-small"
      aria-label={`${playing ? "Pause" : "Play"} ${name}`}
      aria-pressed={playing}
      onClick={onClick}
    >
      {playing ? (
        <svg width="11" height="11" viewBox="0 0 14 14" aria-hidden="true">
          <path
            d="M4 2.5v9M10 2.5v9"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <svg width="11" height="11" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M4 2.5v9l7-4.5z" fill="currentColor" />
        </svg>
      )}
    </button>
  );
}

/** The Music tab: the library (built-in tracks and yours), and uploading a track. */
export function MusicTab() {
  const music = useMusic();
  const upload = useUploadMusic();
  const remove = useDeleteMusic();
  const player = useTrackPlayer();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState<MusicTrackRead["role"]>("bed");
  const [rights, setRights] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [converting, setConverting] = useState(false);
  const [deleting, setDeleting] = useState<MusicTrackRead | null>(null);
  const [added, setAdded] = useState(false);
  const [dragging, setDragging] = useState(false);

  useAssistant({
    page: "voices",
    key: "music",
    moment: "voices",
    mode: "greeting",
    line: "Built-in tracks are free to use. Upload your own too.",
    hint: "Choose music for a show in the Show sound tab.",
    questions: ["Which music can I upload?"],
  });

  function choose(chosen: File | null) {
    setFile(chosen);
    setProblem(null);
    setAdded(false);
    if (chosen && !name) setName(chosen.name.replace(/\.[^.]+$/, ""));
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files?.[0] ?? null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    setAdded(false);
    if (!file) return setProblem("Choose an audio file.");
    if (!rights)
      return setProblem("Confirm that you have the rights to this music.");
    setConverting(true);
    try {
      const { wav, seconds } = await toVoiceWav(await decode(file));
      if (seconds < 1 || seconds > MAX_SECONDS) {
        setProblem(`The track is ${clock(seconds)}; use up to 6 minutes.`);
        return;
      }
      upload.mutate(
        { wav, name: name.trim() || file.name, role, credit: "" },
        {
          onSuccess: () => {
            setFile(null);
            setName("");
            setRights(false);
            setAdded(true);
          },
        },
      );
    } catch {
      setProblem("This file can't be read as audio. Try MP3, WAV, M4A or OGG.");
    } finally {
      setConverting(false);
    }
  }

  return (
    <div className="music-layout">
      <section className="card music-library" aria-labelledby="library-heading">
        <h2 id="library-heading" className="studio-label music-library-head">
          Library
        </h2>
        {music.isPending ? (
          <Skeleton label="Loading the music library" rows={3} />
        ) : null}
        <ErrorAlert error={music.error} />
        <ul className="track-list">
          {music.data?.map((track) => (
            <li key={track.track_id} className="track-row">
              <PlayButton
                playing={player.playing === track.track_id}
                name={track.name}
                onClick={() => player.toggle(track.track_id, track.audio)}
              />
              <span className="track-name">{track.name}</span>
              <span className="role-chip">{ROLE_LABELS[track.role]}</span>
              <span className="muted studio-meta">
                {clock(track.duration_seconds)}
              </span>
              <span className="muted studio-meta track-source">
                {track.builtin ? (
                  "Built-in"
                ) : (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => setDeleting(track)}
                  >
                    Delete
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <form
        className="card stack music-upload"
        onSubmit={submit}
        aria-labelledby="upload-heading"
      >
        <h2 id="upload-heading" className="studio-subhead">
          Upload
        </h2>
        <label
          className={dragging ? "drop-zone dragging" : "drop-zone"}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <svg
            width="26"
            height="26"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M8 14.5V4.5l8-1.5v10" />
            <circle cx="6" cy="14.5" r="2" />
            <circle cx="14" cy="13" r="2" />
          </svg>
          <span className="drop-zone-title">
            {file ? file.name : "Drop audio or browse"}
          </span>
          <span className="muted studio-meta">Up to 6 min</span>
          <input
            type="file"
            accept="audio/*"
            className="sr-only"
            aria-label="Audio file"
            onChange={(event) => choose(event.target.files?.[0] ?? null)}
          />
        </label>
        <TextField
          label="Name"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
        />
        <SelectField
          label="Use as"
          value={role}
          onChange={(e) => setRole(e.target.value as MusicTrackRead["role"])}
          options={(Object.keys(ROLE_LABELS) as MusicTrackRead["role"][]).map(
            (value) => ({
              value,
              label: ROLE_LABELS[value],
            }),
          )}
        />
        <label className="check-inline">
          <input
            type="checkbox"
            checked={rights}
            onChange={(e) => setRights(e.target.checked)}
          />
          I have the rights to this music
        </label>
        {problem ? (
          <p className="field-error" role="alert">
            {problem}
          </p>
        ) : null}
        <ErrorAlert error={upload.error} />
        {added ? <Alert tone="success">Track added.</Alert> : null}
        <Button type="submit" busy={converting || upload.isPending}>
          Upload
        </Button>
      </form>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete this track?"
        confirmLabel="Delete track"
        danger
        busy={remove.isPending}
        error={remove.error}
        onClose={() => setDeleting(null)}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.track_id, {
            onSuccess: () => setDeleting(null),
          })
        }
      >
        Shows using it go back to the default. Published episodes keep their
        audio.
      </ConfirmDialog>
    </div>
  );
}
