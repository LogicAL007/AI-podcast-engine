import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import {
  useRecentEpisodes,
  useReviewQueue,
  useShows,
  useVoices,
} from "../api/queries";
import type { EpisodeStatus } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { useAssistant } from "../bots/assistant";
import { useAvatar } from "../bots/avatar";
import { ErrorAlert } from "../components/Alert";
import { Skeleton } from "../components/Skeleton";
import { StatusBadge } from "../components/StatusBadge";
import { Tabs } from "../components/Tabs";
import { usePageTitle } from "../hooks/usePageTitle";
import { formatDate, timeAgo } from "./format";
import { SHOW_TEMPLATES } from "./shows/showValues";

type Kind = "Episode" | "Show" | "Voice";

interface Row {
  key: string;
  title: string;
  kind: Kind;
  href: string;
  status?: EpisodeStatus;
  detail?: string;
  updated: string;
}

type SortKey = "title" | "kind" | "updated";

const TABS = [
  { id: "all", label: "All" },
  { id: "Episode", label: "Episodes" },
  { id: "Show", label: "Shows" },
  { id: "Voice", label: "Voices" },
];

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const GLYPHS: Record<
  Kind | "add" | "review" | "companion" | "search",
  ReactNode
> = {
  Show: (
    <>
      <rect x="3" y="4" width="14" height="12" rx="2.5" />
      <path d="M7 8.5v3M10 7v6M13 9v2" />
    </>
  ),
  Episode: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M8.5 7.5v5l4-2.5z" />
    </>
  ),
  Voice: (
    <>
      <rect x="7.5" y="2.5" width="5" height="9" rx="2.5" />
      <path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" />
    </>
  ),
  add: <path d="M10 4.5v11M4.5 10h11" />,
  review: (
    <>
      <path d="M4 4.5h12M4 8.5h7M4 12.5h5" />
      <path d="m11.5 14 2 2 3.5-4" />
    </>
  ),
  companion: (
    <>
      <rect x="4" y="5" width="12" height="10" rx="4" />
      <path d="M8 9.5v1M12 9.5v1M10 2.5V5" />
    </>
  ),
  search: (
    <>
      <circle cx="9" cy="9" r="5.5" />
      <path d="m13 13 4 4" />
    </>
  ),
};

/**
 * The signed-in home: search, quick actions, everything recent in one list, and show templates
 * (laid out after Snowflake's home page).
 */
