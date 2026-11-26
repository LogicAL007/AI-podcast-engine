/**
 * A grey outline of the content that is loading, in its final shape, so nothing jumps when the
 * data arrives. Screen readers hear the label; the shapes themselves are hidden from them.
 */
export function Skeleton({
  label,
  kind = "list",
  rows = 3,
}: {
  label: string;
  kind?: "list" | "lines" | "page";
  rows?: number;
}) {
  return (
    <div role="status" className={`skeleton skeleton-${kind}`}>
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="stack">
        {kind === "page" ? (
          <>
            <span
              className="bone"
              style={{ width: "8rem", height: "0.9rem" }}
            />
            <span className="bone" style={{ width: "16rem", height: "2rem" }} />
            <div className="card skeleton-card stack">
              <span className="bone" style={{ width: "10rem" }} />
              <span
                className="bone"
                style={{ width: "100%", height: "0.4rem" }}
              />
            </div>
          </>
        ) : null}
        {kind === "list" ? (
          <ul className="list">
            {Array.from({ length: rows }, (_, i) => (
              <li key={i} className="list-item">
                <span
                  className="stack"
                  style={{ gap: "var(--space-2)", flex: 1 }}
                >
                  <span className="bone" style={{ width: `${55 - i * 8}%` }} />
                  <span
                    className="bone bone-faint"
                    style={{ width: `${35 + i * 5}%` }}
                  />
                </span>
                <span className="bone bone-pill" />
              </li>
            ))}
          </ul>
        ) : null}
        {kind === "lines"
          ? Array.from({ length: rows }, (_, i) => (
              <div key={i} className="stack" style={{ gap: "var(--space-2)" }}>
                <span
                  className="bone"
                  style={{ width: "4rem", height: "0.75rem" }}
                />
                <span className="bone bone-faint" style={{ width: "96%" }} />
                <span
                  className="bone bone-faint"
                  style={{ width: `${60 + (i % 3) * 12}%` }}
                />
              </div>
            ))
          : null}
      </div>
    </div>
  );
}
