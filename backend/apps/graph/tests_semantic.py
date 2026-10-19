from unittest.mock import patch

from django.core import signing
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from . import services
from .serializers import NeighborsQuerySerializer
from .views import GraphNeighborsView


class SemanticPaginationTests(SimpleTestCase):
    def row(self, page_id, score):
        return {"page": {"page_id": page_id, "title": str(page_id)}, "score": score}

    def token(self, **changes):
        data = dict(schema=1, page=3, direction="out", order="semantic",
                    version="v3:test", id=12, score=0.85)
        data.update(changes)
        return signing.dumps(data, salt=services.CURSOR_SALT)

    def test_first_page_and_exact_tie_cursor(self):
        with patch.object(services, "get_order", return_value=("semantic", "v3:test", 4)), patch.object(
            services, "read_query", return_value=[self.row(9, .9), self.row(12, .85), self.row(25, .85)]
        ) as query:
            result = services.get_neighbors(3, "out", 2, "0")
        self.assertEqual([p["page_id"] for p in result["neighbors"]], [9, 12])
        self.assertTrue(result["has_more"])
        self.assertEqual(result["total_neighbors"], 4)
        self.assertIsNone(query.call_args.args[1]["after_score"])
        self.assertEqual(services.decode_cursor(result["next_cursor"], 3, "out", "semantic", "v3:test"), (12, .85))
        with patch.object(services, "get_order", return_value=("semantic", "v3:test", 4)), patch.object(
            services, "read_query", return_value=[self.row(25, .85), self.row(2, .7)]
        ) as query:
            second = services.get_neighbors(3, "out", 2, result["next_cursor"])
        self.assertEqual(query.call_args.args[1]["after"], 12)
        self.assertEqual(query.call_args.args[1]["after_score"], .85)
        self.assertIn("score = $after_score AND neighbor.page_id > $after", query.call_args.args[0])
        self.assertEqual([p["page_id"] for p in second["neighbors"]], [25, 2])
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_cursor"])

    def test_cursor_preserves_float_precision(self):
        score = 0.854731559753418
        self.assertEqual(services.decode_cursor(self.token(score=score), 3, "out", "semantic", "v3:test"), (12, score))

    def test_tampered_cursor_rejected(self):
        with self.assertRaises(ValidationError):
            services.decode_cursor(self.token() + "x", 3, "out", "semantic", "v3:test")

    def test_other_page_and_direction_rejected(self):
        for page, direction in [(7, "out"), (3, "in")]:
            with self.subTest(page=page, direction=direction), self.assertRaises(ValidationError):
                services.decode_cursor(self.token(), page, direction, "semantic", "v3:test")

    def test_changed_version_and_lost_coverage_rejected(self):
        for order, version in [("semantic", "new"), ("page_id", None)]:
            with self.subTest(order=order), self.assertRaises(services.GraphOrderChanged):
                services.decode_cursor(self.token(), 3, "out", order, version)

    def test_invalid_signed_payload_rejected(self):
        for changes in [dict(id=-1), dict(id=True), dict(score=float("nan")), dict(score=2), dict(schema=2)]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                services.decode_cursor(self.token(**changes), 3, "out", "semantic", "v3:test")

    def test_legacy_id_only_for_id_order(self):
        self.assertEqual(services.decode_cursor("17", 3, "out", "page_id", None), (17, None))
        with self.assertRaises(services.GraphOrderChanged):
            services.decode_cursor("17", 3, "out", "semantic", "v3:test")
        with self.assertRaises(ValidationError):
            services.decode_cursor(str(2**63), 3, "out", "page_id", None)

    def test_incoming_never_uses_outgoing_marker(self):
        with patch.object(services, "read_query") as query:
            self.assertEqual(services.get_order(3, "in"), ("page_id", None, None))
        query.assert_not_called()

    def test_complete_coverage_required(self):
        valid = dict(version="v3:test", expected=20, total=20, relationships=21, scored=21)
        for changes, order in [({}, "semantic"), ({"scored": 20}, "page_id"), ({"expected": 19}, "page_id")]:
            with self.subTest(changes=changes), patch.object(services, "read_query", return_value=[{**valid, **changes}]):
                self.assertEqual(services.get_order(3, "out")[0], order)

    def test_unmarked_page_fallback(self):
        with patch.object(services, "read_query", return_value=[]):
            self.assertEqual(services.get_order(33, "out"), ("page_id", None, None))

    def test_id_pagination_and_cached_count(self):
        with patch.object(services, "get_order", return_value=("page_id", None, None)), patch.object(
            services, "read_query", return_value=[self.row(8, None), self.row(12, None)]
        ), patch.object(services, "get_neighbor_count", return_value=2):
            result = services.get_neighbors(33, "out", 1, "0")
        self.assertEqual(services.decode_cursor(result["next_cursor"], 33, "out", "page_id", None), (8, None))
        self.assertEqual(result["order"], "page_id")

    def test_empty_page_has_no_cursor(self):
        with patch.object(services, "get_order", return_value=("semantic", "v3:test", 0)), patch.object(
            services, "read_query", return_value=[]
        ):
            result = services.get_neighbors(3, "out", 20, "0")
        self.assertEqual(result["neighbors"], [])
        self.assertFalse(result["has_more"])
        self.assertIsNone(result["next_cursor"])

    def test_serializer_accepts_cursor_and_rejects_bad_limit(self):
        serializer = NeighborsQuerySerializer(data={"after": self.token(), "limit": 20})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["direction"], "out")
        for data in [{"limit": 0}, {"limit": 201}, {"after": "x" * 2049}, {"direction": "both"}]:
            self.assertFalse(NeighborsQuerySerializer(data=data).is_valid())

    def test_api_exposes_edge_score_and_order(self):
        from . import views
        result = dict(neighbors=[{"page_id": 7, "title": "Algèbre"}], scores={7: .9},
                      has_more=False, next_cursor=None, total_neighbors=1, order="semantic")
        request = APIRequestFactory().get("/", {"limit": 20})
        with patch.object(views, "get_page", return_value={"page_id": 3, "title": "Meillet"}), patch.object(
            views, "get_neighbors", return_value=result
        ):
            response = GraphNeighborsView.as_view()(request, page_id=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["order"], "semantic")
        self.assertEqual(response.data["edges"][0]["semantic_score"], .9)

    def test_api_returns_409_for_changed_order(self):
        from . import views
        request = APIRequestFactory().get("/")
        with patch.object(views, "get_page", return_value={"page_id": 3}), patch.object(
            views, "get_neighbors", side_effect=services.GraphOrderChanged
        ):
            response = GraphNeighborsView.as_view()(request, page_id=3)
        self.assertEqual(response.status_code, 409)
