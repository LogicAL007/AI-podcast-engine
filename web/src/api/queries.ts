// One TanStack Query hook per API call. Mutations refresh what they change.
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { api, API_BASE, ApiError, unwrap } from "./client";
import type {
  AssistantAnswer,
  AssistantQuestion,
  ClaimDetail,
  EpisodeRead,
  EpisodeScript,
  MusicTrackRead,
  Page,
  ScriptEdit,
  ShowCreate,
  ShowRead,
  ShowUpdate,
  SourceRead,
  SpeechClipRead,
  SpeechCreate,
  SpeechEngine,
  StageRunRead,
  UploadRead,
  UsageRead,
  VoiceRead,
} from "./types";

export const PAGE_SIZE = 20;

export const keys = {
  setup: ["setup"] as const,
  me: ["me"] as const,
  shows: (offset: number) => ["shows", offset] as const,
  show: (id: string) => ["show", id] as const,
  showEpisodes: (id: string, offset: number) =>
    ["show", id, "episodes", offset] as const,
  sources: (id: string, offset: number) =>
    ["show", id, "sources", offset] as const,
  uploads: (id: string) => ["show", id, "uploads"] as const,
  episode: (id: string) => ["episode", id] as const,
  script: (id: string) => ["episode", id, "script"] as const,
  runs: (id: string) => ["episode", id, "runs"] as const,
  claims: (id: string) => ["episode", id, "claims"] as const,
  notes: (url: string) => ["notes", url] as const,
  voices: ["voices"] as const,
  recentEpisodes: ["episodes", "recent"] as const,
  reviewQueue: ["episodes", "needs_review"] as const,
  usage: ["usage"] as const,
  consent: ["voices", "consent"] as const,
  speechEngine: ["speech", "engine"] as const,
  speech: ["speech"] as const,
  speechClip: (id: string) => ["speech", id] as const,
  music: ["music"] as const,
};

const paging = (offset: number) => ({ limit: PAGE_SIZE, offset });

// ---- sign-in and setup ----------------------------------------------------------------------
export function useSetupStatus() {
  return useQuery({
    queryKey: keys.setup,
    queryFn: async () => unwrap(await api.GET("/v1/auth/setup")),
    staleTime: 60_000,
  });
}

export function useRegisterFirstAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      unwrap(
        await api.POST("/v1/auth/register", {
          body: { ...body, role: "admin" },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.setup }),
  });
}

/** Self-service sign-up (when open): the account is always a creator, whatever is asked. */
export function useSignUp() {
  return useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      unwrap(
        await api.POST("/v1/auth/register", {
          body: { ...body, role: "creator" },
        }),
      ),
  });
}

export function useRequestPasswordReset() {
  return useMutation({
    mutationFn: async (email: string) =>
      unwrap(await api.POST("/v1/auth/password-reset", { body: { email } })),
  });
}

export function useConfirmPasswordReset() {
  return useMutation({
    mutationFn: async (body: { token: string; new_password: string }) =>
      unwrap(await api.POST("/v1/auth/password-reset/confirm", { body })),
  });
}

// ---- shows ------------------------------------------------------------------------------------
export function useShows(offset: number) {
  return useQuery({
    queryKey: keys.shows(offset),
    queryFn: async (): Promise<Page<ShowRead>> =>
      unwrap(await api.GET("/v1/shows", { params: { query: paging(offset) } })),
    placeholderData: keepPreviousData,
  });
}

export function useShow(showId: string) {
  return useQuery({
    queryKey: keys.show(showId),
    queryFn: async (): Promise<ShowRead> =>
      unwrap(
        await api.GET("/v1/shows/{show_id}", {
          params: { path: { show_id: showId } },
        }),
      ),
  });
}

export function useCreateShow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: ShowCreate): Promise<ShowRead> =>
      unwrap(await api.POST("/v1/shows", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["shows"] }),
  });
}

export function useUpdateShow(showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: ShowUpdate): Promise<ShowRead> =>
      unwrap(
        await api.PATCH("/v1/shows/{show_id}", {
          params: { path: { show_id: showId } },
          body,
        }),
      ),
    onSuccess: (show) => {
      client.setQueryData(keys.show(showId), show);
      return client.invalidateQueries({ queryKey: ["shows"] });
    },
  });
}

export function useDeleteShow(showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.DELETE("/v1/shows/{show_id}", {
          params: { path: { show_id: showId } },
        }),
      ),
    onSuccess: () => {
      client.removeQueries({ queryKey: keys.show(showId) });
      return client.invalidateQueries({ queryKey: ["shows"] });
    },
  });
}

