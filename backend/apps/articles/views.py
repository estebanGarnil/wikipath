from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from .models import Article
from .pagination import ArticlePagination
from .serializers import (
    ArticleContentSerializer,
    ArticleDetailSerializer,
    ArticleListSerializer,
    ArticleSearchSerializer,
)


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
                queryset = queryset.filter(title__icontains=query)

            queryset = queryset.only("page_id", "title")

        return queryset

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