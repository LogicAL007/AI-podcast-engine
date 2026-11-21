import { NavLink, Outlet, useLocation } from "react-router";

import { LinkButton } from "../../components/Button";
import { usePageTitle } from "../../hooks/usePageTitle";

const TABS = [
  { to: "/voices", label: "Voices", end: true },
  { to: "/voices/speak", label: "Type to speech", end: false },
  { to: "/voices/music", label: "Music", end: false },
  { to: "/voices/show-sound", label: "Show sound", end: false },
];

/** The Voice studio: one place for voices, trying them, music and how each show sounds. */
export function VoiceStudio() {
  const { pathname } = useLocation();
  const current = TABS.find((tab) =>
    tab.end
      ? pathname === tab.to || pathname === `${tab.to}/`
      : pathname.startsWith(tab.to),
  );
  usePageTitle(
    current && current.label !== "Voices"
      ? `${current.label} · Voice studio`
      : "Voice studio",
  );
  return (
    <>
      <div className="page-header studio-header">
        <h1>Voice studio</h1>
        {current?.label === "Voices" ? (
          <LinkButton to="/voices/new" data-tour="voices-add">
            Add voice
          </LinkButton>
        ) : null}
      </div>
      <nav className="tabs studio-tabs" aria-label="Voice studio">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className="tab">
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div className="tab-panel">
        <div className="tab-panel-inner" key={current?.to}>
          <Outlet />
        </div>
      </div>
    </>
  );
}
