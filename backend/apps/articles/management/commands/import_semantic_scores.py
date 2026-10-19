"""Import transactionnel du pilote E5 V3 ; verification seule par defaut."""
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.neo4j import get_driver


PILOT_SOURCES = {3, 7, 9, 1095, 2340, 6742, 25828, 2480198, 4154181, 4493780}


def load_scores(csv_path, metadata_path):
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8-sig"))
    if metadata.get("model") != "intfloat/multilingual-e5-small":
        raise ValueError("Le fichier ne correspond pas au pilote E5 small.")
    if "v3" not in metadata.get("variants", {}) or not metadata.get("model_revision"):
        raise ValueError("Variante V3 ou revision du modele absente.")
    pairs = {}
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"variant", "source_id", "target_id", "semantic_score"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Colonnes CSV manquantes.")
        for line, row in enumerate(reader, start=2):
            if row["variant"] != "v3":
                continue
            source, target = int(row["source_id"]), int(row["target_id"])
            score = float(row["semantic_score"])
            if not (0 < source <= 9223372036854775807 and 0 < target <= 9223372036854775807):
                raise ValueError(f"Identifiant invalide, ligne {line}.")
            if source == target or not math.isfinite(score) or not -1 <= score <= 1:
                raise ValueError(f"Score ou lien invalide, ligne {line}.")
            if (source, target) in pairs:
                raise ValueError(f"Lien V3 duplique, ligne {line}.")
            pairs[source, target] = score
    if {source for source, _ in pairs} != PILOT_SOURCES:
        raise ValueError("Les sources ne correspondent pas aux dix pages du pilote.")
    if len(pairs) != metadata.get("links"):
        raise ValueError("Nombre de liens V3 different des metadonnees.")
    rows = [dict(source=s, target=t, score=score) for (s, t), score in sorted(pairs.items())]
    provenance = {
        "model": metadata["model"], "revision": metadata["model_revision"],
        "preparation": metadata.get("preparation_sha256"), "variant": "v3", "rows": rows,
    }
    digest = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
    return rows, metadata, "e5-v3:" + digest


def import_transaction(tx, rows, metadata, version, apply):
    expected = defaultdict(set)
    for row in rows:
        expected[row["source"]].add(row["target"])
    actual = defaultdict(set)
    relationships = 0
    records = tx.run(
        """
        UNWIND $sources AS source_id
        MATCH (p:Page {page_id: source_id})-[r:LINKS_TO]->(n:Page)
        WHERE n <> p AND n.page_id > 0
        RETURN p.page_id AS source, n.page_id AS target,
               r.semantic_score AS score, r.semantic_version AS version
        """, sources=sorted(expected),
    )
    for record in records:
        actual[record["source"]].add(record["target"])
        relationships += 1
        if (record["score"] is not None or record["version"] is not None) and record["version"] != version:
            raise ValueError("Des relations ont deja une autre version semantique. Aucun remplacement automatique.")
    for source, targets in expected.items():
        missing = targets - actual[source]
        extra = actual[source] - targets
        if missing or extra:
            raise ValueError(
                f"Page {source}: {len(missing)} liens du CSV absents du graphe, "
                f"{len(extra)} voisins du graphe absents du CSV. Import annule."
            )
    if apply:
        updated = 0
        for start in range(0, len(rows), 1000):
            record = tx.run(
                """
                UNWIND $rows AS row
                MATCH (:Page {page_id: row.source})-[r:LINKS_TO]->(:Page {page_id: row.target})
                SET r.semantic_score = row.score,
                    r.semantic_version = $version,
                    r.semantic_model = $model,
                    r.semantic_model_revision = $revision
                RETURN count(r) AS updated
                """, rows=rows[start:start + 1000], version=version,
                model=metadata["model"], revision=metadata["model_revision"],
            ).single()
            updated += record["updated"]
        if updated != relationships:
            raise ValueError("Nombre de relations modifiees inattendu. Transaction annulee.")
        tx.run(
            """
            UNWIND $pages AS page
            MATCH (p:Page {page_id: page.id})
            SET p.semantic_out_version = $version,
                p.semantic_out_neighbor_count = page.total
            """, pages=[{"id": s, "total": len(t)} for s, t in sorted(expected.items())],
            version=version,
        ).consume()
    return {source: len(targets) for source, targets in sorted(expected.items())}, relationships


class Command(BaseCommand):
    help = "Verifie les scores E5 V3 des dix pages ; --apply les enregistre dans Neo4j."

    def add_arguments(self, parser):
        parser.add_argument("--scores", required=True)
        parser.add_argument("--metadata", required=True)
        parser.add_argument("--database", default=getattr(settings, "NEO4J_DATABASE", "neo4j"))
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        try:
            rows, metadata, version = load_scores(options["scores"], options["metadata"])
            with get_driver().session(database=options["database"]) as session:
                execute = session.execute_write if options["apply"] else session.execute_read
                counts, relationships = execute(
                    import_transaction, rows, metadata, version, options["apply"],
                )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(str(exc)) from exc
        for source, total in counts.items():
            self.stdout.write(f"Page {source}: {total} voisins verifies")
        mode = "Import termine" if options["apply"] else "Verification seule : aucune ecriture"
        self.stdout.write(self.style.SUCCESS(
            f"{mode}. {len(counts)} pages, {len(rows)} paires, {relationships} relations."
        ))
        self.stdout.write(f"Version : {version}")