// ---- a show's episodes, sources and uploads ------------------------------------------------------
export function useShowEpisodes(showId: string, offset: number) {
  return useQuery({
    queryKey: keys.showEpisodes(showId, offset),
    queryFn: async (): Promise<Page<EpisodeRead>> =>
      unwrap(
        await api.GET("/v1/shows/{show_id}/episodes", {
          params: { path: { show_id: showId }, query: paging(offset) },
        }),
      ),
    placeholderData: keepPreviousData,
    // Keep the list's statuses fresh while anything in it is being made.
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (e) => e.status === "queued" || e.status === "processing",
      )
        ? 5_000
        : false,
  });
}

/** Start an episode. For a published show it is a refresh: only what changed is redone,
 * unless `rebuild` asks for every segment to be regenerated. */
export function useStartEpisode(showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (options?: { rebuild?: boolean }): Promise<EpisodeRead> =>
      unwrap(
        await api.POST("/v1/shows/{show_id}/episodes", {
          params: { path: { show_id: showId } },
          body: options?.rebuild ? { rebuild: true } : undefined,
        }),
      ),
    onSuccess: (episode) => {
      client.setQueryData(keys.episode(episode.episode_id), episode);
      return client.invalidateQueries({
        queryKey: ["show", showId, "episodes"],
      });
    },
  });
}

export function useSources(showId: string, offset: number) {
  return useQuery({
    queryKey: keys.sources(showId, offset),
    queryFn: async (): Promise<Page<SourceRead>> =>
      unwrap(
        await api.GET("/v1/shows/{show_id}/sources", {
          params: { path: { show_id: showId }, query: paging(offset) },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useUploads(showId: string) {
  return useQuery({
    queryKey: keys.uploads(showId),
    queryFn: async (): Promise<Page<UploadRead>> =>
      unwrap(
        await api.GET("/v1/shows/{show_id}/uploads", {
          params: {
            path: { show_id: showId },
            query: { limit: 100, offset: 0 },
          },
        }),
      ),
  });
}

export function useUploadPdf(showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (file: File): Promise<UploadRead> => {
      const form = new FormData();
      form.append("file", file);
      return unwrap(
        await api.POST("/v1/shows/{show_id}/uploads", {
          params: { path: { show_id: showId } },
          body: form as unknown as { file: string },
          bodySerializer: (body) => body as unknown as FormData,
        }),
      );
    },
    onSuccess: () =>
      client.invalidateQueries({ queryKey: keys.uploads(showId) }),
  });
}

export function useDeleteUpload(showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (uploadId: string) =>
      unwrap(
        await api.DELETE("/v1/shows/{show_id}/uploads/{upload_id}", {
          params: { path: { show_id: showId, upload_id: uploadId } },
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: keys.uploads(showId) }),
  });
}

// ---- one episode ----------------------------------------------------------------------------
export function useEpisode(
  episodeId: string,
  refetchInterval: number | false = false,
) {
  return useQuery({
    queryKey: keys.episode(episodeId),
    queryFn: async (): Promise<EpisodeRead> =>
      unwrap(
        await api.GET("/v1/episodes/{episode_id}", {
          params: { path: { episode_id: episodeId } },
        }),
      ),
    refetchInterval,
  });
}

export function useEpisodeScript(episodeId: string, enabled = true) {
  return useQuery({
    queryKey: keys.script(episodeId),
    queryFn: async (): Promise<EpisodeScript> =>
      unwrap(
        await api.GET("/v1/episodes/{episode_id}/script", {
          params: { path: { episode_id: episodeId } },
        }),
      ),
    enabled,
  });
}

export function useEpisodeRuns(episodeId: string) {
  return useQuery({
    queryKey: keys.runs(episodeId),
    queryFn: async (): Promise<Page<StageRunRead>> =>
      unwrap(
        await api.GET("/v1/episodes/{episode_id}/runs", {
          params: {
            path: { episode_id: episodeId },
            query: { limit: 100, offset: 0 },
          },
        }),
      ),
  });
}

export function useEpisodeClaims(episodeId: string) {
  return useQuery({
    queryKey: keys.claims(episodeId),
    queryFn: async (): Promise<Page<ClaimDetail>> =>
      unwrap(
        await api.GET("/v1/episodes/{episode_id}/claims", {
          params: {
            path: { episode_id: episodeId },
            query: { limit: 100, offset: 0 },
          },
        }),
      ),
  });
}

/** The show notes (Markdown), from the episode's public notes link. */
export function useNotes(link: string | null | undefined) {
  return useQuery({
    queryKey: keys.notes(link ?? ""),
    queryFn: async () => {
      const response = await fetch(`${API_BASE}${link}`, {
        credentials: "same-origin",
      });
      if (!response.ok)
        throw new ApiError(
          response.status,
          "The show notes could not be loaded.",
        );
      return response.text();
    },
    enabled: Boolean(link),
  });
}

function refreshEpisode(client: QueryClient, episode: EpisodeRead) {
  client.setQueryData(keys.episode(episode.episode_id), episode);
  void client.invalidateQueries({ queryKey: ["episode", episode.episode_id] });
  void client.invalidateQueries({
    queryKey: ["show", episode.show_id, "episodes"],
  });
}

export function useSaveScript(episodeId: string) {
  const client = useQueryClient();
  return useMutation({
    // Saving re-runs the fact-check, so the answer is the episode, back in progress.
    mutationFn: async (body: ScriptEdit): Promise<EpisodeRead> =>
      unwrap(
        await api.PATCH("/v1/episodes/{episode_id}/script", {
          params: { path: { episode_id: episodeId } },
          body,
        }),
      ),
    onSuccess: (episode) => refreshEpisode(client, episode),
  });
}

type EpisodeAction = "approve" | "retry" | "cancel" | "remix";

export function useEpisodeAction(episodeId: string, action: EpisodeAction) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<EpisodeRead> => {
      const params = { params: { path: { episode_id: episodeId } } };
      if (action === "approve")
        return unwrap(
          await api.POST("/v1/episodes/{episode_id}/approve", params),
        );
      if (action === "retry")
        return unwrap(
          await api.POST("/v1/episodes/{episode_id}/retry", params),
        );
      if (action === "remix")
        return unwrap(
          await api.POST("/v1/episodes/{episode_id}/remix", params),
        );
      return unwrap(await api.POST("/v1/episodes/{episode_id}/cancel", params));
    },
    onSuccess: (episode) => refreshEpisode(client, episode),
  });
}

