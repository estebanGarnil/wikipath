"""Encode every nodes.csv page with pilot V3; durable SQLite checkpoints.

Requires the ORIGINAL prepare_text.py used by the benchmark. Its SHA256 must
match metadata.json; it is deliberately not reimplemented here.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sqlite3
import sys
import time
import zlib

MODEL = "intfloat/multilingual-e5-small"
DIMENSIONS = 384
PREPARER = None


def log(message):
    print(message, flush=True)


def fingerprint(path):
    log(f"Verification SHA256 : {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def readonly(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def get_meta(db, name, default=None):
    row = db.execute("SELECT value FROM metadata WHERE name=?", (name,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(db, name, value):
    db.execute("INSERT OR REPLACE INTO metadata(name,value) VALUES (?,?)",
               (name, json.dumps(value, sort_keys=True)))


def load_preparer(path):
    global PREPARER
    sys.path.insert(0, str(Path(path).resolve().parent))
    spec = importlib.util.spec_from_file_location("wikipath_v3_preparer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    PREPARER = module.prepare


def prepare_one(item):
    page_id, title, revision, blob = item
    try:
        wikitext = zlib.decompress(bytes(blob)).decode("utf-8") if blob is not None else ""
        lead = PREPARER(wikitext, title)["introduction"][:6000] if wikitext else ""
        return page_id, revision, "query: " + title + "\n" + lead, not bool(lead)
    except Exception as exc:
        raise RuntimeError(f"Preparation impossible pour la page {page_id}: {exc}") from exc


def validate_vectors(vectors, expected):
    import numpy as np
    vectors = np.asarray(vectors, dtype="<f4")
    if vectors.shape != (expected, DIMENSIONS) or not np.isfinite(vectors).all():
        raise ValueError("Vecteurs invalides : dimensions ou valeurs non finies.")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-3):
        raise ValueError("Les vecteurs ne sont pas normalises.")
    return vectors


def save_vectors(db, prepared, vectors):
    vectors = validate_vectors(vectors, len(prepared))
    # Vectors AND checkpoint are committed together. A crash cannot advance only
    # the checkpoint. synchronous=FULL also requests durable filesystem writes.
    with db:
        updated = db.executemany(
            "UPDATE pages SET revision_id=?,vector=?,title_only=? WHERE page_id=?",
            [(row[1], vectors[i].tobytes(), int(row[3]), row[0]) for i, row in enumerate(prepared)],
        )
        if updated.rowcount != len(prepared):
            raise ValueError("Pages de sortie manquantes. Lot annule.")
        set_meta(db, "last_encoded_id", prepared[-1][0])
        set_meta(db, "encoded", get_meta(db, "encoded", 0) + len(prepared))
        set_meta(db, "title_only", get_meta(db, "title_only", 0) + sum(row[3] for row in prepared))


def load_nodes(db, path):
    if get_meta(db, "nodes_complete", False):
        return
    saved = get_meta(db, "nodes_loaded", 0)
    log(f"Chargement des titres ; reprise apres {saved:,} lignes.")
    batch = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"page_id:ID(Page)", "title"}.issubset(reader.fieldnames or []):
            raise ValueError("nodes.csv doit contenir page_id:ID(Page) et title.")
        for index, row in enumerate(reader, 1):
            if index <= saved:
                continue
            page_id = int(row["page_id:ID(Page)"])
            if not 0 < page_id < 2**63 or not row["title"].strip():
                raise ValueError(f"Noeud invalide a la ligne {index + 1}.")
            batch.append((page_id, row["title"]))
            if len(batch) == 10000:
                with db:
                    db.executemany("INSERT INTO pages(page_id,title) VALUES (?,?)", batch)
                    set_meta(db, "nodes_loaded", index)
                batch.clear()
                log(f"Titres sauvegardes : {index:,}")
        with db:
            if batch:
                db.executemany("INSERT INTO pages(page_id,title) VALUES (?,?)", batch)
            count = db.execute("SELECT count(*) FROM pages").fetchone()[0]
            if count == 0:
                raise ValueError("Le fichier de noeuds est vide.")
            set_meta(db, "nodes_loaded", count)
            set_meta(db, "nodes_complete", True)


def runtime_versions():
    return {name: importlib.metadata.version(name)
            for name in ("numpy", "torch", "sentence-transformers", "mwparserfromhell")}


def initialize(db, args):
    metadata = json.loads(args.reference_metadata.read_text(encoding="utf-8-sig"))
    revision = metadata.get("model_revision", "")
    if (metadata.get("model") != MODEL or len(revision) != 40
            or any(c not in "0123456789abcdef" for c in revision)
            or "v3" not in metadata.get("variants", {})):
        raise ValueError("Metadonnees du benchmark V1/V2/V3 attendues.")
    cleaner_hash = fingerprint(args.prepare)["sha256"]
    if cleaner_hash != metadata.get("preparation_sha256"):
        raise ValueError("prepare_text.py differe du preparateur V3 valide. Recuperer l'original du benchmark.")
    # Full hashes on every launch permit files to move to a different drive,
    # while preventing accidental resumes against a different dump.
    config = {"schema": 1, "model": MODEL, "model_revision": revision,
              "pipeline": "title-lead-v3-query-symmetric", "dimensions": DIMENSIONS,
              "max_tokens": 512, "preparation_sha256": cleaner_hash,
              "encoder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "nodes": fingerprint(args.nodes), "articles": fingerprint(args.articles),
              "runtime": runtime_versions()}
    previous = get_meta(db, "config")
    if previous is not None and previous != config:
        raise ValueError("Sources, modele ou dependances differents du calcul commence. Utiliser le meme environnement ou un autre fichier --output.")
    if previous is None:
        with db:
            set_meta(db, "config", config)
            digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
            set_meta(db, "version", "e5-full-v3:" + digest[:32])
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--articles", type=Path, required=True)
    parser.add_argument("--prepare", type=Path, required=True)
    parser.add_argument("--reference-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--checkpoint-pages", type=int, default=64)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-pages", type=int, help="Stop propre apres N articles supplementaires pour mesurer la vitesse.")
    args = parser.parse_args()
    if min(args.batch_size, args.checkpoint_pages, args.workers, args.max_pages or 1) < 1 or args.checkpoint_pages > 500:
        parser.error("Valeurs positives requises ; checkpoint-pages <= 500.")
    for path in (args.nodes, args.articles, args.prepare, args.reference_metadata):
        if not path.is_file():
            parser.error(f"Fichier absent : {path}")
    if args.output.resolve() in {args.nodes.resolve(), args.articles.resolve(), args.prepare.resolve(), args.reference_metadata.resolve()}:
        parser.error("La sortie ne peut pas remplacer une source.")
    import torch
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA indisponible. Installer PyTorch CUDA et verifier le pilote NVIDIA.")
    log(f"Materiel : {torch.cuda.get_device_name(0) if args.device == 'cuda' else 'CPU'}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # OS lock is released automatically on crash, unlike a stale lock file.
    lock = args.output.with_suffix(args.output.suffix + ".lock").open("a+b")
    lock.seek(0); lock.write(b"0"); lock.flush(); lock.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise RuntimeError("Un autre calcul utilise deja ce fichier de sortie.") from exc
    try:
        with sqlite3.connect(args.output) as db, readonly(args.articles) as articles:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS pages(page_id INTEGER PRIMARY KEY,title TEXT NOT NULL,revision_id INTEGER,vector BLOB,title_only INTEGER)")
            db.commit()
            config = initialize(db, args)
            load_nodes(db, args.nodes)
            if get_meta(db, "complete", False):
                log("Calcul deja termine : aucun article a recalculer.")
                return
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(MODEL, revision=config["model_revision"], device=args.device)
            model.float()
            model.max_seq_length = 512
            total = get_meta(db, "nodes_loaded")
            done_here = 0
            started = time.monotonic()
            with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn"), initializer=load_preparer,
                                     initargs=(str(args.prepare.resolve()),)) as pool:
                while args.max_pages is None or done_here < args.max_pages:
                    size = min(args.checkpoint_pages, args.max_pages - done_here) if args.max_pages else args.checkpoint_pages
                    pages = db.execute("SELECT page_id,title FROM pages WHERE page_id>? ORDER BY page_id LIMIT ?",
                                       (get_meta(db, "last_encoded_id", 0), size)).fetchall()
                    if not pages:
                        break
                    placeholders = ",".join("?" for _ in pages)
                    records = {row[0]: row[1:] for row in articles.execute(
                        f"SELECT page_id,revision_id,wikitext_zlib FROM articles WHERE page_id IN ({placeholders})",
                        [row[0] for row in pages])}
                    items = [(pid, title, *records.get(pid, (None, None))) for pid, title in pages]
                    prepared = list(pool.map(prepare_one, items, chunksize=1))
                    vectors = model.encode([row[2] for row in prepared], batch_size=args.batch_size,
                                           normalize_embeddings=True, convert_to_numpy=True,
                                           show_progress_bar=False)
                    save_vectors(db, prepared, vectors)
                    done_here += len(pages)
                    done = get_meta(db, "encoded")
                    rate = done_here / (time.monotonic() - started)
                    eta = (total - done) / rate / 3600
                    log(f"Sauvegarde : {done:,}/{total:,} articles | {rate:.2f}/s | reste estime {eta:.1f} h")
            if get_meta(db, "encoded", 0) == total:
                invalid = db.execute("SELECT count(*) FROM pages WHERE vector IS NULL OR length(vector) != ?",
                                     (DIMENSIONS * 4,)).fetchone()[0]
                if invalid:
                    raise ValueError(f"{invalid} vecteurs incomplets. Ne pas importer ce fichier.")
                with db:
                    set_meta(db, "complete", True)
                log(f"TERMINE : {total:,} articles. Fichier a transferer : {args.output}")
            else:
                log("Pause sauvegardee. Relancer la meme commande sans --max-pages pour continuer.")
    finally:
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interruption : les lots deja valides sont conserves. Relancer la meme commande.")
        raise SystemExit(130)
