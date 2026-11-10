#!/usr/bin/env python3
"""Run local-only k6 experiments against a disposable Compose project."""

import argparse
import gzip
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from collect import (BRANDS, QUEUE_QUERY, asynchronous, csv_rows, db_snapshot,
                     http_metrics, ledger_query, observe, utc, write_json)

HERE = Path(__file__).resolve().parent
APPS = HERE.parent.parent / "apps"
sys.path.insert(0, str(APPS / "tests"))
from support import request, token

K6_IMAGE = "grafana/k6:0.57.0"
DEFAULT_RATES = {"idle": (0, 0, 0), "normal": (2, 2, 2),
                 "single-spike": (10, 2, 2), "all-spike": (6, 6, 6)}
SERVICES = ("catalog-api", "order-api", "fulfillment-worker", "postgres", "localstack", "mock-pos")
SUITE = [
    ("idle", "idle", 1, 0), ("normal", "normal", 1, 0),
    ("single-spike", "single-spike", 1, 0), ("all-spike", "all-spike", 1, 0),
    ("single-spike-workers-2", "single-spike", 2, 0),
    ("single-spike-pos-400ms", "single-spike", 1, 400),
    ("single-spike-pos-400ms-workers-2", "single-spike", 2, 400),
]


def command(*args, env=None, capture=True):
    return subprocess.run(args, env=env, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE if capture else None, check=True).stdout


class Stack:
    def __init__(self):
        self.project = "saas-load-" + secrets.token_hex(5)
        example = dict(line.split("=", 1) for line in (APPS / ".env.example").read_text().splitlines()
                       if line and not line.startswith("#"))
        self.env = {**os.environ, **example, "COMPOSE_PROJECT_NAME": self.project,
                    "LOCAL_JWT_SECRET": secrets.token_hex(32), "POS_SHARED_TOKEN": secrets.token_hex(32),
                    "CATALOG_PORT": "18181", "ORDER_PORT": "18182", "WORKER_PORT": "18183", "MOCK_POS_PORT": "18184",
                    "POS_URL": "http://mock-pos:18184", "POS_FAIL_FIRST": "0", "POS_TIMEOUT_MS": "2500"}

    def compose(self, *args, capture=True):
        return command("docker", "compose", "-f", str(APPS / "compose.yaml"),
                       "-f", str(HERE / "compose.load.yaml"), "--env-file", str(APPS / ".env.example"),
                       *args, env=self.env, capture=capture)

    def sql(self, sql):
        return self.compose("exec", "-T", "postgres", "sh", "-ec",
                            'PGPASSWORD="$POSTGRES_PASSWORD" exec psql -X -qAt -v ON_ERROR_STOP=1 '
                            '-h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"', "sql", sql)

    def start(self, replicas, delay, *, build=False):
        self.env["POS_DELAY_MS"] = str(delay)
        self.compose("up", "--build" if build else "--no-build", "--wait", "--wait-timeout", "120",
                     "--scale", f"fulfillment-worker={replicas}", capture=False)

    def docker_stats(self):
        containers = self.compose("ps", "-q", *SERVICES).split()
        samples = command("docker", "stats", "--no-stream", "--format", "{{json .}}", *containers)
        return [{**record, "Name": record["Name"].removeprefix(self.project + "-")}
                for line in samples.splitlines() if (record := json.loads(line))]

    def queues(self):
        return json.loads(self.compose("exec", "-T", "localstack", "python3", "-c", QUEUE_QUERY))

    def warm(self, tokens):
        for brand in BRANDS:
            code, _ = request(18181, "/catalog", bearer=tokens[brand])
            if code != 200:
                raise RuntimeError(f"Catalog warm-up failed with {code}")
            code, _ = request(18182, "/orders/00000000-0000-0000-0000-000000000000", bearer=tokens[brand])
            if code != 404:
                raise RuntimeError(f"Order warm-up failed with {code}")


def local_tokens(stack):
    for key in ("LOCAL_JWT_SECRET", "JWT_ISSUER", "JWT_AUDIENCE"):
        os.environ[key] = stack.env[key]
    return {brand: token(f"brand_{brand}") for brand in BRANDS}


