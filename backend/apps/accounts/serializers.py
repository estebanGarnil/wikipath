from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from rest_framework import serializers


User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=128,
    )
    password_confirm = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=128,
    )

    class Meta:
        model = User
        fields = ["id", "username", "password", "password_confirm"]
        read_only_fields = ["id"]

    def validate_username(self, value):
        value = User.normalize_username(value)

        if len(value) > 150:
            raise serializers.ValidationError(
                "Le nom d'utilisateur est trop long."
            )

        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "Ce nom d'utilisateur est déjà utilisé."
            )

        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({
                "password_confirm": "Les mots de passe ne correspondent pas.",
            })

        user = User(username=attrs["username"])

        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({
                "password": list(exc.messages),
            }) from exc

        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")

        try:
            with transaction.atomic():
                return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            # Deux inscriptions simultanées peuvent choisir le même nom.
            if User.objects.filter(
                username=validated_data["username"],
            ).exists():
                raise serializers.ValidationError({
                    "username": "Ce nom d'utilisateur est déjà utilisé.",
                }) from exc
            raise

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        max_length=128,
    )