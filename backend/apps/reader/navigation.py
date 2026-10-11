"""Follow outgoing edges independently of the displayed neighbor page."""
import hashlib
import unicodedata

import requests
from django.conf import settings
from django.core.cache import cache
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.neo4j import read_query


class NavigationUnavailable(APIException):
    status_code = 503
    default_detail = 'La vérification du lien est temporairement indisponible. Réessayez.'


class FollowParams(serializers.Serializer):
    title = serializers.CharField(max_length=512, trim_whitespace=True)

    def validate_title(self, value):
        value = unicodedata.normalize('NFC', value.replace('_', ' ')).strip().lstrip(':')
        # One title per request; fragment navigation is handled in the reader.
        if not value or any(c in value for c in '|#\x00\n\r'):
            raise serializers.ValidationError('Titre de destination invalide.')
        return value


def resolve_wikipedia(title):
    key = 'wiki-target-v1:' + hashlib.sha256(title.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    try:
        response = requests.get(
            'https://fr.wikipedia.org/w/api.php',
            params={'action':'query','format':'json','formatversion':2,
                    'titles':title,'redirects':1,'maxlag':5},
            headers={'User-Agent': getattr(settings, 'WIKIPEDIA_USER_AGENT',
                'Wikipath/0.1 (https://github.com/estebanGarnil/wikipath; local article reader)')},
            timeout=(5, 10),
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NavigationUnavailable('Impossible de résoudre ce titre via Wikipédia pour le moment.') from exc
    if not isinstance(data, dict) or 'error' in data:
        raise NavigationUnavailable('Wikipédia ne peut pas résoudre ce titre pour le moment.')
    pages = data.get('query', {}).get('pages', [])
    if not isinstance(pages, list):
        raise NavigationUnavailable()
    page = pages[0] if len(pages) == 1 else {}
    if not isinstance(page, dict):
        raise NavigationUnavailable()
    if ('missing' in page or 'invalid' in page or page.get('ns') != 0
            or not isinstance(page.get('pageid'), int) or page['pageid'] <= 0):
        cache.set(key, {}, 300)
        return None
    resolved = {'page_id':page['pageid'], 'title':page['title']}
    cache.set(key, resolved, 3600)
    return resolved


def follow_outgoing(source_id, title):
    source = read_query('MATCH (p:Page {page_id: $id}) RETURN p.page_id AS id', {'id':source_id})
    if not source:
        raise NotFound('La page de départ est absente du graphe.')
    # Expand only the source adjacency, never scan every page by title.
    variants = list(dict.fromkeys([title, title[:1].upper() + title[1:]]))
    rows = read_query('''
        MATCH (source:Page {page_id: $source_id})-[:LINKS_TO]->(target:Page)
        WHERE target.title IN $titles
        RETURN target {.page_id, .title, .namespace, .language} AS page
        LIMIT 1
    ''', {'source_id':source_id, 'titles':variants})
    if rows:
        return rows[0]['page']
    resolved = resolve_wikipedia(title)
    if resolved is None:
        raise NotFound('Ce lien ne correspond pas à un article Wikipédia disponible (page absente ou autre espace de noms).')
    rows = read_query('''
        MATCH (source:Page {page_id: $source_id}), (target:Page {page_id: $target_id})
        WHERE EXISTS { MATCH (source)-[:LINKS_TO]->(target) }
        RETURN target {.page_id, .title, .namespace, .language} AS page
    ''', {'source_id':source_id, 'target_id':resolved['page_id']})
    if not rows:
        raise PermissionDenied('Aucun lien sortant direct vers cette page dans notre graphe importé. Le rendu actuel de Wikipédia peut différer de cet import.')
    return rows[0]['page']


class ArticleFollowView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, page_id):
        if page_id > 9223372036854775807:
            raise NotFound('La page de départ est absente du graphe.')
        params = FollowParams(data=request.query_params)
        params.is_valid(raise_exception=True)
        try:
            page = follow_outgoing(page_id, params.validated_data['title'])
        except (Neo4jError, ServiceUnavailable, SessionExpired) as exc:
            raise NavigationUnavailable() from exc
        return Response({
            'source_id':page_id, 'node':page,
            'edge':{'source':page_id, 'target':page['page_id'], 'type':'LINKS_TO'},
        })
