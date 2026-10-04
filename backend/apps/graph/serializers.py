from rest_framework import serializers


class NeighborsQuerySerializer(serializers.Serializer):
    direction = serializers.ChoiceField(
        choices=["in", "out"],
        default="out",
    )
    limit = serializers.IntegerField(
        min_value=1,
        max_value=200,
        default=50,
    )
    after = serializers.IntegerField(
        min_value=0,
        max_value=9223372036854775807,
        default=0,
    )