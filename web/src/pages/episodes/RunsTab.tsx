import { useEpisodeRuns } from "../../api/queries";
import { ErrorAlert } from "../../components/Alert";
import { EmptyState } from "../../components/EmptyState";
import { stageLabel } from "../../components/ProgressSteps";
import { Skeleton } from "../../components/Skeleton";
import { formatDate } from "../format";

/** What ran, with which model, prompt version and seed: enough to repeat it. */
export function RunsTab({ episodeId }: { episodeId: string }) {
  const runs = useEpisodeRuns(episodeId);
  if (runs.isPending) return <Skeleton label="Loading runs" />;
  if (!runs.data) return <ErrorAlert error={runs.error} />;
  if (runs.data.total === 0)
    return <EmptyState title="No steps have run yet" />;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table">
        <caption className="sr-only">
          Pipeline steps that ran for this episode
        </caption>
        <thead>
          <tr>
            <th scope="col">Step</th>
            <th scope="col">Took</th>
            <th scope="col">Model</th>
            <th scope="col">Prompt</th>
            <th scope="col">Seed</th>
            <th scope="col">When</th>
          </tr>
        </thead>
        <tbody>
          {runs.data.items.map((run, index) => (
            <tr key={`${run.stage}-${index}`}>
              <td>{stageLabel(run.stage)}</td>
              <td>
                {run.seconds == null ? "—" : `${run.seconds.toFixed(1)} s`}
              </td>
              <td>{run.model ?? "—"}</td>
              <td>{run.prompt_version ?? "—"}</td>
              <td>{run.seed ?? "—"}</td>
              <td>{formatDate(run.started_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
