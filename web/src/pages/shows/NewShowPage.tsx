import { Link, useNavigate, useSearchParams } from "react-router";

import { useCreateShow, useVoices } from "../../api/queries";
import { ShowForm } from "./ShowForm";
import { EMPTY_SHOW, SAMPLE_SHOW } from "./showValues";
import { usePageTitle } from "../../hooks/usePageTitle";

export function NewShowPage() {
  usePageTitle("New show");
  const create = useCreateShow();
  const voices = useVoices();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // ?sample=1 (from the welcome card) opens the form with the sample show filled in.
  const initial =
    params.get("sample") === "1"
      ? { ...EMPTY_SHOW, ...SAMPLE_SHOW }
      : EMPTY_SHOW;
  return (
    <>
      <div className="breadcrumb">
        <Link to="/shows">Shows</Link>
      </div>
      <div className="page-header">
        <h1>New show</h1>
      </div>
      <div className="card" style={{ maxWidth: "48rem" }}>
        <ShowForm
          voices={voices.data?.items}
          wizard
          initial={initial}
          submitLabel="Create show"
          busy={create.isPending}
          error={create.error}
          onCancel={() => navigate("/shows")}
          onSubmit={(body) =>
            create.mutate(body, {
              onSuccess: (show) => navigate(`/shows/${show.show_id}`),
            })
          }
        />
      </div>
    </>
  );
}
