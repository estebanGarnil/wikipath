import logging

from neo4j.exceptions import (
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import NeighborsQuerySerializer
from .services import get_neighbors, get_page


logger = logging.getLogger(__name__)


class GraphUnavailable(APIException):
    status_code = 503
    default_detail = "Le graphe est temporairement indisponible."
    default_code = "graph_unavailable"


class GraphAPIView(APIView):
    permission_classes = [AllowAny]

    def handle_exception(self, exc):
        if isinstance(
            exc,
            (ServiceUnavailable, SessionExpired, TransientError),
        ):
            logger.exception("Échec de la requête Neo4j")
            exc = GraphUnavailable()

        return super().handle_exception(exc)

    def get_page_or_404(self, page_id):
        if page_id > 9223372036854775807:
            raise NotFound("Page absente du graphe.")

        page = get_page(page_id)

        if page is None:
            raise NotFound("Page absente du graphe.")

        return page


class GraphPageView(GraphAPIView):
    def get(self, request, page_id):
        page = self.get_page_or_404(page_id)
        return Response(page)


class GraphNeighborsView(GraphAPIView):
    def get(self, request, page_id):
        serializer = NeighborsQuerySerializer(
            data=request.query_params,
        )
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        center = self.get_page_or_404(page_id)
        result = get_neighbors(page_id=page_id, **params)

        # Un nœud peut aussi avoir un lien vers lui-même.
        # Le dictionnaire évite de le renvoyer deux fois.
        nodes_by_id = {center["page_id"]: center}
        edges = []

        for neighbor in result["neighbors"]:
            neighbor_id = neighbor["page_id"]
            nodes_by_id[neighbor_id] = neighbor

            if params["direction"] == "out":
                source, target = page_id, neighbor_id
            else:
                source, target = neighbor_id, page_id

            edges.append({
                "source": source,
                "target": target,
                "type": "LINKS_TO",
            })

        return Response({
            "center_id": page_id,
            "direction": params["direction"],
            "nodes": list(nodes_by_id.values()),
            "edges": edges,
            "has_more": result["has_more"],
            "next_cursor": result["next_cursor"],
        })