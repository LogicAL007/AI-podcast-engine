# Architecture diagrams

Fourteen diagrams of AI Podcast Engine, drawn from the code as it stands (October 2026). They all
share one visual language, so they work as a set in slides or on their own.

| Folder or file | What it is | Use it for |
|---|---|---|
| `svg/` | The diagrams, 1600 px wide | Slides (PowerPoint: Insert → Pictures keeps them sharp at any size), docs, the web |
| `png/` | The same, 3200 px wide (2×) | Anything that cannot take SVG |
| `architecture-diagrams.pdf` | All fourteen, one per page | Handing out, printing, appendices |

## The diagrams

| # | Diagram | What it shows |
|---|---|---|
| 01 | [System context](png/01-system-context.png) | Who uses the system (creators, admins, listeners), the outside systems it relies on (source websites, the language model, speech synthesis, email), and what the system does |
| 02 | [Containers](png/02-containers.png) | Every running piece: nginx, the API, the scheduler, the eight stage workers, Redis, PostgreSQL with pgvector, object storage, Vault, Mailpit and Prometheus. How requests and jobs flow between them |
| 03 | [The episode pipeline](png/03-pipeline.png) | The eight stages: what each one does and writes, the fact-check rewrite loop (at most twice), the review hold, the "unchanged" stop and the failure path |
| 04 | [Episode lifecycle](png/04-episode-lifecycle.png) | Every episode status and what moves it on: queued, processing, needs review, published, unchanged, failed and cancelled. Also retry, cancel and delete |
| 05 | [Keeping episodes current](png/05-refresh.png) | How a scheduled refresh regenerates only what changed sources touch, what is reused and what is regenerated. Planned parts are marked *planned* |
| 06 | [API layers and modules](png/06-api-layers.png) | Router → controller → service → repository for each resource, which routes need a sign-in, the shared modules, and the infrastructure below |
| 07 | [Security architecture](png/07-security.png) | Trust zones; cookie + CSRF, bearer tokens and API keys; Argon2id and HMAC-hashed tokens; login limits; Vault; and which ports are reachable from where |
| 08 | [Sequence: sign-in, then a change](png/08-sign-in-sequence.png) | Step by step: how the browser signs in without seeing its token, and how a later change is authorised |
| 09 | [Sequence: generating an episode](png/09-generation-sequence.png) | From the Generate button through the eight queued stages, with live progress over server-sent events, to playing the audio |
| 10 | [Data model](png/10-data-model.png) | All twelve PostgreSQL tables with their key columns, relationships (crow's-foot notation) and delete behaviour |
| 11 | [Deployment](png/11-deployment.png) | The Docker Compose stack: every container with its image, ports, volumes and secrets, plus the one-shot setup and the start-up order |
| 12 | [Web app](png/12-web-app.png) | The React app's routes, state, live-progress hook and typed client; what nginx does; how the client is generated from the API |
| 13 | [Evaluation and research tooling](png/13-evaluation.png) | How the accuracy, format and trust studies and the technical benchmarks are run; their status; where results land |
| 14 | [Observability](png/14-observability.png) | Prometheus metrics (names and labels), logs, run records, the security log and health checks |

**Colours:** each colour stands for one kind of part, and every diagram has a legend.
- **Dark orange:** the system and the edge (the web app's own colour).
- **Blue:** application services.
- **Green:** pipeline workers.
- **Violet:** data stores.
- **Amber:** security.
- **Grey:** supporting services.
- **Dashed outline:** external systems.

## Changing a diagram

The diagrams are generated, so edit the code, never the SVG files:

- `build.py`: diagrams 01–05.
- `diagrams_more.py`: diagrams 06–14.
- `svgkit.py`: the drawing toolkit (boxes, cylinders, arrows, tables, sequence lifelines). It estimates the width of every label and refuses to build if any text would spill out of its shape.

```bash
python3 presentation/diagrams/build.py          # rewrite svg/*.svg (standard library only)

# PNGs and the PDF need Playwright with Chromium:
npm install --prefix /tmp/pw playwright@1.64.0 && npx --prefix /tmp/pw playwright install chromium
NODE_PATH=/tmp/pw/node_modules node presentation/diagrams/render.mjs
```

**Check each change against the code it describes.** The main sources are:
- `docker-compose.yml`;
- `src/podcast_engine/common/queue.py` and `src/podcast_engine/stages/*/service.py`;
- `src/podcast_engine/api/`;
- `docs/erd.md` and `db/migrations/`;
- `web/src/`;
- `evaluation/README.md`.
