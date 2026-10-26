// The show form's values, checked against the same limits the API enforces, so most mistakes
// are caught before anything is sent.
import type {
  ExpertiseLevel,
  ShowCreate,
  ShowRead,
  Tone,
} from "../../api/types";

export interface ShowValues {
  topic: string;
  tone: Tone;
  target_minutes: string;
  host_count: string;
  language: string;
  expertise: ExpertiseLevel;
  sources: string; // one URL per line
  topic_keywords: string;
  attribution: string;
  max_segments: string;
  ranking_profile: "daily" | "explainer";
  review_before_voice: boolean;
  host_voices: Record<string, string>; // host name -> registered voice id
}

/** Host names in speaking order, as the pipeline uses them. */
export const HOST_NAMES = ["Alex", "Sam", "Jordan", "Riley"];

export type ShowErrors = Partial<Record<keyof ShowValues, string>>;

export const EMPTY_SHOW: ShowValues = {
  topic: "",
  tone: "neutral",
  target_minutes: "7",
  host_count: "2",
  language: "en",
  expertise: "intermediate",
  sources: "",
  topic_keywords: "",
  attribution: "",
  max_segments: "6",
  ranking_profile: "explainer",
  review_before_voice: false,
  host_voices: {},
};

/** "Try a sample": a ready topic on openly licensed sources, so a first episode is one click. */
export const SAMPLE_SHOW: Pick<
  ShowValues,
  "topic" | "sources" | "topic_keywords" | "attribution"
> = {
  topic: "How the Moon makes the tides",
  sources: [
    "https://en.wikipedia.org/wiki/Tide",
    "https://en.wikipedia.org/wiki/Tidal_force",
  ].join("\n"),
  topic_keywords: "tides, Moon, gravity, tidal force, high tide, low tide",
  attribution:
    "Based on the Wikipedia articles Tide and Tidal force, CC BY-SA 4.0.",
};

/** Languages offered in the form. A show saved with another tag keeps it (languageOptions). */
export const LANGUAGES: { value: string; label: string }[] = [
  { value: "en", label: "English" },
  { value: "en-CA", label: "English (Canada)" },
  { value: "fr", label: "French" },
  { value: "fr-CA", label: "French (Canada)" },
  { value: "es", label: "Spanish" },
  { value: "pt", label: "Portuguese" },
  { value: "de", label: "German" },
  { value: "ar", label: "Arabic" },
  { value: "hi", label: "Hindi" },
  { value: "zh", label: "Chinese" },
  { value: "yo", label: "Yoruba" },
];

export function languageOptions(
  current: string,
): { value: string; label: string }[] {
  return LANGUAGES.some((language) => language.value === current) || !current
    ? LANGUAGES
    : [...LANGUAGES, { value: current, label: current }];
}

/** The first step of a new show asks only for these; the rest have defaults. */
export const STEP_ONE: (keyof ShowValues)[] = ["topic", "sources"];
/** Rarely changed settings, kept behind "More options". */
export const ADVANCED: (keyof ShowValues)[] = [
  "max_segments",
  "ranking_profile",
  "topic_keywords",
  "attribution",
];

/** Only the problems among these fields. */
export function errorsAmong(
  errors: ShowErrors,
  fields: (keyof ShowValues)[],
): ShowErrors {
  return Object.fromEntries(
    Object.entries(errors).filter(([field]) =>
      fields.includes(field as keyof ShowValues),
    ),
  ) as ShowErrors;
}

export function valuesOf(show: ShowRead): ShowValues {
  return {
    topic: show.topic,
    tone: show.tone,
    target_minutes: String(show.target_minutes),
    host_count: String(show.host_count),
    language: show.language,
    expertise: show.expertise,
    sources: show.sources.join("\n"),
    topic_keywords: show.topic_keywords ?? "",
    attribution: show.attribution ?? "",
    max_segments: String(show.max_segments ?? 6),
    ranking_profile:
      (show.ranking_profile as ShowValues["ranking_profile"]) ?? "explainer",
    review_before_voice: Boolean(show.review_before_voice),
    host_voices: { ...(show.host_voices ?? {}) },
  };
}

function whole(value: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const n = Number(value);
  return n >= min && n <= max ? n : null;
}

function isWebUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/** The request body, or the problems to fix first. */
export function validateShow(values: ShowValues): {
  body: ShowCreate | null;
  errors: ShowErrors;
} {
  const errors: ShowErrors = {};
  const topic = values.topic.trim();
  if (topic.length < 3 || topic.length > 200)
    errors.topic = "Use 3 to 200 characters.";

  const minutes = whole(values.target_minutes, 1, 30);
  if (minutes === null)
    errors.target_minutes = "A whole number of minutes, 1 to 30.";
  const hosts = whole(values.host_count, 1, 4);
  if (hosts === null) errors.host_count = "1 to 4 hosts.";
  const segments = whole(values.max_segments, 1, 12);
  if (segments === null) errors.max_segments = "1 to 12 segments.";

  if (!/^[a-z]{2}(-[A-Z]{2})?$/.test(values.language.trim())) {
    errors.language = "A language tag such as en or fr-CA.";
  }

  const sources = values.sources
    .split(/\s+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const bad = sources.filter((url) => !isWebUrl(url));
  if (bad.length)
    errors.sources = `Not a web address: ${bad.slice(0, 2).join(", ")}`;
  else if (sources.length > 50) errors.sources = "At most 50 sources.";

  if (values.topic_keywords.length > 1000)
    errors.topic_keywords = "At most 1000 characters.";
  if (values.attribution.length > 2000)
    errors.attribution = "At most 2000 characters.";

  if (Object.keys(errors).length) return { body: null, errors };
  return {
    errors,
    body: {
      topic,
      tone: values.tone,
      target_minutes: minutes as number,
      host_count: hosts as number,
      language: values.language.trim(),
      expertise: values.expertise,
      sources,
      topic_keywords: values.topic_keywords.trim(),
      attribution: values.attribution.trim(),
      max_segments: segments as number,
      ranking_profile: values.ranking_profile,
      review_before_voice: values.review_before_voice,
      // Only hosts the show has; a host set back to its built-in voice is left out.
      host_voices: Object.fromEntries(
        Object.entries(values.host_voices).filter(
          ([host, voice]) =>
            voice && HOST_NAMES.indexOf(host) < (hosts as number),
        ),
      ),
    },
  };
}
