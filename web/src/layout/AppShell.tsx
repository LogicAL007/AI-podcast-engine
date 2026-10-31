import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { AssistantProvider } from "../bots/assistant";
import { AssistantDock } from "../bots/AssistantDock";
import { useAvatar } from "../bots/avatar";
import { AvatarFace } from "../bots/AvatarFace";
import { preloadBots } from "../bots/BotFigure";
import { Button, LinkButton } from "../components/Button";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useRememberedFlag } from "../hooks/useRememberedFlag";
import { LiquidLogo } from "../visual/LiquidLogo";
import { UsageCard } from "./UsageCard";

export function Brand({ size = 34 }: { size?: number }) {
  return (
    <span className="brand">
      <LiquidLogo size={size} />
      <span className="brand-name">Podcast Engine</span>
    </span>
  );
}

/** Below this width the sidebar becomes a drawer behind a menu button. */
const NARROW = "(max-width: 56rem)";

type IconName =
  | "home"
  | "search"
  | "shows"
  | "voices"
  | "add"
  | "menu"
  | "close"
  | "collapse"
  | "expand"
  | "signout";

function Icon({ name }: { name: IconName }) {
  const paths: Record<typeof name, ReactNode> = {
    home: <path d="M3.5 9 10 3.5 16.5 9M5.5 7.5V16h3.5v-4.5h2V16h3.5V7.5" />,
    search: (
      <>
        <circle cx="9" cy="9" r="5.5" />
        <path d="m13 13 4 4" />
      </>
    ),
    shows: (
      <>
        <rect x="3" y="4" width="14" height="12" rx="2.5" />
        <path d="M7 8.5v3M10 7v6M13 9v2" />
      </>
    ),
    voices: (
      <>
        <rect x="7.5" y="2.5" width="5" height="9" rx="2.5" />
        <path d="M4.5 9.5a5.5 5.5 0 0 0 11 0M10 15v2.5" />
      </>
    ),
    add: <path d="M10 4.5v11M4.5 10h11" />,
    menu: <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />,
    close: <path d="M5 5l10 10M15 5L5 15" />,
    collapse: (
      <>
        <rect x="3" y="3.5" width="14" height="13" rx="2.5" />
        <path d="M8 3.5v13M13 8l-2 2 2 2" />
      </>
    ),
    expand: (
      <>
        <rect x="3" y="3.5" width="14" height="13" rx="2.5" />
        <path d="M8 3.5v13M11 8l2 2-2 2" />
      </>
    ),
    signout: (
      <path d="M8 4.5H5.5a1.5 1.5 0 0 0-1.5 1.5v8a1.5 1.5 0 0 0 1.5 1.5H8M12 7l3 3-3 3M15 10H8" />
    ),
  };
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

/**
 * The signed-in app: a sidebar with the main places (shows, the voice studio, your companion),
 * quick actions and your account, beside the page. On narrow screens the sidebar is a drawer.
 */
export function AppShell() {
  const { user, signOut } = useAuth();
  const avatar = useAvatar();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const narrow = useMediaQuery(NARROW);
  const [open, setOpen] = useState(false);
  const [collapsedChoice, setCollapsed] = useRememberedFlag(
    "pe.sidebar.collapsed",
  );
  const collapsed = collapsedChoice && !narrow; // a drawer always shows its labels
  const [leaving, setLeaving] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  useEffect(preloadBots, []);

  // A drawer closes when you go somewhere, and on Escape; focus moves into it and back out.
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    sidebar.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function leave() {
    setLeaving(true);
    try {
      await signOut();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  // Shows stay highlighted inside a show and its episodes.
  const inShows =
    pathname.startsWith("/shows") || pathname.startsWith("/episodes");
  const atHome = pathname === "/";
  const hidden = narrow && !open;

  return (
    <AssistantProvider>
      <div className="app-backdrop" aria-hidden="true" />
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div
        className={collapsed ? "app-layout sidebar-collapsed" : "app-layout"}
      >
        {narrow ? (
          <header className="mobile-bar">
            <button
              ref={menuButton}
              type="button"
              className="menu-button"
              aria-label="Open the menu"
              aria-expanded={open}
              aria-controls="sidebar"
              onClick={() => setOpen(true)}
            >
              <Icon name="menu" />
            </button>
            <Link
              to="/"
              className="brand-link"
              aria-label="Podcast Engine, home"
            >
              <Brand size={30} />
            </Link>
            <Link
              to="/companion"
              className="companion-chip"
              aria-label={`Your companion, ${avatar.name}`}
            >
              <AvatarFace avatar={avatar} size={26} />
            </Link>
          </header>
        ) : null}
        {narrow && open ? (
          <div
            className="sidebar-scrim"
            aria-hidden="true"
            onClick={() => setOpen(false)}
          />
        ) : null}
        <aside
          id="sidebar"
          ref={sidebar}
          className={open ? "sidebar sidebar-open" : "sidebar"}
          aria-label="Sidebar"
          inert={hidden}
        >
          <div className="sidebar-top">
            <Link
              to="/"
              className="brand-link"
              aria-label="Podcast Engine, home"
            >
              <Brand size={34} />
            </Link>
            {!narrow ? (
              <button
                type="button"
                className="collapse-button"
                aria-label={
                  collapsed ? "Expand the sidebar" : "Collapse the sidebar"
                }
                title={
                  collapsed ? "Expand the sidebar" : "Collapse the sidebar"
                }
                aria-expanded={!collapsed}
                aria-controls="sidebar"
                onClick={() => setCollapsed(!collapsed)}
              >
                <Icon name={collapsed ? "expand" : "collapse"} />
              </button>
            ) : null}
            {narrow ? (
              <button
                type="button"
                className="menu-button"
                aria-label="Close the menu"
                onClick={() => {
                  setOpen(false);
                  menuButton.current?.focus();
                }}
              >
                <Icon name="close" />
              </button>
            ) : null}
          </div>

          <div className="sidebar-icons">
            <Link
              to="/"
              className={atHome ? "icon-tab active" : "icon-tab"}
              aria-label="Home"
              aria-current={atHome ? "page" : undefined}
              title="Home"
            >
              <Icon name="home" />
            </Link>
            <Link
              to="/shows/new"
              className="icon-tab"
              aria-label="Create a show"
              title="Create a show"
            >
              <Icon name="add" />
            </Link>
            <Link
              to="/?search=1"
              className="icon-tab"
              aria-label="Search"
              title="Search"
            >
              <Icon name="search" />
            </Link>
          </div>

          <nav className="sidebar-nav" aria-label="Main">
            <p className="sidebar-heading">Studio</p>
            <Link
              to="/shows"
              className={inShows ? "side-link active" : "side-link"}
              aria-current={inShows ? "page" : undefined}
              title={collapsed ? "Shows" : undefined}
            >
              <Icon name="shows" /> <span className="side-label">Shows</span>
            </Link>
            <NavLink
              to="/voices"
              className="side-link"
              data-tour="nav-voices"
              title={collapsed ? "Voice studio" : undefined}
            >
              <Icon name="voices" />{" "}
              <span className="side-label">Voice studio</span>
            </NavLink>
            <NavLink
              to="/companion"
              className="side-link"
              data-tour="nav-companion"
              title={collapsed ? "Companion" : undefined}
            >
              <AvatarFace avatar={avatar} size={20} />{" "}
              <span className="side-label">Companion</span>
            </NavLink>
          </nav>

          <div className="sidebar-section">
            <p className="sidebar-heading">Create</p>
            <LinkButton
              to="/shows/new"
              className="sidebar-cta"
              data-tour="new-show"
              title={collapsed ? "New show" : undefined}
            >
              <Icon name="add" /> <span className="side-label">New show</span>
            </LinkButton>
            <Link
              to="/voices/new"
              className="side-link side-link-quiet"
              title={collapsed ? "Add a voice" : undefined}
            >
              <Icon name="voices" />{" "}
              <span className="side-label">Add a voice</span>
            </Link>
          </div>

          <div className="sidebar-bottom">
            <UsageCard collapsed={collapsed} />
            <Link
              to="/companion"
              className="companion-card"
              aria-label={`${avatar.name}, your companion`}
              title={collapsed ? "Your companion" : undefined}
            >
              <AvatarFace avatar={avatar} size={36} />
              <span className="stack" style={{ gap: 0, minWidth: 0 }}>
                <span className="companion-card-name">{avatar.name}</span>
                <span className="muted companion-card-role">
                  Your companion
                </span>
              </span>
            </Link>
            <p className="sidebar-email muted" title={user?.email}>
              {user?.email}
            </p>
            <Button
              variant="secondary"
              block
              busy={leaving}
              onClick={leave}
              className="sidebar-signout"
              title={collapsed ? "Sign out" : undefined}
            >
              <Icon name="signout" />{" "}
              <span className="side-label">Sign out</span>
            </Button>
          </div>
        </aside>
        <main id="main" className="app-main" tabIndex={-1}>
          <div key={pathname} className="page-enter">
            <Outlet />
          </div>
          <AssistantDock />
        </main>
      </div>
    </AssistantProvider>
  );
}
