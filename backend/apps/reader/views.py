from urllib.parse import quote

from django.apps import apps
from django.db import connection, transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ArticleRender
from .rendering import RenderUnavailable, fetch_render, fingerprint


class ArticleRenderView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, page_id):
        if page_id > 9223372036854775807:
            return Response({'detail': 'Article introuvable.'}, status=404)
        Article = apps.get_model('articles', 'Article')
        article = get_object_or_404(Article, page_id=page_id)
        key = fingerprint(article)
        cached = ArticleRender.objects.filter(article_id=page_id, fingerprint=key).first()
        hit = cached is not None
        if cached is None:
            # Avoid simultaneous remote renders of the same article.
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', [7241, page_id % 2147483647])
                    acquired = cursor.fetchone()[0]
                if not acquired:
                    return Response({'detail':'Le rendu est en cours. Réessayez dans quelques secondes.'}, status=503, headers={'Retry-After':'2'})
                cached = ArticleRender.objects.filter(article_id=page_id, fingerprint=key).first()
                hit = cached is not None
                if cached is None:
                    try:
                        html = fetch_render(article)
                    except RenderUnavailable as exc:
                        return Response({'detail':str(exc)}, status=503)
                    cached, _ = ArticleRender.objects.update_or_create(
                        article_id=page_id, defaults={'fingerprint':key,'html':html})
        return Response({
            'page_id':page_id,'title':article.title,'revision_id':article.revision_id,
            'html':cached.html,'cached':hit,'rendered_at':cached.rendered_at,
            'source_url': 'https://fr.wikipedia.org/wiki/' + quote(article.title.replace(' ', '_'), safe=''),
            'history_url': 'https://fr.wikipedia.org/w/index.php?title=' + quote(article.title, safe='') + '&action=history',
        })
