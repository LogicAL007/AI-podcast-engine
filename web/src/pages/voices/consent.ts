// The consent form's rules, mirroring the server's (api/services/voices_service.py), so the form
// can say what is missing before anything is sent. The server checks again either way.

export interface ConsentValues {
  relationship: "self" | "permission";
  speaker: string;
  permission_record: string;
  name: string;
  license: string;
  agree_clone: boolean;
  agree_ai_label: boolean;
  agree_withdraw: boolean;
  signature: string;
}

export const DEFAULT_TERMS =
  "Used only to voice this account's podcasts in Podcast Engine";

export const EMPTY_CONSENT: ConsentValues = {
  relationship: "self",
  speaker: "",
  permission_record: "",
  name: "",
  license: DEFAULT_TERMS,
  agree_clone: false,
  agree_ai_label: false,
  agree_withdraw: false,
  signature: "",
};

const tidy = (value: string) => value.split(/\s+/).filter(Boolean).join(" ");

export type ConsentErrors = Partial<
  Record<keyof ConsentValues | "agreements", string>
>;

export function consentProblems(values: ConsentValues): ConsentErrors {
  const errors: ConsentErrors = {};
  const speaker = tidy(values.speaker);
  const signature = tidy(values.signature);
  if (!speaker) errors.speaker = "Name the person whose voice this is.";
  if (
    values.relationship === "permission" &&
    tidy(values.permission_record).length < 5
  )
    errors.permission_record = "Say where their written permission is kept.";
  if (!tidy(values.license))
    errors.license = "State the terms the recording may be used under.";
  if (!(values.agree_clone && values.agree_ai_label && values.agree_withdraw))
    errors.agreements = "Agree to all three statements to continue.";
  if (!signature) errors.signature = "Type your full name to sign.";
  else if (
    values.relationship === "self" &&
    speaker &&
    signature.toLowerCase() !== speaker.toLowerCase()
  )
    errors.signature = "For your own voice, sign with the same name as above.";
  if (speaker.length > 100 || signature.length > 100)
    errors.speaker = "Use at most 100 characters.";
  if (tidy(values.name).length > 60) errors.name = "Use at most 60 characters.";
  return errors;
}
