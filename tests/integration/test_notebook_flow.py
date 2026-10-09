"""Executes notebooks/podcast_flow.ipynb end to end and checks the flow's invariants.

Configurations, none needing a network or an API key:
  * offline stand-ins with placeholder tones (fast, runs anywhere)
  * the Gemini and Claude code paths against fake SDKs in tests/fixtures (plumbing, not the models)
  * offline stand-ins with real macOS `say` voices (macOS only)
  * the voice-cloning backend refusing a voice with no consent record (fast)
  * opt-in and slow: the Chatterbox cloning backend with a test reference voice
Run with: make notebook-test
"""

import contextlib
import functools
import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import nbformat
import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

pytestmark = pytest.mark.notebook

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "notebooks" / "podcast_flow.ipynb"
FIXTURES = ROOT / "tests" / "fixtures"
FAKE_LLM_RULES = FIXTURES / "fake_llm"
FAKE_ANTHROPIC = FIXTURES / "fake_anthropic"
FAKE_GENAI = FIXTURES / "fake_genai"


def fake_sdk_path(*sdks: Path) -> str:
    """PYTHONPATH that puts a fake SDK first (absolute: the kernel runs elsewhere)."""
    return os.pathsep.join(str(path) for path in (FAKE_LLM_RULES, *sdks))


def run_notebook(
    monkeypatch: pytest.MonkeyPatch,
    output: Path,
    *,
    notebook: nbformat.NotebookNode | None = None,
    **switches: str,
) -> dict[str, Any]:
    monkeypatch.setenv("PODCAST_NB_OUTPUT_DIR", str(output))
    monkeypatch.setenv("PODCAST_NB_PRESET", "samples")  # the notebook defaults to a live web page
    for name, value in switches.items():
        monkeypatch.setenv(f"PODCAST_NB_{name}", value)
    notebook = notebook or nbformat.read(NOTEBOOK, as_version=4)  # type: ignore[no-untyped-call]
    NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK.parent)}},
    ).execute()
    results: dict[str, Any] = json.loads((output / "last_results.json").read_text())
    return results


def assert_flow_invariants(results: dict[str, Any]) -> None:
    # The gate caught the planted claims on the first draft, and the rewrite loop fixed them.
    assert results["first_draft_support"] < 1.0
    assert results["final_support"] == 1.0
    routes = results["route_log"]
    assert "factcheck -> script" in routes
    assert routes.index("factcheck -> script") < routes.index("factcheck -> voice")
    assert routes[:3] == ["ingest -> index", "index -> retrieve_plan", "retrieve_plan -> script"]

    # Dynamic refresh re-scripted only what changed and reused cached audio for the rest.
    refresh = results["refresh"]
    assert refresh["regenerated"]
    assert refresh["reused"]
    assert refresh["reused_text_identical"]
    synthesised, from_cache = refresh["voice"]
    assert from_cache > synthesised

    # Output quality and publication.
    assert results["audio_checks_pass"], results["audio"]
    assert all(results["rss"][key] for key in ("has_enclosure", "label_in_title", "claims_cited"))
    assert results["rss"]["entries"] == 1
    assert results["rss"]["disclosure_in_description"]
    failing = [fr for fr, status in results["requirements"].items() if status is False]
    assert failing == []


def test_offline_flow_with_placeholder_voices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    results = run_notebook(monkeypatch, tmp_path, USE_LLM="false", TTS_BACKEND="placeholder")
    assert results["script_backend"] == "offline-extractive"
    assert results["tts_provider"] == "placeholder-tones"
    assert_flow_invariants(results)


