from podcast_engine.common.queue import Stage
from podcast_engine.worker import worker_args


def test_worker_consumes_only_its_queue_and_task_module() -> None:
    args = worker_args(Stage.VOICE, concurrency=2, log_level="info")
    assert args[args.index("--queues") + 1] == "voice"
    assert args[args.index("--include") + 1] == "podcast_engine.stages.voice.tasks"
    assert args[args.index("--loglevel") + 1] == "INFO"
    assert args[args.index("--pool") + 1] == "prefork"


def test_host_worker_can_use_the_solo_pool() -> None:
    args = worker_args(Stage.VOICE, concurrency=1, log_level="info", pool="solo")
    assert args[args.index("--pool") + 1] == "solo"
