from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth import authenticate, login, logout

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, RegisterSerializer

@method_decorator(never_cache, name="dispatch")
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "csrf_token": get_token(request),
        })


@method_decorator(never_cache, name="dispatch")
class MeView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({
                "authenticated": False,
                "user": None,
            })

        return Response({
            "authenticated": True,
            "user": {
                "id": request.user.pk,
                "username": request.user.get_username(),
            },
        })

@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class RegisterView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "user": {
                    "id": user.pk,
                    "username": user.get_username(),
                },
            },
            status=201,
        )

@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )

        if user is None:
            return Response(
                {"detail": "Nom d'utilisateur ou mot de passe incorrect."},
                status=400,
            )

        login(request, user)

        return Response({
            "authenticated": True,
            "user": {
                "id": user.pk,
                "username": user.get_username(),
            },
            "csrf_token": get_token(request),
        })


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)

        return Response({
            "authenticated": False,
            "user": None,
            "csrf_token": get_token(request),
        })