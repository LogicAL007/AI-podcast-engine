import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import { useShow, useStartEpisode } from "../../api/queries";
import { useAssistant } from "../../bots/assistant";
import { ErrorAlert } from "../../components/Alert";
import { Skeleton } from "../../components/Skeleton";
import { Tabs } from "../../components/Tabs";
import { NotFoundPage } from "../NotFoundPage";
import { EpisodesTab } from "./EpisodesTab";
import { SettingsTab } from "./SettingsTab";
import { SourcesTab } from "./SourcesTab";
import { UploadsTab } from "./UploadsTab";
import { usePageTitle } from "../../hooks/usePageTitle";

const TABS = [
  { id: "episodes", label: "Episodes" },
  { id: "sources", label: "Sources" },
  { id: "uploads", label: "PDF uploads" },
  { id: "settings", label: "Settings" },
];

export function ShowPage() {
  const { showId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some((t) => t.id === params.get("tab"))
    ? (params.get("tab") as string)
    : "episodes";
  const show = useShow(showId);
  usePageTitle(show.data?.topic ?? "Show");
  const start = useStartEpisode(showId);
  const navigate = useNavigate();
  const openTab = (id: string) =>
    setParams(id === "episodes" ? {} : { tab: id }, { replace: true });
  const noSources = show.data ? show.data.sources.length === 0 : false;
  useAssistant(
    show.data
      ? {
          page: "show",
          key: `show:${showId}`,
          moment: "show",
          mode: "greeting",
          line: noSources
            ? "Add a source page in Settings, or upload a PDF, then generate an episode."
            : "Ready when you are: generate an episode from these sources.",
          hint: "Generating reads the sources again, plans the segments, writes and fact-checks the script, then voices and publishes it. You can leave the page while it works.",
          showId,
          actions: [
            {
              id: "generate_episode",
              label: "Generate an episode",
              run: () =>
                start
                  .mutateAsync()
                  .then((episode) =>
                    navigate(`/episodes/${episode.episode_id}`),
                  ),
              confirm: {
                title: "Generate an episode?",
                body: "It reads the sources, writes and fact-checks a script, then voices it. With the model on, that uses your Oasis quota.",
                confirmLabel: "Generate",
              },
            },
            {
              id: "open_uploads",
              label: "Upload a PDF",
              run: () => openTab("uploads"),
            },
            {
              id: "open_settings",
              label: "Settings",
              hidden: true,
              run: () => openTab("settings"),
            },
          ],
          questions: [
            "What happens when I generate?",
            "What makes a good source?",
          ],
          tour: [
            {
              target: "show-generate",
              title: "Make an episode",
              text: "Generate writes a new episode from this show's sources. If nothing changed since the last one, none is made.",
            },
            {
              target: "show-tabs",
              title: "Everything about the show",
              text: "Its episodes, the sections read from its sources, PDFs you uploaded, and its settings (hosts, voices, length, tone).",
            },
          ],
        }
      : null,
  );

  if (show.error instanceof ApiError && show.error.status === 404)
    return <NotFoundPage />;
  if (show.isPending) return <Skeleton kind="page" label="Loading the show" />;
  if (!show.data) return <ErrorAlert error={show.error} />;

  return (
    <>
      <div className="breadcrumb">
        <Link to="/shows">Shows</Link>
      </div>
      <div className="page-header">
        <div>
          <h1>{show.data.topic}</h1>
          <p className="muted">
            {show.data.target_minutes} min · {show.data.host_count} hosts ·{" "}
            {show.data.tone} tone · {show.data.language}
          </p>
        </div>
      </div>
      <div data-tour="show-tabs">
        <Tabs label="Show sections" tabs={TABS} active={tab} onChange={openTab}>
          {tab === "episodes" ? <EpisodesTab show={show.data} /> : null}
          {tab === "sources" ? <SourcesTab showId={showId} /> : null}
          {tab === "uploads" ? <UploadsTab showId={showId} /> : null}
          {tab === "settings" ? <SettingsTab show={show.data} /> : null}
        </Tabs>
      </div>
    </>
  );
}
