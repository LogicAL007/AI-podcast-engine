"""Scalability and reliability checks against the running Docker stack (NFRs), through the API.

    python -m evaluation.benchmarks.stack [--api http://localhost:8000] [--parallel 3]

* Scalability: start several episodes at once and compare the wall time with one episode alone.
  Stateless workers should overlap them, so N episodes take well under N times as long.
* Reliability: stop one stage's worker, start an episode, and check it waits at that stage; then
  start the worker and check the episode finishes without re-running the earlier stages.

It stops and starts compose services, so run it on a development stack, not one serving listeners.
"""

import argparse
import json
import subprocess
import time
from collections.abc import Sequence
from typing import Any

import httpx

from evaluation.benchmarks.run import CLICKHOUSE
from evaluation.harness import run_folder, write_json

TERMINAL = {"published", "failed", "needs_review", "unchanged"}


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], check=True, capture_output=True)  # noqa: S603, S607


def new_show(client: httpx.Client, label: str) -> str:
    body = {
        **CLICKHOUSE,
        "topic": f"{CLICKHOUSE['topic']} ({label})",
        "tone": "casual",
        "expertise": "beginner",
    }
    reply = client.post("/shows", json=body)
    reply.raise_for_status()
    return str(reply.json()["show_id"])


def start(client: httpx.Client, show_id: str) -> str:
    reply = client.post(f"/shows/{show_id}/episodes")
    reply.raise_for_status()
    return str(reply.json()["episode_id"])


def wait(
    client: httpx.Client, episode_ids: list[str], timeout: float = 600
) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout
    done: dict[str, dict[str, Any]] = {}
    while len(done) < len(episode_ids) and time.monotonic() < deadline:
        for episode_id in episode_ids:
            if episode_id in done:
                continue
            body = client.get(f"/episodes/{episode_id}").json()
            if body["status"] in TERMINAL:
                done[episode_id] = {**body, "finished_after_s": None}
        time.sleep(0.5)
    return done


def timed_batch(client: httpx.Client, count: int, label: str) -> dict[str, Any]:
    shows = [new_show(client, f"{label} {n}") for n in range(count)]
    started = time.monotonic()
    episodes = [start(client, show) for show in shows]
    finished = wait(client, episodes)
    seconds = time.monotonic() - started
    return {
        "episodes": episodes,
        "seconds": seconds,
        "statuses": sorted(v["status"] for v in finished.values()),
        "all_published": len(finished) == count
        and all(v["status"] == "published" for v in finished.values()),
    }


def reliability(client: httpx.Client, stage: str) -> dict[str, Any]:
    show = new_show(client, f"reliability {stage}")
    compose("stop", stage)
    try:
        episode = start(client, show)
        stuck: dict[str, Any] = {}
        for _ in range(120):  # the earlier stages finish; the job then waits in the stopped queue
            stuck = client.get(f"/episodes/{episode}").json()
            runs = [r["stage"] for r in client.get(f"/episodes/{episode}/runs").json()]
            if runs and runs[-1] == _before(stage):
                break
            time.sleep(0.5)
        time.sleep(3)
        waiting = client.get(f"/episodes/{episode}").json()
    finally:
        compose("start", stage)
    finished = wait(client, [episode])
    runs = [r["stage"] for r in client.get(f"/episodes/{episode}/runs").json()]
    return {
        "stopped": stage,
        "while_stopped": {k: waiting.get(k) for k in ("status", "stage")},
        "final_status": finished.get(episode, {}).get("status"),
        "stage_runs": runs,
        "each_stage_ran_once": sorted(runs) == sorted(set(runs)) and len(runs) == 8,
        "first_seen": {k: stuck.get(k) for k in ("status", "stage")},
    }


def _before(stage: str) -> str:
    order = [
        "ingest",
        "index",
        "retrieve_plan",
        "script",
        "factcheck",
        "voice",
        "assemble",
        "publish",
    ]
    return order[order.index(stage) - 1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--stop-stage", default="assemble")
    args = parser.parse_args(argv)
    folder = run_folder("stack")
    with httpx.Client(base_url=args.api, timeout=30) as client:
        client.get("/health").raise_for_status()
        print("one episode alone ...", flush=True)
        single = timed_batch(client, 1, "single")
        print(f"{args.parallel} episodes at once ...", flush=True)
        batch = timed_batch(client, args.parallel, "parallel")
        print(f"stopping the {args.stop_stage} worker mid-pipeline ...", flush=True)
        recovery = reliability(client, args.stop_stage)
    speedup = args.parallel * single["seconds"] / batch["seconds"] if batch["seconds"] else 0.0
    results = {
        "single": single,
        "parallel": batch,
        "parallel_speedup_vs_serial": speedup,
        "reliability": recovery,
    }
    write_json(folder / "results.json", results)
    print(json.dumps(results, indent=2, default=str))
    print(f"wrote {folder}")
    ok = (
        single["all_published"]
        and batch["all_published"]
        and recovery["final_status"] == "published"
    )
    return 0 if ok and recovery["each_stage_ran_once"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
