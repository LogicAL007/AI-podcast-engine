export function Spinner({
  label,
  small = false,
}: {
  label?: string;
  small?: boolean;
}) {
  const size = small ? { width: "1rem", height: "1rem" } : undefined;
  if (!label)
    return <span className="spinner" style={size} aria-hidden="true" />;
  return (
    <span className="row" role="status">
      <span className="spinner" style={size} aria-hidden="true" />
      <span className="muted">{label}</span>
    </span>
  );
}
