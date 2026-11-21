"""Pipeline state in Postgres: the only module the stage workers use to read and write tables.

Workers are stateless and exchange only an episode id over the queue, so everything one stage hands
to the next lives here: source sections, chunks and their vectors, the segment plan, the script, the
fact-check report, the voiced lines and the published artefacts. Each method commits on its own.
"""

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

import numpy as np
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, text

from podcast_engine.common.embeddings import to_pgvector
from podcast_engine.common.models import EpisodeStatus, ExpertiseLevel, ReliabilityTier, Tone
from podcast_engine.common.music import ShowMusic
from podcast_engine.common.text import content_hash
from podcast_engine.common.voice_fx import VoiceEffects


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True)


class ShowRecord(_Record):
    show_id: UUID
    topic: str
    tone: Tone
    target_minutes: int
    host_count: int
    language: str
    expertise: ExpertiseLevel
    sources: list[str]
    search_queries: list[str] = []
    topic_keywords: str
    attribution: str
    max_segments: int
    ranking_profile: str
    review_before_voice: bool = False
    host_voices: dict[str, str] = {}  # host name -> voice_id of a registered (consented) voice
    host_effects: dict[str, VoiceEffects] = {}  # host name -> effects applied at assembly
    music: ShowMusic = ShowMusic()  # intro, outro, sting and bed


class EpisodeRecord(_Record):
    episode_id: UUID
    show_id: UUID
    status: EpisodeStatus
    stage: str | None
    error: str | None
    revision: int
    rewrite_count: int
    rebuild: bool = False  # regenerate every segment, even if no source changed
    changed_item_ids: list[UUID] | None
    script: dict[str, Any] | None
    fact_check: dict[str, Any] | None
    voice_lines: list[dict[str, Any]] | None
    assembly: dict[str, Any] | None
    audio_key: str | None
    notes_key: str | None
    manifest: dict[str, Any] | None
    created_at: datetime
    published_at: datetime | None
    approved_at: datetime | None = None


class VoiceRecord(_Record):
    """A registered voice and its consent record; the recording is in storage at ``object_key``."""

    voice_id: UUID
    speaker: str
    license: str
    consent: dict[str, Any]
    object_key: str
    sha256: str


class MusicTrackRecord(_Record):
    """A track a creator uploaded for their shows' music; its audio is at ``object_key``."""

    track_id: UUID
    name: str
    credit: str
    object_key: str


class SpeechClipRecord(_Record):
    """A type-to-speech request from the voice studio, and once voiced, its clip."""

    clip_id: UUID
    owner_id: UUID
    voice: dict[str, Any]
    text: str
    delivery: str
    effects: dict[str, Any]
    status: str


class UploadRecord(_Record):
    """A file a creator uploaded as a source; its bytes are in object storage at ``object_key``."""

    upload_id: UUID
    filename: str
    content_type: str
    object_key: str


class SourceDoc(_Record):
    """One section of a fetched page, ready to store."""

    url: str
    title: str
    text: str
    published_at: datetime | None
    reliability: ReliabilityTier
    position: int


class StoredItem(_Record):
    item_id: UUID
    url: str
    title: str
    text: str
    published_at: datetime | None
    reliability: ReliabilityTier
    content_hash: str
    position: int


class SyncResult(_Record):
    changed: list[UUID]  # new or with different text
    removed: list[UUID]  # no longer on the page
    unchanged: list[UUID]


class ChunkRecord(_Record):
    chunk_id: UUID
    item_id: UUID
    position: int
    text: str


class RankedChunk(_Record):
    chunk_id: UUID
    item_id: UUID
    position: int
    text: str
    relevance: float
    item_title: str
    item_url: str
    item_position: int
    published_at: datetime | None
    reliability: ReliabilityTier


class SegmentRecord(_Record):
    segment_id: UUID
    position: int
    title: str
    source_item_ids: list[UUID]
    chunk_ids: list[UUID]
    needs_script: bool


class ClaimRecord(_Record):
    claim_id: UUID
    position: int
    text: str
    chunk_ids: list[UUID]
    supported: bool | None
    reason: str | None


class StageRunRecord(_Record):
    stage: str
    seconds: float | None
    model: str | None
    prompt_version: str | None
    seed: int | None
    cost_usd: float | None
    started_at: datetime


def item_id_for(show_id: UUID, url: str) -> UUID:
    """Stable per show and source URL (including the section anchor)."""
    return uuid5(show_id, url)


def chunk_id_for(item_id: UUID, position: int, chunk_text: str) -> UUID:
    """Changes when the chunk's text changes, so an edit never reuses a stale vector."""
    return uuid5(item_id, f"{position}:{content_hash(chunk_text)[:12]}")


