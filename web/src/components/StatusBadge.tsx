import { useState } from "react";

import type { EpisodeStatus } from "../api/types";

const LOOK: Record<EpisodeStatus, { label: string; tone: string }> = {
  queued: { label: "Queued", tone: "neutral" },
  processing: { label: "In progress", tone: "active" },
  needs_review: { label: "Needs review", tone: "attention" },
  published: { label: "Published", tone: "success" },
  unchanged: { label: "No changes", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  failed: { label: "Failed", tone: "danger" },
};

export function statusLabel(status: EpisodeStatus): string {
  return LOOK[status].label;
}

/** The status in words and colour. When it changes while shown, the new badge pops once. */
export function StatusBadge({ status }: { status: EpisodeStatus }) {
  const [first] = useState(status);
  const { label, tone } = LOOK[status];
  const pop = status !== first ? " badge-pop" : "";
  return (
    <span key={status} className={`badge badge-${tone}${pop}`}>
      {label}
    </span>
  );
}
