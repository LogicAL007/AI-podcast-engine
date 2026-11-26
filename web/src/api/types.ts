// Short names for the API's schemas.
import type { components } from "./schema";

type Schemas = components["schemas"];

export type CurrentUser = Schemas["CurrentUser"];
export type Avatar = Required<Schemas["Avatar"]>;
export type VoiceRead = Schemas["VoiceRead"];
export type ShowRead = Schemas["ShowRead"];
export type ShowCreate = Schemas["ShowCreate"];
export type ShowUpdate = Schemas["ShowUpdate"];
export type Tone = Schemas["Tone"];
export type ExpertiseLevel = Schemas["ExpertiseLevel"];
export type EpisodeRead = Schemas["EpisodeRead"];
export type EpisodeStatus = Schemas["EpisodeStatus"];
export type EpisodeScript = Schemas["EpisodeScript"];
export type SegmentScript = Schemas["SegmentScript"];
export type LineRead = Schemas["LineRead"];
export type ScriptEdit = Schemas["ScriptEdit"];
export type ClaimDetail = Schemas["ClaimDetail"];
export type AssistantQuestion = Schemas["Question"];
export type AssistantAnswer = Schemas["Answer"];
export type StageRunRead = Schemas["StageRunRead"];
export type SourceRead = Schemas["SourceRead"];
export type UploadRead = Schemas["UploadRead"];
export type UsageRead = Schemas["UsageRead"];
export type VoiceEffects = Schemas["VoiceEffects"];
export type SpeechClipRead = Schemas["SpeechClipRead"];
export type SpeechCreate = Schemas["SpeechCreate"];
export type SpeechEngine = Schemas["SpeechEngine"];
export type SpeechVoice = SpeechCreate["voice"];
export type MusicTrackRead = Schemas["MusicTrackRead"];
export type ShowMusic = Schemas["ShowMusic"];
export type HostName = Schemas["EngineVoice"]["host"];

/** A page of results, as every list endpoint returns them. */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  next: string | null;
}

/** What the progress stream sends in each `episode` event. */
export interface EpisodeProgress {
  episode_id: string;
  status: EpisodeStatus;
  stage: string | null;
  step: number;
  steps: number;
  error: string | null;
  rewrite_count: number;
  running: boolean;
}