def capture_samples(stack, run_id, target, interval, stop, ready):
    collectors = {"docker": stack.docker_stats, "sqs": stack.queues,
                  "postgres": lambda: json.loads(stack.sql(db_snapshot(run_id)))}
    with target.open("w") as stream, ThreadPoolExecutor(max_workers=3) as executor:
        while not stop.is_set():
            start = time.monotonic()
            futures = {name: executor.submit(observe, action) for name, action in collectors.items()}
            stream.write(json.dumps({name: future.result() for name, future in futures.items()}) + "\n")
            stream.flush()
            ready.set()
            stop.wait(max(0, interval - (time.monotonic() - start)))


def capture_age(stack, since, request_brands, target):
    ages = {f"brand_{brand}": {"age_ms": [], "receive_to_ack_ms": []} for brand in BRANDS}
    with target.open("w") as stream:
        logs = stack.compose("logs", "--no-color", "--no-log-prefix", "--since", since, "fulfillment-worker")
        for line in logs.splitlines():
            if not line.startswith("{"):
                continue
            record = json.loads(line)
            brand = request_brands.get(record.get("request_id"))
            if brand and record.get("tenant_id") == brand and "sqs_message_age_ms" in record:
                age = record["sqs_message_age_ms"]
                ack = record.get("sqs_receive_to_ack_ms")
                ages[brand]["age_ms"].append(age)
                if ack is not None:
                    ages[brand]["receive_to_ack_ms"].append(ack)
                stream.write(json.dumps(dict(timestamp=record["@timestamp"], brand=brand,
                                             age_ms=age, receive_to_ack_ms=ack)) + "\n")
    return ages


def run_k6(stack, settings, tokens, folder):
    env = {**os.environ, **settings,
           "CATALOG_URL": "http://catalog-api:18181", "ORDER_URL": "http://order-api:18182",
           **{f"K6_TOKEN_{b.upper()}": tokens[b] for b in BRANDS}}
    flags = [item for name in env if name in settings or name in ("CATALOG_URL", "ORDER_URL")
             or name in ("K6_TOKEN_A", "K6_TOKEN_B", "K6_TOKEN_C") for item in ("-e", name)]
    command("docker", "run", "--rm", "--network", stack.project + "_default",
            "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{HERE}/workload.js:/workload.js:ro",
            "-v", f"{folder}:/results", *flags, K6_IMAGE, "run", "--quiet",
            "--out", "json=/results/k6.json", "/workload.js", env=env, capture=False)
    source = folder / "k6.json"
    with source.open("rb") as raw, gzip.open(folder / "k6.json.gz", "wb") as zipped:
        shutil.copyfileobj(raw, zipped)
    source.unlink()


