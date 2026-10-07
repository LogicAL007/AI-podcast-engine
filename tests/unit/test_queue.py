from podcast_engine.common.queue import PIPELINE_ORDER, Stage, celery_app, next_stage, task_name


def test_pipeline_has_eight_stages_in_diagram_order() -> None:
    assert [stage.value for stage in PIPELINE_ORDER] == [
        "ingest",
        "index",
        "retrieve_plan",
        "script",
        "factcheck",
        "voice",
        "assemble",
        "publish",
    ]


def test_next_stage_chains_and_ends_after_publish() -> None:
    assert next_stage(Stage.INGEST) is Stage.INDEX
    assert next_stage(Stage.FACTCHECK) is Stage.VOICE
    assert next_stage(Stage.PUBLISH) is None


def test_every_stage_routes_to_its_own_queue() -> None:
    routes = celery_app.conf.task_routes
    for stage in Stage:
        assert routes[task_name(stage)] == {"queue": stage.value}
