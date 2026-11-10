import base64
import concurrent.futures
from contextlib import contextmanager
import json
import subprocess
import time
import unittest
import uuid

from support import BRANDS, CATALOG, ORDER, compose, order, request, sql, token, wait_for
from test_phase13 import assert_ledger, counts, event_for, queue_url, wait_fulfilled


@contextmanager
def sidecar(service, *options):
    container = compose("run", "--no-deps", "--detach", *options, service).stdout.strip().splitlines()[-1]
    try:
        yield container
    finally:
        subprocess.run(["docker", "rm", "-f", container], stdin=subprocess.DEVNULL,
                       check=True, capture_output=True)


class SecurityAndConcurrencyTests(unittest.TestCase):
    def test_jwt_forgery_expiration_and_claims(self):
        header, payload, signature = token("brand_a").split(".")
        forged_claim = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        forged_claim["tenant_id"] = "brand_b"
        altered = base64.urlsafe_b64encode(json.dumps(forged_claim).encode()).decode().rstrip("=")
        unsigned_header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        bad_tokens = {
            "altered claim": ".".join((header, altered, signature)),
            "unsigned": ".".join((unsigned_header, payload, "")),
            "expired": token("brand_a", exp=int(time.time()) - 120),
            "no expiration": token("brand_a", exp=None),
            "future not-before": token("brand_a", nbf=int(time.time()) + 120),
            "wrong issuer": token("brand_a", iss="https://untrusted.test"),
            "wrong audience": token("brand_a", aud="other-api"),
            "unknown tenant": token("brand_x"),
        }
        for case, bearer in bad_tokens.items():
            with self.subTest(case=case):
                self.assertEqual(request(CATALOG, "/catalog", bearer=bearer)[0], 401)
                self.assertEqual(request(ORDER, "/orders", bearer=bearer,
                                         headers={"Idempotency-Key": uuid.uuid4().hex},
                                         body={"menuId": "menu-1", "quantity": 1})[0], 401)

    def test_source_image_enables_only_one_brand(self):
        with sidecar("catalog-api", "-e", "ACTIVE_BRANDS=brand_a", "-e", "DB_BRAND_B_PASSWORD=",
                     "-e", "DB_BRAND_C_PASSWORD=", "-p", f"127.0.0.1::{CATALOG}") as container:
            port = None

            def ready():
                nonlocal port
                published = subprocess.run(["docker", "port", container, f"{CATALOG}/tcp"],
                                           capture_output=True, text=True)
                _, _, port_text = published.stdout.strip().rpartition(":")
                if published.returncode != 0 or not port_text.isdecimal():
                    return False
                port = int(port_text)
                try:
                    return request(port, "/ready")[0] == 200
                except OSError:
                    return False

            wait_for(ready, "single-brand Catalog image")
            self.assertEqual(request(port, "/catalog", bearer=token("brand_a"))[1][0]["name"], "brand_a combo")
            self.assertEqual(request(port, "/catalog", bearer=token("brand_b"))[0], 401)

    def test_concurrent_brands_with_two_publishers(self):
        with sidecar("order-api", "-e", "OUTBOX_POLL_MS=125") as second:
            def ready():
                result = subprocess.run(["docker", "exec", second, "wget", "-q", "-O", "/dev/null",
                                         f"http://127.0.0.1:{ORDER}/ready"], capture_output=True)
                return result.returncode == 0

            wait_for(ready, "second Order API publisher")
            jobs = [(brand, key) for key in [uuid.uuid4().hex for _ in range(4)] for brand in BRANDS]
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(lambda job: order(*job), jobs))
            self.assertEqual([status for status, _ in results], [201] * len(jobs))
            self.assertEqual(len({body["id"] for _, body in results}), len(jobs))
            for (brand, _), (_, created) in zip(jobs, results, strict=True):
                wait_fulfilled(brand, created["id"])
                assert_ledger(self, brand, created["id"], pos_attempts=1)
                other = next(candidate for candidate in BRANDS if candidate != brand)
                self.assertEqual(request(ORDER, "/orders/" + created["id"], bearer=token(other))[0], 404)
            for brand in BRANDS:
                queue = queue_url(brand)
                wait_for(lambda: counts(queue) == (0, 0), f"{brand} input queue drain")

    def test_all_runtime_roles_have_only_assigned_schema(self):
        for brand in BRANDS:
            other = next(candidate for candidate in BRANDS if candidate != brand)
            for role in ("catalog", "order", "worker"):
                user = f"{brand}_{role}"
                auth = dict(user=user, password=f"local-{role}-{brand[-1]}-only")
                with self.subTest(user=user):
                    flags = sql("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
                                "FROM pg_roles WHERE rolname = current_user", **auth)
                    self.assertEqual(flags.stdout.strip(), "f")
                    queries = (f"SELECT * FROM {other}.menus", f"SET ROLE {other}_{role}",
                               "SELECT * FROM mock_pos.deliveries")
                    for query in queries:
                        self.assertIn("42501", sql(query, check=False, **auth).stderr)

        pos = sql("SELECT * FROM brand_a.orders", user="mock_pos_app", password="local-pos-only", check=False)
        self.assertIn("42501", pos.stderr)

    def test_structured_request_correlation(self):
        status, created = order("brand_c")
        self.assertEqual(status, 201)
        wait_fulfilled("brand_c", created["id"])
        event = event_for("brand_c", created["id"])
        for service in ("order-api", "fulfillment-worker", "mock-pos"):
            logs = compose("logs", "--no-color", "--no-log-prefix", service).stdout.splitlines()
            matching = [record for line in logs if line.startswith("{") and
                        (record := json.loads(line)).get("request_id") == event["requestId"]]
            self.assertTrue(matching, service)
            self.assertTrue(all(record["tenant_id"] == "brand_c" for record in matching), service)
