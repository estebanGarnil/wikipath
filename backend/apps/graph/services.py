from django.core.cache import cache

from apps.core.neo4j import read_query


PATTERNS = {
    "out": "(p)-[:LINKS_TO]->(neighbor:Page)",
    "in": "(p)<-[:LINKS_TO]-(neighbor:Page)",
}


def get_page(page_id):
    rows = read_query(
        """
        MATCH (p:Page {page_id: $page_id})
        RETURN p { .page_id, .title, .namespace, .language } AS page
        """,
        {"page_id": page_id},
    )
    return rows[0]["page"] if rows else None


def get_neighbor_count(page_id, direction):
    key = f"graph-neighbor-total-v1:{page_id}:{direction}"
    total = cache.get(key)
    if total is not None:
        return total

    # Direction is selected from a fixed dictionary, never interpolated directly.
    pattern = PATTERNS[direction]
    rows = read_query(
        f"""
        MATCH (p:Page {{page_id: $page_id}})
        MATCH {pattern}
        WHERE neighbor.page_id > 0 AND neighbor <> p
        RETURN count(DISTINCT neighbor) AS total
        """,
        {"page_id": page_id},
    )
    total = rows[0]["total"]
    cache.set(key, total, timeout=3600)
    return total


def get_neighbors(page_id, direction, limit, after):
    pattern = PATTERNS[direction]
    rows = read_query(
        f"""
        MATCH (p:Page {{page_id: $page_id}})
        MATCH {pattern}
        WHERE neighbor.page_id > $after AND neighbor <> p
        WITH DISTINCT neighbor
        ORDER BY neighbor.page_id
        LIMIT $fetch_limit
        RETURN neighbor {{
            .page_id, .title, .namespace, .language
        }} AS page
        ORDER BY page.page_id
        """,
        {"page_id": page_id, "after": after, "fetch_limit": limit + 1},
    )
    has_more = len(rows) > limit
    neighbors = [row["page"] for row in rows[:limit]]
    return {
        "neighbors": neighbors,
        "has_more": has_more,
        "next_cursor": neighbors[-1]["page_id"] if has_more else None,
        "total_neighbors": get_neighbor_count(page_id, direction),
    }
