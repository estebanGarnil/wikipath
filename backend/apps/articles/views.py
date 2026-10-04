from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet
from django.db import connection, transaction

from .models import Article
from .pagination import ArticlePagination
from .serializers import (
    ArticleContentSerializer,
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleSearchSerializer,
    ArticleSuggestSerializer,
)
from .search import search_articles, suggest_articles


class ArticleViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    pagination_class = ArticlePagination
    lookup_field = "page_id"
    lookup_value_regex = r"\d+"
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        queryset = Article.objects.all().order_by("page_id")

        if self.action == "content":
            return queryset

        queryset = queryset.defer("wikitext_zlib")

        if self.action == "list":
            params = ArticleSearchSerializer(data=self.request.query_params)
            params.is_valid(raise_exception=True)

            query = params.validated_data.get("q")
            if query:
                queryset = search_articles(queryset, query)

            queryset = queryset.only("page_id", "title")

        return queryset

    @transaction.atomic
    def list(self, request, *args, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT set_config(
                    'pg_trgm.strict_word_similarity_threshold',
                    %s,
                    true
                )
                """,
                ["0.35"],
            )

        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action == "list":
            return ArticleListSerializer

        if self.action == "content":
            return ArticleContentSerializer

        return ArticleDetailSerializer

    @action(detail=True, methods=["get"])
    def content(self, request, **kwargs):
        article = self.get_object()
        serializer = self.get_serializer(article)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        pagination_class=None,
    )
    @transaction.atomic
    def suggest(self, request):
        params = ArticleSuggestSerializer(
            data=request.query_params,
        )
        params.is_valid(raise_exception=True)

        query = params.validated_data["q"]
        limit = params.validated_data["limit"]

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT set_config(
                    'pg_trgm.strict_word_similarity_threshold',
                    %s,
                    true
                )
                """,
                ["0.35"],
            )

        articles = suggest_articles(
            queryset=Article.objects.only("page_id", "title"),
            query=query,
            limit=limit,
        )

        serializer = ArticleListSerializer(articles, many=True)

        return Response({
            "results": serializer.data,
        })