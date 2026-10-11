"""Offline link-context pilot. Download weights separately; no remote inference."""
import argparse
import csv
import gzip
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from urllib.parse import unquote

from compare_title_models import load_reference, sha256

MODEL = "BAAI/bge-reranker-v2-m3"
PIPELINE = "link-context-v1"
LABELS = {
    "v3": "E5 V3",
    "position": "Emplacement du lien",
    "cross_plain": "Cross-encoder sans contexte",
    "cross_context": "Cross-encoder avec contexte",
}


def norm_title(title):
    title = unicodedata.normalize("NFC", unquote(title).replace("_", " "))
    title = re.sub(r"\s+", " ", title.split("#", 1)[0]).strip().lstrip(":")
    return title[:1].upper() + title[1:]


def clean_code(code):
    import mwparserfromhell as mw
    code = mw.parse(str(code))
    # No expansion: explicit links inside these elements are not treated as body prose.
    for node in list(code.filter_templates(recursive=False)) + list(code.filter_tags(recursive=False)):
        if isinstance(node, mw.nodes.Template) or str(node.tag).lower() in {
            "ref", "references", "gallery", "table", "math", "timeline", "nowiki", "pre", "source", "syntaxhighlight"
        }:
            try:
                code.remove(node)
            except ValueError:
                pass
    for node in list(code.filter_wikilinks()):
        if norm_title(str(node.title)).split(":", 1)[0].lower() in {"image", "fichier", "file", "catégorie", "category"}:
            try:
                code.remove(node)
            except ValueError:
                pass
    return code


def extract_contexts(wikitext, targets, lookup):
    """Explicit local wikilinks only. Missing evidence is not evidence of absence."""
    import mwparserfromhell as mw
    found = {pid: {"contexts": [], "mentions": 0} for pid in targets}
    unmatched = set()
    code = clean_code(wikitext)
    for section_index, section in enumerate(code.get_sections(flat=True, include_lead=True)):
        headings = section.filter_headings()
        heading = str(headings[0].title).strip() if headings else "Introduction"
        text = str(section)
        text = re.sub(r"(?m)^={2,6}.*?={2,6}\s*$", "", text)
        for paragraph_index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
            parsed = mw.parse(paragraph)
            links = list(parsed.filter_wikilinks())
            is_list = bool(re.search(r"(?m)^\s*[*#;:]", paragraph))
            location = "list" if is_list else ("lead" if section_index == 0 else "body")
            for link in links:
                raw_title = str(link.title)
                if not raw_title.strip() or raw_title.lstrip().startswith("#"):
                    continue
                normalized = norm_title(raw_title)
                target = lookup.get(normalized)
                if target not in targets:
                    if target is None:
                        unmatched.add(normalized)
                    continue
                item = found[target]
                item["mentions"] += 1
                # Put a marker at this occurrence to keep the target inside the excerpt.
                marker = "WIKIPATHLINKMARKER"
                fragment = mw.parse(paragraph.replace(str(link), marker + str(link), 1))
                plain = re.sub(r"\s+", " ", fragment.strip_code()).strip()
                offset = plain.find(marker)
                if offset < 0:
                    continue
                plain = plain.replace(marker, "", 1)
                excerpt = plain[max(0, offset - 300):offset + 600].strip()
                context = {"location": location, "section": heading,
                           "section_index": section_index, "paragraph_index": paragraph_index,
                           "text": excerpt, "link_title": raw_title}
                # Keep up to two earliest contexts of each class. Entire edge set is retained.
                same = [c for c in item["contexts"] if c["location"] == location]
                if len(same) < 2 and not any(c["text"] == excerpt for c in item["contexts"]):
                    item["contexts"].append(context)
    order = {"lead": 0, "body": 1, "list": 2}
    for item in found.values():
        item["contexts"].sort(key=lambda c: (order[c["location"]], c["section_index"], c["paragraph_index"]))
        item["contexts"] = item["contexts"][:2]
        item["status"] = item["contexts"][0]["location"] if item["contexts"] else "not_found"
    return found, sorted(unmatched)


