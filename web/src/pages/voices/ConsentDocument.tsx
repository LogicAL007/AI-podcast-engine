import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE } from "../../api/client";
import type { components } from "../../api/schema";

type Consent = components["schemas"]["ConsentDocument"];

/** How close to the bottom counts as having reached the end (rounding, zoom). */
const SLACK_PX = 8;

const BULLET = "- ";

/** A section's paragraphs, with each run of "- " items as one bulleted list. */
function Paragraphs({ paragraphs }: { paragraphs: string[] }) {
  const blocks: (string | string[])[] = [];
  for (const text of paragraphs) {
    const last = blocks[blocks.length - 1];
    if (!text.startsWith(BULLET)) blocks.push(text);
    else if (Array.isArray(last)) last.push(text.slice(BULLET.length));
    else blocks.push([text.slice(BULLET.length)]);
  }
  return blocks.map((block) =>
    Array.isArray(block) ? (
      <ul key={block[0]}>
        {block.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    ) : (
      <p key={block}>{block}</p>
    ),
  );
}

/**
 * The consent form, in full, in a scrollable box, with the same form as a PDF to download.
 * `onRead` fires once the reader has reached the end (or at once if it all fits), so the page
 * can ask for agreement only after the whole form has been seen.
 */
export function ConsentDocument({
  consent,
  onRead,
}: {
  consent: Consent;
  onRead: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [read, setRead] = useState(false);

  const check = useCallback(() => {
    const el = box.current;
    if (!el || read) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - SLACK_PX) {
      setRead(true);
      onRead();
    }
  }, [read, onRead]);

  // A tall screen may show it all without scrolling.
  useEffect(check, [check]);

  return (
    <section className="consent-doc-wrap" aria-labelledby="consent-doc-title">
      <div className="consent-doc-bar">
        <p id="consent-doc-title" className="consent-label">
          Consent form · version {consent.version}
        </p>
        <a
          className="consent-doc-pdf"
          href={`${API_BASE}${consent.pdf}`}
          target="_blank"
          rel="noopener"
        >
          Open the PDF
        </a>
      </div>
      <div
        ref={box}
        className="consent-doc"
        tabIndex={0}
        role="document"
        aria-label={`${consent.title}, version ${consent.version}. Scroll to read it all.`}
        onScroll={check}
      >
        <h3 className="consent-doc-title">{consent.title}</h3>
        {consent.sections.map((section) => (
          <div key={section.heading} className="consent-doc-section">
            <h4>{section.heading}</h4>
            <Paragraphs paragraphs={section.paragraphs} />
          </div>
        ))}
        <p className="consent-doc-end">End of the consent form.</p>
      </div>
      <p className="consent-doc-status muted" aria-live="polite">
        {read
          ? "You have read the whole form."
          : "Scroll to the end of the form to continue."}
      </p>
    </section>
  );
}