def test_gemini_switches_to_a_requested_fallback_once_and_stays_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Opt-in only: an overloaded main model then costs one short wait, not a wait on every call."""
    monkeypatch.setenv("PYTHONPATH", fake_sdk_path(FAKE_GENAI))
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    monkeypatch.setenv("FAKE_GENAI_BUSY_MODELS", "gemini-3.8-flash")
    results = run_notebook(
        monkeypatch,
        tmp_path,
        USE_LLM="true",
        LLM_PROVIDER="gemini",
        TTS_BACKEND="placeholder",
        LLM_FALLBACK_MODEL="gemini-3.7-flash",
    )
    assert set(results["llm_models_used"]) == {"gemini-3.7-flash"}  # the busy model never answered
    # Two short waits on the first call only. Waiting on every call would be 2 per call.
    assert results["llm_busy_retries"] == 2
    assert_flow_invariants(results)


def preset_with(extra: str) -> nbformat.NotebookNode:
    """The notebook with one more line added to its 'samples' preset in the 'Your run' cell."""
    notebook: nbformat.NotebookNode = nbformat.read(NOTEBOOK, as_version=4)  # type: ignore[no-untyped-call]
    marker = '"SOURCE_URLS": "",'
    assert notebook.cells[2].source.count(marker) == 1
    notebook.cells[2].source = notebook.cells[2].source.replace(
        marker, f"{marker}\n        {extra}"
    )
    return notebook


@pytest.mark.parametrize("value", ["False", '"false"'], ids=["python-bool", "string"])
def test_use_llm_false_never_touches_the_model_even_with_a_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """USE_LLM = False means no model client, no call, no key needed, however it is written."""
    calls = tmp_path / "sdk_calls.log"
    monkeypatch.setenv("PYTHONPATH", fake_sdk_path(FAKE_GENAI))
    monkeypatch.setenv("FAKE_GENAI_LOG", str(calls))
    monkeypatch.setenv("GEMINI_API_KEY", "a-key-is-present")  # the switch must still win
    results = run_notebook(
        monkeypatch,
        tmp_path / "out",
        notebook=preset_with(f'"USE_LLM": {value},'),
        TTS_BACKEND="placeholder",
    )
    assert results["script_backend"] == "offline-extractive"
    assert not calls.exists(), calls.read_text()  # the SDK was never even constructed
    assert_flow_invariants(results)


def test_editing_your_run_without_rerunning_setup_stops_the_notebook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The half-rerun trap: the setup cell still holds the old settings, so refuse to carry on."""
    monkeypatch.setenv("PYTHONPATH", fake_sdk_path(FAKE_GENAI))
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    monkeypatch.setenv("PODCAST_NB_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("PODCAST_NB_PRESET", "samples")
    monkeypatch.setenv("PODCAST_NB_TTS_BACKEND", "placeholder")
    notebook = preset_with('"USE_LLM": "true",')
    outline = next(
        i
        for i, cell in enumerate(notebook.cells)
        if cell.cell_type == "code" and "SEGMENTS = plan_outline_llm" in cell.source
    )
    client = NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK.parent)}},
    )
    with client.setup_kernel():
        for index in range(outline):  # setup, show, ingest and index, all with the model on
            if notebook.cells[index].cell_type == "code":
                client.execute_cell(notebook.cells[index], index)
        notebook.cells[2].source = notebook.cells[2].source.replace(
            '"USE_LLM": "true"', '"USE_LLM": "false"'
        )
        client.execute_cell(notebook.cells[2], 2)  # edit 'Your run' but do not re-run setup
        with pytest.raises(CellExecutionError, match="Restart the kernel and use Run All"):
            client.execute_cell(notebook.cells[outline], outline)


def test_anthropic_code_path_against_the_fake_sdk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PYTHONPATH", fake_sdk_path(FAKE_ANTHROPIC))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    results = run_notebook(
        monkeypatch, tmp_path, USE_LLM="true", LLM_PROVIDER="anthropic", TTS_BACKEND="placeholder"
    )
    assert results["script_backend"].startswith("anthropic:")
    assert_flow_invariants(results)


def test_gemini_code_path_against_the_fake_sdk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PYTHONPATH", fake_sdk_path(FAKE_GENAI))
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    results = run_notebook(
        monkeypatch, tmp_path, USE_LLM="true", LLM_PROVIDER="gemini", TTS_BACKEND="placeholder"
    )
    assert results["script_backend"] == "gemini:gemini-3.8-flash"
    # Every call used gemini-3.8-flash. No other model is configured unless asked for.
    assert set(results["llm_models_used"]) == {"gemini-3.8-flash"}
    assert results["llm_fallback_model"] == ""
    assert_flow_invariants(results)


@pytest.mark.skipif(shutil.which("say") is None, reason="needs macOS `say`")
def test_offline_flow_with_real_system_voices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    results = run_notebook(monkeypatch, tmp_path, USE_LLM="false", TTS_BACKEND="say")
    assert results["tts_provider"] == "macos-say"
    assert_flow_invariants(results)


def _have_chatterbox() -> bool:
    return importlib.util.find_spec("chatterbox") is not None


