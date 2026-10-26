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
  ClaimDetail,
  EpisodeRead,
  EpisodeScript,
  Page,
  ScriptEdit,
  ShowCreate,
  ShowRead,
  ShowUpdate,
  SourceRead,
  StageRunRead,
  UploadRead,
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
  consent: ["voices", "consent"] as const,
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

export function useStartEpisode(showId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<EpisodeRead> =>
      unwrap(
        await api.POST("/v1/shows/{show_id}/episodes", {
          params: { path: { show_id: showId } },
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

type EpisodeAction = "approve" | "retry" | "cancel";

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
