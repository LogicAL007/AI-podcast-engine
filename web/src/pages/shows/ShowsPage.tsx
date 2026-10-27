import { Link, useNavigate, useSearchParams } from "react-router";

import { PAGE_SIZE, useShows } from "../../api/queries";
import { ErrorAlert } from "../../components/Alert";
import { LinkButton } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { Pagination } from "../../components/Pagination";
import { Skeleton } from "../../components/Skeleton";
import { useRememberedFlag } from "../../hooks/useRememberedFlag";
import { useAssistant } from "../../bots/assistant";
import { Welcome } from "./Welcome";
import { usePageTitle } from "../../hooks/usePageTitle";

export function ShowsPage() {
  usePageTitle("Shows");
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const shows = useShows(offset);
  const [welcomeSkipped, skipWelcome] = useRememberedFlag("pe.welcome.skipped");
  const navigate = useNavigate();
  const any = (shows.data?.total ?? 0) > 0;
  useAssistant({
    page: "shows",
    key: "shows",
    moment: "shows",
    mode: "greeting",
    line: any
      ? "Pick a show to see its episodes, or start a new one."
      : "Let's make your first show!",
    hint: "This is your studio. Each show reads the sources you give it and turns them into fact-checked episodes. I'm on every page: tap me, ask me anything, or let me show you around.",
    actions: [
      { id: "new_show", label: "New show", run: () => navigate("/shows/new") },
    ],
    questions: [
      "How is an episode made?",
      "What makes a good source?",
      "Can I use my own voice?",
    ],
    tour: [
      {
        target: "new-show",
        title: "Start a show",
        text: "A show is a topic plus the pages, feeds and PDFs to read. Every episode is written only from them.",
      },
      {
        target: "shows-list",
        title: "Your shows",
        text: "Open a show to generate episodes, check its sources and change its settings.",
      },
      {
        target: "nav-voices",
        title: "Voice studio",
        text: "Record or upload a voice (with the speaker's consent) and give it to a host.",
      },
      {
        target: "nav-companion",
        title: "That's me!",
        text: "Rebuild me any time: my shape, face, colours, outfit, personality and voice.",
      },
    ],
  });

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Shows</h1>
          <p className="muted">Each show turns its sources into episodes.</p>
        </div>
        <LinkButton to="/shows/new" data-tour="new-show">
          New show
        </LinkButton>
      </div>
      {shows.isPending ? <Skeleton label="Loading your shows" /> : null}
      <ErrorAlert error={shows.error} />
      {shows.data && shows.data.total === 0 && !welcomeSkipped ? (
        <Welcome onSkip={() => skipWelcome(true)} />
      ) : null}
      {shows.data && shows.data.total === 0 && welcomeSkipped ? (
        <EmptyState
          title="No shows yet"
          action={
            <LinkButton to="/shows/new">Create your first show</LinkButton>
          }
        >
          A show has a topic and a set of sources. Episodes are written from
          those sources and checked against them.
        </EmptyState>
      ) : null}
      {shows.data && shows.data.total > 0 ? (
        <div className="stack">
          <ul className="list" data-tour="shows-list">
            {shows.data.items.map((show) => (
              <li key={show.show_id}>
                <Link className="list-item" to={`/shows/${show.show_id}`}>
                  <span className="stack" style={{ gap: "var(--space-1)" }}>
                    <span className="list-item-title">{show.topic}</span>
                    <span
                      className="muted"
                      style={{ fontSize: "var(--text-sm)" }}
                    >
                      {show.sources.length} source page
                      {show.sources.length === 1 ? "" : "s"} ·{" "}
                      {show.target_minutes} min · {show.host_count} host
                      {show.host_count === 1 ? "" : "s"}
                      {show.review_before_voice
                        ? " · reviewed before voicing"
                        : ""}
                    </span>
                  </span>
                  <span aria-hidden="true" className="muted">
                    →
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <Pagination
            offset={offset}
            limit={PAGE_SIZE}
            total={shows.data.total}
            onChange={(next) => setParams(next ? { offset: String(next) } : {})}
          />
        </div>
      ) : null}
    </>
  );
}
