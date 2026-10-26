import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import {
  useDeleteEpisode,
  useEpisode,
  useEpisodeAction,
  useShow,
} from "../../api/queries";
import type { EpisodeRead } from "../../api/types";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ProgressSteps } from "../../components/ProgressSteps";
import { Skeleton } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { Tabs } from "../../components/Tabs";
import { AssistantDock } from "../../bots/AssistantDock";
import { useDoneNotice } from "../../hooks/useDoneNotice";
import { useEpisodeEvents } from "../../hooks/useEpisodeEvents";
import { formatDate } from "../format";
import { NotFoundPage } from "../NotFoundPage";
import { ClaimsTab } from "./ClaimsTab";
import { ListenTab } from "./ListenTab";
import { RunsTab } from "./RunsTab";
import { ScriptTab } from "./ScriptTab";
import { usePageTitle } from "../../hooks/usePageTitle";

const TABS = [
  { id: "listen", label: "Listen" },
  { id: "script", label: "Script" },
  { id: "claims", label: "Fact-check" },
  { id: "runs", label: "Runs" },
];

const RUNNING = new Set(["queued", "processing"]);

function defaultTab(episode: EpisodeRead): string {
  return episode.status === "needs_review" ? "script" : "listen";
}

export function EpisodePage() {
  const { episodeId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [pollEvery, setPollEvery] = useState<number | false>(false);
  const episode = useEpisode(episodeId, pollEvery);
  const running = episode.data ? RUNNING.has(episode.data.status) : false;
  const mode = useEpisodeEvents(episodeId, running);
  const wantPolling = running && mode === "polling" ? 5_000 : false;
  if (wantPolling !== pollEvery) setPollEvery(wantPolling);

  if (episode.error instanceof ApiError && episode.error.status === 404)
    return <NotFoundPage />;
  if (episode.isPending)
    return <Skeleton kind="page" label="Loading the episode" />;
  if (!episode.data) return <ErrorAlert error={episode.error} />;

  const data = episode.data;
  const requested = params.get("tab");
  const tab = TABS.some((t) => t.id === requested)
    ? (requested as string)
    : defaultTab(data);

  return (
    <>
      <EpisodeHeader episode={data} following={mode !== "idle"} />
      <Tabs
        label="Episode sections"
        tabs={TABS}
        active={tab}
        onChange={(id) => setParams({ tab: id }, { replace: true })}
      >
        {tab === "listen" ? <ListenTab episode={data} /> : null}
        {tab === "script" ? <ScriptTab episode={data} /> : null}
        {tab === "claims" ? <ClaimsTab episodeId={data.episode_id} /> : null}
        {tab === "runs" ? <RunsTab episodeId={data.episode_id} /> : null}
      </Tabs>
      <AssistantDock
        episodeId={data.episode_id}
        status={data.status}
        stage={data.stage}
      />
    </>
  );
}

function EpisodeHeader({
  episode,
  following,
}: {
  episode: EpisodeRead;
  following: boolean;
}) {
  const show = useShow(episode.show_id);
  usePageTitle(
    show.data
      ? `Episode ${episode.revision} · ${show.data.topic}`
      : `Episode ${episode.revision}`,
  );
  const retry = useEpisodeAction(episode.episode_id, "retry");
  const cancel = useEpisodeAction(episode.episode_id, "cancel");
  const remove = useDeleteEpisode(episode.episode_id, episode.show_id);
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState<"cancel" | "delete" | null>(null);
  const canRetry =
    episode.status === "failed" || episode.status === "cancelled";
  const canCancel = ["queued", "processing", "needs_review"].includes(
    episode.status,
  );
  const running = RUNNING.has(episode.status);
  const notice = useDoneNotice(
    episode.status,
    show.data
      ? `${show.data.topic}, episode ${episode.revision}`
      : `Episode ${episode.revision}`,
  );

  return (
    <div className="stack" style={{ marginBottom: "var(--space-5)" }}>
      <div className="breadcrumb">
        <Link to="/shows">Shows</Link>
        {" / "}
        <Link to={`/shows/${episode.show_id}`}>
          {show.data?.topic ?? "Show"}
        </Link>
      </div>
      <div className="page-header" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: "var(--space-2)" }}>
          <div className="row">
            <h1>Episode {episode.revision}</h1>
            <StatusBadge status={episode.status} />
          </div>
          <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
            Started {formatDate(episode.created_at)}
            {episode.published_at
              ? ` · published ${formatDate(episode.published_at)}`
              : ""}
            {episode.rewrite_count
              ? ` · rewritten ${episode.rewrite_count} time${episode.rewrite_count === 1 ? "" : "s"} by the fact-check`
              : ""}
          </p>
        </div>
        <div className="row">
          {running && notice.permission === "default" ? (
            <Button variant="ghost" onClick={() => void notice.ask()}>
              Notify me when it is done
            </Button>
          ) : null}
          {running && notice.permission === "granted" ? (
            <span className="muted" style={{ fontSize: "var(--text-sm)" }}>
              You will be notified when it is done.
            </span>
          ) : null}
          {canRetry ? (
            <Button busy={retry.isPending} onClick={() => retry.mutate()}>
              Retry
            </Button>
          ) : null}
          {canCancel ? (
            <Button variant="secondary" onClick={() => setConfirm("cancel")}>
              Cancel
            </Button>
          ) : null}
          <Button variant="ghost" onClick={() => setConfirm("delete")}>
            Delete
          </Button>
        </div>
      </div>

      <div className="card card-muted">
        <ProgressSteps status={episode.status} stage={episode.stage} />
        {following ? (
          <p
            className="muted"
            style={{ fontSize: "var(--text-xs)", marginTop: "var(--space-2)" }}
          >
            Updating live.
          </p>
        ) : null}
      </div>
      {episode.status === "failed" && episode.error ? (
        <Alert tone="error">It stopped with an error: {episode.error}</Alert>
      ) : null}
      {episode.status === "needs_review" ? (
        <Alert tone="info">
          This episode is waiting for you. Review the script and the fact-check,
          edit any line, then approve it to voice and publish.
        </Alert>
      ) : null}
      {episode.status === "unchanged" ? (
        <Alert tone="info">
          None of the sources changed, so no new episode was needed.
        </Alert>
      ) : null}
      <ErrorAlert error={retry.error} />

      <ConfirmDialog
        open={confirm === "cancel"}
        title="Cancel this episode?"
        confirmLabel="Cancel episode"
        danger
        busy={cancel.isPending}
        error={cancel.error}
        onClose={() => setConfirm(null)}
        onConfirm={() =>
          cancel.mutate(undefined, { onSuccess: () => setConfirm(null) })
        }
      >
        No further steps run. You can retry it later.
      </ConfirmDialog>
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this episode?"
        confirmLabel="Delete episode"
        danger
        busy={remove.isPending}
        error={remove.error}
        onClose={() => setConfirm(null)}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () =>
              navigate(`/shows/${episode.show_id}`, { replace: true }),
          })
        }
      >
        Its script, audio and show notes are deleted, and it leaves the feed.
      </ConfirmDialog>
    </div>
  );
}
