import unittest

from backend.core import dedupe_products, is_stale, stable_product_id, transition_sync_status, validate_product_response


class CoreTests(unittest.TestCase):
    def test_deduplication_by_id_and_name(self):
        pid = stable_product_id("u1", "A Product", "Beauty")
        products = [
            {"id": pid, "name": "A Product", "category": "Beauty"},
            {"id": pid, "name": "A Product", "category": "Beauty"},
            {"id": "x2", "name": "A   product!!!", "category": "Beauty"},
            {"id": "x3", "name": "A Product", "category": "Fashion"},
        ]
        output = dedupe_products(products)
        self.assertEqual(len(output), 2)

    def test_stale(self):
        self.assertTrue(is_stale("2000-01-01T00:00:00+00:00", 30))

    def test_sync_state_transitions(self):
        self.assertEqual(transition_sync_status("idle", "running"), "running")
        self.assertEqual(transition_sync_status("running", "success"), "success")
        with self.assertRaises(ValueError):
            transition_sync_status("idle", "success")

    def test_api_response_validation(self):
        validate_product_response({"id": "1", "name": "x", "category": "Beauty", "product_url": "https://example.com"})
        with self.assertRaises(ValueError):
            validate_product_response({"id": "1", "name": "x"})


if __name__ == "__main__":
    unittest.main()
