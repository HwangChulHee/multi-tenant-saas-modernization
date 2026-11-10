import json
import unittest

from support import ORDER, compose, order, request, sql, token, wait_for


def sqs(*args):
    return json.loads(compose("exec", "-T", "localstack", "awslocal", "sqs", *args,
                              "--output", "json").stdout or "{}")


def queue_url(brand, *, dlq=False):
    name = "brand-" + brand[-1] + "-orders" + ("-dlq" if dlq else "")
    return sqs("get-queue-url", "--queue-name", name)["QueueUrl"]


def counts(url):
    fields = ("ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible")
    attributes = sqs("get-queue-attributes", "--queue-url", url, "--attribute-names", *fields)["Attributes"]
    return tuple(int(attributes[field]) for field in fields)


def send(url, event):
    sqs("send-message", "--queue-url", url, "--message-body", json.dumps(event))


def event_for(brand, order_id):
    fields = sql(f"""
        SELECT e.event_id, o.request_id FROM {brand}.outbox_events e
        JOIN {brand}.orders o ON o.id = e.order_id WHERE o.id = '{order_id}'
        """).stdout.strip().split("|")
    return dict(eventId=fields[0], orderId=order_id, tenantId=brand, requestId=fields[1])


def wait_fulfilled(brand, order_id):
    def fulfilled():
        status, body = request(ORDER, "/orders/" + order_id, bearer=token(brand))
        return status == 200 and body["status"] == "FULFILLED"

    wait_for(fulfilled, f"{brand} order {order_id} fulfillment")


def assert_ledger(test, brand, order_id, pos_attempts=None):
    result = sql(f"""
        SELECT (SELECT count(*) FROM {brand}.orders WHERE id = '{order_id}'),
               (SELECT count(*) FROM {brand}.outbox_events WHERE order_id = '{order_id}' AND published_at IS NOT NULL),
               (SELECT count(*) FROM {brand}.processed_events WHERE order_id = '{order_id}'),
               (SELECT count(*) FROM mock_pos.deliveries WHERE order_id = '{order_id}' AND accepted_at IS NOT NULL)
        """).stdout.strip()
    test.assertEqual(result, "1|1|1|1")
    if pos_attempts is not None:
        attempts = sql(f"SELECT attempts FROM mock_pos.deliveries WHERE order_id = '{order_id}'")
        test.assertEqual(attempts.stdout.strip(), str(pos_attempts))


class FulfillmentTests(unittest.TestCase):
    def test_end_to_end(self):
        status, created = order("brand_a")
        self.assertEqual(status, 201)
        wait_fulfilled("brand_a", created["id"])
        assert_ledger(self, "brand_a", created["id"], pos_attempts=1)

    def test_duplicate_delivery(self):
        status, created = order("brand_b")
        self.assertEqual(status, 201)
        order_id = created["id"]
        wait_fulfilled("brand_b", order_id)
        queue = queue_url("brand_b")
        event = event_for("brand_b", order_id)
        for _ in range(2):
            send(queue, event)
        wait_for(lambda: counts(queue) == (0, 0), "duplicate message acknowledgements")
        assert_ledger(self, "brand_b", order_id, pos_attempts=1)

    def test_wrong_brand_delivery(self):
        status, created = order("brand_a")
        self.assertEqual(status, 201)
        order_id = created["id"]
        wait_fulfilled("brand_a", order_id)
        event = event_for("brand_a", order_id)
        queue = queue_url("brand_c")
        dlq = queue_url("brand_c", dlq=True)
        before = counts(dlq)[0]
        send(queue, event)
        send(queue, {**event, "tenantId": "brand_c"})
        wait_for(lambda: counts(dlq)[0] >= before + 2, "two rejected messages on the brand C DLQ", seconds=65)
        assert_ledger(self, "brand_a", order_id, pos_attempts=1)
        self.assertEqual(sql(f"SELECT count(*) FROM brand_c.processed_events WHERE order_id = '{order_id}'")
                         .stdout.strip(), "0")

    def test_publish_failure_recovers(self):
        compose("pause", "localstack")
        try:
            status, created = order("brand_a")
            self.assertEqual(status, 201)
            order_id = created["id"]

            def retry_recorded():
                return sql(f"""
                    SELECT attempts > 0 AND published_at IS NULL
                    FROM brand_a.outbox_events WHERE order_id = '{order_id}'
                    """).stdout.strip() == "t"

            wait_for(retry_recorded, "persisted outbox failure")
        finally:
            compose("unpause", "localstack")
        wait_fulfilled("brand_a", order_id)
        assert_ledger(self, "brand_a", order_id, pos_attempts=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
