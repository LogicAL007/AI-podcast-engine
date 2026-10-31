import pytest

from podcast_engine import worker
from podcast_engine.common.config import Settings
from podcast_engine.common.queue import Stage, celery_app
from podcast_engine.stages.voice import backends
from podcast_engine.worker import worker_args


def test_worker_consumes_only_its_queue_and_task_module() -> None:
    args = worker_args([Stage.VOICE], concurrency=2, log_level="info")
    assert args[args.index("--queues") + 1] == "voice"
    assert args[args.index("--include") + 1] == "podcast_engine.stages.voice.tasks"
    assert args[args.index("--loglevel") + 1] == "INFO"
    assert args[args.index("--pool") + 1] == "prefork"


def test_one_worker_can_serve_several_stages_each_on_its_own_queue() -> None:
    args = worker_args([Stage.SCRIPT, Stage.FACTCHECK], concurrency=2, log_level="info")
    assert args[args.index("--queues") + 1] == "script,factcheck"
    assert args[args.index("--include") + 1] == (
        "podcast_engine.stages.script.tasks,podcast_engine.stages.factcheck.tasks"
    )


def test_host_worker_can_use_the_solo_pool() -> None:
    args = worker_args([Stage.VOICE], concurrency=1, log_level="info", pool="solo")
    assert args[args.index("--pool") + 1] == "solo"


def test_a_voice_worker_without_its_backend_stands_down_before_taking_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[object] = []
    monkeypatch.setattr(celery_app, "worker_main", started.append)
    monkeypatch.setattr(worker, "start_metrics_server", started.append)
    monkeypatch.setattr(
        worker, "get_settings", lambda: Settings(tts_backend="chatterbox", log_level="info")
    )
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    assert worker.main(["voice"]) == 0
    assert started == []  # no metrics server, no Celery worker: no job is taken


def test_other_workers_do_not_check_the_voice_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[object] = []
    monkeypatch.setattr(celery_app, "worker_main", started.append)
    monkeypatch.setattr(worker, "start_metrics_server", lambda port: None)
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(tts_backend="chatterbox"))
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    assert worker.main(["assemble"]) == 0
    assert len(started) == 1


def test_backend_unavailable_names_what_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    problem = backends.backend_unavailable(Settings(tts_backend="chatterbox"))
    assert problem is not None
    assert "make voice-host" in problem
    assert "Missing: torch, chatterbox." in problem
    assert backends.backend_unavailable(Settings(tts_backend="placeholder")) is None


def test_backend_unavailable_passes_when_the_modules_are_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    assert backends.backend_unavailable(Settings(tts_backend="chatterbox")) is None
    assert backends.backend_unavailable(Settings(tts_backend="gemini")) is None
