from apps.core.neo4j import read_query


def get_page(page_id):
    rows = read_query(
        """
        MATCH (p:Page {page_id: $page_id})
        RETURN p {
            .page_id,
            .title,
            .namespace,
            .language
        } AS page
        """,
        {"page_id": page_id},
    )

    return rows[0]["page"] if rows else None


def get_neighbors(page_id, direction, limit, after):
    patterns = {
        "out": "(p)-[:LINKS_TO]->(neighbor:Page)",
        "in": "(p)<-[:LINKS_TO]-(neighbor:Page)",
    }

    # Le fragment vient uniquement de ce dictionnaire.
    # Les valeurs fournies par le client restent paramétrées.
    pattern = patterns[direction]

    rows = read_query(
        f"""
        MATCH (p:Page {{page_id: $page_id}})
        MATCH {pattern}
        WHERE neighbor.page_id > $after
        WITH DISTINCT neighbor
        ORDER BY neighbor.page_id
        LIMIT $fetch_limit
        RETURN neighbor {{
            .page_id,
            .title,
            .namespace,
            .language
        }} AS page
        ORDER BY page.page_id
        """,
        {
            "page_id": page_id,
            "after": after,
            "fetch_limit": limit + 1,
        },
    )

    has_more = len(rows) > limit
    neighbors = [row["page"] for row in rows[:limit]]

    return {
        "neighbors": neighbors,
        "has_more": has_more,
        "next_cursor": (
            neighbors[-1]["page_id"] if has_more else None
        ),
    }