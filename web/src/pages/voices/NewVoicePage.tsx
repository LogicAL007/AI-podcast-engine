import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { Link, useNavigate } from "react-router";

import { useConsentForm, useRegisterVoice } from "../../api/queries";
import {
  decode,
  formatTime,
  MAX_SECONDS,
  MIN_SECONDS,
  toVoiceWav,
} from "../../audio/wav";
import { useRecorder, type Recording } from "../../audio/useRecorder";
import { useAssistant } from "../../bots/assistant";
import { Alert, ErrorAlert } from "../../components/Alert";
import { Button } from "../../components/Button";
import { CheckboxField, TextArea, TextField } from "../../components/Field";
import { LiveWaveform } from "../../components/LiveWaveform";
import { WaveformPlayer } from "../../components/WaveformPlayer";
import { usePageTitle } from "../../hooks/usePageTitle";
import { formatDate } from "../format";
import {
  consentProblems,
  EMPTY_CONSENT,
  type ConsentErrors,
  type ConsentValues,
} from "./consent";

const STEPS = ["Consent", "Record or upload", "Review and register"];

/** What to read aloud: about 20 seconds, with a mix of sounds that helps the clone. */
const PROMPT =
  "Hello, and welcome to the show. Today we're looking at how the Moon pulls on the oceans to " +
  "make the tides. Twice a day the water rises and falls, and the timing shifts a little every " +
  "day. Stay with us: by the end, you'll know exactly why.";

function lengthProblem(seconds: number): string | null {
  if (seconds < MIN_SECONDS)
    return `That is ${seconds.toFixed(0)} s; record at least ${MIN_SECONDS} s.`;
  if (seconds > MAX_SECONDS)
    return `That is ${formatTime(seconds)}; keep it under ${MAX_SECONDS} s.`;
  return null;
}

/**
 * Register a voice for Chatterbox to clone. The consent form comes first and must be complete
 * before anything is recorded or uploaded; its signed text is stored with the recording.
 */
