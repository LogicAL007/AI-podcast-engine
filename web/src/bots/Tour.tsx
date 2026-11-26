import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "../components/Button";
import type { TourStep } from "./assistant";
import { useAvatar } from "./avatar";
import { AvatarFace } from "./AvatarFace";

/** The element a step points at: the first one marked for it that is usable (not in a closed
 * drawer), so a sidebar link on a phone falls back to the same button in the page. */
function findTarget(step: TourStep): HTMLElement | null {
  const marked = document.querySelectorAll<HTMLElement>(
    `[data-tour="${step.target}"]`,
  );
  return [...marked].find((element) => !element.closest("[inert]")) ?? null;
}

/**
 * A guided tour: the page dims, a spotlight sits on one element at a time, and the bot explains
 * it in a small dialog. Back, Next and Done step through; Escape or Skip ends it. Focus moves into
 * the dialog and back to where it was afterwards. Steps whose element is not on the page are
 * skipped.
 */
export function Tour({
  steps,
  onClose,
}: {
  steps: TourStep[];
  onClose: (finished: boolean) => void;
}) {
  const avatar = useAvatar();
  const present = steps.filter((step) => findTarget(step));
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const titleId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const returnTo = useRef<Element | null>(document.activeElement);
  const step = present[index];

  useLayoutEffect(() => {
    if (!step) return;
    const target = findTarget(step);
    target?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    const measure = () =>
      setRect(findTarget(step)?.getBoundingClientRect() ?? null);
    measure();
    const timer = window.setTimeout(measure, 350); // after the smooth scroll settles
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step]);

  useEffect(() => heading.current?.focus(), [index]);

  // Nothing to point at on this page (yet): end quietly.
  const empty = present.length === 0;
  useEffect(() => {
    if (empty) onClose(false);
  }, [empty, onClose]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function close(finished: boolean) {
    onClose(finished);
    (returnTo.current as HTMLElement | null)?.focus?.();
  }

  if (!step) return null;
  const last = index === present.length - 1;
  const pad = 8;
  const below = !rect || rect.bottom + 220 < window.innerHeight;
  const cardTop = rect
    ? below
      ? rect.bottom + pad + 12
      : Math.max(16, rect.top - pad - 12)
    : 80;
  const cardLeft = rect
    ? Math.min(
        Math.max(16, rect.left),
        window.innerWidth - 16 - Math.min(360, window.innerWidth - 32),
      )
    : 16;

  return createPortal(
    <div className="tour">
      {rect ? (
        <div
          className="tour-spotlight"
          aria-hidden="true"
          style={{
            top: rect.top - pad,
            left: rect.left - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
          }}
        />
      ) : (
        <div className="tour-scrim" aria-hidden="true" />
      )}
      <div
        className="tour-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          top: cardTop,
          left: cardLeft,
          transform: below ? undefined : "translateY(-100%)",
        }}
      >
        <div className="row tour-head">
          <AvatarFace avatar={avatar} size={30} />
          <span className="muted tour-count">
            {index + 1} of {present.length}
          </span>
        </div>
        <h2 id={titleId} ref={heading} tabIndex={-1} className="tour-title">
          {step.title}
        </h2>
        <p className="tour-text">{step.text}</p>
        <div className="row tour-buttons">
          <button
            type="button"
            className="link-button"
            onClick={() => close(false)}
          >
            Skip tour
          </button>
          <span className="tour-spacer" />
          {index > 0 ? (
            <Button variant="secondary" onClick={() => setIndex(index - 1)}>
              Back
            </Button>
          ) : null}
          <Button onClick={() => (last ? close(true) : setIndex(index + 1))}>
            {last ? "Done" : "Next"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