def prepare(args):
    if args.output.exists():
        raise ValueError("Output exists; choose a new prepared directory.")
    ref, titles, scores, hashes = load_reference(args.reference)
    sources = sorted({source for source, _ in scores})
    pages = {}
    with gzip.open(args.export, "rt", encoding="utf-8") as stream:
        manifest = json.loads(next(stream))
        if manifest.get("schema") != 1 or manifest.get("direction") != "out":
            raise ValueError("Unsupported export schema/direction.")
        if set(map(tuple, manifest["links"])) != set(scores) or set(manifest["sources"]) != set(sources):
            raise ValueError("Export and reference do not contain the same sources/edges.")
        for line in stream:
            row = json.loads(line)
            if row["page_id"] in sources:
                if row["page_id"] in pages:
                    raise ValueError("Duplicate source in export.")
                pages[row["page_id"]] = row
    if set(pages) != set(sources):
        raise ValueError("Source missing from export.")
    for pid, row in pages.items():
        if row["revision_id"] != ref["source_revisions"][str(pid)] or row["title"] != titles[pid]:
            raise ValueError("Source title/revision mismatch.")
    leads = {}
    with (args.reference / "texts.jsonl").open(encoding="utf-8-sig") as stream:
        for row in map(json.loads, stream):
            leads[row["page_id"]] = row["variants"]["v3"]
    lookup = {}
    for pid, title in titles.items():
        key = norm_title(title)
        if key in lookup and lookup[key] != pid:
            raise ValueError("Ambiguous normalized title: " + key)
        lookup[key] = pid
    if args.aliases:
        with args.aliases.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                target = int(row["target_page_id"])
                if target not in titles:
                    continue
                key = norm_title(row["alias"])
                if not key or (key in lookup and lookup[key] != target):
                    raise ValueError("Empty or conflicting redirect alias: " + key)
                lookup[key] = target
    args.output.mkdir(parents=True)
    coverage = []
    with (args.output / "pairs.jsonl").open("w", encoding="utf-8") as out, \
         (args.output / "unresolved_titles.csv").open("w", encoding="utf-8-sig", newline="") as unknown:
        writer = csv.writer(unknown)
        writer.writerow(["source_id", "unresolved_title"])
        for source in sources:
            targets = {target for src, target in scores if src == source}
            contexts, unresolved = extract_contexts(pages[source]["wikitext"], targets, lookup)
            counts = {key: sum(x["status"] == key for x in contexts.values())
                      for key in ("lead", "body", "list", "not_found")}
            coverage.append({"page_id": source, "title": titles[source], "neighbors": len(targets), **counts})
            for title in unresolved:
                writer.writerow([source, title])
            for target in sorted(targets):
                out.write(json.dumps({"source_id": source, "target_id": target,
                    "source_title": titles[source], "target_title": titles[target],
                    "source_lead": leads[source], "target_lead": leads[target],
                    "v3": scores[source, target], **contexts[target]}, ensure_ascii=False) + "\n")
            print(titles[source], counts, flush=True)
    metadata = {"pipeline": PIPELINE, "reference_sha256": hashes,
                "export_sha256": sha256(args.export),
                "aliases_sha256": sha256(args.aliases) if args.aliases else None,
                "coverage": coverage, "pairs": len(scores), "status": "prepared"}
    (args.output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Prepared:", args.output, "No model loaded; no database changes.")


def download(args):
    from huggingface_hub import snapshot_download, model_info
    if args.output.exists():
        raise ValueError("Model directory exists; use it for scoring or choose a new directory.")
    revision = model_info(MODEL).sha
    snapshot_download(MODEL, revision=revision, local_dir=str(args.output),
                      allow_patterns=["*.json", "*.safetensors", "*.model"])
    (args.output / "wikipath_model.json").write_text(json.dumps({"model": MODEL, "revision": revision}), encoding="utf-8")
    print("Downloaded. Scoring will load only from:", args.output)


def position_key(row):
    # Unknown context is kept separate: it may be a redirect or generated link.
    tier = {"lead": 0, "body": 1, "list": 2, "not_found": 3}[row["status"]]
    first = row["contexts"][0] if row["contexts"] else {}
    return tier, first.get("section_index", 10**9), first.get("paragraph_index", 10**9), row["target_id"]


def model_pair(row, variant, tokenizer):
    def clipped(text, budget):
        ids = tokenizer.encode(text, add_special_tokens=False)
        return tokenizer.decode(ids[:budget], skip_special_tokens=True)
    query = clipped(row["source_title"] + "\n" + row["source_lead"], 112)
    # Fixed title/definition budget in both variants, to isolate added context.
    target = clipped(row["target_title"] + "\n" + row["target_lead"], 144)
    if variant == "cross_context" and row["contexts"]:
        passages = "\n".join(c["text"] for c in row["contexts"])
        target += "\nPassage contenant le lien dans la page source :\n" + clipped(passages, 208)
    return query, target


def score(args):
    # No hub requests, telemetry or inference API in this execution path.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    if args.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; use --device cpu.")
    model_path = args.model_dir.resolve()
    model_meta = json.loads((model_path / "wikipath_model.json").read_text())
    if model_meta["model"] != MODEL:
        raise ValueError("Wrong local model.")
    rows = [json.loads(line) for line in (args.prepared / "pairs.jsonl").open(encoding="utf-8")]
    meta = json.loads((args.prepared / "metadata.json").read_text(encoding="utf-8"))
    if meta.get("pipeline") != PIPELINE or len(rows) != meta["pairs"]:
        raise ValueError("Prepared data mismatch.")
    if len({(r['source_id'], r['target_id']) for r in rows}) != len(rows):
        raise ValueError("Duplicate prepared pairs.")
    if args.max_sources:
        selected = sorted({r["source_id"] for r in rows})[:args.max_sources]
        rows = [r for r in rows if r["source_id"] in selected]
    config = {"pipeline": PIPELINE, "model": model_meta,
              "pairs_sha256": sha256(args.prepared / "pairs.jsonl"),
              "script_sha256": sha256(Path(__file__)),
              "device": args.device, "dtype": "fp16" if args.device == "cuda" else "fp32",
              "max_tokens": 512, "source_ids": sorted({r['source_id'] for r in rows})}
    signature = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.output / "progress.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS config (signature TEXT PRIMARY KEY)")
    previous = db.execute("SELECT signature FROM config").fetchone()
    if previous and previous[0] != signature:
        raise ValueError("Resume configuration differs. Choose a new output directory.")
    db.execute("INSERT OR IGNORE INTO config VALUES (?)", (signature,))
    db.execute("CREATE TABLE IF NOT EXISTS scores (variant TEXT, source INTEGER, target INTEGER, value REAL, PRIMARY KEY(variant,source,target))")
    db.commit()
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_path), local_files_only=True, trust_remote_code=False)
    if args.device == "cuda":
        model.half()
    model.to(args.device).eval()
    started = time.perf_counter()
    computed = 0
    for variant in ("cross_plain", "cross_context"):
        completed = {(a, b) for a, b in db.execute("SELECT source,target FROM scores WHERE variant=?", (variant,))}
        pending = [r for r in rows if (r["source_id"], r["target_id"]) not in completed]
        print(variant, len(completed), "saved;", len(pending), "remaining", flush=True)
        for start in range(0, len(pending), args.batch_size):
            batch = pending[start:start + args.batch_size]
            # Identical input for missing contexts: reuse the plain score exactly.
            reuse = [r for r in batch if variant == "cross_context" and not r["contexts"]]
            active = [r for r in batch if r not in reuse]
            values = []
            if active:
                pairs = [model_pair(r, variant, tokenizer) for r in active]
                inputs = tokenizer(pairs, padding=True, truncation="only_second", max_length=512, return_tensors="pt")
                with torch.inference_mode():
                    output = model(**{key: value.to(args.device) for key, value in inputs.items()})
                    values = output.logits.reshape(-1).float().cpu().tolist()
                if len(values) != len(active) or not all(math.isfinite(v) for v in values):
                    raise ValueError("Invalid model scores.")
                computed += len(active)
            for row, value in zip(active, values):
                db.execute("INSERT INTO scores VALUES (?,?,?,?)", (variant, row["source_id"], row["target_id"], value))
            for row in reuse:
                value = db.execute("SELECT value FROM scores WHERE variant='cross_plain' AND source=? AND target=?",
                                   (row["source_id"], row["target_id"])).fetchone()[0]
                db.execute("INSERT INTO scores VALUES (?,?,?,?)", (variant, row["source_id"], row["target_id"], value))
            db.commit()
            done = min(start + args.batch_size, len(pending))
            if start == 0 or done % (args.batch_size * 10) == 0 or done == len(pending):
                print(f"{variant}: {done}/{len(pending)}; session {time.perf_counter()-started:.0f}s", flush=True)
    scores = {(variant, a, b): value for variant, a, b, value in db.execute("SELECT * FROM scores")}
    make_report(args.output, rows, scores)
    result = {**config, "status": "complete", "pairs": len(rows),
              "scored_this_session": computed, "scoring_session_seconds": time.perf_counter() - started,
              "coverage": meta["coverage"]}
    (args.output / "metadata.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    db.close()
    print("Done:", args.output / "report.html")


def make_report(output, rows, scores):
    report = ["<!doctype html><html lang='fr'><meta charset='utf-8'><title>Wikipath — contexte des liens</title>",
              "<style>body{font:15px/1.5 system-ui;margin:24px;color:#202122}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;vertical-align:top}th{background:#eee}small{display:block;color:#555}details{max-width:360px}h2{margin-top:40px}.scroll{overflow:auto}</style>",
              "<h1>Contexte des liens : pilote local</h1><p>Tous les voisins de chaque source sont classés. Les 60 premiers sont affichés. Scores E5 et logits du cross-encoder ne sont pas comparables.</p>",
              "<p>Introuvable signifie absence de contexte extrait, pas absence de relation : redirections non résolues, modèles non développés, références ou tableaux retirés sont possibles. Aucun appel Wikipédia. Le classement par emplacement est une heuristique à évaluer.</p>",
              "<p>Le cross-encoder avec contexte peut favoriser un passage simplement parce qu’il reprend le texte source. La colonne sans contexte sert de contrôle ; aucun gain n’est présumé.</p>"]
    with (output / "scores.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["variant", "source_id", "target_id", "rank", "score", "title", "context_status"])
        for source in sorted({r["source_id"] for r in rows}):
            group = [r for r in rows if r["source_id"] == source]
            orders = {}
            for variant in LABELS:
                if variant == "position":
                    orders[variant] = sorted(group, key=position_key)
                else:
                    def value(row):
                        return row["v3"] if variant == "v3" else scores[variant, source, row["target_id"]]
                    orders[variant] = sorted(group, key=lambda r: (-value(r), r["target_id"]))
                for rank, row in enumerate(orders[variant], 1):
                    val = "" if variant == "position" else (row["v3"] if variant == "v3" else scores[variant, source, row["target_id"]])
                    writer.writerow([variant, source, row["target_id"], rank, val, row["target_title"], row["status"]])
            covered = sum(bool(r["contexts"]) for r in group)
            report.append("<h2>" + html.escape(group[0]["source_title"]) + f" — {len(group)} voisins</h2><p>Contexte retrouvé pour {covered}/{len(group)} liens.</p>")
            report.append("<div class='scroll'><table><tr><th>Rang</th>" + "".join("<th>"+label+"</th>" for label in LABELS.values()) + "</tr>")
            for index in range(min(60, len(group))):
                report.append(f"<tr><td>{index+1}</td>")
                for variant in LABELS:
                    row = orders[variant][index]
                    desc = {"lead": "Introduction", "body": "Corps", "list": "Liste", "not_found": "Introuvable"}[row["status"]]
                    report.append("<td>" + html.escape(row["target_title"]) + "<small>" + desc + f" · ID {row['target_id']}</small>")
                    if row["contexts"]:
                        report.append("<details><summary>Voir le contexte</summary>" + "<hr>".join(html.escape(c["text"]) for c in row["contexts"]) + "</details>")
                    report.append("</td>")
                report.append("</tr>")
            report.append("</table></div>")
    report.append("</html>")
    (output / "report.html").write_text("\n".join(report), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--aliases", type=Path, help="Optional local CSV: alias,target_page_id (resolved final target)")
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(run=prepare)
    p = commands.add_parser("download")
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(run=download)
    p = commands.add_parser("score")
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--max-sources", type=int, help="Optional timing trial: first N complete source neighborhoods")
    p.set_defaults(run=score)
    args = parser.parse_args()
    if getattr(args, "batch_size", 1) < 1 or (getattr(args, "max_sources", None) is not None and args.max_sources < 1):
        parser.error("Batch size and source limit must be positive.")
    try:
        args.run(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
