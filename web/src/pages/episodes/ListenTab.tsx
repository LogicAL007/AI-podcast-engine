import Markdown from "react-markdown";

import { useNotes } from "../../api/queries";
import type { EpisodeRead } from "../../api/types";
import { Alert, ErrorAlert } from "../../components/Alert";
import { AudioPlayer } from "../../components/AudioPlayer";
import { EmptyState } from "../../components/EmptyState";
import { Spinner } from "../../components/Spinner";

/** The test voice: tones in the rhythm of speech, not words. */
const PLACEHOLDER_VOICE = "placeholder-tones";

export function ListenTab({ episode }: { episode: EpisodeRead }) {
  const notes = useNotes(episode.links.notes);
  const audio = episode.links.audio;

  if (!audio && !episode.links.notes) {
    return (
      <EmptyState title="Nothing to listen to yet">
        The audio and show notes appear here once the episode is voiced and
        published.
      </EmptyState>
    );
  }
  return (
    <div className="stack" style={{ gap: "var(--space-6)" }}>
      {audio ? (
        <section className="stack" aria-labelledby="audio-heading">
          <h2 id="audio-heading" style={{ fontSize: "var(--text-lg)" }}>
            Audio
          </h2>
          {episode.voice_provider === PLACEHOLDER_VOICE ? (
            <Alert tone="info">
              This audio is placeholder tones, not speech: it was voiced with
              the test voice. Generate a new episode to hear real voices, or ask
              your administrator to set one up.
            </Alert>
          ) : null}
          <AudioPlayer
            src={audio}
            title={`Episode ${episode.revision} audio`}
          />
          <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
            This episode is AI-generated. A full transcript is in the Script
            tab.
          </p>
        </section>
      ) : null}
      {episode.links.notes ? (
        <section className="stack" aria-labelledby="notes-heading">
          <h2 id="notes-heading" style={{ fontSize: "var(--text-lg)" }}>
            Show notes
          </h2>
          {notes.isPending ? <Spinner label="Loading show notes" /> : null}
          <ErrorAlert error={notes.error} />
          {notes.data ? (
            <div className="notes card">
              {/* react-markdown renders no raw HTML, so the notes cannot inject markup. */}
              <Markdown>{notes.data}</Markdown>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
