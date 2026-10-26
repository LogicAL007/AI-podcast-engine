import { useState } from "react";
import { useSearchParams } from "react-router";

import { useDeleteVoice, useVoices } from "../../api/queries";
import type { VoiceRead } from "../../api/types";
import { formatTime } from "../../audio/wav";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button, LinkButton } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { Skeleton } from "../../components/Skeleton";
import { WaveformPlayer } from "../../components/WaveformPlayer";
import { usePageTitle } from "../../hooks/usePageTitle";
import { formatDate } from "../format";

/** Your registered voices, each with its consent record; delete one to withdraw it. */
export function VoicesPage() {
  usePageTitle("Voice studio");
  const voices = useVoices();
  const [params] = useSearchParams();
  const remove = useDeleteVoice();
  const [deleting, setDeleting] = useState<VoiceRead | null>(null);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Voice studio</h1>
          <p className="muted">
            Recorded voices your hosts can speak with, each kept with its
            consent.
          </p>
        </div>
        <LinkButton to="/voices/new">Add a voice</LinkButton>
      </div>
      <div className="stack">
        {params.get("added") === "1" ? (
          <Alert tone="success">
            Voice registered. Give it to a host in a show&apos;s settings, under
            Host voices.
          </Alert>
        ) : null}
        <Alert tone="info">
          Voices are cloned by the Chatterbox voice engine, when the server uses
          it. Episodes voiced with a cloned voice are labelled AI-generated, and
          the credits name the speaker.
        </Alert>
        {voices.isPending ? (
          <Skeleton label="Loading your voices" rows={2} />
        ) : null}
        <ErrorAlert error={voices.error} />
        {voices.data?.total === 0 ? (
          <EmptyState
            title="No voices yet"
            action={<LinkButton to="/voices/new">Record a voice</LinkButton>}
          >
            Record or upload 15 to 30 seconds of one person speaking, after they
            complete the consent form.
          </EmptyState>
        ) : null}
        {voices.data?.items.map((voice) => (
          <article
            key={voice.voice_id}
            className="card voice-card stack"
            aria-labelledby={`voice-${voice.voice_id}`}
          >
            <div className="voice-card-head">
              <div className="stack" style={{ gap: "var(--space-1)" }}>
                <h2 id={`voice-${voice.voice_id}`} className="voice-name">
                  {voice.name}
                </h2>
                <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
                  {voice.speaker} · {formatTime(voice.duration_seconds)} ·{" "}
                  {voice.source === "recorded" ? "recorded here" : "uploaded"}
                </p>
              </div>
              <Button variant="ghost" onClick={() => setDeleting(voice)}>
                Delete
              </Button>
            </div>
            <WaveformPlayer src={voice.audio} title={voice.name} />
            <p className="consent-line">
              <span className="consent-badge">Consent on file</span>{" "}
              {voice.consent.relationship === "self"
                ? `Signed by ${voice.consent.signed_by}, their own voice`
                : `Signed by ${voice.consent.signed_by}, with written permission (${voice.consent.permission_record})`}
              , {formatDate(voice.consent.agreed_at)} · form{" "}
              {voice.consent.version}
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
        This withdraws consent: the recording is deleted, and hosts that used it
        go back to their built-in voice. Episodes already published keep their
        audio.
      </ConfirmDialog>
    </>
  );
}
