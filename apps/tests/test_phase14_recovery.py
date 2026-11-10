from contextlib import contextmanager
import subprocess
import unittest

from support import compose, order, sql, wait_for
from test_phase13 import assert_ledger, counts, queue_url, sqs, wait_fulfilled


@contextmanager
def pos_mode(**settings):
    def recreate(overrides=None):
        compose("up", "--no-build", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "40",
                "mock-pos", overrides=overrides)

    recreate(settings)
    try:
        yield
    finally:
        recreate()


def ledger_snapshot(brand, order_id):
    return sql(f"""
        SELECT o.status, e.published_at IS NOT NULL, (p.event_id IS NOT NULL),
               (d.accepted_at IS NOT NULL), d.attempts
        FROM {brand}.orders o JOIN {brand}.outbox_events e ON e.order_id = o.id
        LEFT JOIN {brand}.processed_events p ON p.event_id = e.event_id
        LEFT JOIN mock_pos.deliveries d ON d.event_id = e.event_id
        WHERE o.id = '{order_id}'
        """).stdout.strip()


def queue_arn(url):
    return sqs("get-queue-attributes", "--queue-url", url,
               "--attribute-names", "QueueArn")["Attributes"]["QueueArn"]


class RecoveryTests(unittest.TestCase):
    def new_order(self, brand):
        status, created = order(brand)
        self.assertEqual(status, 201)
        return created["id"]

    def test_worker_kill_after_pos_acceptance(self):
        brand = "brand_a"
        with pos_mode(POS_DELAY_MS="12000"):
            order_id = self.new_order(brand)
            wait_for(lambda: ledger_snapshot(brand, order_id) == "PENDING|t|f|t|1",
                     "POS acceptance before worker commit")
            container = compose("ps", "-q", "fulfillment-worker").stdout.strip()
            compose("kill", "-s", "SIGKILL", "fulfillment-worker")
            try:
                exit_code = subprocess.check_output(["docker", "inspect", "--format", "{{.State.ExitCode}}",
                                                     container], text=True)
                self.assertEqual(exit_code.strip(), "137")
                self.assertEqual(ledger_snapshot(brand, order_id), "PENDING|t|f|t|1")
            finally:
                compose("start", "fulfillment-worker")
            wait_fulfilled(brand, order_id)
            assert_ledger(self, brand, order_id, pos_attempts=2)
            queue = queue_url(brand)
            wait_for(lambda: counts(queue) == (0, 0), "worker restart acknowledgement")

    def test_pos_timeout_retries(self):
        brand = "brand_a"
        with pos_mode(POS_DELAY_MS="4000"):
            order_id = self.new_order(brand)
            wait_for(lambda: ledger_snapshot(brand, order_id) == "PENDING|t|f|t|1",
                     "delayed POS response with durable acceptance")
            wait_fulfilled(brand, order_id)
            assert_ledger(self, brand, order_id, pos_attempts=2)

    def test_pos_transient_failure_retries(self):
        brand = "brand_a"
        with pos_mode(POS_FAIL_FIRST="1"):
            order_id = self.new_order(brand)
            wait_for(lambda: ledger_snapshot(brand, order_id) == "PENDING|t|f|f|1", "first POS failure")
            wait_fulfilled(brand, order_id)
            assert_ledger(self, brand, order_id, pos_attempts=2)

    def test_dlq_then_redrive(self):
        brand = "brand_b"
        queue = queue_url(brand)
        dlq = queue_url(brand, dlq=True)
        self.assertEqual(counts(dlq), (0, 0))
        with pos_mode(POS_FAIL_FIRST="99"):
            order_id = self.new_order(brand)
            wait_for(lambda: counts(dlq) == (1, 0), "persistent POS failure moved to DLQ", seconds=65)
            self.assertEqual(counts(queue), (0, 0))
            self.assertEqual(ledger_snapshot(brand, order_id), "PENDING|t|f|f|3")

        source = queue_arn(dlq)
        sqs("start-message-move-task", "--source-arn", source, "--destination-arn", queue_arn(queue))
        wait_fulfilled(brand, order_id)
        assert_ledger(self, brand, order_id, pos_attempts=4)
        wait_for(lambda: counts(queue) == (0, 0) and counts(dlq) == (0, 0),
                 "original queue and DLQ drain after redrive")
