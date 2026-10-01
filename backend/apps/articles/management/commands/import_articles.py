import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.articles.models import Article


class Command(BaseCommand):
    help = "Importe les articles SQLite dans une table PostgreSQL vide."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path)

    def handle(self, *args, **options):
        path = options["source"].resolve()

        if not path.is_file():
            raise CommandError(f"Fichier introuvable : {path}")

        if connection.vendor != "postgresql":
            raise CommandError("Cette commande nécessite PostgreSQL.")

        table = connection.ops.quote_name(Article._meta.db_table)
        count = 0

        with closing(
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        ) as source:
            rows = source.execute("""
                SELECT page_id, title, revision_id, timestamp, wikitext_zlib
                FROM articles
                ORDER BY page_id
            """)

            # Tout l'import est validé ensemble, ou annulé en cas d'erreur.
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"
                    )

                    if Article.objects.exists():
                        raise CommandError(
                            "La table contient déjà des articles. "
                            "Aucune donnée n'a été remplacée."
                        )

                    with cursor.copy(
                        f"""
                        COPY {table}
                        (page_id, title, revision_id, timestamp, wikitext_zlib)
                        FROM STDIN
                        """
                    ) as copy:
                        for page_id, title, revision_id, stamp, blob in rows:
                            date = None

                            if stamp is not None:
                                date = datetime.fromisoformat(
                                    stamp.replace("Z", "+00:00")
                                )
                                if date.utcoffset() is None:
                                    raise CommandError(
                                        f"Date sans fuseau pour la page {page_id}"
                                    )

                            copy.write_row(
                                (page_id, title, revision_id, date, blob)
                            )
                            count += 1

                            if count % 50_000 == 0:
                                self.stdout.write(
                                    f"{count:,} articles transférés "
                                    "(validation finale en attente)"
                                )
                                self.stdout.flush()

        self.stdout.write(
            self.style.SUCCESS(f"Import terminé : {count:,} articles.")
        )