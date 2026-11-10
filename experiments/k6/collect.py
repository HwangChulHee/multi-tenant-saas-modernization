"""Collect local observations and summarize sanitized k6/DB points."""

import csv
import gzip
import io
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

BRANDS = ("a", "b", "c")


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def csv_rows(result):
    return list(csv.DictReader(io.StringIO(result)))


def percentiles(values):
    values = sorted(values)
    if not values:
        return {"p50_ms": None, "p95_ms": None, "p99_ms": None}
    return {f"p{p}_ms": round(values[math.ceil(len(values) * p / 100) - 1], 3) for p in (50, 95, 99)}


def http_metrics(path, seconds):
    samples = defaultdict(list)
    dropped = Counter()
    with gzip.open(path, "rt") as source:
        for line in source:
            point = json.loads(line)
            if point["type"] != "Point":
                continue
            data = point["data"]
            tags = data["tags"]
            tenant = tags.get("tenant")
            if point["metric"] == "dropped_iterations":
                dropped[tenant or tags.get("scenario", "unknown")] += int(data["value"])
            if point["metric"] == "http_req_duration":
                sample = (float(data["value"]), tags.get("status") != {"catalog": "200", "order": "201"}[tags["operation"]])
                samples[(tenant, tags["operation"])].append(sample)
                samples[(tenant, "all")].append(sample)
                samples[("all", "all")].append(sample)

    def summarize(rows):
        failures = sum(failed for _, failed in rows)
        return dict(requests=len(rows), rps=round(len(rows) / seconds, 3), errors=failures,
                    successes=len(rows) - failures,
                    success_pct=round(100 * (len(rows) - failures) / len(rows), 3) if rows else None,
                    error_pct=round(100 * failures / len(rows), 3) if rows else None,
                    **percentiles(value for value, _ in rows))

    result = {tenant: {operation: summarize(samples[(tenant, operation)])
                       for operation in ("all", "catalog", "order")}
              for tenant in (f"brand_{brand}" for brand in BRANDS)}
    result["total"] = summarize(samples[("all", "all")])
    result["dropped_iterations"] = dict(dropped)
    return result


def observe(action):
    started = utc()
    start = time.monotonic()
    try:
        data = action()
        return dict(started_at=started, elapsed_seconds=round(time.monotonic() - start, 3), data=data)
    except Exception as error:
        return dict(started_at=started, error=type(error).__name__)


# Run once inside LocalStack. The boto3 client is part of its local test image.
QUEUE_QUERY = """
import boto3, json, os
sqs = boto3.client('sqs', endpoint_url='http://127.0.0.1:4566',
                   region_name=os.environ['AWS_DEFAULT_REGION'],
                   aws_access_key_id='test', aws_secret_access_key='test')
result = {}
for brand in 'abc':
    base = 'brand-' + brand + '-orders'
    result['brand_' + brand] = {}
    for queue, field in ((base, 'source'), (base + '-dlq', 'dlq')):
        url = sqs.get_queue_url(QueueName=queue)['QueueUrl']
        attributes = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=[
            'ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible'])['Attributes']
        result['brand_' + brand][field] = {key: int(value) for key, value in attributes.items()}
print(json.dumps(result))
"""


def db_snapshot(run_id):
    orders = " UNION ALL ".join(
        f"""SELECT 'brand_{b}' AS brand, count(*) AS orders,
                count(*) FILTER (WHERE o.status = 'FULFILLED') AS fulfilled,
                count(*) FILTER (WHERE e.published_at IS NULL) AS outbox_pending
            FROM brand_{b}.orders o JOIN brand_{b}.outbox_events e ON o.id = e.order_id
            WHERE o.idempotency_key LIKE '{run_id}-%'"""
        for b in BRANDS
    )
    return f"""
        SELECT json_build_object(
            'orders', (SELECT json_agg(s ORDER BY brand) FROM ({orders}) s),
            'worker_db_sessions', (SELECT coalesce(json_agg(s ORDER BY role), '[]') FROM (
                SELECT usename AS role, count(*) AS connections,
                    count(*) FILTER (WHERE xact_start IS NOT NULL) AS in_transaction,
                    count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction,
                    count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiters,
                    round(coalesce(max(extract(epoch FROM (clock_timestamp() - xact_start))) * 1000, 0), 2)
                        AS oldest_transaction_ms
                FROM pg_stat_activity WHERE usename IN ('brand_a_worker','brand_b_worker','brand_c_worker')
                GROUP BY usename
            ) s)
        )
    """


def ledger_query(run_id):
    selects = [
        f"""SELECT 'brand_{b}' AS brand, o.request_id, o.created_at, e.published_at, p.processed_at,
            o.status, d.accepted_at AS pos_accepted_at, d.attempts AS pos_attempts,
            round(extract(epoch FROM (p.processed_at - o.created_at)) * 1000, 3) AS fulfillment_ms
            FROM brand_{b}.orders o
            LEFT JOIN brand_{b}.outbox_events e ON o.id = e.order_id
            LEFT JOIN brand_{b}.processed_events p ON o.id = p.order_id
            LEFT JOIN mock_pos.deliveries d ON d.order_id = o.id AND d.tenant_id = 'brand_{b}'
            WHERE o.idempotency_key LIKE '{run_id}-%'""" for b in BRANDS
    ]
    return "COPY (" + " UNION ALL ".join(selects) + " ORDER BY created_at) TO STDOUT WITH CSV HEADER"


def asynchronous(ledger, ages, load_start, load_end):
    load_seconds = (load_end - load_start).total_seconds()
    result = {}
    for brand in (f"brand_{b}" for b in BRANDS):
        rows = [row for row in ledger if row["brand"] == brand]
        processed = [datetime.fromisoformat(row["processed_at"]) for row in rows if row["processed_at"]]
        during_load = sum(load_start <= at <= load_end for at in processed)
        result[brand] = dict(
            orders=len(rows), fulfilled=sum(row["status"] == "FULFILLED" for row in rows),
            processed=len(processed), published=sum(bool(row["published_at"]) for row in rows),
            pos_accepted=sum(bool(row["pos_accepted_at"]) for row in rows),
            completed_during_load=during_load, worker_orders_per_sec=round(during_load / load_seconds, 3),
            fulfillment=percentiles(float(row["fulfillment_ms"]) for row in rows if row["fulfillment_ms"]),
            sqs_message_age=dict(samples=len(ages[brand]["age_ms"]), **percentiles(ages[brand]["age_ms"])),
            sqs_receive_to_ack=dict(samples=len(ages[brand]["receive_to_ack_ms"]),
                                    **percentiles(ages[brand]["receive_to_ack_ms"])),
        )
    return result
