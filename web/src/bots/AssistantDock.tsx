import type { EpisodeStatus } from "../api/types";
import { useRememberedFlag } from "../hooks/useRememberedFlag";
import { GlassPanel } from "../visual/GlassPanel";
import { useAvatar } from "./avatar";
import { AvatarFace } from "./AvatarFace";
import { BotFigure } from "./BotFigure";
import { botFor } from "./botMode";

/**
 * A floating glass card with the assistant bot for the episode's current moment. The first time
 * a creator meets a moment, the bot explains it (readable by screen readers) until they press
 * "Got it"; after that it gives a short status, which the page also states in words. Closing the
 * dock is remembered per episode, and a small bot button brings it back. The bot is the one the
 * person chose (name and look), and it can be tapped, hovered and spun.
 */
export function AssistantDock({
  episodeId,
  status,
  stage,
}: {
  episodeId: string;
  status: EpisodeStatus;
  stage: string | null | undefined;
}) {
  const bot = botFor(status, stage);
  const avatar = useAvatar();
  const [closed, setClosed] = useRememberedFlag(`pe.dock.closed.${episodeId}`);
  const [hintSeen, setHintSeen] = useRememberedFlag(
    `pe.hint.${bot?.moment ?? "none"}`,
  );
  if (!bot) return null;
  if (closed) {
    return (
      <button
        type="button"
        className="dock-reopen"
        onClick={() => setClosed(false)}
        aria-label="Show the assistant"
      >
        <AvatarFace avatar={avatar} />
      </button>
    );
  }
  return (
    <aside className="assistant-dock" aria-label="Assistant">
      <GlassPanel radius={26}>
        <div className="dock-inner">
          <div className="dock-bot">
            <BotFigure mode={bot.mode} interactive />
          </div>
          <div className="dock-text">
            <span className="dock-name" aria-hidden="true">
              {avatar.name}
            </span>
            {hintSeen ? (
              <span className="dock-line" aria-hidden="true">
                {bot.line}
              </span>
            ) : (
              <>
                <p className="dock-hint">{bot.hint}</p>
                <button
                  type="button"
                  className="link-button dock-got-it"
                  onClick={() => setHintSeen(true)}
                >
                  Got it
                </button>
              </>
            )}
          </div>
          <button
            type="button"
            className="dock-close"
            onClick={() => setClosed(true)}
            aria-label="Hide the assistant"
          >
            ×
          </button>
        </div>
      </GlassPanel>
    </aside>
  );
}