export function NewVoicePage() {
  usePageTitle("Add a voice");
  const navigate = useNavigate();
  const register = useRegisterVoice();
  const heading = useRef<HTMLHeadingElement>(null);
  const [step, setStep] = useState(0);
  const [consent, setConsent] = useState<ConsentValues>(EMPTY_CONSENT);
  const [audio, setAudio] = useState<
    (Recording & { source: "recorded" | "uploaded" }) | null
  >(null);

  useEffect(() => heading.current?.focus(), [step]);
  const LINES = [
    "First, the speaker signs the consent form. Their voice is used only as they agree here.",
    "Now record or upload 5 to 90 seconds of clear speech, in a quiet room.",
    "Listen back. If it sounds right, register it.",
  ];
  useAssistant({
    page: "new_voice",
    key: "new_voice",
    moment: "new_voice",
    mode: step === 2 ? "celebrating" : "working",
    line: LINES[step],
    hint: "Adding a voice takes three steps: the speaker's consent, a short recording, and a check before it is registered. You can withdraw a voice any time by deleting it.",
    questions: [
      "What should I say in the recording?",
      "Can I use someone else's voice?",
    ],
    tour: [
      {
        target: "voice-steps",
        title: "Three steps",
        text: "Consent first, then the recording, then a last check. Nothing is stored until you register it.",
      },
      { target: "voice-card", title: "This step", text: LINES[step] },
    ],
  });

  async function submit() {
    if (!audio) return;
    await register.mutateAsync({
      wav: audio.wav,
      source: audio.source,
      name: consent.name,
      speaker: consent.speaker,
      relationship: consent.relationship,
      permission_record: consent.permission_record,
      license: consent.license,
      signature: consent.signature,
    });
    navigate("/voices?added=1");
  }

  return (
    <>
      <div className="breadcrumb">
        <Link to="/voices">Voice studio</Link>
      </div>
      <div className="page-header">
        <h1>Add a voice</h1>
      </div>
      <ol className="voice-steps" aria-label="Steps" data-tour="voice-steps">
        {STEPS.map((label, index) => (
          <li
            key={label}
            className={index === step ? "now" : index < step ? "done" : ""}
            aria-current={index === step ? "step" : undefined}
          >
            <span className="voice-step-number">{index + 1}</span> {label}
          </li>
        ))}
      </ol>
      <div
        className="card stack"
        style={{ maxWidth: "52rem" }}
        data-tour="voice-card"
      >
        <h2 ref={heading} tabIndex={-1} className="voice-step-title">
          {STEPS[step]}
        </h2>
        {step === 0 ? (
          <ConsentStep
            values={consent}
            onChange={setConsent}
            onDone={() => setStep(1)}
          />
        ) : null}
        {step === 1 ? (
          <CaptureStep
            initial={audio}
            onBack={() => setStep(0)}
            onDone={(captured) => {
              setAudio(captured);
              setStep(2);
            }}
          />
        ) : null}
        {step === 2 && audio ? (
          <div className="stack">
            <dl className="voice-summary">
              <dt>Voice of</dt>
              <dd>{consent.speaker.trim()}</dd>
              <dt>Consent</dt>
              <dd>
                {consent.relationship === "self"
                  ? "Their own voice, signed by them"
                  : `Written permission: ${consent.permission_record.trim()}`}
              </dd>
              <dt>Signed</dt>
              <dd>
                {consent.signature.trim()},{" "}
                {formatDate(new Date().toISOString())}
              </dd>
              <dt>Terms</dt>
              <dd>{consent.license.trim()}</dd>
              <dt>Recording</dt>
              <dd>
                {formatTime(audio.seconds)},{" "}
                {audio.source === "recorded" ? "recorded here" : "uploaded"}
              </dd>
            </dl>
            <WaveformPlayer blob={audio.wav} title="Your recording" />
            <ErrorAlert error={register.error} />
            <div className="row">
              <Button variant="secondary" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button busy={register.isPending} onClick={() => void submit()}>
                Register voice
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}

function ConsentStep({
  values,
  onChange,
  onDone,
}: {
  values: ConsentValues;
  onChange: (values: ConsentValues) => void;
  onDone: () => void;
}) {
  const form = useConsentForm();
  const [errors, setErrors] = useState<ConsentErrors>({});
  const set = <K extends keyof ConsentValues>(
    key: K,
    value: ConsentValues[K],
  ) => onChange({ ...values, [key]: value });
  const own = values.relationship === "self";

  function next(event: FormEvent) {
    event.preventDefault();
    const problems = consentProblems(values);
    setErrors(problems);
    if (!Object.keys(problems).length) onDone();
  }

  return (
    <form className="stack" onSubmit={next} noValidate>
      <p className="muted">
        A voice can only be cloned with its speaker&apos;s permission. Complete
        this form before recording or uploading; it is kept with the recording.
      </p>
      <fieldset className="choice-group">
        <legend>Whose voice is it?</legend>
        <div className="character-cards">
          {(
            [
              ["self", "My own voice", "You are the person speaking."],
              [
                "permission",
                "Someone else's voice",
                "You hold their written permission.",
              ],
            ] as const
          ).map(([value, label, about]) => (
            <label key={value} className="character-card">
              <input
                type="radio"
                name="relationship"
                value={value}
                checked={values.relationship === value}
                onChange={() => set("relationship", value)}
              />
              <span className="character-name">{label}</span>
              <span className="muted">{about}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <TextField
        label={own ? "Your full name" : "Their full name"}
        autoComplete={own ? "name" : "off"}
        value={values.speaker}
        error={errors.speaker}
        onChange={(event) => set("speaker", event.target.value)}
      />
      {!own ? (
        <TextArea
          label="Where is their written permission kept?"
          hint="For example: signed release form, saved in the show's shared drive."
          rows={2}
          value={values.permission_record}
          error={errors.permission_record}
          onChange={(event) => set("permission_record", event.target.value)}
        />
      ) : null}
      <TextField
        label="Label (optional)"
        hint="How it appears in your voice list, for example “My voice”."
        value={values.name}
        error={errors.name}
        onChange={(event) => set("name", event.target.value)}
      />
      <TextArea
        label="Terms of use"
        rows={2}
        value={values.license}
        error={errors.license}
        onChange={(event) => set("license", event.target.value)}
      />
      <div className="consent-statement" aria-live="polite">
        <p className="consent-label">
          Consent statement {form.data ? `(version ${form.data.version})` : ""}
        </p>
        <p>{form.data?.statement ?? "Loading the consent statement…"}</p>
      </div>
      <fieldset
        className="choice-group stack"
        style={{ gap: "var(--space-2)" }}
      >
        <legend>Agreements</legend>
        <CheckboxField
          label="I agree to the consent statement above."
          checked={values.agree_clone}
          onChange={(event) => set("agree_clone", event.target.checked)}
        />
        <CheckboxField
          label="Episodes voiced with this voice will be labelled as AI-generated."
          checked={values.agree_ai_label}
          onChange={(event) => set("agree_ai_label", event.target.checked)}
        />
        <CheckboxField
          label="I can withdraw consent at any time by deleting the voice."
          checked={values.agree_withdraw}
          onChange={(event) => set("agree_withdraw", event.target.checked)}
        />
        {errors.agreements ? (
          <p className="field-error" role="alert">
            {errors.agreements}
          </p>
        ) : null}
      </fieldset>
      <TextField
        label="Signature"
        hint={
          own
            ? "Type your full name, the same as above."
            : "Type your own full name."
        }
        autoComplete="name"
        value={values.signature}
        error={errors.signature}
        onChange={(event) => set("signature", event.target.value)}
      />
      <p className="muted" style={{ fontSize: "var(--text-sm)" }}>
        Signed on {formatDate(new Date().toISOString())}.
      </p>
      <div className="row">
        <Button type="submit" disabled={!form.data}>
          Agree and continue
        </Button>
      </div>
    </form>
  );
}

function CaptureStep({
  initial,
  onBack,
  onDone,
}: {
  initial: (Recording & { source: "recorded" | "uploaded" }) | null;
  onBack: () => void;
  onDone: (audio: Recording & { source: "recorded" | "uploaded" }) => void;
}) {
  const [mode, setMode] = useState<"record" | "upload">(
    initial?.source === "uploaded" ? "upload" : "record",
  );
  const recorder = useRecorder();
  const [uploaded, setUploaded] = useState<Recording | null>(
    initial?.source === "uploaded" ? initial : null,
  );
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [converting, setConverting] = useState(false);
  const recorded =
    recorder.recording ?? (initial?.source === "recorded" ? initial : null);
  const current = mode === "record" ? recorded : uploaded;
  const problem = current ? lengthProblem(current.seconds) : null;

  async function pick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadError(null);
    setConverting(true);
    try {
      setUploaded(await toVoiceWav(await decode(file)));
    } catch {
      setUploaded(null);
      setUploadError(
        "That file could not be read as audio. Try a WAV, MP3 or M4A file.",
      );
    } finally {
      setConverting(false);
    }
  }

  return (
    <div className="stack">
      <div
        className="segmented"
        role="radiogroup"
        aria-label="How to add the voice"
      >
        {(
          [
            ["record", "Record here"],
            ["upload", "Upload a file"],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="choice-pill">
            <input
              type="radio"
              name="capture"
              checked={mode === value}
              onChange={() => setMode(value)}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>

      {mode === "record" ? (
        <div className="stack">
          <div className="read-aloud">
            <p className="consent-label">
              Read this aloud, in your natural voice
            </p>
            <p className="read-aloud-text">{PROMPT}</p>
          </div>
          <div className={`recorder recorder-${recorder.state}`}>
            <LiveWaveform analyser={recorder.analyser} />
            <div className="recorder-controls">
              {recorder.state === "recording" ? (
                <Button onClick={recorder.stop}>
                  <span className="rec-dot" aria-hidden="true" /> Stop recording
                </Button>
              ) : (
                <Button
                  variant={recorded ? "secondary" : "primary"}
                  busy={
                    recorder.state === "asking" ||
                    recorder.state === "processing"
                  }
                  onClick={() => void recorder.start()}
                >
                  {recorded ? "Record again" : "Start recording"}
                </Button>
              )}
              <span className="recorder-time" aria-live="off">
                {formatTime(recorder.seconds)}{" "}
                <span className="muted">· aim for 15–30 s</span>
              </span>
            </div>
            <p className="sr-only" aria-live="polite">
              {recorder.state === "recording"
                ? "Recording"
                : recorder.state === "ready"
                  ? "Recording finished"
                  : ""}
            </p>
          </div>
          {recorder.error ? <Alert tone="error">{recorder.error}</Alert> : null}
        </div>
      ) : (
        <div className="stack">
          <label className="upload-drop">
            <input
              type="file"
              accept="audio/*"
              onChange={(event) => void pick(event)}
            />
            <span>
              <strong>Choose an audio file</strong>
              <span className="muted">
                {" "}
                · WAV, MP3, M4A or WebM, 5 to 90 seconds, one speaker
              </span>
            </span>
          </label>
          {converting ? <p className="muted">Reading the file…</p> : null}
          {uploadError ? <Alert tone="error">{uploadError}</Alert> : null}
        </div>
      )}

      {current ? (
        <div className="stack">
          <WaveformPlayer blob={current.wav} title="Your recording" />
          {problem ? <Alert tone="error">{problem}</Alert> : null}
        </div>
      ) : null}

      <div className="row">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button
          disabled={
            !current || Boolean(problem) || recorder.state === "recording"
          }
          onClick={() =>
            current &&
            onDone({
              ...current,
              source: mode === "record" ? "recorded" : "uploaded",
            })
          }
        >
          Continue
        </Button>
      </div>
    </div>
  );
}
