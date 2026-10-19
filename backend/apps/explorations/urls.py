from django.urls import path

from .views import ExplorationListCreateView


app_name = "explorations"

urlpatterns = [
    path(
        "",
        ExplorationListCreateView.as_view(),
        name="list-create",
    ),
]

from django.urls import path

from .views import (
    ExplorationDetailView,
    ExplorationListCreateView,
    ExplorationVisitsView,
)


app_name = "explorations"

urlpatterns = [
    path(
        "",
        ExplorationListCreateView.as_view(),
        name="list-create",
    ),
    path(
        "<uuid:exploration_id>/",
        ExplorationDetailView.as_view(),
        name="detail",
    ),
    path(
        "<uuid:exploration_id>/visits/",
        ExplorationVisitsView.as_view(),
        name="visits",
    ),
]