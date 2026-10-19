"""Compute edge cosines on CPU and import complete pages with atomic progress."""
import json
import math
from collections import OrderedDict
from pathlib import Path
import sqlite3
import time

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.neo4j import get_driver


DIMENSIONS = 384


class VectorStore:
    def __init__(self, path, allow_partial=False):
        self.db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            self.metadata = {name: json.loads(value) for name, value in self.db.execute("SELECT name,value FROM metadata")}
            self.config = self.metadata["config"]
            if (self.config.get("schema") != 1 or self.config.get("dimensions") != DIMENSIONS
                    or self.config.get("pipeline") != "title-lead-v3-query-symmetric"):
                raise ValueError("Format de vecteurs incompatible.")
            if not self.metadata.get("complete") and not allow_partial:
                raise ValueError("Encodage incomplet. Terminer encode_full.py avant l'import.")
            self.version = self.metadata["version"]
            self.cache = OrderedDict()
        except Exception:
            self.db.close()
            raise

    def get_many(self, ids):
        ids = list(dict.fromkeys(ids))
        found = {}
        missing = []
        for pid in ids:
            if pid in self.cache:
                found[pid] = self.cache[pid]
                self.cache.move_to_end(pid)
            else:
                missing.append(pid)
        for start in range(0, len(missing), 500):
            part = missing[start:start + 500]
            sql = "SELECT page_id,vector FROM pages WHERE page_id IN (" + ",".join("?" for _ in part) + ")"
            for pid, blob in self.db.execute(sql, part):
                if blob is None or len(blob) != 4 * DIMENSIONS:
                    raise ValueError(f"Vecteur absent/incomplet pour {pid}.")
                vector = np.frombuffer(blob, dtype="<f4")
                if not np.isfinite(vector).all() or not math.isclose(float(np.linalg.norm(vector)), 1, abs_tol=1e-3):
                    raise ValueError(f"Vecteur invalide pour {pid}.")
                found[pid] = vector
                self.cache[pid] = vector
                while len(self.cache) > 25000:
                    self.cache.popitem(last=False)
        absent = set(ids) - found.keys()
        if absent:
            raise ValueError(f"{len(absent)} pages du graphe sans vecteur, exemple {min(absent)}. Lot annule.")
        return found

    def score_page(self, source, targets):
        source_vector = self.get_many([source])[source]
        result = {}
        for start in range(0, len(targets), 2048):
            part = targets[start:start + 2048]
            vectors = self.get_many(part)
            matrix = np.stack([vectors[pid] for pid in part])
            values = np.clip(np.einsum("ij,j->i", matrix, source_vector), -1, 1)
            result.update((str(pid), float(score)) for pid, score in zip(part, values))
        return result

    def close(self):
        self.db.close()


def fetch_pages(tx, after, limit):
    return [dict(row) for row in tx.run(
        """
        MATCH (p:Page) WHERE p.page_id > $after
        WITH p ORDER BY p.page_id LIMIT $limit
        OPTIONAL MATCH (p)-[:LINKS_TO]->(n:Page)
        WHERE n.page_id > 0 AND n <> p
        RETURN p.page_id AS page_id, collect(DISTINCT n.page_id) AS targets
        ORDER BY page_id
        """, after=after, limit=limit,
    )]


def open_run(tx, version, config):
    row = tx.run(
        """
        MERGE (run:WikipathSemanticRun {run_id: $version})
        ON CREATE SET run.last_page_id = 0, run.pages_done = 0,
                      run.edges_done = 0, run.complete = false,
                      run.config_json = $config, run.created_at = datetime()
        RETURN run.last_page_id AS last_id, run.pages_done AS pages_done,
               run.edges_done AS edges_done, run.complete AS complete,
               run.config_json AS config
        """, version=version, config=json.dumps(config, sort_keys=True),
    ).single()
    if row["config"] != json.dumps(config, sort_keys=True):
        raise ValueError("Configuration differente pour cette version.")
    return dict(row)


def lock_run(tx, version, expected_last):
    row = tx.run(
        """
        MATCH (run:WikipathSemanticRun {run_id: $version})
        SET run.lock_counter = coalesce(run.lock_counter, 0) + 1
        RETURN run.last_page_id AS last_id
        """, version=version,
    ).single()
    if row is None or row["last_id"] != expected_last:
        raise ValueError("Le point de reprise a change (autre import actif). Relancer un seul import.")


