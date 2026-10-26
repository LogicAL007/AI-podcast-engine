import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "../../api/client";
import { useShow } from "../../api/queries";
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
      <Tabs
        label="Show sections"
        tabs={TABS}
        active={tab}
        onChange={(id) =>
          setParams(id === "episodes" ? {} : { tab: id }, { replace: true })
        }
      >
        {tab === "episodes" ? <EpisodesTab show={show.data} /> : null}
        {tab === "sources" ? <SourcesTab showId={showId} /> : null}
        {tab === "uploads" ? <UploadsTab showId={showId} /> : null}
        {tab === "settings" ? <SettingsTab show={show.data} /> : null}
      </Tabs>
    </>
  );
}
