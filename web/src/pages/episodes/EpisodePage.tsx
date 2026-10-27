import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import {
  useDeleteEpisode,
  useEpisode,
  useEpisodeAction,
  useShow,
  useStartEpisode,
} from "../../api/queries";
import type { EpisodeRead } from "../../api/types";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ProgressSteps } from "../../components/ProgressSteps";
import { Skeleton } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { Tabs } from "../../components/Tabs";
import {
  useAssistant,
  type BotAction,
  type PageAssist,
} from "../../bots/assistant";
import { botFor } from "../../bots/botMode";
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

const QUESTIONS: Partial<Record<EpisodeRead["status"], string[]>> = {
  queued: ["How long will it take?", "What are the eight steps?"],
  processing: ["What happens in this step?", "How long will it take?"],
  needs_review: ["Which claims were cut, and why?", "How do I approve it?"],
  failed: ["Why did it stop?", "Will Retry redo everything?"],
  published: [
    "How do I listen in a podcast app?",
    "What happens if I generate again?",
  ],
};

const TOUR = [
  {
    target: "episode-progress",
    title: "Where it is",
    text: "The bar and the word above it show the step your episode is on. Press ? for what each step does.",
  },
  {
    target: "episode-actions",
    title: "What you can do",
    text: "Retry a stopped episode, cancel one that is running, or delete it.",
  },
  {
    target: "episode-tabs",
    title: "Look inside",
    text: "Listen to it, read and edit the script, see each claim's fact-check verdict, and the timing of every step.",
  },
];

/** What the bot says and offers on an episode: the moment from botMode, and its next steps. */
function useEpisodeAssist(
  episode: EpisodeRead | undefined,
  openTab: (tab: string) => void,
): PageAssist | null {
  const id = episode?.episode_id ?? "";
  const approve = useEpisodeAction(id, "approve");
  const retry = useEpisodeAction(id, "retry");
  const cancel = useEpisodeAction(id, "cancel");
  const again = useStartEpisode(episode?.show_id ?? "");
  const navigate = useNavigate();
  if (!episode) return null;
  const status = episode.status;
  const bot = botFor(status, episode.stage);
  const tab = (tabId: string, label: string, hidden = false): BotAction => ({
    id: `open_${tabId === "claims" ? "factcheck" : tabId}`,
    label,
    hidden,
    run: () => openTab(tabId),
  });
  const actions: BotAction[] = [];
  if (status === "needs_review") {
    actions.push(
      tab("script", "Open the script"),
      tab("claims", "See the fact-check"),
      {
        id: "approve",
        label: "Approve",
        run: () => approve.mutateAsync(),
        confirm: {
          title: "Approve this episode?",
          body: "It will be voiced and published to your feed. Voicing uses your text-to-speech quota.",
          confirmLabel: "Approve and publish",
        },
      },
    );
  } else if (status === "failed" || status === "cancelled") {
    actions.push({
      id: "retry",
      label: "Retry",
      run: () => retry.mutateAsync(),
    });
    actions.push(tab("runs", "See the steps' timings", true));
  } else if (status === "published") {
    actions.push(tab("listen", "Listen"), {
      id: "generate_episode",
      label: "Make the next episode",
      run: () =>
        again
          .mutateAsync()
          .then((next) => navigate(`/episodes/${next.episode_id}`)),
      confirm: {
        title: "Make the next episode?",
        body: "It reads the sources again and redoes only what changed. Writing and voicing it can use your Gemini quota.",
        confirmLabel: "Make it",
      },
    });
  } else if (episode.stage === "factcheck") {
    actions.push(tab("claims", "Watch the fact-check"));
  }
  if (["queued", "processing", "needs_review"].includes(status)) {
    actions.push({
      id: "cancel",
      label: "Cancel",
      hidden: true,
      run: () => cancel.mutateAsync(),
      confirm: {
        title: "Cancel this episode?",
        body: "No further steps run. You can retry it later.",
        confirmLabel: "Cancel episode",
        danger: true,
      },
    });
  }
  for (const [tabId, label] of [
    ["script", "Open the script"],
    ["claims", "See the fact-check"],
    ["listen", "Listen"],
  ] as const) {
    if (
      !actions.some(
        (a) => a.id === `open_${tabId === "claims" ? "factcheck" : tabId}`,
      )
    )
      actions.push(tab(tabId, label, true));
  }
  if (!bot) {
    // Unchanged: the page says what happened; the bot just offers help.
    return {
      page: "episode",
      key: episode.episode_id,
      moment: "episode-other",
      mode: "greeting",
      line: "Nothing changed in the sources, so there was nothing new to make.",
      actions,
      questions: QUESTIONS[status],
      tour: TOUR,
      episodeId: episode.episode_id,
      showId: episode.show_id,
    };
  }
  return {
    page: "episode",
    key: episode.episode_id,
    moment: bot.moment,
    mode: bot.mode,
    line:
      status === "failed"
        ? "It stopped. Retry carries on from the step that failed."
        : bot.line,
    hint: status === "failed" ? undefined : bot.hint,
    actions,
    questions: QUESTIONS[status],
    tour: TOUR,
    episodeId: episode.episode_id,
    showId: episode.show_id,
  };
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
  useAssistant(
    useEpisodeAssist(episode.data, (tab) =>
      setParams({ tab }, { replace: true }),
    ),
  );

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
      <div data-tour="episode-tabs">
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
      </div>
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
        <div className="row" data-tour="episode-actions">
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

      <div className="card card-muted" data-tour="episode-progress">
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
