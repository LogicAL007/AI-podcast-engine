import { useEpisodeClaims } from "../../api/queries";
import { ErrorAlert } from "../../components/Alert";
import { EmptyState } from "../../components/EmptyState";
import { Skeleton } from "../../components/Skeleton";
import { VerdictBadge } from "./VerdictBadge";

export function ClaimsTab({ episodeId }: { episodeId: string }) {
  const claims = useEpisodeClaims(episodeId);
  if (claims.isPending) return <Skeleton label="Loading the fact-check" />;
  if (!claims.data) return <ErrorAlert error={claims.error} />;
  if (claims.data.total === 0) {
    return (
      <EmptyState title="No claims yet">
        Every factual line in the script is checked against the passage it
        cites. The verdicts appear here after the fact-check step.
      </EmptyState>
    );
  }
  const items = claims.data.items;
  const unsupported = items.filter((c) => c.supported === false).length;
  return (
    <div className="stack">
      <p className="muted">
        {items.length} claim{items.length === 1 ? "" : "s"} checked ·{" "}
        {unsupported === 0 ? "all supported" : `${unsupported} not supported`}
      </p>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <caption className="sr-only">
            Claims and their fact-check verdicts
          </caption>
          <thead>
            <tr>
              <th scope="col">Segment</th>
              <th scope="col">Claim</th>
              <th scope="col">Verdict</th>
              <th scope="col">Reason</th>
            </tr>
          </thead>
          <tbody>
            {items.map((claim) => (
              <tr key={claim.claim_id}>
                <td>{claim.segment}</td>
                <td>{claim.text}</td>
                <td>
                  <VerdictBadge
                    supported={claim.supported}
                    cited={claim.chunk_ids.length > 0}
                  />
                </td>
                <td className="muted">{claim.reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