def run_one(stack, label, scenario, workers, delay, base, *, build):
    rates = {b.upper(): int(os.getenv(f"RATE_{b.upper()}", default))
             for b, default in zip(BRANDS, DEFAULT_RATES[scenario])}
    if scenario == "idle":
        rates = dict.fromkeys(rates, 0)
    order_pct = {b.upper(): int(os.getenv(f"ORDER_PERCENT_{b.upper()}", "35")) for b in BRANDS}
    seconds = int(os.getenv("DURATION_SECONDS", "12"))
    vus = int(os.getenv("VUS_PER_BRAND", "4"))
    interval = float(os.getenv("SAMPLE_SECONDS", "4"))
    drain = int(os.getenv("DRAIN_SECONDS", "100"))
    if (not 1 <= seconds <= 300 or not 1 <= vus <= 100 or not 1 <= interval <= 300 or drain < 1
            or any(not 0 <= rate <= 100 for rate in rates.values())
            or any(not 0 <= mix <= 100 for mix in order_pct.values())
            or (scenario != "idle" and sum(rates.values()) == 0)):
        raise ValueError("Invalid load or sampling configuration")
    folder = base / label
    folder.mkdir()
    run_id = "k6-" + secrets.token_hex(8)
    settings = dict(SCENARIO=scenario, DURATION_SECONDS=str(seconds), VUS_PER_BRAND=str(vus), RUN_ID=run_id,
                    **{f"RATE_{b}": str(rate) for b, rate in rates.items()},
                    **{f"ORDER_PERCENT_{b}": str(mix) for b, mix in order_pct.items()})
    print(f"=== {label}: {rates} req/s, {workers} worker(s), POS delay {delay} ms", flush=True)
    stack.start(workers, delay, build=build)
    tokens = local_tokens(stack)
    stack.warm(tokens)
    stop, ready = threading.Event(), threading.Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        samples = executor.submit(capture_samples, stack, run_id, folder / "samples.jsonl", interval, stop, ready)
        try:
            if not ready.wait(20):
                raise RuntimeError("Initial sample timed out")
            start = utc()
            run_k6(stack, settings, tokens, folder)
            end = utc()
            deadline = time.monotonic() + drain
            while True:
                rows = json.loads(stack.sql(db_snapshot(run_id)))["orders"]
                if all(row["orders"] == row["fulfilled"] for row in rows):
                    queues = stack.queues()
                    if not any(count for brand in queues.values() for kind in brand.values() for count in kind.values()):
                        break
                if time.monotonic() >= deadline:
                    break
                time.sleep(1)
        finally:
            stop.set()
            samples.result()

    metadata = dict(scenario=scenario, rates_rps=rates, order_percent=order_pct, duration_seconds=seconds,
                    vus_per_active_brand=vus if scenario != "idle" else 0,
                    worker_replicas=workers, pos_delay_ms=delay, sampling_target_seconds=interval,
                    drain_limit_seconds=drain, load_started_at=start, load_ended_at=end, observation_ended_at=utc())
    write_json(folder / "conditions.json", metadata)
    ledger = csv_rows(stack.sql(ledger_query(run_id)))
    request_brands = {row.pop("request_id"): row["brand"] for row in ledger}
    ages = capture_age(stack, start, request_brands, folder / "sqs-age.jsonl")
    write_json(folder / "orders.json", ledger)
    final_queues = observe(stack.queues)
    metrics = dict(http=http_metrics(folder / "k6.json.gz", seconds),
                   asynchronous=asynchronous(ledger, ages, datetime.fromisoformat(start), datetime.fromisoformat(end)),
                   final_queues=final_queues)
    write_json(folder / "summary.json", metrics)
    if any("error" in obs for line in (folder / "samples.jsonl").read_text().splitlines()
           for obs in json.loads(line).values()) or "error" in final_queues:
        raise RuntimeError(f"Collection failed for {label}; inspect samples and summary")
    if any(count for brand in final_queues["data"].values()
           for queue in brand.values() for count in queue.values()):
        raise RuntimeError(f"Queue did not drain for {label}")
    for brand, counts in metrics["asynchronous"].items():
        expected = metrics["http"][brand]["order"]["successes"]
        if any(counts[key] != expected for key in ("orders", "fulfilled", "processed", "published", "pos_accepted")):
            raise RuntimeError(f"Order/ledger mismatch for {label} {brand}")
        if expected and not counts["sqs_message_age"]["samples"]:
            raise RuntimeError(f"No SQS age observations for {label} {brand}")


def environment():
    cpu = next(line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
               if line.startswith("model name"))
    docker = json.loads(command("docker", "info", "--format", "{{json .}}"))
    return dict(cpu_model=cpu, wsl_release=platform.release(), machine=platform.machine(),
                docker_cpu=docker["NCPU"], docker_memory_bytes=docker["MemTotal"],
                docker_version=docker["ServerVersion"], docker_os=docker["OperatingSystem"],
                compose=command("docker", "compose", "version", "--short").strip(), k6_image=K6_IMAGE,
                k6_image_id=command("docker", "image", "inspect", "--format", "{{.Id}}", K6_IMAGE).strip(),
                app_base_commit=command("git", "-C", str(APPS), "rev-parse", "HEAD").strip(),
                started_at=utc())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--suite", action="store_true")
    mode.add_argument("--scenario", choices=DEFAULT_RATES)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--pos-delay-ms", type=int, default=0)
    parser.add_argument("--output", type=Path, default=HERE / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    if not 0 <= args.pos_delay_ms <= 10000:
        parser.error("--pos-delay-ms must be between 0 and 10000")
    base = args.output.resolve()
    base.mkdir(parents=True)
    if subprocess.run(["docker", "image", "inspect", K6_IMAGE], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        command("docker", "pull", K6_IMAGE, capture=False)
    write_json(base / "environment.json", environment())
    stack = Stack()
    cases = SUITE if args.suite else [(args.scenario, args.scenario, args.workers, args.pos_delay_ms)]
    try:
        for index, (label, scenario, workers, delay) in enumerate(cases):
            run_one(stack, label, scenario, workers, delay, base, build=index == 0)
    finally:
        stack.compose("down", "--volumes", capture=False)


if __name__ == "__main__":
    main()
