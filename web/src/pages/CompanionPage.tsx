import { useId, useState } from "react";

import { Alert, ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { useAssistant } from "../bots/assistant";
import { useAvatar, useSaveAvatar } from "../bots/avatar";
import { AvatarFace } from "../bots/AvatarFace";
import { CompanionPicker } from "../bots/CompanionPicker";
import {
  endOfToday,
  useJamesSettings,
  type Chattiness,
  type Corner,
} from "../bots/jamesSettings";
import { canSpeak } from "../bots/speech";
import { CheckboxField } from "../components/Field";
import { Tabs } from "../components/Tabs";
import { usePageTitle } from "../hooks/usePageTitle";

const CHATTINESS: { id: Chattiness; label: string; says: string }[] = [
  { id: "quiet", label: "Quiet", says: "Only when you open him" },
  {
    id: "helpful",
    label: "Helpful",
    says: "Speaks up when something finishes or fails",
  },
  { id: "chatty", label: "Chatty", says: "Also offers a tip on new pages" },
];
const CORNERS: { id: Corner; label: string }[] = [
  { id: "right", label: "Bottom right" },
  { id: "left", label: "Bottom left" },
];

/** A row of radio buttons drawn as a segmented control. */
function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { id: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className="toggle-group">
      <legend className="sr-only">{label}</legend>
      {options.map((option) => (
        <label key={option.id} className="toggle-option">
          <input
            type="radio"
            name={name}
            className="sr-only"
            checked={value === option.id}
            onChange={() => onChange(option.id)}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function Behaviour({ name }: { name: string }) {
  const settings = useJamesSettings();
  const chosen =
    CHATTINESS.find((c) => c.id === settings.chattiness) ?? CHATTINESS[1];
  const mac =
    typeof navigator !== "undefined" &&
    /Mac|iPhone|iPad/.test(navigator.platform);
  return (
    <div className="behaviour">
      <div className="behaviour-row">
        <span className="behaviour-label">How chatty</span>
        <div className="stack" style={{ gap: "var(--space-2)" }}>
          <Segmented
            label={`How chatty ${name} is`}
            value={settings.chattiness}
            options={CHATTINESS}
            onChange={settings.setChattiness}
          />
          <span className="muted behaviour-note">{chosen.says}</span>
        </div>
      </div>
      {canSpeak() ? (
        <div className="behaviour-row">
          <span className="behaviour-label">Answer out loud</span>
          <CheckboxField
            label="Read answers aloud"
            hint="With the words on screen. Talking to him always answers out loud."
            checked={settings.speakReplies}
            onChange={(event) => settings.setSpeakReplies(event.target.checked)}
          />
        </div>
      ) : null}
      <div className="behaviour-row">
        <span className="behaviour-label">Where he sits</span>
        <Segmented
          label={`Where ${name} sits`}
          value={settings.corner}
          options={CORNERS}
          onChange={settings.setCorner}
        />
      </div>
      <div className="behaviour-row">
        <span className="behaviour-label">Snooze</span>
        {settings.snoozedUntil ? (
          <div className="row" style={{ alignItems: "center" }}>
            <span className="behaviour-note">
              Snoozed until{" "}
              {new Date(settings.snoozedUntil).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            <Button
              variant="secondary"
              onClick={() => settings.snoozeUntil(null)}
            >
              Wake up
            </Button>
          </div>
        ) : (
          <div className="row">
            <Button
              variant="secondary"
              onClick={() => settings.snoozeUntil(Date.now() + 3_600_000)}
            >
              1 hour
            </Button>
            <Button
              variant="secondary"
              onClick={() => settings.snoozeUntil(endOfToday())}
            >
              Rest of today
            </Button>
          </div>
        )}
      </div>
      <div className="behaviour-row">
        <span className="behaviour-label">On every page</span>
        <CheckboxField
          label={`Show ${name}`}
          hint="Remembered on this device."
          checked={!settings.off}
          onChange={(event) => settings.setOff(!event.target.checked)}
        />
      </div>
      <div className="behaviour-row">
        <span className="behaviour-label">Shortcut</span>
        <span className="behaviour-note">
          <kbd>{mac ? "⌘" : "Ctrl"}</kbd> <kbd>J</kbd> opens {name} anywhere
        </span>
      </div>
    </div>
  );
}

/** Your companion: how he looks (saved on your account) and how he behaves (this device). */
export function CompanionPage() {
  usePageTitle("Companion");
  const saved = useAvatar();
  const save = useSaveAvatar();
  const [draft, setDraft] = useState(saved);
  const [tab, setTab] = useState("look");
  const changed = JSON.stringify(draft) !== JSON.stringify(saved);
  useAssistant({
    page: "companion",
    key: "companion",
    moment: "companion",
    mode: "celebrating",
    context: "your companion",
    line: changed
      ? "Ooh, I like it! Save when you're happy."
      : "Change how I look, or how chatty I am.",
    questions: [
      "What does my personality change?",
      "Can you read your answers aloud?",
    ],
  });

  return (
    <>
      <div className="page-header">
        <h1>Companion</h1>
      </div>
      <Tabs
        label="Companion"
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "look", label: "Look" },
          { id: "behaviour", label: "Behaviour" },
        ]}
      >
        {tab === "look" ? (
          <div className="card stack">
            <CompanionPicker value={draft} onChange={setDraft} />
            {save.isSuccess && !changed ? (
              <Alert tone="success">Saved. Say hi to {saved.name}!</Alert>
            ) : null}
            <ErrorAlert error={save.error} />
            <div className="row">
              <Button
                busy={save.isPending}
                disabled={!changed || !draft.name.trim()}
                onClick={() => save.mutate(draft)}
              >
                Save companion
              </Button>
              {changed ? (
                <Button variant="ghost" onClick={() => setDraft(saved)}>
                  Undo changes
                </Button>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="behaviour-layout">
            <div className="card behaviour-preview">
              <AvatarFace avatar={saved} size={140} mood="happy" />
              <p className="behaviour-name">{saved.name}</p>
            </div>
            <section className="card" aria-label="Behaviour">
              <Behaviour name={saved.name} />
            </section>
          </div>
        )}
      </Tabs>
    </>
  );
}
