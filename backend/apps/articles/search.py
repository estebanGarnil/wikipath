import re

from django.contrib.postgres.search import (
    TrigramSimilarity,
    TrigramStrictWordSimilarity,
)
from django.db import connection
from django.db.models import Case, IntegerField, Q, Value, When


def search_articles(queryset, query):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT lower(unaccent(%s))",
            [query],
        )
        normalized_query = cursor.fetchone()[0].strip()

    if not normalized_query:
        return queryset.none()

    # Bornes de mots PostgreSQL, saisie échappée :
    # "meilet" ne correspond pas exactement au mot "dumeilet".
    whole_words_pattern = (
        r"\m" + re.escape(normalized_query) + r"\M"
    )

    return (
        queryset.filter(
            Q(title_search__contains=normalized_query)
            | Q(
                title_search__trigram_strict_word_similar=normalized_query
            )
        )
        .annotate(
            search_priority=Case(
                When(
                    title_search=normalized_query,
                    then=Value(0),
                ),
                When(
                    title_search__regex=whole_words_pattern,
                    then=Value(1),
                ),
                default=Value(2),
                output_field=IntegerField(),
            ),
            word_similarity=TrigramStrictWordSimilarity(
                normalized_query,
                "title_search",
            ),
            title_similarity=TrigramSimilarity(
                "title_search",
                normalized_query,
            ),
        )
        .order_by(
            "search_priority",
            "-word_similarity",
            "-title_similarity",
            "title_search",
            "page_id",
        )
    )

def suggest_articles(queryset, query, limit):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT lower(unaccent(%s))",
            [query],
        )
        normalized_query = cursor.fetchone()[0].strip()

    if not normalized_query:
        return []

    whole_words_pattern = (
        r"\m" + re.escape(normalized_query) + r"\M"
    )

    # Première passe : expression exacte sur des mots entiers.
    exact_results = list(
        queryset.filter(
            title_search__regex=whole_words_pattern,
        )
        .annotate(
            exact_priority=Case(
                When(
                    title_search=normalized_query,
                    then=Value(0),
                ),
                When(
                    title_search__startswith=normalized_query,
                    then=Value(1),
                ),
                default=Value(2),
                output_field=IntegerField(),
            ),
        )
        .order_by(
            "exact_priority",
            "title_search",
            "page_id",
        )[:limit]
    )

    if exact_results:
        return exact_results

    remaining = limit

    # Deuxième passe : compléter avec des titres approchants.
    # Exclusion des résultats déjà sélectionnés.
    selected_ids = [article.page_id for article in exact_results]

    fuzzy_results = list(
        search_articles(
            queryset.exclude(page_id__in=selected_ids),
            query,
        )[:remaining]
    )

    return exact_results + fuzzy_results