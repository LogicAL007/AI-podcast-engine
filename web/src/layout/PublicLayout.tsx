import type { ReactNode } from "react";

import { usePageTitle } from "../hooks/usePageTitle";
import { Backdrop } from "../visual/Backdrop";
import { GlassPanel } from "../visual/GlassPanel";
import { LiquidLogo } from "../visual/LiquidLogo";
import { Brand } from "./AppShell";

/**
 * Signing in, setup and password reset: a liquid-glass card over a slow warm gradient.
 * `split` (sign-in and sign-up) puts the card on the left and a short description on the right.
 */
export function PublicLayout({
  title,
  split = false,
  children,
}: {
  title: string;
  split?: boolean;
  children: ReactNode;
}) {
  usePageTitle(title);
  if (split) {
    return (
      <main className="auth-split">
        <section className="auth-split-form">
          <Backdrop />
          <GlassPanel className="public-card auth-card" radius={28}>
            <span className="auth-logo">
              <LiquidLogo size={52} />
              <span className="auth-logo-name">Podcast Engine</span>
            </span>
            <h1 className="auth-title">{title}</h1>
            <div className="stack">{children}</div>
          </GlassPanel>
        </section>
        <AuthDescription />
      </main>
    );
  }
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

/** The right-hand panel: what the product is, in a few words. */
function AuthDescription() {
  return (
    <aside className="auth-split-about" aria-label="About Podcast Engine">
      <div className="auth-about">
        <span className="auth-about-mark" aria-hidden="true" />
        <p className="auth-about-brand">Podcast Engine</p>
        <p className="auth-about-eyebrow">
          Grounded&nbsp;·&nbsp;Checked&nbsp;·&nbsp;Voiced
        </p>
        <p className="auth-about-headline">
          Your sources, turned into a podcast.
        </p>
        <p className="auth-about-lede">
          Pick the pages you trust. Two hosts talk them through, every claim is
          checked against its source, and the episode is voiced, including in
          your own recorded voice.
        </p>
      </div>
    </aside>
  );
}
