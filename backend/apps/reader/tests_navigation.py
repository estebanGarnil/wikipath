from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework.exceptions import NotFound, PermissionDenied

from .navigation import FollowParams, NavigationUnavailable, follow_outgoing, resolve_wikipedia


class ArticleNavigationTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.target = {'page_id': 123, 'title': 'Destination', 'namespace': 0, 'language': 'fr'}

    @patch('apps.reader.navigation.resolve_wikipedia')
    @patch('apps.reader.navigation.read_query')
    def test_direct_neighbor_does_not_need_wikipedia_or_displayed_ids(self, query, resolve):
        query.side_effect = [[{'id': 3}], [{'page': self.target}]]
        self.assertEqual(follow_outgoing(3, 'Destination'), self.target)
        resolve.assert_not_called()

    @patch('apps.reader.navigation.resolve_wikipedia')
    @patch('apps.reader.navigation.read_query')
    def test_redirect_requires_graph_edge(self, query, resolve):
        query.side_effect = [[{'id': 3}], [], [{'page': self.target}]]
        resolve.return_value = {'page_id': 123, 'title': 'Destination'}
        self.assertEqual(follow_outgoing(3, 'Ancien titre'), self.target)
        self.assertEqual(query.call_args.args[1], {'source_id': 3, 'target_id': 123})

    @patch('apps.reader.navigation.resolve_wikipedia')
    @patch('apps.reader.navigation.read_query')
    def test_resolved_page_without_outgoing_edge_is_rejected(self, query, resolve):
        query.side_effect = [[{'id': 3}], [], []]
        resolve.return_value = {'page_id': 123, 'title': 'Destination'}
        with self.assertRaises(PermissionDenied):
            follow_outgoing(3, 'Destination')

    @patch('apps.reader.navigation.resolve_wikipedia')
    @patch('apps.reader.navigation.read_query', return_value=[])
    def test_missing_source_is_rejected_before_remote_request(self, query, resolve):
        with self.assertRaises(NotFound):
            follow_outgoing(3, 'Destination')
        resolve.assert_not_called()

    @patch('apps.reader.navigation.requests.get')
    def test_redirect_resolution_is_cached(self, get):
        get.return_value = Mock(**{'json.return_value': {'query': {'pages': [
            {'pageid': 123, 'ns': 0, 'title': 'Destination'}]}}})
        self.assertEqual(resolve_wikipedia('Alias')['page_id'], 123)
        self.assertEqual(resolve_wikipedia('Alias')['page_id'], 123)
        self.assertEqual(get.call_count, 1)

    @patch('apps.reader.navigation.requests.get')
    def test_non_article_namespace_not_navigable(self, get):
        get.return_value = Mock(**{'json.return_value': {'query': {'pages': [
            {'pageid': 123, 'ns': 6, 'title': 'Fichier:Test.jpg'}]}}})
        self.assertIsNone(resolve_wikipedia('Fichier:Test.jpg'))

    @patch('apps.reader.navigation.requests.get', side_effect=requests.Timeout())
    def test_remote_failure_is_reported_as_unavailable(self, get):
        with self.assertRaises(NavigationUnavailable):
            resolve_wikipedia('Alias')

    def test_title_validation_and_normalization(self):
        params = FollowParams(data={'title':'Alge\u0300bre_line\u0301aire'})
        self.assertTrue(params.is_valid())
        self.assertEqual(params.validated_data['title'], 'Algèbre linéaire')
        self.assertFalse(FollowParams(data={'title':'France|Brésil'}).is_valid())
