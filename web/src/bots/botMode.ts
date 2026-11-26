import type { EpisodeStatus } from "../api/types";
import { stageVerb } from "../components/ProgressSteps";

/** The assistant animations: three tied to real moments in an episode's life, and a wave that
 * greets a new creator. */
export type BotMode = "working" | "reviewing" | "celebrating" | "greeting";

export interface BotLine {
  mode: BotMode;
  name: string;
  line: string;
  /** Which moment this is; a creator sees each moment's hint once. */
  moment: "queued" | "making" | "factcheck" | "review" | "published";
  /** The first-time explanation of this moment, in place of the short line. */
  hint: string;
}

const HINTS: Record<BotLine["moment"], string> = {
  queued:
    "Every episode goes through eight steps, from gathering your sources to publishing. You can leave this page; it keeps going.",
  making:
    "I am reading your sources and writing the hosts' dialogue. Every line must come from a source, and the bar above shows the step.",
  factcheck:
    "I match each claim in the script to the passage it came from. Claims I cannot support are rewritten or removed.",
  review:
    "Open the Script tab and edit any line that reads wrong, look over the Fact-check tab, then press Approve to voice and publish.",
  published:
    "Play it in the Listen tab, or add the feed link to any podcast app. Generating again later redoes only what changed.",
};

/** Which bot appears for an episode, and what it says; null when there is nothing to help with. */
export function botFor(
  status: EpisodeStatus,
  stage: string | null | undefined,
): BotLine | null {
  const line = lineFor(status, stage);
  return line ? { ...line, hint: HINTS[line.moment] } : null;
}

function lineFor(
  status: EpisodeStatus,
  stage: string | null | undefined,
): Omit<BotLine, "hint"> | null {
  switch (status) {
    case "queued":
      return {
        mode: "working",
        name: "Scout",
        line: "Warming up: your episode is next in line.",
        moment: "queued",
      };
    case "processing":
      return stage === "factcheck"
        ? {
            mode: "reviewing",
            name: "Checker",
            line: "Checking every claim against its source.",
            moment: "factcheck",
          }
        : {
            mode: "working",
            name: "Scout",
            line: `On it: ${stageVerb(stage).toLowerCase()}…`,
            moment: "making",
          };
    case "needs_review":
      return {
        mode: "reviewing",
        name: "Checker",
        line: "Ready for your review: read the script, then approve it.",
        moment: "review",
      };
    case "published":
      return {
        mode: "celebrating",
        name: "Herald",
        line: "Published! It is in your feed and ready to play.",
        moment: "published",
      };
    default:
      return null; // failed, cancelled, unchanged: the page says what happened
  }
}
