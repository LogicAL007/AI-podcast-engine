import { useState } from "react";
import { useNavigate } from "react-router";

import { useStartEpisode } from "../../api/queries";
import { ConfirmDialog } from "../../components/ConfirmDialog";

type Mode = "changes" | "rebuild";

const MODES: [Mode, string, string][] = [
  [
    "changes",
    "Only what changed",
    "Reads the sources and runs the searches again, then rewrites and revoices only the segments whose sources changed. If nothing changed, nothing is made.",
  ],
  [
    "rebuild",
    "Everything, from scratch",
    "Plans, writes and voices every segment again from the sources as they are now, even if none changed. Uses the most Podcast Engine requests.",
  ],
];

/**
 * Refresh a show's episode by hand (FR8, instead of a timer): a new revision from the sources
 * as they are now, either only where they changed or every segment. Opens the new episode.
 */
export function RefreshDialog({
  showId,
  open,
  onClose,
}: {
  showId: string;
  open: boolean;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<Mode>("changes");
  const start = useStartEpisode(showId);
  const navigate = useNavigate();
  return (
    <ConfirmDialog
      open={open}
      title="Refresh this episode?"
      confirmLabel={mode === "rebuild" ? "Rebuild it" : "Refresh it"}
      busy={start.isPending}
      error={start.error}
      onClose={onClose}
      onConfirm={() =>
        start.mutate(
          { rebuild: mode === "rebuild" },
          {
            onSuccess: (next) => {
              onClose();
              navigate(`/episodes/${next.episode_id}`);
            },
          },
        )
      }
    >
      <p>
        A refresh makes the next revision of this show from its sources as they
        are now. This episode stays as it is.
      </p>
      <fieldset className="choice-group">
        <legend>What should it redo?</legend>
        <div className="character-cards">
          {MODES.map(([value, label, about]) => (
            <label key={value} className="character-card">
              <input
                type="radio"
                name="refresh-mode"
                value={value}
                checked={mode === value}
                onChange={() => setMode(value)}
              />
              <span className="character-name">{label}</span>
              <span className="muted">{about}</span>
            </label>
          ))}
        </div>
      </fieldset>
    </ConfirmDialog>
  );
}
