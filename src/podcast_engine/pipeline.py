"""Run the whole pipeline for one episode in this process, without the queue.

The Celery workers are the normal path. This one is for tests and for running a stage the containers
cannot, such as the Chatterbox voice-cloning backend on a host with a GPU:

    python -m podcast_engine.pipeline --show <show_id>
"""

import argparse
import json
from collections.abc import Sequence
from uuid import UUID

from podcast_engine.common.context import PipelineContext, get_context
from podcast_engine.common.queue import Stage
from podcast_engine.common.runner import StageFunction, run_stage
from podcast_engine.stages.assemble.service import assemble_episode
from podcast_engine.stages.factcheck.service import check_script
from podcast_engine.stages.index.service import index_items
from podcast_engine.stages.ingest.service import ingest_sources
from podcast_engine.stages.publish.service import publish_episode
from podcast_engine.stages.retrieve_plan.service import retrieve_and_plan
from podcast_engine.stages.script.service import write_script
from podcast_engine.stages.voice.service import synthesise_voices

STAGE_FUNCTIONS: dict[Stage, StageFunction] = {
    Stage.INGEST: ingest_sources,
    Stage.INDEX: index_items,
    Stage.RETRIEVE_PLAN: retrieve_and_plan,
    Stage.SCRIPT: write_script,
    Stage.FACTCHECK: check_script,
    Stage.VOICE: synthesise_voices,
    Stage.ASSEMBLE: assemble_episode,
    Stage.PUBLISH: publish_episode,
}
MAX_HOPS = 40  # far more than 8 stages plus every allowed rewrite; guards against a routing loop


def run_inline(
    episode_id: UUID,
    ctx: PipelineContext,
    *,
    start: Stage = Stage.INGEST,
    stop_after: Stage | None = None,
    stop_before: Stage | None = None,
) -> list[str]:
    """Run stages in order (following the fact-check loop) and return the route taken."""
    route: list[str] = []
    stage: Stage | None = start
    while stage is not None and stage is not stop_before:
        if len(route) >= MAX_HOPS:
            raise RuntimeError(f"pipeline did not finish after {MAX_HOPS} stages: {route}")
        route.append(stage.value)
        ran, stage = stage, run_stage(stage, STAGE_FUNCTIONS[stage], episode_id, ctx)
        if ran is stop_after:
            break
    return route


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--show", type=UUID, help="create a new episode for this show and run it")
    target.add_argument("--episode", type=UUID, help="run an existing episode")
    parser.add_argument("--from-stage", type=Stage, choices=list(Stage), default=Stage.INGEST)
    args = parser.parse_args(argv)
    ctx = get_context()
    episode_id = args.episode or ctx.repo.create_episode(args.show)
    route = run_inline(episode_id, ctx, start=args.from_stage)
    episode = ctx.repo.get_episode(episode_id)
    print(  # noqa: T201 - the command's output
        json.dumps(
            {
                "episode_id": str(episode_id),
                "status": episode.status,
                "error": episode.error,
                "route": route,
            }
        )
    )
    return 0 if episode.status in {"published", "unchanged"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
