import { useRef, useState, type ChangeEvent } from "react";

import { API_BASE } from "../../api/client";
import { useDeleteUpload, useUploadPdf, useUploads } from "../../api/queries";
import type { UploadRead } from "../../api/types";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState } from "../../components/EmptyState";
import { Skeleton } from "../../components/Skeleton";
import { formatBytes, formatDate } from "../format";

const MAX_MB = 25; // the API's default MAX_UPLOAD_MB

export function UploadsTab({ showId }: { showId: string }) {
  const uploads = useUploads(showId);
  const upload = useUploadPdf(showId);
  const remove = useDeleteUpload(showId);
  const input = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<UploadRead | null>(null);

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow choosing the same file again
    if (!file) return;
    setTooBig(
      file.size > MAX_MB * 1024 * 1024
        ? `${file.name} is larger than ${MAX_MB} MB.`
        : null,
    );
    if (file.size <= MAX_MB * 1024 * 1024) upload.mutate(file);
  }

  return (
    <div className="stack">
      <div className="spread">
        <p className="muted">
          PDFs are read like source pages; their text is cited by page. Up to{" "}
          {MAX_MB} MB each.
        </p>
        <span>
          <input
            ref={input}
            id="pdf-upload"
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={choose}
          />
          <Button
            busy={upload.isPending}
            onClick={() => input.current?.click()}
          >
            Upload PDF
          </Button>
        </span>
      </div>
      {tooBig ? <Alert tone="error">{tooBig}</Alert> : null}
      <ErrorAlert error={upload.error} />
      {upload.isSuccess ? (
        <Alert tone="success">
          Uploaded. It is read the next time you generate an episode.
        </Alert>
      ) : null}
      {uploads.isPending ? <Skeleton label="Loading uploads" rows={2} /> : null}
      <ErrorAlert error={uploads.error} />
      {uploads.data && uploads.data.total === 0 ? (
        <EmptyState title="No PDFs uploaded">
          Upload a PDF to use it as a source.
        </EmptyState>
      ) : null}
      {uploads.data && uploads.data.total > 0 ? (
        <ul className="list">
          {uploads.data.items.map((item) => (
            <li key={item.upload_id} className="list-item">
              <span className="stack" style={{ gap: "var(--space-1)" }}>
                <a className="list-item-title" href={`${API_BASE}${item.file}`}>
                  {item.filename}
                </a>
                <span className="muted" style={{ fontSize: "var(--text-sm)" }}>
                  {formatBytes(item.size_bytes)} · uploaded{" "}
                  {formatDate(item.created_at)}
                </span>
              </span>
              <Button
                variant="ghost"
                onClick={() => setDeleting(item)}
                aria-label={`Delete ${item.filename}`}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <ConfirmDialog
        open={deleting !== null}
        title="Delete this PDF?"
        confirmLabel="Delete"
        danger
        busy={remove.isPending}
        error={remove.error}
        onClose={() => {
          setDeleting(null);
          remove.reset();
        }}
        onConfirm={() =>
          deleting &&
          remove.mutate(deleting.upload_id, {
            onSuccess: () => setDeleting(null),
          })
        }
      >
        {deleting?.filename} is removed. Episodes already published keep what
        they said.
      </ConfirmDialog>
    </div>
  );
}
