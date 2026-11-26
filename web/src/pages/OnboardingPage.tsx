import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { useAvatar, useSaveAvatar } from "../bots/avatar";
import { BotFigure } from "../bots/BotFigure";
import { CompanionPicker } from "../bots/CompanionPicker";
import type { BotMode } from "../bots/botMode";
import { Button, LinkButton } from "../components/Button";
import { usePageTitle } from "../hooks/usePageTitle";
import { useRememberedFlag } from "../hooks/useRememberedFlag";
import { Backdrop } from "../visual/Backdrop";
import { GlassPanel } from "../visual/GlassPanel";
import { LiquidLogo } from "../visual/LiquidLogo";

interface Step {
  id: "welcome" | "companion" | "how" | "first";
  title: string;
  bot: BotMode;
}

const STEPS: Step[] = [
  { id: "welcome", title: "Welcome to Oasis", bot: "greeting" },
  { id: "companion", title: "Meet your companion", bot: "greeting" },
  { id: "how", title: "How an episode is made", bot: "reviewing" },
  { id: "first", title: "Make your first show", bot: "celebrating" },
];

const STAGES = [
  {
    name: "Gather and plan",
    text: "It reads your web pages and PDFs, then picks the passages that matter for your topic.",
  },
  {
    name: "Write and check",
    text: "Two hosts' dialogue is written from those passages. Every claim is checked against its source, and you can review the script before anything is voiced.",
  },
  {
    name: "Voice and publish",
    text: "Each host gets a distinct AI voice, announced as AI-generated. A transcript and show notes come with every episode, and it lands in your podcast feed.",
  },
];

/** Full-page steps after signing up: what this is, choosing a companion bot, how it works, and a
 * first show. The chosen bot is saved when they move on, and appears on the later steps. */
export function OnboardingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [, setOnboarded] = useRememberedFlag("pe.welcome.skipped");
  const heading = useRef<HTMLHeadingElement>(null);
  const saved = useAvatar();
  const save = useSaveAvatar();
  const [draft, setDraft] = useState(saved);
  const requested = Number(params.get("step"));
  const index =
    Number.isInteger(requested) && requested >= 1 && requested <= STEPS.length
      ? requested - 1
      : 0;
  const step = STEPS[index];
  usePageTitle(`${step.title} (step ${index + 1} of ${STEPS.length})`);

  // Land keyboard and screen-reader users on each step's heading.
  useEffect(() => heading.current?.focus(), [index]);

  function keepCompanion() {
    if (draft.name.trim() && JSON.stringify(draft) !== JSON.stringify(saved))
      save.mutate(draft);
  }
  function go(next: number) {
    if (step.id === "companion") keepCompanion();
    setParams({ step: String(next + 1) });
  }
  function finish(to: string) {
    keepCompanion();
    setOnboarded(true); // the empty Shows page then skips its welcome card
    navigate(to);
  }
  const name = user?.email.split("@")[0];

  return (
    <main className="onboarding-page">
      <Backdrop />
      <GlassPanel className="onboarding-card" radius={32}>
        <div className="onboarding-top">
          <span className="brand">
            <LiquidLogo size={32} />
            Oasis
          </span>
          <button
            type="button"
            className="link-button"
            onClick={() => finish("/shows")}
          >
            Skip
          </button>
        </div>
        <div
          className={
            step.id === "companion"
              ? "onboarding-body onboarding-body-wide"
              : "onboarding-body"
          }
          key={index}
        >
          {step.id === "companion" ? null : (
            <div className="onboarding-bot">
              <BotFigure mode={step.bot} avatar={draft} interactive />
            </div>
          )}
          <div className="stack">
            <p className="wizard-step muted">
              Step {index + 1} of {STEPS.length}
            </p>
            <h1 ref={heading} tabIndex={-1}>
              {step.id === "welcome" && name ? `Welcome, ${name}` : step.title}
            </h1>
            {step.id === "welcome" ? (
              <>
                <p className="onboarding-lead">
                  Oasis turns a topic and the sources you trust into a podcast
                  episode with two hosts.
                </p>
                <ul className="onboarding-points">
                  <li>
                    Every line is drawn from your sources, and each one is
                    cited.
                  </li>
                  <li>
                    Claims are fact-checked before a single word is voiced.
                  </li>
                  <li>
                    You stay in charge: review and edit the script whenever you
                    like.
                  </li>
                </ul>
              </>
            ) : null}
            {step.id === "companion" ? (
              <>
                <p className="onboarding-lead">
                  Pick the bot that keeps you company while your episodes are
                  made. You can change it any time.
                </p>
                <CompanionPicker value={draft} onChange={setDraft} compact />
              </>
            ) : null}
            {step.id === "how" ? (
              <ol className="onboarding-stages">
                {STAGES.map((stage) => (
                  <li key={stage.name}>
                    <strong>{stage.name}</strong>
                    <span className="muted">{stage.text}</span>
                  </li>
                ))}
              </ol>
            ) : null}
            {step.id === "first" ? (
              <>
                <p className="onboarding-lead">
                  A show is a topic and its sources. Start from a ready-made
                  sample, or bring your own.
                </p>
                <div className="onboarding-choices">
                  <button
                    type="button"
                    className="onboarding-choice"
                    onClick={() => finish("/shows/new?sample=1")}
                  >
                    <strong>Try the sample</strong>
                    <span className="muted">
                      &ldquo;How the Moon makes the tides&rdquo;, from two
                      openly licensed articles. One click to your first episode.
                    </span>
                  </button>
                  <button
                    type="button"
                    className="onboarding-choice"
                    onClick={() => finish("/shows/new")}
                  >
                    <strong>Use my own topic</strong>
                    <span className="muted">
                      Name a topic and paste the pages to build from. PDFs can
                      come later.
                    </span>
                  </button>
                </div>
              </>
            ) : null}
          </div>
        </div>
        <div className="onboarding-foot">
          <div className="onboarding-dots" aria-hidden="true">
            {STEPS.map((s, i) => (
              <span
                key={s.title}
                className={i === index ? "dot dot-on" : "dot"}
              />
            ))}
          </div>
          <div className="row">
            {index > 0 ? (
              <Button variant="secondary" onClick={() => go(index - 1)}>
                Back
              </Button>
            ) : null}
            {index < STEPS.length - 1 ? (
              <Button
                disabled={step.id === "companion" && !draft.name.trim()}
                onClick={() => go(index + 1)}
              >
                Next
              </Button>
            ) : (
              <LinkButton
                to="/shows"
                variant="secondary"
                onClick={() => setOnboarded(true)}
              >
                Go to my shows
              </LinkButton>
            )}
          </div>
        </div>
      </GlassPanel>
      <p className="onboarding-help muted">
        You can come back to this tour any time from{" "}
        <Link to="/welcome">/welcome</Link>.
      </p>
    </main>
  );
}
