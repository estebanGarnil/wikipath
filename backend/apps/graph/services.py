import math

from django.core import signing
from django.core.cache import cache
from rest_framework.exceptions import APIException, ValidationError

from apps.core.neo4j import read_query


PATTERNS = {
    "out": "(p)-[:LINKS_TO]->(neighbor:Page)",
    "in": "(p)<-[:LINKS_TO]-(neighbor:Page)",
}
CURSOR_SALT = "wikipath.graph.neighbors.v1"
MAX_ID = 9223372036854775807


class GraphOrderChanged(APIException):
    status_code = 409
    default_detail = "Le classement a changé. Rechargez la page pour recommencer l’exploration."
    default_code = "graph_order_changed"


def get_page(page_id):
    rows = read_query(
        """
        MATCH (p:Page {page_id: $page_id})
        RETURN p { .page_id, .title, .namespace, .language } AS page
        """, {"page_id": page_id},
    )
    return rows[0]["page"] if rows else None


def get_neighbor_count(page_id, direction):
    key = f"graph-neighbor-total-v1:{page_id}:{direction}"
    total = cache.get(key)
    if total is not None:
        return total
    pattern = PATTERNS[direction]
    rows = read_query(
        f"""
        MATCH (p:Page {{page_id: $page_id}})
        MATCH {pattern}
        WHERE neighbor.page_id > 0 AND neighbor <> p
        RETURN count(DISTINCT neighbor) AS total
        """, {"page_id": page_id},
    )
    total = rows[0]["total"]
    cache.set(key, total, timeout=3600)
    return total


def get_order(page_id, direction):
    # An outgoing pilot marker says nothing about coverage of incoming links.
    if direction != "out":
        return "page_id", None, None
    rows = read_query(
        """
        MATCH (p:Page {page_id: $page_id})
        WHERE p.semantic_out_version IS NOT NULL
        OPTIONAL MATCH (p)-[r:LINKS_TO]->(n:Page)
        WHERE n.page_id > 0 AND n <> p
        RETURN p.semantic_out_version AS version,
               p.semantic_out_neighbor_count AS expected,
               count(DISTINCT n) AS total, count(r) AS relationships,
               count(CASE WHEN (p.semantic_out_storage = 'page-v1' OR r.semantic_version = p.semantic_out_version)
                          AND r.semantic_score >= -1 AND r.semantic_score <= 1
                     THEN 1 END) AS scored
        """, {"page_id": page_id},
    )
    if not rows:
        return "page_id", None, None
    state = rows[0]
    if (state["version"] and state["expected"] == state["total"]
            and state["relationships"] == state["scored"]):
        return "semantic", state["version"], state["total"]
    # Never silently hide unscored neighbors in a partially scored page.
    return "page_id", None, state["total"]


def decode_cursor(after, page_id, direction, order, version):
    token = str(after)
    if token == "0":
        return 0, None
    # Compatibility with old clients on pages still ordered by ID.
    if token.isascii() and token.isdigit():
        last_id = int(token)
        if not 0 < last_id <= MAX_ID:
            raise ValidationError({"after": "Identifiant invalide."})
        if order != "page_id":
            raise GraphOrderChanged()
        return last_id, None
    try:
        payload = signing.loads(token, salt=CURSOR_SALT)
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            raise ValueError
        if payload.get("page") != page_id or payload.get("direction") != direction:
            raise ValueError
        last_id = payload.get("id")
        score = payload.get("score")
        if type(last_id) is not int or not 0 < last_id <= MAX_ID:
            raise ValueError
        if payload.get("order") not in {"semantic", "page_id"}:
            raise ValueError
        if payload["order"] == "semantic":
            if type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1:
                raise ValueError
        elif score is not None:
            raise ValueError
    except (signing.BadSignature, ValueError, TypeError, OverflowError) as exc:
        raise ValidationError({"after": "Curseur invalide pour cette page et cette direction."}) from exc
    if payload["order"] != order or payload.get("version") != version:
        raise GraphOrderChanged()
    return last_id, score


def get_neighbors(page_id, direction, limit, after):
    order, version, total = get_order(page_id, direction)
    last_id, last_score = decode_cursor(after, page_id, direction, order, version)
    params = {"page_id": page_id, "after": last_id, "fetch_limit": limit + 1}
    if order == "semantic":
        params.update(version=version, after_score=last_score)
        rows = read_query(
            """
            MATCH (p:Page {page_id: $page_id})-[r:LINKS_TO]->(neighbor:Page)
            WHERE neighbor.page_id > 0 AND neighbor <> p
              AND p.semantic_out_version = $version
              AND (p.semantic_out_storage = 'page-v1' OR r.semantic_version = $version)
            WITH neighbor, max(r.semantic_score) AS score
            WHERE $after_score IS NULL OR score < $after_score
               OR (score = $after_score AND neighbor.page_id > $after)
            WITH neighbor, score
            ORDER BY score DESC, neighbor.page_id ASC
            LIMIT $fetch_limit
            RETURN neighbor { .page_id, .title, .namespace, .language } AS page, score
            ORDER BY score DESC, page.page_id ASC
            """, params,
        )
    else:
        pattern = PATTERNS[direction]
        rows = read_query(
            f"""
            MATCH (p:Page {{page_id: $page_id}})
            MATCH {pattern}
            WHERE neighbor.page_id > $after AND neighbor <> p
            WITH DISTINCT neighbor
            ORDER BY neighbor.page_id
            LIMIT $fetch_limit
            RETURN neighbor {{ .page_id, .title, .namespace, .language }} AS page,
                   null AS score
            ORDER BY page.page_id
            """, params,
        )
    has_more = len(rows) > limit
    retained = rows[:limit]
    cursor = None
    if has_more:
        last = retained[-1]
        cursor = signing.dumps({
            "schema": 1, "page": page_id, "direction": direction,
            "order": order, "version": version,
            "id": last["page"]["page_id"], "score": last["score"],
        }, salt=CURSOR_SALT)
    return {
        "neighbors": [row["page"] for row in retained],
        "scores": {row["page"]["page_id"]: row["score"] for row in retained},
        "has_more": has_more, "next_cursor": cursor,
        "total_neighbors": total if total is not None else get_neighbor_count(page_id, direction),
        "order": order,
    }
