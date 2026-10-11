import csv
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from context_pilot import extract_contexts, make_report, norm_title, prepare


class ContextTests(unittest.TestCase):
    def test_alias_fragment_reference_and_template(self):
        text = "{{Infobox|x=[[Cible cachée]]}}\nMarie découvre le [[Polonium#Histoire|polonium]].<ref>[[Référence]]</ref>\n\n== Travaux ==\nElle étudie [[Alias_local|un élément]].\n\n* Voir [[Liste liée]]."
        lookup = {"Polonium": 2, "Alias local": 2, "Cible cachée": 3, "Référence": 4, "Liste liée": 5}
        found, _ = extract_contexts(text, {2, 3, 4, 5}, lookup)
        self.assertEqual(found[2]["status"], "lead")
        self.assertEqual(found[2]["mentions"], 2)
        self.assertEqual([c["location"] for c in found[2]["contexts"]], ["lead", "body"])
        self.assertEqual(found[3]["status"], "not_found")
        self.assertEqual(found[4]["status"], "not_found")
        self.assertEqual(found[5]["status"], "list")
        self.assertNotIn("WIKIPATHLINKMARKER", str(found))

    def test_keep_mention_in_long_paragraph_and_missing_neighbors(self):
        found, unknown = extract_contexts("a " * 1000 + "[[Cible|MENTION]]" + " b" * 1000 + " [[Inconnue]]", {2, 3}, {"Cible": 2})
        self.assertIn("MENTION", found[2]["contexts"][0]["text"])
        self.assertLessEqual(len(found[2]["contexts"][0]["text"]), 900)
        self.assertEqual(found[3]["status"], "not_found")
        self.assertIn("Inconnue", unknown)

    def test_normalization_preserves_internal_case(self):
        self.assertEqual(norm_title("algèbre_linéaire#Histoire"), "Algèbre linéaire")
        self.assertNotEqual(norm_title("iPhone"), norm_title("iphone"))

    def test_all_edges_exported_even_missing_context(self):
        rows = [{"source_id": 1, "target_id": i, "source_title": "Source", "target_title": "<unsafe>",
                 "v3": i / 100, "contexts": [], "status": "not_found"} for i in range(2, 72)]
        scores = {(variant, 1, row["target_id"]): float(row["target_id"])
                  for variant in ("cross_plain", "cross_context") for row in rows}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            make_report(output, rows, scores)
            with (output / "scores.csv").open(encoding="utf-8-sig") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 70 * 4)
            text = (output / "report.html").read_text()
            self.assertIn("&lt;unsafe&gt;", text)
            self.assertNotIn("<unsafe>", text)

    def test_prepare_checks_revisions_and_preserves_missing_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference"
            reference.mkdir()
            meta = {"model": "intfloat/multilingual-e5-small", "model_revision": "a" * 40,
                    "variants": {"v3": "test"}, "pages": 3, "links": 2,
                    "source_revisions": {"1": 10, "2": 20, "3": 30}}
            (reference / "metadata.json").write_text(json.dumps(meta))
            pages = [{"page_id": i, "title": title, "variants": {"v3": title}}
                     for i, title in [(1, "Source"), (2, "Cible"), (3, "Manquante")]]
            (reference / "texts.jsonl").write_text("\n".join(map(json.dumps, pages)))
            (reference / "scores.csv").write_text("variant,source_id,target_id,rank,semantic_score,title\nv3,1,2,1,0.9,Cible\nv3,1,3,2,0.8,Manquante\n")
            export = root / "export.gz"
            with gzip.open(export, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps({"schema": 1, "direction": "out", "sources": [1], "links": [[1, 2], [1, 3]]}) + "\n")
                stream.write(json.dumps({"page_id": 1, "title": "Source", "revision_id": 10, "wikitext": "Texte [[Cible]]."}) + "\n")
            args = SimpleNamespace(reference=reference, export=export, aliases=None, output=root / "prepared")
            prepare(args)
            pairs = [json.loads(line) for line in (args.output / "pairs.jsonl").read_text().splitlines()]
            self.assertEqual(len(pairs), 2)
            self.assertEqual([row["status"] for row in pairs], ["lead", "not_found"])
            meta["source_revisions"]["1"] = 11
            (reference / "metadata.json").write_text(json.dumps(meta))
            args.output = root / "invalid"
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                prepare(args)


if __name__ == "__main__":
    unittest.main()
