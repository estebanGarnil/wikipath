"""Resolve a diverse, fixed selection in the local dump, then export all neighbors."""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.articles.models import Article
from apps.core.neo4j import read_query


DEFAULT_TITLES = (
    "Antoine Meillet",
    "Algèbre linéaire",
    "Algèbre générale",
    "France",
    "Python (langage)",
    "Photosynthèse",
    "Révolution française",
    "Impressionnisme",
    "Marie Curie",
    "Football",
)


class Command(BaseCommand):
    help = "Export ten diverse sources and ALL their distinct outgoing neighbors."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--max-pages", type=int, default=20000)
        parser.add_argument("--titles", nargs="+", help="Override the exact source titles.")

    def handle(self, *args, **options):
        titles = list(dict.fromkeys(options["titles"] or DEFAULT_TITLES))
        if not 1 <= len(titles) <= 30:
            raise CommandError("Choose between 1 and 30 titles.")
        if options["max_pages"] < len(titles):
            raise CommandError("--max-pages must be at least the number of sources.")

        # Resolve against the user's snapshot, not Wikipedia's current page IDs.
        rows = list(Article.objects.filter(title__in=titles).values("page_id", "title"))
        by_title = {}
        for row in rows:
            by_title.setdefault(row["title"], []).append(row["page_id"])
        problems = [title for title in titles if len(by_title.get(title, [])) != 1]
        if problems:
            raise CommandError(
                "Titles absent or ambiguous in PostgreSQL: " + ", ".join(problems)
                + ". Use --titles with exact local titles; no export was written."
            )

        ids = [by_title[title][0] for title in titles]
        graph_rows = read_query(
            "UNWIND $ids AS id MATCH (p:Page {page_id: id}) "
            "RETURN p.page_id AS page_id, p.title AS title",
            {"ids": ids},
        )
        graph = {row["page_id"]: row["title"] for row in graph_rows}
        missing = [title for title, page_id in zip(titles, ids) if page_id not in graph]
        if missing:
            raise CommandError("Sources absent from Neo4j: " + ", ".join(missing))

        for title, page_id in zip(titles, ids):
            self.stdout.write(f"{page_id}: {title}")
        self.stdout.write("Exporting all outgoing neighbors; no ranking or database writes.")
        call_command(
            "export_semantic_pilot",
            page_ids=ids,
            output=options["output"],
            max_pages=options["max_pages"],
            stdout=self.stdout,
            stderr=self.stderr,
        )
