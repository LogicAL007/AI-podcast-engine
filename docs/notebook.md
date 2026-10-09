# The flow notebook

[notebooks/podcast_flow.ipynb](../notebooks/podcast_flow.ipynb) runs one episode through the whole PRD
pipeline so you can see, run and test each stage before the real stage code exists.

```
1 Ingest → 2 Index → 3 Retrieve and plan → 4 Script ⇄ 5 Fact-check → 6 Voice → 7 Assemble → 8 Publish
                                                  ↓
                      dynamic refresh (re-run only what changed) → scorecard → run manifest
```

## Run it

The notebook opens set up for the real workflow: it **scrapes a web page** (the ClickHouse docs intro),
has **Gemini** write and fact-check the script (Claude is one switch away), and **voices it with your cloned voice**. The "Your run" cell
near the top holds those choices.

**Once, in a terminal:**

```bash
python -m venv .venv-cloning && source .venv-cloning/bin/activate
pip install -e ".[notebook,cloning]"          # the voice model, torch, and the notebook's dependencies
```

Then put your Gemini API key in `secrets/llm_api_key.txt` (one line, git-ignored; create one at
<https://aistudio.google.com/apikey>), or export `GEMINI_API_KEY` before starting VS Code. Gemini has a free tier
with rate limits; the scorecard reports what a run would cost on the paid tier. Your voice recording and consent record go in
`assets/voices/` and `config/voices.yaml` (see "Cloned voices" below).

**In VS Code or Jupyter:**

1. Open `notebooks/podcast_flow.ipynb`. Click *Select Kernel* (top right), then *Python Environments*, then
   **`.venv-cloning`**. If it is not listed, run
   `.venv-cloning/bin/python -m ipykernel install --user --name podcast-cloning` and reload the window.
2. *Run All*. The first cell checks your key, the voice model and the voice registry, and stops with a clear
   message if one is wrong. Everything before the voice step takes seconds to a minute (it includes the
   model calls). The voice step takes about 10 minutes for this page and prints a line per sentence.
3. The episode plays in the output of section 8. Files are in `notebooks/output/<run>/`.

The scorecard at the end reports the real token usage and cost of the model calls, from the API's own token counts.

To run something else, edit the "Your run" cell: another page (or several, comma-separated) in `SOURCE_URLS`,
a different `TOPIC`, or `PRESET = "samples"` for the bundled demo texts.

The saved notebook keeps its outputs, including the audio, which makes the file large. Run
`make notebook-clean` before committing it.

### If Gemini says it is busy

Every Gemini call (outline, script, fact-check, and the start-up check) uses one model, `gemini-3.8-flash`, set
by the `LLM_MODEL` line in the *Your run* cell. New models are often overloaded and answer `503 high demand`.
The notebook waits and retries (about 2, 4, 8, 16, then 32 seconds, up to about two minutes per call) and prints
each wait. If the model is still busy after that, the run stops with the error, and you can start it again.

- A different model answers **only if you ask for one**: set `PODCAST_NB_LLM_FALLBACK_MODEL=<model id>`. After
  two short retries on `gemini-3.8-flash` it then switches to that model for the rest of the run, and
  `run_manifest.json` records which model really answered (`llm_models_used`).
- A model ID your key cannot use is caught in the first cell, with a message.

### After editing "Your run"

Use **Run All**, or restart the kernel and run from the top. The setup cell is where the model client, the voices
and the sources are created, so editing "Your run" and re-running only some cells would carry on with the *old*
settings (for example, still calling Gemini after `USE_LLM` was set to `false`). The notebook now checks for this
at the start of the ingest, outline, script and voice cells and stops with a message naming what changed.

Settings in "Your run" can be written as text (`"false"`) or as Python values (`False`, `6`); both work.

### Without a key or a network

`USE_LLM=false` (or the `samples` preset with no key) swaps the LLM for an offline stand-in: an extractive
writer that quotes sentences from the sources, and a word-overlap fact-check. It exists so the flow can be
tested anywhere; it is not the intended path, and its script is the source's own wording. The automated test
runs this way, plus once each against stand-ins for the Gemini and Claude SDKs:

```bash
make notebook-test                  # executes the notebook offline and checks the invariants (about 40 s)
```

## What is real and what is a stand-in

| Stage | In the notebook | Real code from `podcast_engine` |
|---|---|---|
| Ingest | bundled sample texts, any web page, or live RSS summaries | `extract_page`, `speakable_sentences`, `content_hash`, `has_changed` |
| Index | hashed word vectors (or BGE with `USE_BGE`), in-memory store | `chunk_words` |
| Retrieve and plan | topic matching, two ranking profiles, segment outline | `recency_score`, `combined_score` |
| Script | Gemini by default, or Claude (offline: an extractive writer) | `load_prompt` (versioned prompts in `prompts/`) |
| Fact-check | Gemini by default, or Claude (offline: a word-overlap judge) | `route_after_factcheck` |
| Voice | `say` system voices, Chatterbox (can clone), or placeholder tones | `segment_cache_key`, the consent registry |
| Assemble | numpy mix, `pyloudnorm` to -16 LUFS, soft limiter | `needs_normalisation`, `TARGET_LUFS` |
| Publish | show notes, RSS with `feedgen` | `with_disclosure`, `AI_DISCLOSURE`, `feed_key` |

The stage bodies are prototypes: the matching stages in `src/podcast_engine/stages/*/service.py` still
raise `NotImplementedError`. The notebook is the executable spec to port them from.

## Switches

Set them in the second code cell, or as environment variables named `PODCAST_NB_<NAME>`.

| Switch | Default | Effect |
|---|---|---|
| `USE_LLM` | `"true"` in the ClickHouse preset, `"auto"` otherwise | `true` requires the LLM and fails at the first cell if the key is missing or wrong. `auto` uses it only if a key is found. `false` is offline. |
| `LLM_PROVIDER`, `LLM_MODEL` | `gemini`, `gemini-3.8-flash` | Switch to `anthropic` for Claude (default model `claude-sonnet-5-5`). The first cell checks that the model exists for your key. |
| `TTS_BACKEND` | `"auto"` | `say` (macOS system voices), `chatterbox` (open model, can clone voices), or `placeholder` (tones, not speech). `auto` picks `say` on a Mac, otherwise `placeholder`. |
| `VOICES_FILE` | `config/voices.yaml` | The voice registry the `chatterbox` backend reads. |
| `USE_BGE` | `False` | Embed with `BAAI/bge-small-en-v1.5`. Needs `pip install -e ".[embeddings]"` and a download. |
| `SOURCE_URLS` | none | Comma-separated web pages to turn into an episode (see below). Replaces the bundled samples. |
| `TOPIC`, `TOPIC_KEYWORDS` | the RAG demo | The show topic and the keywords that, with the title, form the topic profile used for matching. |
| `TOPIC_THRESHOLD` | `0.07` (`0` with `SOURCE_URLS`) | Chunks scoring below this against the topic are off-topic and dropped. |
| `SEGMENT_ORDER` | `rank` (`source` with `SOURCE_URLS`) | Order segments by relevance, or in the order they appear on the page. |
| `FACTS_PER_SEGMENT` | `8` | The most sentences one segment quotes (offline writer). |
| `URL_RELIABILITY` | from `config/source_tiers.yaml` | Force `primary`, `established` or `unverified` for the pages you give. |
| `SOURCE_ATTRIBUTION` | none | A credit and licence line added to the show notes. |
| `LIVE_SOURCES` | `False` | Add the latest items of the RSS feeds in `LIVE_FEEDS`. |
| `INJECT_HALLUCINATION` | `True` | Offline only. Plants two bad claims in the first draft so you can watch the gate catch them. |
| `CLEAR_TTS_CACHE` | `True` | Start with a cold voice cache so the refresh demo shows the saving. |
| `PUSH_TO_S3` | `False` | Upload the feed to the compose object store and fetch it back through the API. |
| `MAX_SEGMENTS` | `5` | How many segments the episode has. Fewer means a shorter, faster episode. |
| `RANKING_PROFILE` | `"explainer"` | `"daily"` favours fresh items; `"explainer"` favours authoritative ones. |

`PUSH_TO_S3` needs the stack with ports published:
`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis s3 s3-init api`.

## What to try

- **Change the topic** in the show cell, or `TOPIC_KEYWORDS`, and watch which sources fall below the
  threshold. Change `RANKING_PROFILE` and compare the outline.
- **Break the gate:** start Jupyter with `MAX_REWRITES=0` in the environment. The planted claims are
  then flagged, there is no rewrite budget, and the gate cell stops with "held for human review"
  instead of voicing the episode.
- **Edit the script by hand** (FR7) between the fact-check and voice cells, then rerun from voice.
- **Rerun the refresh cell** after changing `text_v2` in `notebooks/sample_sources.json`.

## Using a web page as the source

```bash
export PODCAST_NB_SOURCE_URLS="https://clickhouse.com/docs/get-started/about/intro"
export PODCAST_NB_TOPIC="What ClickHouse is and why it is fast for analytics"
export PODCAST_NB_TOPIC_KEYWORDS="ClickHouse column-oriented database OLAP analytics queries rows columns"
```

The page is split at its headings, and **each section becomes its own source**. It has its own content
hash, so a change on the page re-runs only the segment built from it, and its own anchor, so show-notes
citations link to `page#section`. The code is `podcast_engine/stages/ingest/extract.py` (unit-tested), which
the real ingest worker will reuse.

In offline mode the writer **quotes whole sentences** from the page. That keeps it faithful (nothing to fact-check
away) but it is not paraphrase, so spoken text is the source's wording. A few heuristics keep it listenable:
labels, code, and sentences pointing at a diagram or link ("as shown below", "see the ... guide") are
dropped, near-repeats are kept once, and a section cannot open on a sentence that leans on the text before
it ("Such a level of ..."). With an LLM enabled the script is written, not quoted.

The notebook prints the sections it skipped because they had too little speakable text, so omissions are
visible. If the page is not covered, the usual causes are:

- **The page is built in the browser** (the HTML has no text). This fetches HTML only and runs no JavaScript.
- **Unusual markup.** Different sites mark paragraphs differently (one used `<span data-as="p">`, which a
  general article extractor silently skipped, losing most of the page). A page with headings but no
  recovered text is a sign of this.
- **A login or paywall**, or a site that blocks automated requests.

Points to check before using a page:

- **Licence and copyright.** The PRD's risk table says to use licensed, open or user-owned sources and to
  summarise rather than reproduce. Quoting a page verbatim is the opposite of that. Check the page's terms,
  and use `SOURCE_ATTRIBUTION` to put the credit and licence in the show notes. For example, the ClickHouse
  documentation repository's `LICENSE` is CC BY-NC-SA 4.0 (attribution, non-commercial, share-alike), so an
  episode adapted from it is for non-commercial use, and sharing it publicly means passing on the same terms.
  Confirm the current terms on the live site, since the docs have moved between repositories.
- **Refreshing.** The refresh step re-fetches the page. If nothing changed it correctly re-runs nothing
  and says so; the FR8 line then reads "not exercised" instead of passing.
- **Politeness.** One request per page, with an identifying User-Agent.

## Cloned voices (Chatterbox)

`TTS_BACKEND = "chatterbox"` uses [Chatterbox](https://github.com/resemble-ai/chatterbox), an open model
(MIT) that can imitate a voice from a short recording. This is a deliberate change from the PRD, which
lists voice cloning as a non-goal and "no cloning of real people" as a risk mitigation. Update the PRD
to say what is now allowed (cloning with documented consent) so the two agree.

**Consent gate.** Voices are defined in [config/voices.yaml](../config/voices.yaml). A voice with a
`reference_audio` is a clone, and the notebook refuses to start unless that entry also names the
`speaker`, says where their written `consent` is kept, and states the `license`, and the recording
exists. Every problem is listed at once. A voice with `reference_audio: null` uses Chatterbox's built-in
default voice and clones nobody. Use recordings only of people who agreed (yourself, or someone who gave
written permission), never a public figure or anyone who did not. The registry is a gate against
forgetting, not proof: nothing checks that the consent record is genuine.

**Install** in a separate environment, because the model pins heavy dependencies (torch,
`transformers==5.2.0`, `gradio`, `numpy>=2`) that can clash with the rest:

```bash
python -m venv .venv-cloning && source .venv-cloning/bin/activate
pip install -e ".[notebook,cloning]"
```

The `cloning` extra pins `setuptools<81`. Without it Chatterbox's watermarker cannot import
`pkg_resources` and the model fails to load with `'NoneType' object is not callable`.

**Set up the voices.** Put a clean, single-speaker recording of 10 to 20 seconds (24 kHz or higher) in
`assets/voices/` (git-ignored, so voices are never committed), then fill in that host's entry in
`config/voices.yaml`. The two hosts need different voices (FR6), so at least one needs a reference.

**Run** with `PODCAST_NB_TTS_BACKEND=chatterbox`, or set `TTS_BACKEND` in the second cell. The first run
downloads about 3 GB of model weights into the Hugging Face cache (`HF_HOME`).

What this does with the voices:

- Each line is cached under `segment_cache_key("chatterbox", voice, text)`, where the voice part includes a
  hash of the reference recording, so replacing a recording never serves old audio.
- **Show notes** credit a cloned voice ("voice cloned from a recording by NAME, with their permission").
  The full consent record (speaker, where consent is kept, licence) goes only to the private
  `run_manifest.json`.
- **Watermark.** Chatterbox embeds an imperceptible AI watermark in what it generates. The scorecard checks
  for it in the final mixed and normalised episode. In a test run it was detected in every clip and in the
  final episode, and not in a non-Chatterbox recording. Whether it survives MP3/AAC encoding is untested.

**Speed.** Measured on an Apple-silicon Mac using its GPU (MPS): about 17 seconds per spoken line.
A 3.3-minute, 40-line episode took about 10 minutes to voice (623 s in total), which is 99% of the run, and
misses the PRD's "under 10 minutes" target. A 7-minute episode would take roughly twice that. Reaching the
target needs a CUDA GPU, a hosted TTS, or several voice workers in parallel (the pipeline already runs one
worker per stage). A refresh, which re-voices only changed lines, took 33 seconds.

**Judging a clone.** Listen first: `notebooks/output/<run>/episode_r1.wav`, and the side-by-side clips if
you generate them. An objective cross-check is the speaker-similarity score from Chatterbox's own voice
encoder (cosine, 1.0 = identical). It is the same encoder family the model conditions on, so it measures
consistency with the model's idea of a voice, not an independent verdict. Measured in one session on an
Apple-silicon Mac:

| Comparison | Similarity |
|---|---|
| Two different Apple system voices, against each other | 0.57 to 0.61 |
| Default Chatterbox voice against a clean Apple voice | 0.61 to 0.65 |
| **Clone of a clean Apple voice** against that voice | **0.93 to 0.94** |
| A person's own recording, first half against second half | 0.91 |
| Clone of that person's recording (23 dB signal-to-noise) against the recording | 0.87 |
| Default Chatterbox voice against that same recording | 0.89 |

Cloning clearly works as a mechanism (the third row), but a clone is only as good as its reference. In that
test the default voice was already close to the speaker, and the clone from a quiet, slightly noisy
recording did not beat it. If a clone does not sound like the speaker: re-record closer to the microphone in
a quiet room (aim for speech around -20 dBFS with a very low noise floor, not -37), use 15 to 20 seconds of
continuous natural speech, and avoid reverb, music and a second voice.

**Tested with** a synthetic reference only (a macOS system voice rendered locally, recorded in the
registry as a test fixture), plus the default voice. It has not been tried with a real person's recording,
so the quality of a real clone is unknown. The test for this backend is opt-in and slow:
`PODCAST_TEST_CHATTERBOX=1 pytest tests/integration/test_notebook_flow.py -k cloning --no-cov`. A fast
test always runs and checks that a clone with no consent record is refused.

## Outputs

Each run writes to `notebooks/output/<run id>/` (git-ignored): the episode audio for revision 1 and 2,
show notes, the RSS feed under `store/feeds/<show id>.xml` (the same key the API serves), and
`run_manifest.json` with the model, prompt versions, voices and seed. `notebooks/output/last_results.json`
holds the scorecard in machine-readable form, and `notebooks/output/tts_cache/` is the voice cache.

## Limits

- The offline fact-check is a **word-overlap proxy**. It catches invented detail, not a subtle
  contradiction. The LLM judges when enabled. Neither replaces the PRD's manual claim audit.
- The **live LLM calls have not been run in testing.** They are exercised against stand-ins
  (`tests/fixtures/fake_genai`, `fake_anthropic`), which check prompt building, id mapping, validation and
  the rewrite loop, not what a model writes. What was checked against the real SDKs is the start-up check:
  with no credentials, or a bad key, the first cell stops with a clear message. Read the first live script
  and the fact-check verdicts yourself before trusting them. The model ID `gemini-3.8-flash` comes from
  Google's model list, and the first cell confirms your key can use it. The cost figure uses the API's real
  token counts (thinking tokens count as output) at list prices written into the scorecard cell. Those are
  only filled in for a few models, and Gemini's Flash price changes on 2027-01-01.
- The sample sources hold about 3 minutes of material, so **episode length** misses the PRD's 5 to 10
  minute target. The scorecard says so.
- Audio is **WAV**. Podcast apps want MP3 or M4A, so a real feed needs an encode step (ffmpeg).
- **Naturalness and comprehension** (RQ2, RQ3) need listeners; the scorecard marks them not measured.
- Not covered: PDF and search ingestion (FR2), script review UI (FR7), personalisation and
  interactive segments (FR11, FR12).
