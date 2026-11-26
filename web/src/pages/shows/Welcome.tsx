import { BotFigure } from "../../bots/BotFigure";
import { LinkButton } from "../../components/Button";
import { GlassPanel } from "../../visual/GlassPanel";

const STEPS = [
  {
    title: "Create a show",
    text: "Give it a topic. Everything else has a sensible default.",
  },
  {
    title: "Add sources",
    text: "Web pages or PDFs. Every line the hosts say is drawn from them.",
  },
  {
    title: "Generate",
    text: "It is written, fact-checked and voiced. You can review it first.",
  },
];

/** The first thing a new creator sees: what a show is, and the three steps to a first episode. */
export function Welcome({ onSkip }: { onSkip: () => void }) {
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <GlassPanel className="welcome-card" radius={28}>
        <div className="welcome-inner">
          <div className="welcome-bot" aria-hidden="true">
            <BotFigure mode="greeting" />
          </div>
          <div className="stack">
            <div className="stack" style={{ gap: "var(--space-1)" }}>
              <h2 id="welcome-title">Let&apos;s make your first episode</h2>
              <p className="muted">
                A show turns a topic and its sources into podcast episodes you
                can trust.
              </p>
            </div>
            <ol className="welcome-steps">
              {STEPS.map((step) => (
                <li key={step.title}>
                  <strong>{step.title}</strong>
                  <span className="muted">{step.text}</span>
                </li>
              ))}
            </ol>
            <div className="row">
              <LinkButton to="/shows/new">Create your first show</LinkButton>
              <LinkButton to="/shows/new?sample=1" variant="secondary">
                Try a sample show
              </LinkButton>
              <button type="button" className="link-button" onClick={onSkip}>
                Skip the tour
              </button>
            </div>
          </div>
        </div>
      </GlassPanel>
    </section>
  );
}
