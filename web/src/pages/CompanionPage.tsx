import { useState } from "react";

import { Alert, ErrorAlert } from "../components/Alert";
import { Button } from "../components/Button";
import { useAssistant } from "../bots/assistant";
import { ASSISTANT_OFF } from "../bots/AssistantDock";
import { useAvatar, useSaveAvatar } from "../bots/avatar";
import { CheckboxField } from "../components/Field";
import { useRememberedFlag } from "../hooks/useRememberedFlag";
import { CompanionPicker } from "../bots/CompanionPicker";
import { usePageTitle } from "../hooks/usePageTitle";

/** Change your assistant bot any time; it is saved on your account, for every device. */
export function CompanionPage() {
  usePageTitle("Your companion");
  const saved = useAvatar();
  const save = useSaveAvatar();
  const [draft, setDraft] = useState(saved);
  const changed = JSON.stringify(draft) !== JSON.stringify(saved);
  const [off, setOff] = useRememberedFlag(ASSISTANT_OFF);
  useAssistant({
    page: "companion",
    key: "companion",
    moment: "companion",
    mode: "celebrating",
    line: changed
      ? "Ooh, I like it! Save when you're happy."
      : "Build me however you like: shape, face, colours, outfit and voice.",
    questions: [
      "What does my personality change?",
      "Can you read your tips aloud?",
    ],
  });

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Your companion</h1>
          <p className="muted">
            The bot that keeps you company while your episodes are made.
          </p>
        </div>
      </div>
      <div className="card stack">
        <CompanionPicker value={draft} onChange={setDraft} />
        {save.isSuccess && !changed ? (
          <Alert tone="success">Saved. Say hi to {saved.name}!</Alert>
        ) : null}
        <ErrorAlert error={save.error} />
        <CheckboxField
          label={`Show ${saved.name} on every page`}
          hint="With tips, next steps, a chat and tours. Remembered on this device."
          checked={!off}
          onChange={(event) => setOff(!event.target.checked)}
        />
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
    </>
  );
}
