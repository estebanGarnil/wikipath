"""Compare legacy MiniLM titles, E5 titles and existing E5 V3 on ALL edges."""
import argparse
import csv
import hashlib
import html
import json
import math
import re
import time
from collections import defaultdict
from pathlib import Path

E5 = "intfloat/multilingual-e5-small"
MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
LABELS = {
    "minilm_title": "MiniLM · titre seul (ancienne méthode)",
    "e5_title": "E5 · titre seul",
    "e5_v3": "E5 · titre + introduction (V3 existante)",
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_reference(directory):
    paths = {name: directory / name for name in ("metadata.json", "texts.jsonl", "scores.csv")}
    metadata = json.loads(paths["metadata.json"].read_text(encoding="utf-8-sig"))
    if metadata.get("model") != E5 or not re.fullmatch(r"[0-9a-f]{40}", metadata.get("model_revision") or ""):
        raise ValueError("Reference must contain E5-small and its pinned model revision.")
    if "v3" not in metadata.get("variants", {}):
        raise ValueError("Reference has no V3 variant.")
    titles = {}
    with paths["texts.jsonl"].open(encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.strip():
                continue
            page = json.loads(line)
            page_id, title = int(page["page_id"]), page["title"]
            if page_id <= 0 or page_id in titles or not isinstance(title, str) or not title.strip():
                raise ValueError("Invalid/duplicate page ID or empty title.")
            titles[page_id] = title
    if len(titles) != metadata["pages"] or set(map(str, titles)) != set(metadata["source_revisions"]):
        raise ValueError("Page IDs/count do not match reference metadata.")
    scores, recorded_ranks = {}, defaultdict(list)
    with paths["scores.csv"].open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["variant"] != "v3":
                continue
            key = (int(row["source_id"]), int(row["target_id"]))
            score = float(row["semantic_score"])
            if key in scores or any(pid not in titles for pid in key) or key[0] == key[1]:
                raise ValueError("Duplicate edge, missing page or self-link in reference.")
            if not math.isfinite(score) or not -1.00001 <= score <= 1.00001:
                raise ValueError("Invalid reference cosine score.")
            if row["title"] != titles[key[1]]:
                raise ValueError("Title mismatch between scores.csv and texts.jsonl.")
            scores[key] = score
            recorded_ranks[key[0]].append((int(row["rank"]), key[1]))
    if not scores or len(scores) != metadata["links"]:
        raise ValueError("Edge count does not match reference metadata.")
    ranked = rank_scores(scores)
    for source, rows in ranked.items():
        expected = [(i, target) for i, (target, _) in enumerate(rows, 1)]
        if sorted(recorded_ranks[source]) != expected:
            raise ValueError("Reference rank differs from cosine DESC, target ID ASC.")
    return metadata, titles, scores, {name: sha256(path) for name, path in paths.items()}


def rank_scores(scores):
    result = defaultdict(list)
    for (source, target), score in scores.items():
        result[source].append((target, score))
    return {source: sorted(rows, key=lambda row: (-row[1], row[0]))
            for source, rows in sorted(result.items())}


def title_inputs(titles, model_key):
    # Legacy batch code used original case and no prefix. E5 keeps query: on both sides.
    prefix = "query: " if model_key == "e5_title" else ""
    return [prefix + titles[pid] for pid in sorted(titles)]


def write_results(output, variants, titles):
    rankings = {name: rank_scores(scores) for name, scores in variants.items()}
    edges = set(variants["e5_v3"])
    if any(set(scores) != edges for scores in variants.values()):
        raise ValueError("Variants must rank exactly the same edges.")
    rank_maps = {name: {(source, target): i
                        for source, rows in ranking.items()
                        for i, (target, _) in enumerate(rows, 1)}
                 for name, ranking in rankings.items()}
    with (output / "scores.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["variant", "source_id", "target_id", "rank", "cosine_score", "legacy_score_0_1", "title"])
        for name, ranking in rankings.items():
            for source, rows in ranking.items():
                for rank, (target, score) in enumerate(rows, 1):
                    writer.writerow([name, source, target, rank, repr(score),
                                     repr((score + 1) / 2) if name == "minilm_title" else "", titles[target]])
    with (output / "evaluation.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["source_id", "source_title", "target_id", "title",
                         *["rank_" + name for name in LABELS], "pertinence_0_1_2", "commentaire"])
        for source, target in sorted(edges):
            writer.writerow([source, titles[source], target, titles[target],
                             *[rank_maps[name][source, target] for name in LABELS], "", ""])
    report = ["<!doctype html><html lang='fr'><meta charset='utf-8'>",
              "<meta name='viewport' content='width=device-width, initial-scale=1'>",
              "<title>Wikipath — comparaison des modèles sur les titres</title>",
              "<style>body{font:15px/1.5 system-ui;color:#202122;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:9px;vertical-align:top}th{background:#f5f5f5}small{display:block;color:#555}.scroll{overflow:auto}h2{margin-top:40px}.boundary td{border-top:3px solid #555}nav{display:flex;gap:16px;flex-wrap:wrap}a{color:inherit}</style>",
              "<h1>MiniLM et E5 : titres seuls ou introduction</h1>",
              "<p>Mêmes pages et mêmes liens pour chaque classement. Tous les voisins sont classés ; les 60 premiers sont affichés. Les séparations marquent les lots de 20.</p>",
              "<p>Comparez la pertinence des voisins, pas les valeurs des scores entre modèles. Aucun filtre ni pénalité d’homonymie n’est appliqué. La V3 est réutilisée sans nouvel encodage.</p>",
              "<p>MiniLM reproduit la méthode de l’ancien code sur notre graphe complet, avec une révision désormais enregistrée. La révision utilisée autrefois n’était pas fixée.</p>",
              "<nav>" + "".join(f"<a href='#p{source}'>" + html.escape(titles[source]) + "</a>"
                                  for source in rankings["e5_v3"]) + "</nav>"]
    for source, rows in rankings["e5_v3"].items():
        report.append(f"<h2 id='p{source}'>" + html.escape(titles[source]) + f" — {len(rows)} voisins</h2>")
        report.append("<div class='scroll'><table><thead><tr><th>Rang</th>" +
                      "".join("<th>" + html.escape(label) + "</th>" for label in LABELS.values()) + "</tr></thead><tbody>")
        for index in range(min(60, len(rows))):
            css = " class='boundary'" if index in (20, 40) else ""
            report.append(f"<tr{css}><td>{index + 1}</td>")
            for name in LABELS:
                target, score = rankings[name][source][index]
                report.append("<td>" + html.escape(titles[target]) + f"<small>cosinus {score:.4f} · ID {target}</small></td>")
            report.append("</tr>")
        report.append("</tbody></table></div>")
    report.append("</html>")
    (output / "report.html").write_text("\n".join(report), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Existing semantic-benchmark-results directory")
    parser.add_argument("--output", type=Path, default=Path("semantic-title-results"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists: choose a new directory to preserve results.")
    if args.batch_size <= 0:
        parser.error("Batch size must be positive.")
    try:
        reference, titles, v3, fingerprints = load_reference(args.reference)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))

    import numpy as np
    import torch
    from huggingface_hub import model_info
    from sentence_transformers import SentenceTransformer

    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA unavailable: use --device cpu.")
    # Resolve the exact MiniLM revision once, then pin both model loads.
    mini_revision = model_info(MINILM).sha
    if not re.fullmatch(r"[0-9a-f]{40}", mini_revision or ""):
        parser.error("Could not resolve the MiniLM revision.")
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    metadata = {
        "pipeline": "title-model-comparison-v1", "device": args.device,
        "pages": len(titles), "links": len(v3), "batch_size": args.batch_size,
        "reference_sha256": fingerprints, "models": {},
        "v3_reused": True, "e5_reference_revision": reference["model_revision"],
        "source_revisions": reference["source_revisions"],
        "status": "running",
    }
    meta_path = args.output / "metadata.json"

    def save_metadata():
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    save_metadata()
    ids = sorted(titles)
    lookup = {pid: i for i, pid in enumerate(ids)}
    variants = {}
    for name, model_id, revision in (
        ("minilm_title", MINILM, mini_revision),
        ("e5_title", E5, reference["model_revision"]),
    ):
        print(f"Loading {model_id} at {revision}", flush=True)
        before_load = time.perf_counter()
        model = SentenceTransformer(model_id, revision=revision, device=args.device)
        if name == "e5_title":
            model.max_seq_length = 512
        values = title_inputs(titles, name)
        truncated = sum(len(model.tokenizer(value, truncation=False)["input_ids"]) > model.max_seq_length
                        for value in values)
        before_encode = time.perf_counter()
        vectors = model.encode(values, batch_size=args.batch_size, normalize_embeddings=True,
                               convert_to_numpy=True, show_progress_bar=True)
        after_encode = time.perf_counter()
        if not np.isfinite(vectors).all():
            raise ValueError("Model produced non-finite vectors.")
        # Keep reusable vectors: no need to rerun models for future score combinations.
        np.savez_compressed(args.output / (name + "_embeddings.npz"),
                            page_ids=np.asarray(ids, dtype=np.int64), embeddings=vectors)
        variants[name] = {(source, target): float(np.dot(vectors[lookup[source]], vectors[lookup[target]]))
                          for source, target in v3}
        metadata["models"][name] = {
            "model": model_id, "revision": revision, "max_tokens": model.max_seq_length,
            "prefix": "query: " if name == "e5_title" else "",
            "dimensions": int(vectors.shape[1]), "truncated_titles": truncated,
            "load_and_audit_seconds": before_encode - before_load,
            "encoding_seconds": after_encode - before_encode,
        }
        save_metadata()
        del model, vectors
        if args.device == "cuda":
            torch.cuda.empty_cache()
    variants["e5_v3"] = v3
    write_results(args.output, variants, titles)
    metadata.update(status="complete", total_seconds=time.perf_counter() - started)
    save_metadata()
    print("Done:", args.output / "report.html")


if __name__ == "__main__":
    main()
