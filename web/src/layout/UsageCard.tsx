import { useUsage } from "../api/queries";
import type { UsageRead } from "../api/types";

const VOICES: Record<string, string> = {
  chatterbox: "Voices: Chatterbox on this computer, no quota",
  say: "Voices: this computer's system voice",
  placeholder: "Voices: placeholder tones",
};

function hours(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  return h >= 1 ? `${h} h` : `${Math.max(1, Math.round(seconds / 60))} min`;
}

/** One model's line: "13 of 18 left", or the count when there is no cap. */
function line(model: UsageRead["models"][number]): string {
  const what = model.kind === "text" ? "script" : "voice";
  return model.limit === null
    ? `${model.used} ${what} requests today`
    : `${model.left} of ${model.limit} ${what} requests left`;
}

/**
 * Today's request budget at the foot of the sidebar, under the product's name rather than the
 * model's: shared by every account and the bot, and reset at midnight Pacific time.
 */
export function UsageCard({ collapsed }: { collapsed: boolean }) {
  const usage = useUsage();
  if (!usage.data?.models) return null;
  const { models, resets_in_seconds, voice_engine, writer } = usage.data;
  const main = models.find((m) => m.kind === "text") ?? models[0];
  const share =
    main && main.limit ? (main.left ?? 0) / Math.max(main.limit, 1) : 1;
  const low = main?.limit != null && share <= 0.25;
  const summary = main
    ? line(main)
    : "The writing model is off: no daily quota applies";

  if (collapsed) {
    return (
      <p
        className={low ? "usage-mini usage-low" : "usage-mini"}
        title={`Today's Oasis budget: ${summary}`}
        data-tour="nav-usage"
      >
        {main?.limit != null ? main.left : "∞"}
      </p>
    );
  }
  return (
    <section
      className="usage-card"
      aria-labelledby="usage-title"
      data-tour="nav-usage"
    >
      <h2 id="usage-title" className="usage-title">
        Today's Oasis budget
      </h2>
      <p className="usage-main">
        <strong>{summary}</strong>
      </p>
      {main?.limit != null ? (
        <div
          className={low ? "usage-bar usage-low" : "usage-bar"}
          role="meter"
          aria-label="Script requests left today"
          aria-valuemin={0}
          aria-valuemax={main.limit}
          aria-valuenow={main.left ?? 0}
        >
          <span style={{ width: `${Math.round(share * 100)}%` }} />
        </div>
      ) : null}
      {models
        .filter((m) => m !== main)
        .map((m) => (
          <p key={m.model} className="usage-line">
            {line(m)}
          </p>
        ))}
      {VOICES[voice_engine] ? (
        <p className="usage-line">{VOICES[voice_engine]}</p>
      ) : null}
      {writer === "offline" ? (
        <p className="usage-line">Scripts: written offline, no quota</p>
      ) : null}
      {main ? (
        <p className="usage-reset">
          Resets in {hours(resets_in_seconds)} (midnight Pacific)
        </p>
      ) : null}
    </section>
  );
}
