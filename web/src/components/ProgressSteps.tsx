import { useId, useState, type CSSProperties } from "react";

import type { EpisodeStatus } from "../api/types";

export const STAGES = [
  {
    id: "ingest",
    verb: "Gathering",
    doing: "Reading your sources",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 20,
    label: "Gather",
    about:
      "Reads your source pages and PDFs, and notes which changed since last time.",
  },
  {
    id: "index",
    verb: "Indexing",
    doing: "Sorting the sources into passages",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 15,
    label: "Index",
    about:
      "Splits the sources into passages and indexes them so the right ones can be found.",
  },
  {
    id: "retrieve_plan",
    verb: "Planning",
    doing: "Choosing what the episode covers",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 180,
    label: "Plan",
    about:
      "Picks the passages most relevant to the topic and plans the episode's segments.",
  },
  {
    id: "script",
    verb: "Writing",
    doing: "Writing the hosts' conversation",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 480,
    label: "Script",
    about:
      "Writes the hosts' dialogue, each line citing the passage it comes from.",
  },
  {
    id: "factcheck",
    verb: "Fact-checking",
    doing: "Checking every claim against its source",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 300,
    label: "Fact-check",
    about:
      "Checks every claim against its passage; unsupported claims are rewritten or removed.",
  },
  {
    id: "voice",
    verb: "Voicing",
    doing: "Reading the script aloud",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 300,
    label: "Voice",
    about: "Gives each host a distinct voice and reads the script aloud.",
  },
  {
    id: "assemble",
    verb: "Assembling",
    doing: "Mixing in the intro, music and outro",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 30,
    label: "Assemble",
    about:
      "Joins the lines with an intro, transitions and outro, and evens out the loudness.",
  },
  {
    id: "publish",
    verb: "Publishing",
    doing: "Adding the episode to your feed",
    // About how long this step usually takes, so the bar creeps at a believable pace.
    seconds: 15,
    label: "Publish",
    about: "Adds the audio and show notes to the show's podcast feed.",
  },
] as const;

export function stageLabel(stage: string | null | undefined): string {
  return STAGES.find((s) => s.id === stage)?.label ?? "Waiting to start";
}

/** Which step (1-8) an episode is on, or 8 when done; the same rule the progress stream uses. */
export function stepOf(
  status: EpisodeStatus,
  stage: string | null | undefined,
): number {
  if (status === "published" || status === "unchanged") return STAGES.length;
  const index = STAGES.findIndex((s) => s.id === stage);
  return index + 1;
}

export function stageVerb(stage: string | null | undefined): string {
  return STAGES.find((s) => s.id === stage)?.verb ?? "Waiting";
}

/** The headline and its detail line for an episode's state. */
function headline(
  status: EpisodeStatus,
  stage: string | null | undefined,
): { word: string; detail: string; moving: boolean } {
  const current = STAGES.find((s) => s.id === stage);
  switch (status) {
    case "published":
      return { word: "Published", detail: "All 8 steps done.", moving: false };
    case "unchanged":
      return {
        word: "Up to date",
        detail: "No source changed, so there was nothing new to make.",
        moving: false,
      };
    case "needs_review":
      return {
        word: "Waiting for your review",
        detail: "Read the script, then approve it to carry on.",
        moving: false,
      };
    case "failed":
      return {
        word: current ? `Stopped at ${current.label}` : "Stopped",
        detail: "See the reason below; Retry carries on from this step.",
        moving: false,
      };
    case "cancelled":
      return {
        word: "Cancelled",
        detail: "Nothing more will run.",
        moving: false,
      };
    case "queued":
      return {
        word: "Getting ready",
        detail: "Waiting for a free worker.",
        moving: true,
      };
    default:
      return current
        ? { word: current.verb, detail: `${current.doing}.`, moving: true }
        : { word: "Getting ready", detail: "Starting up.", moving: true };
  }
}

export function ProgressSteps({
  status,
  stage,
}: {
  status: EpisodeStatus;
  stage: string | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const guideId = useId();
  const step = stepOf(status, stage);
  const done = status === "published" || status === "unchanged";
  const summary = done
    ? "All 8 steps done"
    : step === 0
      ? "Waiting to start"
      : `Step ${step} of 8: ${stageLabel(stage)}`;
  const { word, detail, moving } = headline(status, stage);
  const current = STAGES[step - 1];
  // The fill: finished steps, plus (while a step runs) a slow creep across most of the current one.
  const start = done ? 1 : Math.max(step - 1, 0) / STAGES.length;
  const end = done
    ? 1
    : moving
      ? start + (0.9 * (step === 0 ? 0.25 : 1)) / STAGES.length
      : status === "needs_review"
        ? step / STAGES.length
        : start;
  const tone =
    status === "failed"
      ? "progress-failed"
      : status === "cancelled"
        ? "progress-stopped"
        : done
          ? "progress-done"
          : moving
            ? "progress-moving"
            : "";
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <div className="steps-summary">
        <div className="progress-headline" aria-hidden="true">
          {/* Keyed so each new word slides in. */}
          <span key={word} className="progress-word">
            {word}
            {moving ? (
              <span className="progress-dots">
                <span>.</span>
                <span>.</span>
                <span>.</span>
              </span>
            ) : null}
          </span>
          <span key={`${word}-detail`} className="progress-detail muted">
            {step > 0 && !done ? `Step ${step} of 8 · ` : ""}
            {detail}
          </span>
        </div>
        {/* Announced to screen readers whenever the step changes. */}
        <p aria-live="polite" className="sr-only">
          {summary}
        </p>
        <button
          type="button"
          className="steps-help"
          aria-expanded={open}
          aria-controls={guideId}
          onClick={() => setOpen((value) => !value)}
        >
          <span aria-hidden="true">?</span>
          <span className="sr-only">What the steps mean</span>
        </button>
      </div>
      <div className={`progress-track ${tone}`} aria-hidden="true">
        <span
          // Restarted for each step, from where the last one ended.
          key={`${status}-${stage ?? ""}`}
          className="progress-fill"
          style={
            {
              "--from": `${start * 100}%`,
              "--to": `${end * 100}%`,
              "--creep": `${current?.seconds ?? 20}s`,
            } as CSSProperties
          }
        />
      </div>
      {open ? (
        <ol id={guideId} className="step-guide">
          {STAGES.map((s, index) => (
            <li
              key={s.id}
              className={index + 1 === step && !done ? "step-guide-now" : ""}
            >
              <strong>{s.label}</strong>
              {index + 1 === step && !done ? (
                <span className="step-guide-tag"> now</span>
              ) : null}
              <span className="muted"> {s.about}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