@pytest.mark.skipif(
    not (shutil.which("say") and _have_chatterbox() and os.environ.get("PODCAST_TEST_CHATTERBOX")),
    reason="opt-in: PODCAST_TEST_CHATTERBOX=1, `.[cloning]` installed, macOS (slow, big download)",
)
def test_cloning_backend_with_a_test_reference_voice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The reference is a macOS system voice rendered locally, so no real person's voice is involved.
    reference = tmp_path / "reference.wav"
    spoken = (
        "This is a short test recording of a built in system voice, used only to check that the "
        "voice cloning pipeline runs on this machine. The library opens at nine, and the weather "
        "is mild today."
    )
    subprocess.run(  # noqa: S603 - fixed arguments, text on stdin
        ["say", "-v", "Daniel", "-o", str(reference), "--data-format=LEI16@24000", "-f", "-"],  # noqa: S607
        input=spoken.encode(),
        check=True,
    )
    registry = tmp_path / "voices.yaml"
    registry.write_text(
        "chatterbox:\n"
        f"  Alex:\n    reference_audio: {reference}\n"
        '    speaker: "TEST FIXTURE: macOS system voice Daniel, rendered locally"\n'
        '    consent: "Not applicable: synthetic system voice, local test only"\n'
        '    license: "Local test only"\n'
        "  Sam:\n    reference_audio: null\n"
    )
    results = run_notebook(
        monkeypatch,
        tmp_path / "out",
        USE_LLM="false",
        TTS_BACKEND="chatterbox",
        VOICES_FILE=str(registry),
        RANKING_PROFILE="daily",  # puts the updated source in the first segments...
        MAX_SEGMENTS="2",  # ...so a short episode still exercises the refresh
    )
    assert results["tts_provider"] == "chatterbox"
    assert results["watermark_score"] >= 0.5
    assert_flow_invariants(results)


def test_cloning_backend_refuses_a_voice_without_consent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"not really audio")
    registry = tmp_path / "voices.yaml"
    registry.write_text(
        f"chatterbox:\n  Alex:\n    reference_audio: {reference}\n"
        "  Sam:\n    reference_audio: null\n"
    )
    monkeypatch.setenv("PODCAST_NB_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("PODCAST_NB_PRESET", "samples")
    monkeypatch.setenv("PODCAST_NB_USE_LLM", "false")
    monkeypatch.setenv("PODCAST_NB_TTS_BACKEND", "chatterbox")
    monkeypatch.setenv("PODCAST_NB_VOICES_FILE", str(registry))
    notebook = nbformat.read(NOTEBOOK, as_version=4)  # type: ignore[no-untyped-call]
    client = NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK.parent)}},
    )
    with pytest.raises(CellExecutionError, match="cloned voice needs a consent record"):
        client.execute()


@contextlib.contextmanager
def serve_pages(directory: Path) -> Iterator[str]:
    """Serve a folder over HTTP on a free local port: URL ingestion without a network."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *args: None  # type: ignore[attr-defined]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()


def test_url_source_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A web page becomes an episode: sections as sources, anchored citations, no planted claims."""
    with serve_pages(ROOT / "tests" / "fixtures" / "pages") as base:
        results = run_notebook(
            monkeypatch,
            tmp_path,
            USE_LLM="false",
            TTS_BACKEND="placeholder",
            SOURCE_URLS=f"{base}/intro.html",
            TOPIC="What Tidewater is and why it is fast",
            TOPIC_KEYWORDS="Tidewater storage engine columns files compression replication tables",
            SOURCE_ATTRIBUTION="Source material: made-up fixture page, for tests only.",
        )
    assert results["final_support"] == 1.0
    assert results["first_draft_support"] == 1.0  # real sources: nothing is planted
    assert "factcheck -> script" not in results["route_log"]
    # Nothing changed on the page, so change detection correctly re-runs nothing.
    assert results["refresh"]["skipped"] is True
    assert results["refresh"]["regenerated"] == []
    assert results["audio_checks_pass"], results["audio"]
    assert all(results["rss"][key] for key in ("has_enclosure", "label_in_title", "claims_cited"))
    assert results["requirements"]["FR8"] is None
    notes = next(tmp_path.glob("*/show_notes_r1.md")).read_text()
    assert "Source material: made-up fixture page" in notes
    assert "#why-columns" in notes  # citations link to the section they came from
    assert "diagram below" not in notes  # sentences that point at a picture were left out
    assert "Navigation" not in notes
    assert (
        notes.count("high-performance") == 0
    )  # the repeated tagline was kept once, in its short form
