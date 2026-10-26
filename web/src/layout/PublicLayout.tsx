import type { ReactNode } from "react";

import { usePageTitle } from "../hooks/usePageTitle";
import { Backdrop } from "../visual/Backdrop";
import { GlassPanel } from "../visual/GlassPanel";
import { Brand } from "./AppShell";

/** Signing in, setup and password reset: a liquid-glass card over a slow warm gradient. */
export function PublicLayout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  usePageTitle(title);
  return (
    <main className="public-page">
      <Backdrop />
      <GlassPanel className="public-card" radius={28}>
        <Brand size={44} />
        <div className="stack">
          <h1 style={{ fontSize: "var(--text-xl)" }}>{title}</h1>
          {children}
        </div>
      </GlassPanel>
    </main>
  );
}
