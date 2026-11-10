import concurrent.futures
import unittest
import uuid

from support import BRANDS, CATALOG, ORDER, order, request, sql, token


class TenantApiTests(unittest.TestCase):
    def test_menu_and_order_per_brand(self):
        shared_key = uuid.uuid4().hex
        ids = set()
        for brand in BRANDS:
            status, menu = request(CATALOG, "/catalog", bearer=token(brand))
            self.assertEqual(status, 200)
            self.assertEqual([item["name"] for item in menu], [f"{brand} combo"])
            status, created = order(brand, shared_key)
            self.assertEqual(status, 201)
            ids.add(created["id"])
            self.assertEqual(request(ORDER, "/orders/" + created["id"], bearer=token(brand))[0], 200)
        self.assertEqual(len(ids), 3)

    def test_cross_brand_order(self):
        status, created = order("brand_b")
        self.assertEqual(status, 201)
        self.assertEqual(request(ORDER, "/orders/" + created["id"], bearer=token("brand_a"))[0], 404)

    def test_header_does_not_switch_tenant(self):
        status, menu = request(CATALOG, "/catalog", bearer=token("brand_a"), headers={"X-Tenant-ID": "brand_b"})
        self.assertEqual(status, 200)
        self.assertEqual(menu[0]["name"], "brand_a combo")
        self.assertEqual(request(CATALOG, "/catalog", headers={"X-Tenant-ID": "brand_b"})[0], 401)

    def test_database_privileges(self):
        auth = dict(user="brand_a_catalog", password="local-catalog-a-only")
        self.assertEqual(sql("SELECT name FROM brand_a.menus", **auth).stdout.strip(), "brand_a combo")
        for query in ("SELECT * FROM brand_b.menus", "SELECT * FROM brand_a.orders",
                      "SET ROLE brand_b_catalog", "CREATE TABLE brand_a.forbidden (id int)"):
            with self.subTest(query=query):
                denied = sql(query, check=False, **auth)
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn("42501", denied.stderr)

    def test_concurrent_idempotent_requests(self):
        key = uuid.uuid4().hex
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: order("brand_a", key), range(8)))
        self.assertEqual(sorted(status for status, _ in results), [200] * 7 + [201])
        self.assertEqual(len({body["id"] for _, body in results}), 1)
        self.assertEqual(order("brand_a", key, quantity=2)[0], 409)
        count = sql(f"SELECT count(*) FROM brand_a.orders WHERE idempotency_key = '{key}'")
        self.assertEqual(count.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
