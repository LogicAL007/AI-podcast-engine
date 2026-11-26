import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { useDeleteVoice, useVoices } from "../../api/queries";
import type { VoiceRead } from "../../api/types";
import { formatTime } from "../../audio/wav";
import { useAssistant } from "../../bots/assistant";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button, LinkButton } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { Skeleton } from "../../components/Skeleton";
import { WaveformPlayer } from "../../components/WaveformPlayer";
import { formatDate } from "../format";

/** The Voices tab: your recorded voices, each with its consent; delete one to withdraw it. */
export function VoicesPage() {
  const voices = useVoices();
  const [params] = useSearchParams();
  const remove = useDeleteVoice();
  const [deleting, setDeleting] = useState<VoiceRead | null>(null);
  const navigate = useNavigate();
  useAssistant({
    page: "voices",
    key: "voices",
    moment: "voices",
    mode: "greeting",
    line: "Add a voice, then try it in Type to speech.",
    hint: "Your hosts can speak with a real person's voice, but only with that person's signed consent.",
    actions: [
      {
        id: "add_voice",
        label: "Add a voice",
        run: () => navigate("/voices/new"),
      },
    ],
    questions: ["How long should a recording be?", "Why does it need consent?"],
  });

  return (
    <div className="stack">
      {params.get("added") === "1" ? (
        <Alert tone="success">Voice added. Try it in Type to speech.</Alert>
      ) : null}
      {voices.isPending ? (
        <Skeleton label="Loading your voices" rows={2} />
      ) : null}
      <ErrorAlert error={voices.error} />
      {voices.data?.total === 0 ? (
        <EmptyState
          title="No voices yet"
          action={<LinkButton to="/voices/new">Add voice</LinkButton>}
        >
          Record or upload 15 to 30 seconds of one person speaking.
        </EmptyState>
      ) : null}
      <div className="studio-grid">
        {voices.data?.items.map((voice) => (
          <article
            key={voice.voice_id}
            className="card stack studio-card"
            aria-labelledby={`voice-${voice.voice_id}`}
          >
            <div className="voice-card-head">
              <div>
                <h2
                  id={`voice-${voice.voice_id}`}
                  className="studio-card-title"
                >
                  {voice.name}
                </h2>
                <p className="muted studio-meta">
                  {voice.speaker} · {formatTime(voice.duration_seconds)}
                </p>
              </div>
              <div className="row studio-actions">
                <LinkButton
                  variant="secondary"
                  to={`/voices/speak?voice=${voice.voice_id}`}
                >
                  Try it
                </LinkButton>
                <Button variant="ghost" onClick={() => setDeleting(voice)}>
                  Delete
                </Button>
              </div>
            </div>
            <WaveformPlayer src={voice.audio} title={voice.name} />
            <p className="consent-ok">
              ✓ Consent on file
              <span className="muted">
                {" "}
                · {voice.consent.signed_by},{" "}
                {formatDate(voice.consent.agreed_at)}
              </span>
            </p>
          </article>
        ))}
      </div>
      <ConfirmDialog
        open={deleting !== null}
        title="Delete this voice?"
        confirmLabel="Delete voice"
        danger
        busy={remove.isPending}
        error={remove.error}
        onClose={() => setDeleting(null)}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.voice_id, {
            onSuccess: () => setDeleting(null),
          })
        }
      >
        This withdraws consent: the recording and clips made with it are
        deleted, and hosts that used it go back to their built-in voice.
        Published episodes keep their audio.
      </ConfirmDialog>
    </div>
  );
}