export function HomePage() {
  usePageTitle("Home");
  const { user } = useAuth();
  const avatar = useAvatar();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const shows = useShows(0);
  const episodes = useRecentEpisodes();
  const review = useReviewQueue();
  const voices = useVoices();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; up: boolean }>({
    key: "updated",
    up: false,
  });
  const search = useRef<HTMLInputElement>(null);

  // The sidebar's search button opens this page with ?search=1.
  const wantsSearch = params.get("search") === "1";
  useEffect(() => {
    if (wantsSearch) search.current?.focus();
  }, [wantsSearch]);

  const waiting = review.data?.total ?? 0;
  const firstWaiting = review.data?.items[0]?.episode_id;

  useAssistant({
    page: "other",
    key: "home",
    moment: "home",
    mode: "greeting",
    line:
      waiting > 0
        ? `${waiting} episode${waiting === 1 ? " is" : "s are"} waiting for your review.`
        : "Welcome back! Start something new, or pick up where you left off.",
    hint: "This is home: search everything, start a show from a template, or jump back into recent work.",
    actions: [
      { id: "new_show", label: "New show", run: () => navigate("/shows/new") },
    ],
    questions: ["How is an episode made?", "Can I use my own voice?"],
    tour: [
      {
        target: "home-search",
        title: "Find anything",
        text: "Search your shows, episodes and voices by name.",
      },
      {
        target: "home-actions",
        title: "Quick actions",
        text: "Start a show, add a voice, review held episodes or change me.",
      },
      {
        target: "home-recent",
        title: "Recent work",
        text: "Everything you made, newest first. Sort by any column.",
      },
      {
        target: "home-templates",
        title: "Templates",
        text: "A topic and sources ready to go: open one, check it, create the show.",
      },
      {
        target: "nav-usage",
        title: "Today's budget",
        text: "How many Podcast Engine requests are left today. It resets at midnight Pacific time.",
      },
    ],
  });

  const rows = useMemo<Row[]>(() => {
    const topics = new Map(
      (shows.data?.items ?? []).map((s) => [s.show_id, s.topic]),
    );
    return [
      ...(episodes.data?.items ?? []).map((e) => ({
        key: `e-${e.episode_id}`,
        title: `${topics.get(e.show_id) ?? "Episode"} · episode ${e.revision}`,
        kind: "Episode" as const,
        href: `/episodes/${e.episode_id}`,
        status: e.status,
        updated: e.published_at ?? e.created_at,
      })),
      ...(shows.data?.items ?? []).map((s) => ({
        key: `s-${s.show_id}`,
        title: s.topic,
        kind: "Show" as const,
        href: `/shows/${s.show_id}`,
        detail: `${s.sources.length} source${s.sources.length === 1 ? "" : "s"}`,
        updated: s.created_at,
      })),
      ...(voices.data?.items ?? []).map((v) => ({
        key: `v-${v.voice_id}`,
        title: v.name,
        kind: "Voice" as const,
        href: "/voices",
        detail: v.speaker,
        updated: v.created_at,
      })),
    ];
  }, [shows.data, episodes.data, voices.data]);

  const needle = query.trim().toLowerCase();
  const shown = rows
    .filter((row) => tab === "all" || row.kind === tab)
    .filter((row) => !needle || row.title.toLowerCase().includes(needle))
    .sort((a, b) => {
      const order =
        sort.key === "updated"
          ? a.updated.localeCompare(b.updated)
          : a[sort.key].localeCompare(b[sort.key], undefined, {
              sensitivity: "base",
            });
      return sort.up ? order : -order;
    });

  const loading = shows.isPending || episodes.isPending || voices.isPending;
  const name = user?.email?.split("@")[0] ?? "";

  function header(key: SortKey, label: string) {
    const active = sort.key === key;
    return (
      <th
        scope="col"
        aria-sort={active ? (sort.up ? "ascending" : "descending") : "none"}
      >
        <button
          type="button"
          className={active ? "sort-button active" : "sort-button"}
          onClick={() =>
            setSort({ key, up: active ? !sort.up : key !== "updated" })
          }
        >
          {label}
          <span aria-hidden="true" className="sort-arrow">
            {active ? (sort.up ? "↑" : "↓") : "↕"}
          </span>
        </button>
      </th>
    );
  }

  const actions = [
    {
      to: "/shows/new",
      glyph: GLYPHS.add,
      title: "New show",
      text: "Turn pages, feeds and PDFs into episodes",
    },
    {
      to: "/voices/new",
      glyph: GLYPHS.Voice,
      title: "Add a voice",
      text: "Record a host's voice, with their consent",
    },
    {
      to: firstWaiting ? `/episodes/${firstWaiting}` : "/shows",
      glyph: GLYPHS.review,
      title: "Review queue",
      text:
        waiting > 0
          ? `${waiting} episode${waiting === 1 ? "" : "s"} waiting for you`
          : "Nothing waiting for review",
    },
    {
      to: "/companion",
      glyph: GLYPHS.companion,
      title: "Your companion",
      text: `Change how ${avatar.name} looks and sounds`,
    },
  ];

  return (
    <div className="home">
      <div className="home-head">
        <h1>Home</h1>
        {name ? <p className="muted">Welcome back, {name}.</p> : null}
      </div>

      <label className="home-search" data-tour="home-search">
        <span className="sr-only">Search</span>
        <Glyph>{GLYPHS.search}</Glyph>
        <input
          ref={search}
          type="search"
          placeholder="Search shows, episodes and voices"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      <section aria-labelledby="home-actions-title">
        <h2 id="home-actions-title">Quick actions</h2>
        <div className="quick-actions" data-tour="home-actions">
          {actions.map((action) => (
            <Link key={action.title} to={action.to} className="quick-action">
              <span className="quick-action-icon">
                <Glyph>{action.glyph}</Glyph>
              </span>
              <span className="quick-action-title">{action.title}</span>
              <span className="quick-action-text">{action.text}</span>
            </Link>
          ))}
        </div>
      </section>

      <section aria-labelledby="home-recent-title" data-tour="home-recent">
        <h2 id="home-recent-title">
          {needle ? `Results for “${query.trim()}”` : "Recent work"}
        </h2>
        <ErrorAlert error={shows.error ?? episodes.error ?? voices.error} />
        <Tabs tabs={TABS} active={tab} onChange={setTab} label="Recent work">
          {loading ? (
            <Skeleton label="Loading your recent work" />
          ) : shown.length === 0 ? (
            <p className="muted home-empty">
              {needle
                ? "Nothing matches that search."
                : "Nothing here yet. Start with a quick action or a template."}
            </p>
          ) : (
            <div className="table-wrap">
              <table className="home-table">
                <thead>
                  <tr>
                    {header("title", "Title")}
                    {header("kind", "Type")}
                    <th scope="col">Status</th>
                    {header("updated", "Updated")}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((row) => (
                    <tr key={row.key}>
                      <td>
                        <Link to={row.href} className="home-row-title">
                          <Glyph>{GLYPHS[row.kind]}</Glyph>
                          <span>{row.title}</span>
                        </Link>
                      </td>
                      <td>{row.kind}</td>
                      <td>
                        {row.status ? (
                          <StatusBadge status={row.status} />
                        ) : (
                          <span className="muted">{row.detail}</span>
                        )}
                      </td>
                      <td>
                        <time
                          dateTime={row.updated}
                          title={formatDate(row.updated)}
                        >
                          {timeAgo(row.updated)}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Tabs>
      </section>

      <section
        className="home-templates"
        aria-labelledby="home-templates-title"
        data-tour="home-templates"
      >
        <div className="home-templates-head">
          <h2 id="home-templates-title">Start with a show template</h2>
          <Link to="/shows/new">Start from scratch</Link>
        </div>
        <ul className="template-grid">
          {SHOW_TEMPLATES.map((template) => (
            <li key={template.id}>
              <Link
                to={`/shows/new?template=${template.id}`}
                className="template-card"
              >
                <span className="template-title">{template.title}</span>
                <span className="template-add" aria-hidden="true">
                  <Glyph>{GLYPHS.add}</Glyph>
                </span>
                <span className="template-tags">
                  <Glyph>{GLYPHS.Show}</Glyph>
                  {template.tags.join(" · ")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
