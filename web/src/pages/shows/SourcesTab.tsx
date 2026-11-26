import { useState } from "react";

import { PAGE_SIZE, useSources } from "../../api/queries";
import { ErrorAlert } from "../../components/Alert";
import { EmptyState } from "../../components/EmptyState";
import { Pagination } from "../../components/Pagination";
import { Skeleton } from "../../components/Skeleton";
import { formatDate } from "../format";

const TIER: Record<string, string> = {
  primary: "Primary",
  established: "Established",
  unverified: "Unverified",
};

export function SourcesTab({ showId }: { showId: string }) {
  const [offset, setOffset] = useState(0);
  const sources = useSources(showId, offset);

  if (sources.isPending) return <Skeleton label="Loading sources" />;
  if (!sources.data) return <ErrorAlert error={sources.error} />;
  if (sources.data.total === 0) {
    return (
      <EmptyState title="No sources read yet">
        Sources appear here once an episode has gathered them: each section of a
        page or PDF is one source the hosts can cite.
      </EmptyState>
    );
  }
  return (
    <div className="stack">
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <caption className="sr-only">Sources read for this show</caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Reliability</th>
              <th scope="col">Words</th>
              <th scope="col">Read</th>
            </tr>
          </thead>
          <tbody>
            {sources.data.items.map((source) => (
              <tr key={source.item_id}>
                <td>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.title || source.url}
                  </a>
                </td>
                <td>{TIER[source.reliability] ?? source.reliability}</td>
                <td>{source.words.toLocaleString()}</td>
                <td>{formatDate(source.fetched_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination
        offset={offset}
        limit={PAGE_SIZE}
        total={sources.data.total}
        onChange={setOffset}
      />
    </div>
  );
}
