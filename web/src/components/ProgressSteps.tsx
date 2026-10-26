import { useId, useState } from "react";

import type { EpisodeStatus } from "../api/types";

export const STAGES = [
  {
    id: "ingest",
    label: "Gather",
    about:
      "Reads your source pages and PDFs, and notes which changed since last time.",
  },
  {
    id: "index",
    label: "Index",
    about:
      "Splits the sources into passages and indexes them so the right ones can be found.",
  },
  {
    id: "retrieve_plan",
    label: "Plan",
    about:
      "Picks the passages most relevant to the topic and plans the episode's segments.",
  },
  {
    id: "script",
    label: "Script",
    about:
      "Writes the hosts' dialogue, each line citing the passage it comes from.",
  },
  {
    id: "factcheck",
    label: "Fact-check",
    about:
      "Checks every claim against its passage; unsupported claims are rewritten or removed.",
  },
  {
    id: "voice",
    label: "Voice",
    about: "Gives each host a distinct voice and reads the script aloud.",
  },
  {
    id: "assemble",
    label: "Assemble",
    about:
      "Joins the lines with an intro, transitions and outro, and evens out the loudness.",
  },
  {
    id: "publish",
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
  return (
    <div className="stack" style={{ gap: "var(--space-2)" }}>
      <div className="steps-summary">
        {/* Announced to screen readers whenever it changes. */}
        <p
          aria-live="polite"
          className="muted"
          style={{ fontSize: "var(--text-sm)" }}
        >
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
      <ol className="steps" aria-hidden="true">
        {STAGES.map((s, index) => {
          const n = index + 1;
          const state =
            n < step || done ? "step-done" : n === step ? "step-current" : "";
          return (
            <li key={s.id} className={`step ${state}`}>
              <span className="step-bar" />
              <span className="step-label">{s.label}</span>
            </li>
          );
        })}
      </ol>
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
