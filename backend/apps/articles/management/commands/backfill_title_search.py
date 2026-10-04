from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Remplit les titres normalisés manquants par lots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]

        if not 1 <= batch_size <= 50000:
            raise CommandError(
                "--batch-size doit être compris entre 1 et 50000."
            )

        last_id = -9223372036854775808
        total = 0

        while True:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH batch AS (
                        SELECT page_id
                        FROM articles_article
                        WHERE title_search IS NULL
                          AND page_id > %s
                        ORDER BY page_id
                        LIMIT %s
                    )
                    UPDATE articles_article AS article
                    SET title_search = lower(unaccent(article.title))
                    FROM batch
                    WHERE article.page_id = batch.page_id
                    RETURNING article.page_id
                    """,
                    [last_id, batch_size],
                )
                updated_ids = [row[0] for row in cursor.fetchall()]

            if not updated_ids:
                break

            last_id = max(updated_ids)
            total += len(updated_ids)

            self.stdout.write(
                f"{total:,} titres traités ; dernier ID : {last_id}"
            )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM articles_article
                WHERE title_search IS NULL
                """
            )
            remaining = cursor.fetchone()[0]

        if remaining:
            raise CommandError(
                f"{remaining:,} titres restent à traiter. "
                "Relance la commande."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Terminé : {total:,} titres normalisés pendant "
                "cette exécution, aucun titre manquant."
            )
        )