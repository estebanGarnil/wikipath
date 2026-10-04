from rest_framework import serializers

from .models import Article


class ArticleListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["page_id", "title"]


class ArticleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Article
        fields = ["page_id", "title", "revision_id", "timestamp"]


class ArticleContentSerializer(ArticleDetailSerializer):
    wikitext = serializers.CharField(read_only=True)

    class Meta(ArticleDetailSerializer.Meta):
        fields = ArticleDetailSerializer.Meta.fields + ["wikitext"]


class ArticleSearchSerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False,
        min_length=3,
        max_length=200,
        trim_whitespace=True,
    )