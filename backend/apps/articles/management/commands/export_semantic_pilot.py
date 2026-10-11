import gzip
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.articles.models import Article
from apps.core.neo4j import read_query


class Command(BaseCommand):
    help = 'Export a few source pages and ALL their distinct outgoing neighbors.'

    def add_arguments(self, parser):
        parser.add_argument('--page-ids', nargs='+', type=int, required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--max-pages', type=int, default=20000)

    def handle(self, *args, **options):
        sources = sorted(set(options['page_ids']))
        if len(sources) > 30 or any(x <= 0 for x in sources):
            raise CommandError('Choose 1 to 30 positive source IDs for this pilot.')
        pages, links = {}, []
        for source in sources:
            rows = read_query('''MATCH (p:Page {page_id: $id})
                RETURN p.page_id AS page_id, p.title AS title''', {'id': source})
            if not rows:
                raise CommandError(f'Source {source} absent from Neo4j.')
            pages[source] = rows[0]['title']
            # Limit is a safety guard: abort on overflow, never silently sample neighbors.
            rows = read_query('''MATCH (p:Page {page_id: $id})-[:LINKS_TO]->(n:Page)
                WHERE n <> p AND n.page_id > 0
                RETURN DISTINCT n.page_id AS page_id, n.title AS title
                ORDER BY page_id LIMIT $guard''',
                {'id': source, 'guard': options['max_pages'] + 1}, timeout=60)
            for row in rows:
                pages[row['page_id']] = row['title']
                links.append([source, row['page_id']])
            if len(pages) > options['max_pages']:
                raise CommandError('Pilot too large. Choose fewer sources; no partial export written.')
            self.stdout.write(f'{source}: {len(rows)} outgoing neighbors')
        path = Path(options['output'])
        if path.exists():
            raise CommandError(f'{path} already exists; choose a new output path.')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.partial')
        missing = 0
        try:
            with gzip.open(temporary, 'wt', encoding='utf-8') as stream:
                stream.write(json.dumps({'kind': 'manifest', 'schema': 1, 'sources': sources,
                    'links': links, 'direction': 'out'}, ensure_ascii=False) + '\n')
                ids = sorted(pages)
                for offset in range(0, len(ids), 200):
                    batch = ids[offset:offset + 200]
                    articles = {a.page_id: a for a in Article.objects.filter(page_id__in=batch)
                                .only('page_id', 'title', 'revision_id', 'wikitext_zlib')}
                    for page_id in batch:
                        article = articles.get(page_id)
                        missing += article is None
                        stream.write(json.dumps({'kind': 'page', 'page_id': page_id,
                            'title': pages[page_id], 'revision_id': article.revision_id if article else None,
                            'wikitext': article.wikitext if article else '',
                            'missing_article': article is None}, ensure_ascii=False) + '\n')
                    self.stdout.write(f'{min(offset + 200, len(ids))}/{len(ids)} pages exported')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(
            f'{path}: {len(pages)} pages, {len(links)} links, {missing} missing articles (title fallback).'))