# Episode columns a stage may set, and how each is sent to Postgres.
_EPISODE_JSON = {"script", "fact_check", "voice_lines", "assembly", "manifest"}
_EPISODE_PLAIN = {
    "approved_at",
    "status",
    "stage",
    "error",
    "revision",
    "rewrite_count",
    "audio_key",
    "notes_key",
    "published_at",
}
_EPISODE_COLUMNS = (
    "episode_id, show_id, status, stage, error, revision, rewrite_count, rebuild, "
    "changed_item_ids, script, fact_check, voice_lines, assembly, audio_key, notes_key, manifest, "
    "created_at, published_at, approved_at"
)


def _uuids(values: Iterable[UUID]) -> list[str]:
    return [str(value) for value in values]


class PipelineRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- shows and episodes ---------------------------------------------------------------
    def get_show(self, show_id: UUID) -> ShowRecord:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT show_id, topic, tone, target_minutes, host_count, language, "
                        "expertise, "
                        "sources, search_queries, topic_keywords, attribution, max_segments, "
                        "ranking_profile, "
                        "review_before_voice, host_voices, host_effects, music "
                        "FROM shows WHERE show_id = :id"
                    ),
                    {"id": show_id},
                )
                .mappings()
                .one()
            )
        return ShowRecord.model_validate(dict(row))

    def get_episode(self, episode_id: UUID) -> EpisodeRecord:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(f"SELECT {_EPISODE_COLUMNS} FROM episodes WHERE episode_id = :id"),  # noqa: S608
                    {"id": episode_id},
                )
                .mappings()
                .one()
            )
        return EpisodeRecord.model_validate(dict(row))

    def create_episode(self, show_id: UUID, *, rebuild: bool = False) -> UUID:
        with self._engine.begin() as connection:
            episode_id: UUID = connection.execute(
                text(
                    "INSERT INTO episodes (show_id, rebuild) VALUES (:id, :rebuild)"
                    " RETURNING episode_id"
                ),
                {"id": show_id, "rebuild": rebuild},
            ).scalar_one()
        return episode_id

    def update_episode(self, episode_id: UUID, **fields: Any) -> None:
        """Set episode columns. JSON columns take Python objects, ``changed_item_ids`` UUIDs."""
        unknown = set(fields) - _EPISODE_JSON - _EPISODE_PLAIN - {"changed_item_ids"}
        if unknown:
            raise ValueError(f"not an episode column a stage may set: {sorted(unknown)}")
        assignments: list[str] = []
        params: dict[str, Any] = {"id": episode_id}
        for name, value in fields.items():
            if name in _EPISODE_JSON:
                assignments.append(f"{name} = CAST(:{name} AS jsonb)")
                params[name] = None if value is None else json.dumps(value, default=str)
            elif name == "changed_item_ids":
                assignments.append("changed_item_ids = CAST(:changed_item_ids AS uuid[])")
                params[name] = None if value is None else _uuids(value)
            else:
                assignments.append(f"{name} = :{name}")
                params[name] = value.value if isinstance(value, EpisodeStatus) else value
        with self._engine.begin() as connection:
            connection.execute(
                # Column names come from the fixed sets above; values are bound parameters.
                text(f"UPDATE episodes SET {', '.join(assignments)} WHERE episode_id = :id"),  # noqa: S608
                params,
            )

    def shows_due_for_refresh(self, interval_hours: float) -> list[UUID]:
        """Published shows with no episode in progress and none started within the interval."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT s.show_id FROM shows s WHERE EXISTS (SELECT 1 FROM episodes e"
                    " WHERE e.show_id = s.show_id AND e.status = 'published')"
                    " AND NOT EXISTS (SELECT 1 FROM episodes e WHERE e.show_id = s.show_id"
                    " AND (e.status IN ('queued', 'processing')"
                    " OR e.created_at > now() - make_interval(secs => :seconds)))"
                ),
                {"seconds": interval_hours * 3600},
            )
            return [row.show_id for row in rows]

    def list_uploads(self, show_id: UUID) -> list[UploadRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT upload_id, filename, content_type, object_key FROM uploads"
                    " WHERE show_id = :id ORDER BY created_at, upload_id"
                ),
                {"id": show_id},
            ).mappings()
            return [UploadRecord.model_validate(dict(row)) for row in rows]

    def get_voices(self, voice_ids: Iterable[str]) -> dict[str, VoiceRecord]:
        """Registered voices by id (as text); ids that no longer exist are left out."""
        ids = sorted(set(voice_ids))
        if not ids:
            return {}
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT voice_id, speaker, license, consent, object_key, sha256 FROM voices"
                    " WHERE voice_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": ids},
            ).mappings()
            records = [VoiceRecord.model_validate(dict(row)) for row in rows]
        return {str(record.voice_id): record for record in records}

    def get_music_tracks(self, track_ids: Iterable[str]) -> dict[str, MusicTrackRecord]:
        """Uploaded music tracks by id (as text); ids that no longer exist are left out."""
        ids = sorted(set(track_ids))
        if not ids:
            return {}
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT track_id, name, credit, object_key FROM music_tracks"
                    " WHERE track_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": ids},
            ).mappings()
            records = [MusicTrackRecord.model_validate(dict(row)) for row in rows]
        return {str(record.track_id): record for record in records}

    def get_speech_clip(self, clip_id: UUID) -> SpeechClipRecord | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT clip_id, owner_id, voice, text, delivery, effects, status"
                        " FROM speech_clips WHERE clip_id = :id"
                    ),
                    {"id": clip_id},
                )
                .mappings()
                .one_or_none()
            )
        return SpeechClipRecord.model_validate(dict(row)) if row else None

    def finish_speech_clip(
        self,
        clip_id: UUID,
        *,
        status: str,
        object_key: str | None = None,
        duration_s: float | None = None,
        error: str | None = None,
    ) -> None:
        """Record a clip as working, done (with its file) or failed (with the reason)."""
        finished = status in {"done", "failed"}
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE speech_clips SET status = :status, object_key = :object_key,"
                    " duration_s = :duration_s, error = :error,"
                    " finished_at = CASE WHEN :finished THEN now() ELSE NULL END"
                    " WHERE clip_id = :id"
                ),
                {
                    "id": clip_id,
                    "status": status,
                    "object_key": object_key,
                    "duration_s": duration_s,
                    "error": error,
                    "finished": finished,
                },
            )

    def voice_hashes(self) -> set[str]:
        """The fingerprints of every registered voice: copies of anything else are withdrawn."""
        with self._engine.connect() as connection:
            rows = connection.execute(text("SELECT sha256 FROM voices")).scalars()
            return set(rows)

    def list_published(self, show_id: UUID) -> list[EpisodeRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"SELECT {_EPISODE_COLUMNS} FROM episodes "  # noqa: S608 - constant column list
                    "WHERE show_id = :id AND status = 'published' ORDER BY published_at DESC"
                ),
                {"id": show_id},
            ).mappings()
            return [EpisodeRecord.model_validate(dict(row)) for row in rows]

    # ---- source items ---------------------------------------------------------------------
    def sync_items(self, show_id: UUID, docs: Sequence[SourceDoc]) -> SyncResult:
        """Store the current sections of the show's sources and report what changed.

        A section is changed if it is new or its text differs (by content hash). Sections that were
        stored before but are gone now are removed, together with their chunks.
        """
        changed: list[UUID] = []
        unchanged: list[UUID] = []
        with self._engine.begin() as connection:
            existing = {
                row.item_id: row.content_hash
                for row in connection.execute(
                    text("SELECT item_id, content_hash FROM source_items WHERE show_id = :id"),
                    {"id": show_id},
                )
            }
            seen: set[UUID] = set()
            for doc in docs:
                item_id = item_id_for(show_id, doc.url)
                seen.add(item_id)
                digest = content_hash(doc.text)
                if existing.get(item_id) == digest:
                    unchanged.append(item_id)
                    connection.execute(
                        text(
                            "UPDATE source_items SET position = :p, fetched_at = now() WHERE "
                            "item_id = :i"
                        ),
                        {"p": doc.position, "i": item_id},
                    )
                    continue
                connection.execute(
                    text(
                        "INSERT INTO source_items (item_id, show_id, url, title, published_at, "
                        "content_hash, reliability, text, position) VALUES (:item_id, :show_id, "
                        ":url, "
                        ":title, :published_at, :hash, :reliability, :text, :position) "
                        "ON CONFLICT (item_id) DO UPDATE SET title = EXCLUDED.title, "
                        "published_at = EXCLUDED.published_at, content_hash = "
                        "EXCLUDED.content_hash, "
                        "reliability = EXCLUDED.reliability, text = EXCLUDED.text, "
                        "position = EXCLUDED.position, fetched_at = now()"
                    ),
                    {
                        "item_id": item_id,
                        "show_id": show_id,
                        "url": doc.url,
                        "title": doc.title,
                        "published_at": doc.published_at,
                        "hash": digest,
                        "reliability": doc.reliability.value,
                        "text": doc.text,
                        "position": doc.position,
                    },
                )
                changed.append(item_id)
            removed = [item_id for item_id in existing if item_id not in seen]
            if removed:
                connection.execute(
                    text("DELETE FROM source_items WHERE item_id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": _uuids(removed)},
                )
        return SyncResult(changed=changed, removed=removed, unchanged=unchanged)

    def list_items(self, show_id: UUID) -> list[StoredItem]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT item_id, url, title, text, published_at, reliability, content_hash, "
                    "position "
                    "FROM source_items WHERE show_id = :id ORDER BY position, url"
                ),
                {"id": show_id},
            ).mappings()
            return [StoredItem.model_validate(dict(row)) for row in rows]

    # ---- chunks ---------------------------------------------------------------------------
    def replace_chunks(
        self, item_id: UUID, pieces: Sequence[str], embed: Callable[[list[str]], np.ndarray]
    ) -> tuple[int, int]:
        """Store an item's chunks, embedding only new ones. Returns (embedded, reused).

        A chunk's id includes a hash of its text, so an unchanged chunk keeps its stored vector
        and an edited one is re-embedded.
        """
        wanted = {chunk_id_for(item_id, n, piece): (n, piece) for n, piece in enumerate(pieces)}
        with self._engine.begin() as connection:
            have = {
                row.chunk_id
                for row in connection.execute(
                    text("SELECT chunk_id FROM chunks WHERE item_id = :id"), {"id": item_id}
                )
            }
            stale = have - set(wanted)
            if stale:
                connection.execute(
                    text("DELETE FROM chunks WHERE chunk_id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": _uuids(stale)},
                )
            missing = [(chunk_id, *wanted[chunk_id]) for chunk_id in wanted if chunk_id not in have]
            vectors = embed([piece for _, _, piece in missing]) if missing else np.zeros((0, 0))
            for (chunk_id, position, piece), vector in zip(missing, vectors, strict=True):
                connection.execute(
                    text(
                        "INSERT INTO chunks (chunk_id, item_id, position, text, embedding) VALUES "
                        "(:chunk_id, :item_id, :position, :text, CAST(:embedding AS vector))"
                    ),
                    {
                        "chunk_id": chunk_id,
                        "item_id": item_id,
                        "position": position,
                        "text": piece,
                        "embedding": to_pgvector(vector),
                    },
                )
        return len(missing), len(wanted) - len(missing)

    def rank_chunks(
        self, show_id: UUID, query: np.ndarray, *, item_ids: Iterable[UUID] | None = None
    ) -> list[RankedChunk]:
        """Every chunk of the show (or of some items) with its cosine similarity to ``query``."""
        sql = (
            "SELECT c.chunk_id, c.item_id, c.position, c.text, "
            "1 - (c.embedding <=> CAST(:query AS vector)) AS relevance, i.title AS item_title, "
            "i.url AS item_url, i.position AS item_position, i.published_at, i.reliability "
            "FROM chunks c JOIN source_items i ON i.item_id = c.item_id WHERE i.show_id = :show_id"
        )
        params: dict[str, Any] = {"query": to_pgvector(query), "show_id": show_id}
        if item_ids is not None:
            sql += " AND c.item_id = ANY(CAST(:items AS uuid[]))"
            params["items"] = _uuids(item_ids)
        with self._engine.connect() as connection:
            rows = connection.execute(text(sql + " ORDER BY relevance DESC"), params).mappings()
            return [RankedChunk.model_validate(dict(row)) for row in rows]

    def get_chunks(self, chunk_ids: Iterable[UUID]) -> dict[UUID, ChunkRecord]:
        ids = _uuids(chunk_ids)
        if not ids:
            return {}
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT chunk_id, item_id, position, text FROM chunks "
                    "WHERE chunk_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": ids},
            ).mappings()
            return {row["chunk_id"]: ChunkRecord.model_validate(dict(row)) for row in rows}

    # ---- segments ---------------------------------------------------------------------------
    def replace_segments(self, episode_id: UUID, segments: Sequence[Mapping[str, Any]]) -> None:
        """Replace the plan.

        Each mapping has position, title, source_item_ids, chunk_ids and needs_script.
        """
        with self._engine.begin() as connection:
            connection.execute(
                text("DELETE FROM segments WHERE episode_id = :id"), {"id": episode_id}
            )
            for segment in segments:
                connection.execute(
                    text(
                        "INSERT INTO segments (segment_id, episode_id, position, title, "
                        "source_item_ids, "
                        "chunk_ids, needs_script) VALUES (:segment_id, :episode_id, :position, "
                        ":title, "
                        "CAST(:items AS uuid[]), CAST(:chunks AS uuid[]), :needs)"
                    ),
                    {
                        "segment_id": uuid5(episode_id, f"segment-{segment['position']}"),
                        "episode_id": episode_id,
                        "position": segment["position"],
                        "title": segment["title"],
                        "items": _uuids(segment["source_item_ids"]),
                        "chunks": _uuids(segment["chunk_ids"]),
                        "needs": segment.get("needs_script", True),
                    },
                )

    def list_segments(self, episode_id: UUID) -> list[SegmentRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT segment_id, position, title, source_item_ids, chunk_ids, needs_script "
                    "FROM segments WHERE episode_id = :id ORDER BY position"
                ),
                {"id": episode_id},
            ).mappings()
            return [SegmentRecord.model_validate(dict(row)) for row in rows]

    def update_segment(
        self,
        episode_id: UUID,
        position: int,
        *,
        needs_script: bool | None = None,
        chunk_ids: Sequence[UUID] | None = None,
    ) -> None:
        sets, params = [], {"id": episode_id, "position": position}
        if needs_script is not None:
            sets.append("needs_script = :needs")
            params["needs"] = needs_script
        if chunk_ids is not None:
            sets.append("chunk_ids = CAST(:chunks AS uuid[])")
            params["chunks"] = _uuids(chunk_ids)
        if not sets:
            return
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    f"UPDATE segments SET {', '.join(sets)} WHERE episode_id = :id AND position = "  # noqa: S608
                    ":position"
                ),
                params,
            )

    # ---- claims -----------------------------------------------------------------------------
    def replace_claims(
        self, episode_id: UUID, position: int, claims: Sequence[Mapping[str, Any]]
    ) -> None:
        """Replace one segment's claims. Each mapping has claim_id, text and chunk_ids."""
        with self._engine.begin() as connection:
            connection.execute(
                text("DELETE FROM claims WHERE episode_id = :id AND position = :position"),
                {"id": episode_id, "position": position},
            )
            for claim in claims:
                connection.execute(
                    text(
                        "INSERT INTO claims (claim_id, episode_id, segment_id, text, chunk_ids, "
                        "position) "
                        "VALUES (:claim_id, :episode_id, :segment_id, :text, CAST(:chunks AS "
                        "uuid[]), :position) "
                        "ON CONFLICT (claim_id) DO UPDATE SET text = EXCLUDED.text, chunk_ids = "
                        "EXCLUDED.chunk_ids, "
                        "position = EXCLUDED.position, supported = NULL, reason = NULL"
                    ),
                    {
                        "claim_id": claim["claim_id"],
                        "episode_id": episode_id,
                        "segment_id": uuid5(episode_id, f"segment-{position}"),
                        "text": claim["text"],
                        "chunks": _uuids(claim["chunk_ids"]),
                        "position": position,
                    },
                )

    def list_claims(self, episode_id: UUID) -> list[ClaimRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT claim_id, position, text, chunk_ids, supported, reason FROM claims "
                    "WHERE episode_id = :id ORDER BY position, claim_id"
                ),
                {"id": episode_id},
            ).mappings()
            return [ClaimRecord.model_validate(dict(row)) for row in rows]

    def set_verdicts(self, verdicts: Mapping[UUID, tuple[bool, str]]) -> None:
        with self._engine.begin() as connection:
            for claim_id, (supported, reason) in verdicts.items():
                connection.execute(
                    text("UPDATE claims SET supported = :ok, reason = :why WHERE claim_id = :id"),
                    {"ok": supported, "why": reason, "id": claim_id},
                )

    # ---- stage runs -------------------------------------------------------------------------
    def record_stage_run(
        self,
        episode_id: UUID,
        stage: str,
        *,
        seconds: float,
        model: str | None = None,
        prompt_version: str | None = None,
        seed: int | None = None,
        cost_usd: float | None = None,
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO stage_runs (episode_id, stage, model, prompt_version, seed, "
                    "seconds, cost_usd) "
                    "VALUES (:episode_id, :stage, :model, :prompt_version, :seed, :seconds, :cost)"
                ),
                {
                    "episode_id": episode_id,
                    "stage": stage,
                    "model": model,
                    "prompt_version": prompt_version,
                    "seed": seed,
                    "seconds": round(seconds, 3),
                    "cost": cost_usd,
                },
            )

    def list_stage_runs(self, episode_id: UUID) -> list[StageRunRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT stage, seconds, model, prompt_version, seed, cost_usd, started_at "
                    "FROM stage_runs WHERE episode_id = :id ORDER BY started_at"
                ),
                {"id": episode_id},
            ).mappings()
            return [StageRunRecord.model_validate(dict(row)) for row in rows]
