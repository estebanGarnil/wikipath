from rest_framework import serializers


class NeighborsQuerySerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=["in", "out"], default="out")
    limit = serializers.IntegerField(min_value=1, max_value=200, default=50)
    # The client must return next_cursor unchanged (it is no longer an ID).
    after = serializers.CharField(max_length=2048, default="0", trim_whitespace=False)