export function useDeleteEpisode(episodeId: string, showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.DELETE("/v1/episodes/{episode_id}", {
          params: { path: { episode_id: episodeId } },
        }),
      ),
    onSuccess: () => {
      client.removeQueries({ queryKey: ["episode", episodeId] });
      return client.invalidateQueries({
        queryKey: ["show", showId, "episodes"],
      });
    },
  });
}

// ---- voices (recorded for Chatterbox, with consent) ------------------------------------------

export function useVoices() {
  return useQuery({
    queryKey: keys.voices,
    queryFn: async (): Promise<Page<VoiceRead>> =>
      unwrap(
        await api.GET("/v1/voices", {
          params: { query: { limit: 100, offset: 0 } },
        }),
      ),
  });
}

export function useConsentForm() {
  return useQuery({
    queryKey: keys.consent,
    queryFn: async () => unwrap(await api.GET("/v1/voices/consent")),
    staleTime: Infinity,
  });
}

export interface VoiceRegistration {
  wav: Blob;
  source: "recorded" | "uploaded";
  name: string;
  speaker: string;
  relationship: "self" | "permission";
  permission_record: string;
  license: string;
  signature: string;
}

export function useRegisterVoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (voice: VoiceRegistration): Promise<VoiceRead> => {
      const form = new FormData();
      form.append("audio", voice.wav, "voice.wav");
      for (const field of [
        "source",
        "name",
        "speaker",
        "relationship",
        "permission_record",
        "license",
        "signature",
      ] as const)
        form.append(field, voice[field]);
      for (const agreement of [
        "agree_clone",
        "agree_ai_label",
        "agree_withdraw",
      ])
        form.append(agreement, "true");
      return unwrap(
        await api.POST("/v1/voices", {
          body: form as never,
          bodySerializer: (body) => body as unknown as FormData,
        }),
      );
    },
    onSuccess: () => client.invalidateQueries({ queryKey: keys.voices }),
  });
}

export function useDeleteVoice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (voiceId: string) =>
      unwrap(
        await api.DELETE("/v1/voices/{voice_id}", {
          params: { path: { voice_id: voiceId } },
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.voices });
      void client.invalidateQueries({ queryKey: ["show"] }); // hosts that used it lose it
    },
  });
}

// ---- type-to-speech (voiced by the voice worker) --------------------------------------------

export function useSpeechEngine() {
  return useQuery({
    queryKey: keys.speechEngine,
    queryFn: async (): Promise<SpeechEngine> =>
      unwrap(await api.GET("/v1/speech/engine")),
    staleTime: 30_000,
  });
}

