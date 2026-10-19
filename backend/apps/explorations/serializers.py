from rest_framework import serializers

from .models import Exploration, ExplorationVisit


class ExplorationCreateSerializer(serializers.Serializer):
    page_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
    )


class ExplorationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exploration
        fields = [
            "id",
            "start_page_id",
            "start_page_title",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

class ExplorationVisitCreateSerializer(serializers.Serializer):
    page_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
    )
    position = serializers.IntegerField(
        min_value=2,
        max_value=2147483647,
    )
    parent_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
        required=False,
    )


class ExplorationVisitSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ExplorationVisit
        fields = [
            "id",
            "position",
            "parent_id",
            "page_id",
            "page_title",
            "visited_at",
        ]
        read_only_fields = fields