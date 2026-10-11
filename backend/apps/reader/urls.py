from django.urls import path
from .views import ArticleRenderView
from .navigation import ArticleFollowView

urlpatterns = [path('articles/<int:page_id>/follow/', ArticleFollowView.as_view(), name='article-follow'), path('articles/<int:page_id>/render/', ArticleRenderView.as_view(), name='article-render')]