export function useSpeechClips() {
  return useQuery({
    queryKey: keys.speech,
    queryFn: async (): Promise<SpeechClipRead[]> =>
      unwrap(await api.GET("/v1/speech")),
  });
}

const SPEECH_POLL_MS = 1500;

/** One clip, polled until the voice worker has finished it (done or failed). */
export function useSpeechClip(clipId: string | null) {
  const client = useQueryClient();
  return useQuery({
    queryKey: keys.speechClip(clipId ?? ""),
    enabled: clipId !== null,
    queryFn: async (): Promise<SpeechClipRead> => {
      const clip = unwrap(
        await api.GET("/v1/speech/{clip_id}", {
          params: { path: { clip_id: clipId as string } },
        }),
      );
      if (clip.status === "done" || clip.status === "failed")
        void client.invalidateQueries({ queryKey: keys.speech, exact: true });
      return clip;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "done" || status === "failed" ? false : SPEECH_POLL_MS;
    },
  });
}

export function useCreateSpeech() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: SpeechCreate): Promise<SpeechClipRead> =>
      unwrap(await api.POST("/v1/speech", { body })),
    onSuccess: (clip) => {
      client.setQueryData(keys.speechClip(clip.clip_id), clip);
      void client.invalidateQueries({ queryKey: keys.speech, exact: true });
      void client.invalidateQueries({ queryKey: keys.speechEngine });
    },
  });
}

export function useDeleteSpeech() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (clipId: string) =>
      unwrap(
        await api.DELETE("/v1/speech/{clip_id}", {
          params: { path: { clip_id: clipId } },
        }),
      ),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: keys.speech, exact: true }),
  });
}

// ---- music (built-in tracks and uploads) -------------------------------------------------------

export function useMusic() {
  return useQuery({
    queryKey: keys.music,
    queryFn: async (): Promise<MusicTrackRead[]> =>
      unwrap(await api.GET("/v1/music")),
    staleTime: 60_000,
  });
}

export interface MusicUpload {
  wav: Blob;
  name: string;
  role: MusicTrackRead["role"];
  credit: string;
}

export function useUploadMusic() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (track: MusicUpload): Promise<MusicTrackRead> => {
      const form = new FormData();
      form.append("audio", track.wav, "track.wav");
      form.append("name", track.name);
      form.append("role", track.role);
      form.append("credit", track.credit);
      form.append("rights", "true");
      return unwrap(
        await api.POST("/v1/music", {
          body: form as never,
          bodySerializer: (body) => body as unknown as FormData,
        }),
      );
    },
    onSuccess: () => client.invalidateQueries({ queryKey: keys.music }),
  });
}

export function useDeleteMusic() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (trackId: string) =>
      unwrap(
        await api.DELETE("/v1/music/{track_id}", {
          params: { path: { track_id: trackId } },
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.music });
      void client.invalidateQueries({ queryKey: ["show"] }); // shows that used it lose it
    },
  });
}

/** Ask the companion bot; with the LLM on, each question is one model call (limited per hour). */
export function useAskAssistant() {
  return useMutation({
    mutationFn: async (question: AssistantQuestion): Promise<AssistantAnswer> =>
      unwrap(await api.POST("/v1/assistant/ask", { body: question })),
  });
}

// ---- home: recent episodes across shows, the review queue and today's Gemini budget ---------

/** The newest episodes of every show, kept fresh while any is being made. */
export function useRecentEpisodes() {
  return useQuery({
    queryKey: keys.recentEpisodes,
    queryFn: async (): Promise<Page<EpisodeRead>> =>
      unwrap(await api.GET("/v1/episodes", { params: { query: paging(0) } })),
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (e) => e.status === "queued" || e.status === "processing",
      )
        ? 5_000
        : false,
  });
}

/** Episodes waiting for a person: held by the fact-check, or paused before voicing. */
export function useReviewQueue() {
  return useQuery({
    queryKey: keys.reviewQueue,
    queryFn: async (): Promise<Page<EpisodeRead>> =>
      unwrap(
        await api.GET("/v1/episodes", {
          params: { query: { status: "needs_review", limit: 5, offset: 0 } },
        }),
      ),
  });
}

/** Today's Gemini requests, used and left; shared by every account, so refreshed often. */
export function useUsage() {
  return useQuery({
    queryKey: keys.usage,
    queryFn: async (): Promise<UsageRead> => unwrap(await api.GET("/v1/usage")),
    refetchInterval: 60_000,
  });
}
