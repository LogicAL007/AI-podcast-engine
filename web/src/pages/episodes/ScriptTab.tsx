import { useState } from "react";

import {
  useEpisodeAction,
  useEpisodeScript,
  useSaveScript,
} from "../../api/queries";
import type {
  EpisodeRead,
  EpisodeScript,
  LineRead,
  ScriptEdit,
} from "../../api/types";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Skeleton } from "../../components/Skeleton";
import { VerdictBadge } from "./VerdictBadge";

/** The passages a line cites, so an edit keeps its citations (null: framing, not a claim). */
export function citationsOf(line: LineRead): string[] | null {
  if (!line.claims || line.claims.length === 0) return null;
  return [...new Set(line.claims.flatMap((claim) => claim.chunk_ids))];
}

/** The edit request for the segments whose text was changed. */
export function editFor(
  script: EpisodeScript,
  drafts: Record<string, string>,
): ScriptEdit {
  const segments = script.segments
    .filter((segment) =>
      segment.lines.some(
        (_, i) => drafts[`${segment.position}:${i}`] !== undefined,
      ),
    )
    .map((segment) => ({
      position: segment.position,
      lines: segment.lines.map((line, i) => ({
        speaker: line.speaker,
        text: (drafts[`${segment.position}:${i}`] ?? line.text).trim(),
        chunk_ids: citationsOf(line),
        delivery: line.delivery ?? "neutral",
      })),
    }));
  return { segments };
}

export function ScriptTab({ episode }: { episode: EpisodeRead }) {
  const script = useEpisodeScript(episode.episode_id);
  const save = useSaveScript(episode.episode_id);
  const approve = useEpisodeAction(episode.episode_id, "approve");
  const [editing, setEditing] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const reviewable = episode.status === "needs_review";

  if (script.isPending)
    return <Skeleton kind="lines" label="Loading the script" rows={4} />;
  if (!script.data) return <ErrorAlert error={script.error} />;
  if (script.data.segments.length === 0) {
    return (
      <EmptyState title="No script yet">
        The script appears here once the hosts&apos; dialogue is written.
      </EmptyState>
    );
  }

  const data = script.data;
  const changed = Object.keys(drafts).length > 0;
  const empty = Object.values(drafts).some((text) => text.trim() === "");

  function saveEdits() {
    save.mutate(editFor(data, drafts), {
      onSuccess: () => {
        setDrafts({});
        setEditing(false);
      },
    });
  }

  return (
    <div className="stack" style={{ gap: "var(--space-5)" }}>
      {reviewable ? (
        <div className="card card-muted spread">
          <p>
            {editing
              ? "Edit any line, then save. Your edits are fact-checked again; citations stay with their lines."
              : "Read the script and its verdicts. Approve it to voice and publish, or edit lines first."}
          </p>
          <div className="row">
            {editing ? (
              <>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDrafts({});
                    setEditing(false);
                  }}
                >
                  Discard edits
                </Button>
                <Button
                  busy={save.isPending}
                  disabled={!changed || empty}
                  onClick={saveEdits}
                >
                  Save and re-check
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Edit script
                </Button>
                <Button
                  busy={approve.isPending}
                  onClick={() => approve.mutate()}
                >
                  Approve and voice
                </Button>
              </>
            )}
          </div>
        </div>
      ) : null}
      {empty ? <Alert tone="error">A line cannot be empty.</Alert> : null}
      <ErrorAlert error={save.error ?? approve.error} />
      {save.isSuccess ? (
        <Alert tone="success">Saved. The fact-check is running again.</Alert>
      ) : null}

      {data.segments.map((segment) => (
        <section
          key={segment.position}
          className="segment"
          aria-labelledby={`segment-${segment.position}`}
        >
          <h2
            id={`segment-${segment.position}`}
            style={{
              fontSize: "var(--text-lg)",
              marginBottom: "var(--space-3)",
            }}
          >
            {segment.position}. {segment.title}
          </h2>
          {segment.lines.map((line, i) => {
            const key = `${segment.position}:${i}`;
            return (
              <div key={key} className="line">
                <span className="line-speaker">
                  {line.speaker}
                  {line.delivery && line.delivery !== "neutral" ? (
                    <span className="line-delivery">{line.delivery}</span>
                  ) : null}
                </span>
                <div>
                  {editing ? (
                    <>
                      <label htmlFor={`line-${key}`} className="sr-only">
                        {line.speaker}, line {i + 1} of segment{" "}
                        {segment.position}
                      </label>
                      <textarea
                        id={`line-${key}`}
                        className="textarea"
                        rows={2}
                        style={{ minHeight: "3.5rem" }}
                        value={drafts[key] ?? line.text}
                        onChange={(event) =>
                          setDrafts((d) => ({
                            ...d,
                            [key]: event.target.value,
                          }))
                        }
                      />
                    </>
                  ) : (
                    <p>{line.text}</p>
                  )}
                  {line.claims?.map((claim, n) => (
                    <span
                      key={n}
                      className="claim"
                      title={claim.reason ?? undefined}
                    >
                      <VerdictBadge
                        supported={claim.supported ?? null}
                        cited={claim.chunk_ids.length > 0}
                      />
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
