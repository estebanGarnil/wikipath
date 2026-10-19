from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from apps.graph.views import GraphAPIView

from .models import Exploration, ExplorationVisit
from .serializers import (
    ExplorationCreateSerializer,
    ExplorationSerializer,
    ExplorationVisitCreateSerializer,
    ExplorationVisitSerializer,
)


class ExplorationPagination(PageNumberPagination):
    page_size = 20


@method_decorator(never_cache, name="dispatch")
class ExplorationListCreateView(GraphAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Exploration.objects.filter(
            user=request.user,
        ).order_by("-created_at", "-id")

        paginator = ExplorationPagination()
        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        serializer = ExplorationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = ExplorationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        page = self.get_page_or_404(
            serializer.validated_data["page_id"],
        )

        with transaction.atomic():
            exploration = Exploration.objects.create(
                user=request.user,
                start_page_id=page["page_id"],
                start_page_title=page["title"],
            )

            ExplorationVisit.objects.create(
                exploration=exploration,
                position=1,
                page_id=page["page_id"],
                page_title=page["title"],
            )

        return Response(
            ExplorationSerializer(exploration).data,
            status=201,
        )

class ExplorationVisitPagination(PageNumberPagination):
    page_size = 100


@method_decorator(never_cache, name="dispatch")
class ExplorationDetailView(GraphAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, exploration_id):
        exploration = get_object_or_404(
            Exploration,
            pk=exploration_id,
            user=request.user,
        )

        last_visit = exploration.visits.order_by("-position").first()

        data = dict(ExplorationSerializer(exploration).data)
        data["last_visit"] = (
            ExplorationVisitSerializer(last_visit).data
            if last_visit is not None
            else None
        )

        return Response(data)


@method_decorator(never_cache, name="dispatch")
class ExplorationVisitsView(GraphAPIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, exploration_id):
        exploration = get_object_or_404(
            Exploration,
            pk=exploration_id,
            user=request.user,
        )

        queryset = exploration.visits.order_by("position")
        paginator = ExplorationVisitPagination()
        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        serializer = ExplorationVisitSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, exploration_id):
        serializer = ExplorationVisitCreateSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        # Vérifier le propriétaire avant de consulter Neo4j.
        exploration = get_object_or_404(
            Exploration,
            pk=exploration_id,
            user=request.user,
        )

        existing = exploration.visits.filter(
            position=params["position"],
        ).first()

        if existing is not None:
            return self.existing_response(existing, params)

        # Un parent doit appartenir au parcours demandé.
        if "parent_id" in params:
            get_object_or_404(
                exploration.visits,
                pk=params["parent_id"],
            )

        page = self.get_page_or_404(params["page_id"])

        with transaction.atomic():
            # Sérialiser les ajouts concurrents.
            exploration = get_object_or_404(
                Exploration.objects.select_for_update(),
                pk=exploration_id,
                user=request.user,
            )

            existing = exploration.visits.filter(
                position=params["position"],
            ).first()

            if existing is not None:
                return self.existing_response(existing, params)

            last_visit = (
                exploration.visits.order_by("-position").first()
            )

            if last_visit is None:
                return Response(
                    {"detail": "Ce parcours ne possède pas de visite initiale."},
                    status=409,
                )

            next_position = last_visit.position + 1

            if params["position"] != next_position:
                return Response(
                    {
                        "detail": (
                            "Le parcours a changé. Rechargez-le "
                            "avant d'ajouter une visite."
                        ),
                        "expected_position": next_position,
                    },
                    status=409,
                )

            if "parent_id" in params:
                parent = get_object_or_404(
                    exploration.visits,
                    pk=params["parent_id"],
                )
            else:
                # Compatibilité avec le frontend actuel.
                parent = last_visit

            visit = ExplorationVisit.objects.create(
                exploration=exploration,
                parent=parent,
                position=next_position,
                page_id=page["page_id"],
                page_title=page["title"],
            )

            exploration.save(update_fields=["updated_at"])

        return Response(
            ExplorationVisitSerializer(visit).data,
            status=201,
        )

    @staticmethod
    def existing_response(visit, params):
        same_page = visit.page_id == params["page_id"]
        same_parent = (
            "parent_id" not in params
            or visit.parent_id == params["parent_id"]
        )

        if not same_page or not same_parent:
            return Response(
                {
                    "detail": (
                        "Cette position appartient déjà à une autre "
                        "visite ou branche. Rechargez le parcours."
                    ),
                },
                status=409,
            )

        return Response(ExplorationVisitSerializer(visit).data)