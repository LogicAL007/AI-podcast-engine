import { useRef, useState, type FormEvent } from "react";

import type { ShowCreate, VoiceRead } from "../../api/types";
import { ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import {
  CheckboxField,
  SelectField,
  TextArea,
  TextField,
} from "../../components/Field";
import {
  ADVANCED,
  HOST_NAMES,
  SAMPLE_SHOW,
  STEP_ONE,
  errorsAmong,
  languageOptions,
  validateShow,
  type ShowErrors,
  type ShowValues,
} from "./showValues";

/**
 * The show's settings. As a `wizard` (a new show) it asks for the topic and sources first, then
 * how the show should sound; either way, rarely changed settings wait behind "More options".
 */
export function ShowForm({
  initial,
  submitLabel,
  busy,
  error,
  onSubmit,
  onCancel,
  wizard = false,
  voices = [],
}: {
  initial: ShowValues;
  submitLabel: string;
  busy: boolean;
  error: unknown;
  onSubmit: (body: ShowCreate) => void;
  onCancel?: () => void;
  wizard?: boolean;
  /** The creator's registered voices, offered to each host. */
  voices?: VoiceRead[];
}) {
  const [values, setValues] = useState<ShowValues>(initial);
  const [errors, setErrors] = useState<ShowErrors>({});
  const [step, setStep] = useState<1 | 2>(1);
  const [moreOpen, setMoreOpen] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const showFirst = !wizard || step === 1;
  const showSecond = !wizard || step === 2;

  function set<K extends keyof ShowValues>(key: K, value: ShowValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function goTo(next: 1 | 2) {
    setStep(next);
    // Move focus to the new step's heading, so keyboard and screen-reader users land on it.
    requestAnimationFrame(() => heading.current?.focus());
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const result = validateShow(values);
    if (wizard && step === 1) {
      const first = errorsAmong(result.errors, STEP_ONE);
      setErrors(first);
      if (!Object.keys(first).length) goTo(2);
      return;
    }
    setErrors(result.errors);
    if (Object.keys(errorsAmong(result.errors, ADVANCED)).length)
      setMoreOpen(true);
    if (wizard && Object.keys(errorsAmong(result.errors, STEP_ONE)).length) {
      goTo(1);
      return;
    }
    if (result.body) onSubmit(result.body);
  }

  return (
    <form className="stack" onSubmit={submit} noValidate>
      {wizard ? (
        <div className="wizard-head">
          <div className="wizard-top">
            <p className="wizard-step muted">Step {step} of 2</p>
            {step === 1 ? (
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setValues((current) => ({ ...current, ...SAMPLE_SHOW }));
                  setErrors({});
                }}
              >
                Try a sample
              </button>
            ) : null}
          </div>
          <h2 ref={heading} tabIndex={-1}>
            {step === 1 ? "What is the show about?" : "How should it sound?"}
          </h2>
        </div>
      ) : null}
      {showFirst ? (
        <>
          <TextField
            label="Topic"
            data-tour="show-topic"
            required
            hint="What the show is about. The hosts say it in the opening, and it is matched against your sources."
            value={values.topic}
            error={errors.topic}
            onChange={(event) => set("topic", event.target.value)}
          />
          <TextArea
            label="Source pages"
            data-tour="show-sources"
            hint="Web pages to build episodes from, one address per line. You can also upload PDFs after creating the show."
            rows={4}
            value={values.sources}
            error={errors.sources}
            onChange={(event) => set("sources", event.target.value)}
          />
        </>
      ) : null}
      {showSecond ? (
        <>
          <div className="form-grid">
            <SelectField
              label="Tone"
              value={values.tone}
              onChange={(event) =>
                set("tone", event.target.value as ShowValues["tone"])
              }
              options={[
                { value: "casual", label: "Casual" },
                { value: "neutral", label: "Neutral" },
                { value: "formal", label: "Formal" },
              ]}
            />
            <SelectField
              label="Audience"
              value={values.expertise}
              onChange={(event) =>
                set("expertise", event.target.value as ShowValues["expertise"])
              }
              options={[
                { value: "beginner", label: "Beginners" },
                { value: "intermediate", label: "Some background" },
                { value: "expert", label: "Experts" },
              ]}
            />
            <TextField
              label="Episode length (minutes)"
              inputMode="numeric"
              value={values.target_minutes}
              error={errors.target_minutes}
              onChange={(event) => set("target_minutes", event.target.value)}
            />
            <TextField
              label="Hosts"
              inputMode="numeric"
              value={values.host_count}
              error={errors.host_count}
              onChange={(event) => set("host_count", event.target.value)}
            />
            <SelectField
              label="Language"
              value={values.language}
              onChange={(event) => set("language", event.target.value)}
              options={languageOptions(values.language)}
            />
          </div>
          <CheckboxField
            label="Review each script before it is voiced"
            data-tour="show-review"
            hint="Episodes pause after the fact-check until you approve them."
            checked={values.review_before_voice}
            onChange={(event) =>
              set("review_before_voice", event.target.checked)
            }
          />
          {voices.length ? (
            <fieldset
              className="choice-group stack"
              style={{ gap: "var(--space-3)" }}
            >
              <legend>Host voices</legend>
              <p className="field-hint" style={{ marginTop: 0 }}>
                Give a host one of your recorded voices. Used when the voice
                engine is Chatterbox; otherwise hosts keep their built-in
                voices.
              </p>
              <div className="form-grid">
                {HOST_NAMES.slice(
                  0,
                  Math.max(1, Math.min(4, Number(values.host_count) || 1)),
                ).map((host) => (
                  <SelectField
                    key={host}
                    label={`${host}'s voice`}
                    value={values.host_voices[host] ?? ""}
                    onChange={(event) =>
                      set("host_voices", {
                        ...values.host_voices,
                        [host]: event.target.value,
                      })
                    }
                    options={[
                      { value: "", label: "Built-in voice" },
                      ...voices.map((voice) => ({
                        value: voice.voice_id,
                        label: `${voice.name} (${voice.speaker})`,
                      })),
                    ]}
                  />
                ))}
              </div>
            </fieldset>
          ) : null}
          <details
            className="more-options"
            open={moreOpen}
            onToggle={(event) => setMoreOpen(event.currentTarget.open)}
          >
            <summary>More options</summary>
            <div className="stack">
              <div className="form-grid">
                <TextField
                  label="Most segments per episode"
                  inputMode="numeric"
                  value={values.max_segments}
                  error={errors.max_segments}
                  onChange={(event) => set("max_segments", event.target.value)}
                />
                <SelectField
                  label="Favour"
                  value={values.ranking_profile}
                  onChange={(event) =>
                    set(
                      "ranking_profile",
                      event.target.value as ShowValues["ranking_profile"],
                    )
                  }
                  options={[
                    { value: "explainer", label: "Authoritative sources" },
                    { value: "daily", label: "Fresh sources" },
                  ]}
                />
              </div>
              <TextField
                label="Topic keywords"
                hint="Optional. Words that describe the topic, used with it to find relevant passages."
                value={values.topic_keywords}
                error={errors.topic_keywords}
                onChange={(event) => set("topic_keywords", event.target.value)}
              />
              <TextArea
                label="Attribution"
                hint="Optional. Credit and licence line printed in the show notes."
                rows={2}
                value={values.attribution}
                error={errors.attribution}
                onChange={(event) => set("attribution", event.target.value)}
              />
            </div>
          </details>
        </>
      ) : null}
      {Object.keys(errors).length ? (
        <p className="field-error" role="alert">
          Fix the highlighted fields.
        </p>
      ) : null}
      <ErrorAlert error={error} />
      <div className="row">
        {wizard && step === 2 ? (
          <Button variant="secondary" onClick={() => goTo(1)}>
            Back
          </Button>
        ) : null}
        <Button type="submit" busy={busy}>
          {wizard && step === 1 ? "Next" : submitLabel}
        </Button>
        {onCancel ? (
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
    </form>
  );
}
