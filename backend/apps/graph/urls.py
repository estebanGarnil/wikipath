from django.urls import path

from .views import GraphNeighborsView, GraphPageView


urlpatterns = [
    path(
        "pages/<int:page_id>/",
        GraphPageView.as_view(),
        name="graph-page",
    ),
    path(
        "pages/<int:page_id>/neighbors/",
        GraphNeighborsView.as_view(),
        name="graph-neighbors",
    ),
]