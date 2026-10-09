# Validation plan and status

Everything the PRD (*AI Podcast Creation with Dynamic Content: PRD and Design Architecture*, 30
September 2026) says must be measured or shown, how each item is validated here, and where it
stands. Status as of **9 October 2026**.

**Status key:** **Pass** (measured, meets the target) · **Fail** (measured, misses it) · **Ready**
(tooling built and dry-run, waiting on a live model run or people) · **Open** (nothing built yet) ·
**Out of scope** (the MVP does not build it).

## How to run

```bash
make bench-db                                      # throwaway pgvector database on :55433
python -m evaluation.benchmarks.run --tts say      # technical benchmarks (add --llm to use Gemini)
.venv-cloning/bin/python -m evaluation.benchmarks.wer evaluation/results/benchmarks/<run>
python -m evaluation.benchmarks.gate               # fact-check gate catch rate (add --llm)
python -m evaluation.benchmarks.stack              # parallelism and recovery on the Docker stack
python -m evaluation.rq1_claim_audit.generate --limit 1   # RQ1: spends API quota; then all 30
python -m evaluation.rq1_claim_audit.sheets evaluation/results/rq1/<run>
python -m evaluation.rq1_claim_audit.analyse evaluation/results/rq1/<run>
```

Each run writes `evaluation/results/<kind>/<UTC time>/` with `results.json` and `report.md`. Audio,
object stores and cached pages are git-ignored. Page snapshots are cached on first fetch, so every
condition and rerun reads the same text.

## 1. Success metrics

| Metric | Target | How it is validated | Status | Evidence |
|---|---|---|---|---|
| Factual accuracy of script | ≥ 90% of claims supported by a cited source | Claim-level manual audit by two raters (RQ1 tooling). The gate's support rate is only an automated proxy | **Ready** (manual audit). Proxy: 22/22 | `rq1_claim_audit/`; proxy in `results/benchmarks/20261009T212011Z` |
| End-to-end generation time | < 10 min for a 7-minute episode | Per-stage timing, projected linearly to 7 minutes | **Pass** with `say` voices (31 s for 3.7 min, about 58 s for 7 min). Chatterbox not yet benchmarked; the notebook run took about 556 s for 9.3 min | `results/benchmarks/20261009T212011Z` |
| Listener naturalness | MOS ≥ 3.8 / 5 | Listener survey (RQ3) | **Open**: needs participants and ethics approval | |
| Comprehension | quiz score ≥ text summary | Between-group quiz (RQ2) | **Open**: needs participants and ethics approval | |
| Cost per episode | < USD 1 | Token usage × list price, from the run manifest | **Pass** offline (USD 0). The Gemini run has not been measured | benchmarks `--llm` |
| Episode length (MVP definition) | 5 to 10 minutes, two hosts | Measured length | **Fail** with `say`: 3.7 min from the ClickHouse page. Length follows the source page, `MAX_SEGMENTS` and voice speed (Chatterbox gave 9.3 min) | `results/benchmarks/20261009T212011Z` |

## 2. Research questions

| RQ | Design (PRD) | What is built | Status |
|---|---|---|---|
| RQ1: grounded vs ungrounded accuracy | 30 scripts per condition, same topics and model. Two raters label claims; Cohen's kappa | 30 topics (`rq1_claim_audit/topics.yaml`). `generate.py` writes both conditions: same model, segment titles, tone and length, with only retrieval differing; the grounded draft before the gate and the final script after it are both kept. `sheets.py` makes blinded, shuffled sheets and source snapshots. `RATING_GUIDE.md` is for the raters. `analyse.py` reports accuracy with 95% CIs, unsupported rate, citation coverage, kappa, and a paired test by topic | **Ready.** Dry run on the fake SDK passed (`results/rq1/DRYRUN-fake-sdk-20261009`, fake answers, not data). Next: a live run (about 300 Gemini calls), then two raters |
| RQ2: dialogue vs narrator | Between-subjects, about 30 per group; quiz, engagement, completion | Statistics only (`stats.compare_independent`) | **Open**: needs the narrator version of each episode, quiz items, an engagement scale, a survey platform and ethics approval |
| RQ3: AI vs human episode | Within-subjects, randomized order; naturalness, trust, usefulness (5-point) | Statistics only (`stats.compare_paired`, `stats.mean_interval`) | **Open**: needs a human-produced episode on the same topic, the survey, counterbalanced orders and ethics approval |
| Analysis plan | t-tests, or Mann-Whitney U when not normal; effect sizes; limitations | `evaluation/stats.py`: Shapiro-Wilk picks the test, and the effect size and the reason are reported. Tested against worked examples | **Pass** (tooling) |
| Ethics | Informed consent, anonymised data, institutional approval before any user study | Nothing to build | **Open**: get approval before recruiting RQ1 raters (if your institution counts that as human-subjects work), and before RQ2 and RQ3 |

## 3. Technical benchmarks (per episode, automatic)

| Benchmark | Result | Evidence |
|---|---|---|
| Generation time per stage | Recorded in `stage_runs`. With `say`, voice is 92% of the time | benchmarks `results.json` → `stage_seconds` |
| Cost per episode | USD 0 offline; Gemini not run | |
| Loudness and silence | -16.00 LUFS, peak 0.96, 0 clipped samples, longest silence 0.94 s: **Pass** | benchmarks report |
| Speech-to-text round trip (WER) | **4.3%** (517 words; Whisper base.en; `say` voices). Main errors: "ClickHouse" heard as "Click House" (a spelling difference, not mishearing), and "vs." and "i.e." read aloud as abbreviations | `results/benchmarks/20261009T212011Z/wer.json` |