def write_batch(tx, version, previous_id, pages):
    lock_run(tx, version, previous_id)
    # One expansion per source, not one adjacency search for every source/target
    # pair. Every write AND the run checkpoint share this transaction.
    records = list(tx.run(
        """
        UNWIND $pages AS page
        MATCH (p:Page {page_id: page.id})
        USING INDEX p:Page(page_id)
        OPTIONAL MATCH (p)-[r:LINKS_TO]->(n:Page)
        WHERE n.page_id > 0 AND n <> p
        FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END |
            SET r.semantic_score = page.scores[toString(n.page_id)]
            REMOVE r.semantic_version, r.semantic_model, r.semantic_model_revision
        )
        WITH p, page, count(DISTINCT n) AS actual,
             count(DISTINCT CASE WHEN page.scores[toString(n.page_id)] IS NOT NULL THEN n END) AS matched,
             count(r) AS relationships
        SET p.semantic_out_version = $version,
            p.semantic_out_storage = 'page-v1',
            p.semantic_out_neighbor_count = page.total
        RETURN p.page_id AS page_id, actual, matched, relationships
        """, pages=pages, version=version,
    ))
    expected = {page["id"]: page["total"] for page in pages}
    if len(records) != len(expected) or {r["page_id"] for r in records} != set(expected):
        raise ValueError("Pages du graphe manquantes ou identifiants dupliques. Transaction annulee.")
    for row in records:
        if row["actual"] != expected[row["page_id"]] or row["matched"] != row["actual"]:
            raise ValueError(f"Voisins modifies pendant le calcul pour {row['page_id']}. Transaction annulee.")
    count = sum(r["relationships"] for r in records)
    tx.run(
        """
        MATCH (run:WikipathSemanticRun {run_id: $version})
        SET run.last_page_id = $last_id, run.pages_done = run.pages_done + $pages,
            run.edges_done = run.edges_done + $edges, run.updated_at = datetime()
        """, version=version, last_id=pages[-1]["id"], pages=len(pages), edges=count,
    ).consume()
    return count


def finish_run(tx, version, last_id):
    lock_run(tx, version, last_id)
    tx.run("MATCH (r:WikipathSemanticRun {run_id:$version}) SET r.complete=true, r.updated_at=datetime()",
           version=version).consume()


class Command(BaseCommand):
    help = "Calcule/import les scores V3 par pages completes, avec reprise transactionnelle dans Neo4j."

    def add_arguments(self, parser):
        parser.add_argument("--vectors", required=True)
        parser.add_argument("--pages-per-batch", type=int, default=20)
        parser.add_argument("--max-pages", type=int)
        parser.add_argument("--check-only", action="store_true")
        parser.add_argument("--database", default=getattr(settings, "NEO4J_DATABASE", "neo4j"))

    def handle(self, *args, **options):
        size = options["pages_per_batch"]
        maximum = options["max_pages"]
        if not 1 <= size <= 200 or (maximum is not None and maximum < 1):
            raise CommandError("pages-per-batch doit etre entre 1 et 200 ; max-pages positif.")
        if options["check_only"] and maximum is None:
            maximum = 20
        path = Path(options["vectors"])
        if not path.is_file():
            raise CommandError(f"Fichier absent : {path}")
        store = None
        try:
            store = VectorStore(path)
            # Limit BLAS thread overhead on small vectors using numpy einsum.
            with get_driver().session(database=options["database"]) as session:
                if options["check_only"]:
                    state = dict(last_id=0, pages_done=0, edges_done=0, complete=False)
                else:
                    session.run("CREATE CONSTRAINT wikipath_semantic_run_id IF NOT EXISTS FOR (r:WikipathSemanticRun) REQUIRE r.run_id IS UNIQUE").consume()
                    state = session.execute_write(open_run, store.version, store.config)
                self.stdout.write(f"Version {store.version} | reprise apres ID {state['last_id']} | {state['pages_done']:,} pages deja importees")
                if state["complete"]:
                    self.stdout.write(self.style.SUCCESS("Import deja termine pour cette version."))
                    return
                done_here = 0
                started = time.monotonic()
                while maximum is None or done_here < maximum:
                    take = min(size, maximum - done_here) if maximum else size
                    graph_pages = session.execute_read(fetch_pages, state["last_id"], take)
                    if not graph_pages:
                        if not options["check_only"]:
                            session.execute_write(finish_run, store.version, state["last_id"])
                        self.stdout.write(self.style.SUCCESS("Toutes les pages du graphe ont ete traitees."))
                        break
                    pages = []
                    for page in graph_pages:
                        scores = store.score_page(page["page_id"], page["targets"])
                        pages.append({"id": page["page_id"], "scores": scores, "total": len(scores)})
                    if options["check_only"]:
                        count = sum(p["total"] for p in pages)
                    else:
                        count = session.execute_write(write_batch, store.version, state["last_id"], pages)
                    state["last_id"] = pages[-1]["id"]
                    state["pages_done"] += len(pages)
                    state["edges_done"] += count
                    done_here += len(pages)
                    mode = "VERIFIE, sans ecriture" if options["check_only"] else "SAUVEGARDE"
                    rate = done_here / (time.monotonic() - started)
                    self.stdout.write(f"{mode}: {state['pages_done']:,} pages | {state['edges_done']:,} liens | dernier ID {state['last_id']} | {rate:.1f} pages/s")
                    self.stdout.flush()
                else:
                    self.stdout.write("Limite demandee atteinte. Reprise automatique a la prochaine execution.")
        except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        finally:
            if store is not None:
                store.close()
