import { Button } from "./Button";

export function Pagination({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const first = offset + 1;
  const last = Math.min(offset + limit, total);
  return (
    <nav className="pagination" aria-label="Pages">
      <span className="muted">
        {first}–{last} of {total}
      </span>
      <span className="row">
        <Button
          variant="secondary"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </Button>
        <Button
          variant="secondary"
          disabled={last >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </Button>
      </span>
    </nav>
  );
}