## 4. Functional requirements

| ID | Requirement | Priority | Status | Evidence or gap |
|---|---|---|---|---|
| FR1 | Create a show: topic, tone, length, hosts, language | Must | **Pass** | API tests; `stack` run |
| FR2 | Ingest RSS, URLs, PDFs, search results | Must | **Partial**: URLs only | RSS feeds as sources, PDF upload (PyMuPDF) and search are not built |
| FR3 | Retrieve and rank passages | Must | **Pass** | pgvector ranking; `test_pipeline.py` |
| FR4 | Outline, then a grounded multi-speaker script | Must | **Pass** offline; LLM path dry-run only | 6 segments, 2 hosts |
| FR5 | Every claim cited, viewable in show notes | Must | **Pass**: 22/22 cited, numbered in notes | benchmarks |
| FR6 | Distinct voice per host; intro, outro, transitions | Must | **Pass** | Samantha / Daniel; 6 chapters; synthetic chimes (no `assets/audio/` files yet) |
| FR7 | Review and edit the script before audio | Should | **Partial**: readable at `/episodes/{id}/script`, no editing | |
| FR8 | Regenerate when sources change | Should | **Pass**: one edited section → 1 segment re-scripted, 3 of 45 lines resynthesised, 4.9 s vs 30.8 s | benchmarks |
| FR9 | Fact-check flags unsupported claims | Should | **Weak** (see §6): the offline gate misses all 33 one-word distortions | `results/gate/20261009T212120Z` |
| FR10 | RSS feed and show notes for podcast apps | Should | **Pass**: parses with feedparser; enclosure served | Not yet checked in a real podcast app; WAV, not MP3 |
| FR11 | Listener personalisation | Could | **Out of scope** | |
| FR12 | Interactive segments | Could | **Out of scope** | |
| FR13 | AI-generated disclosure | Must | **Pass**: spoken first, in notes, RSS title and description | benchmarks |

## 5. Non-functional requirements

| Area | Requirement | Status | Evidence or gap |
|---|---|---|---|
| Performance | 7-minute episode < 10 min; stages run asynchronously through a queue | **Pass** (`say`, offline). Chatterbox and Gemini not benchmarked | benchmarks; 8 Celery queues |
| Accuracy | Claims traceable; unsupported flagged or removed | **Pass** for traceability (100% cited). **Weak** for flagging (§6) | |
| Audio quality | 24 kHz+, about -16 LUFS, no clipping, no long silences | **Pass** | benchmarks |
| Scalability | Stateless workers, episodes in parallel | **Pass**: 3 episodes in 11.3 s vs 8.5 s for one (2.2× faster than in sequence) | `results/stack/20261009T212340Z` |
| Cost | < USD 1; cache embeddings and repeated TTS segments | **Pass** offline; caching shown (42 of 45 lines reused on refresh) | |
| Reliability | Each stage retryable; a failed stage does not restart the job | **Pass**: assemble worker stopped mid-episode; the job waited, then finished with every stage run once | `results/stack/…` |
| Privacy and security | Uploads private; keys in a secrets manager; no training on user content | **Partial**: keys are Docker secrets. Uploads are not built. "No training" depends on the provider's terms (check the Gemini API terms for your tier) | Manual check |
| Transparency | AI label; model and prompt versions logged per episode | **Pass** | manifest and `stage_runs` |
| Reproducibility | Prompts, models and seeds stored; experiments rerunnable | **Pass** for the script (identical rebuild). Audio is identical with placeholder tones, not with `say` | benchmarks |

## 6. Findings so far

1. **The offline fact-check gate cannot tell a fact from its distortion.** On 122 labelled claims
   from the ClickHouse page, it caught fabrications in new words (90%), misattributed citations
   (100%) and uncited claims (100%). It caught **0 of 33** single-edit distortions: an added "not",
   another product's name, rows and columns swapped, a changed quantity. It also wrongly rejected
   46% of correct paraphrases. The 22/22 support rate is real only because the offline writer
   quotes source sentences word for word. It is not evidence that the gate would catch an LLM
   writer's mistakes. Run `gate --llm` to measure the Gemini judge on the same claims.
2. **Episode length is set by the source, not the target.** One documentation page gives 3.7
   minutes with `say` voices. To reach 5 to 10 minutes, use several sources, raise
   `MAX_SEGMENTS`, or let the LLM writer expand (it is asked for about 150 words a minute).
3. **Spoken style needs abbreviation handling.** "vs." and "i.e." are read as written. Expanding
   them before synthesis (the pronunciation lexicon exists but is not applied) would fix this.
4. **Status visibility.** While an episode waits for a stopped worker, the API shows the last
   finished stage, not the stage it is waiting for.

## 7. Threats to validity (so far)

- RQ1 topics come from one domain (one vendor's technical documentation).
- Generation time is projected linearly from a 3.7-minute episode, not measured on a 7-minute one.
- The automated support rate uses a lexical judge with the weaknesses described in §6.
- `say` voices stand in for the PRD's hosted or open neural TTS in the timing and WER figures.
