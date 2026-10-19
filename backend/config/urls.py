from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.reader.urls")),
    path("api/", include("apps.core.urls")),
    path("api/", include("apps.articles.urls")),
    path("api/graph/", include("apps.graph.urls")),
    path("api/explorations/", include("apps.explorations.urls")),
]