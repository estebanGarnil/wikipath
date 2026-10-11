from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from .services import get_neighbor_count, get_neighbors


class NeighborCountTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.graph.services.read_query")
    def test_zero_total_is_cached(self, query):
        query.return_value = [{"total": 0}]
        self.assertEqual(get_neighbor_count(3, "out"), 0)
        self.assertEqual(get_neighbor_count(3, "out"), 0)
        query.assert_called_once()

    @patch("apps.graph.services.read_query")
    def test_cache_separates_pages_and_directions(self, query):
        query.side_effect = [[{"total": 212}], [{"total": 40}], [{"total": 7}]]
        self.assertEqual(get_neighbor_count(3, "out"), 212)
        self.assertEqual(get_neighbor_count(3, "in"), 40)
        self.assertEqual(get_neighbor_count(7, "out"), 7)
        self.assertEqual(get_neighbor_count(3, "out"), 212)
        self.assertEqual(query.call_count, 3)

    @patch("apps.graph.services.read_query")
    def test_total_stays_independent_of_cursor_and_last_page(self, query):
        query.side_effect = [
            [{"page": {"page_id": 7}}, {"page": {"page_id": 9}}],
            [{"total": 2}],
            [{"page": {"page_id": 9}}],
        ]
        first = get_neighbors(3, "out", 1, 0)
        last = get_neighbors(3, "out", 1, first["next_cursor"])
        self.assertEqual(first["next_cursor"], 7)
        self.assertTrue(first["has_more"])
        self.assertFalse(last["has_more"])
        self.assertIsNone(last["next_cursor"])
        self.assertEqual(first["total_neighbors"], 2)
        self.assertEqual(last["total_neighbors"], 2)
        self.assertEqual(query.call_count, 3)
