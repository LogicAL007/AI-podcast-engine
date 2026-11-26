import { useState } from "react";
import { useNavigate } from "react-router";

import { API_BASE } from "../../api/client";
import { useDeleteShow, useUpdateShow, useVoices } from "../../api/queries";
import type { ShowRead } from "../../api/types";
import { Alert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ShowForm } from "./ShowForm";
import { valuesOf } from "./showValues";

export function SettingsTab({ show }: { show: ShowRead }) {
  const update = useUpdateShow(show.show_id);
  const voices = useVoices();
  const remove = useDeleteShow(show.show_id);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const feed = `${window.location.origin}${API_BASE}/v1/feeds/${show.show_id}/rss.xml`;

  return (
    <div className="stack" style={{ maxWidth: "48rem", gap: "var(--space-6)" }}>
      <section className="card stack" aria-labelledby="feed-heading">
        <h2 id="feed-heading" style={{ fontSize: "var(--text-lg)" }}>
          Podcast feed
        </h2>
        <p className="muted">
          Add this address to a podcast app to subscribe. It updates as episodes
          are published.
        </p>
        <code style={{ overflowWrap: "anywhere" }}>{feed}</code>
      </section>

      <section className="card stack" aria-labelledby="edit-heading">
        <h2 id="edit-heading" style={{ fontSize: "var(--text-lg)" }}>
          Show settings
        </h2>
        {update.isSuccess ? <Alert tone="success">Saved.</Alert> : null}
        <ShowForm
          voices={voices.data?.items}
          key={show.show_id}
          initial={valuesOf(show)}
          submitLabel="Save changes"
          busy={update.isPending}
          error={update.error}
          onSubmit={(body) => update.mutate(body)}
        />
      </section>

      <section className="card stack" aria-labelledby="delete-heading">
        <h2 id="delete-heading" style={{ fontSize: "var(--text-lg)" }}>
          Delete show
        </h2>
        <p className="muted">
          Deletes the show with all its episodes, sources and uploads. This
          cannot be undone.
        </p>
        <div>
          <Button variant="danger" onClick={() => setConfirming(true)}>
            Delete show
          </Button>
        </div>
      </section>

      <ConfirmDialog
        open={confirming}
        title="Delete this show?"
        confirmLabel="Delete show"
        danger
        busy={remove.isPending}
        error={remove.error}
        onClose={() => setConfirming(false)}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => navigate("/shows", { replace: true }),
          })
        }
      >
        “{show.topic}” and everything in it will be deleted for good.
      </ConfirmDialog>
    </div>
  );
}
