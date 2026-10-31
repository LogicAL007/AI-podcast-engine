import { Link, useNavigate, useSearchParams } from "react-router";

import { useCreateShow, useVoices } from "../../api/queries";
import { useAssistant } from "../../bots/assistant";
import { ShowForm } from "./ShowForm";
import { EMPTY_SHOW, SAMPLE_SHOW, SHOW_TEMPLATES } from "./showValues";
import { usePageTitle } from "../../hooks/usePageTitle";

export function NewShowPage() {
  usePageTitle("New show");
  const create = useCreateShow();
  const voices = useVoices();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  // ?sample=1 (the welcome card) or ?template=<id> (the home page) opens the form filled in.
  const template = SHOW_TEMPLATES.find((t) => t.id === params.get("template"));
  const sample = params.get("sample") === "1";
  const initial = template
    ? { ...EMPTY_SHOW, ...template.values }
    : sample
      ? { ...EMPTY_SHOW, ...SAMPLE_SHOW }
      : EMPTY_SHOW;
  useAssistant({
    page: "new_show",
    key: "new_show",
    moment: "new_show",
    mode: "working",
    line: "Give me a topic and a few pages to read; I'll do the rest.",
    hint: "Pick a clear topic and two or three good pages, feeds or PDFs. Every line of the episode must come from them, so better sources make a better show.",
    actions: sample
      ? []
      : [
          {
            id: "fill_sample",
            label: "Fill in the sample",
            run: () => navigate("/shows/new?sample=1"),
          },
        ],
    questions: [
      "What makes a good source?",
      "What does reviewing before voicing do?",
    ],
    tour: [
      {
        target: "show-topic",
        title: "The topic",
        text: "What the show is about. It decides which passages from your sources make it into each episode.",
      },
      {
        target: "show-sources",
        title: "Your sources",
        text: "Pages and feeds to read, one per line. You can also upload PDFs after creating the show.",
      },
      {
        target: "show-review",
        title: "Stay in charge",
        text: "Tick this to read and edit every script before a word is voiced.",
      },
    ],
  });
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
          key={template?.id ?? (sample ? "sample" : "blank")}
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
