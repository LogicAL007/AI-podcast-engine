export function VerdictBadge({
  supported,
  cited,
}: {
  supported: boolean | null;
  cited: boolean;
}) {
  if (!cited) return <span className="badge badge-danger">No citation</span>;
  if (supported === true)
    return <span className="badge badge-success">Supported</span>;
  if (supported === false)
    return <span className="badge badge-danger">Not supported</span>;
  return <span className="badge badge-neutral">Not checked yet</span>;
}
