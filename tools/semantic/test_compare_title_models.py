import csv
from pathlib import Path
import tempfile
import unittest

from compare_title_models import rank_scores, title_inputs, write_results


class TitleComparisonTests(unittest.TestCase):
    def test_all_neighbors_are_ranked_with_stable_ties(self):
        scores = {(1, target): 0.5 for target in range(81, 1, -1)}
        scores[1, 81] = 0.9
        rows = rank_scores(scores)[1]
        self.assertEqual(len(rows), 80)
        self.assertEqual([target for target, _ in rows[:3]], [81, 2, 3])
        self.assertEqual(rows[20][0], 21)
        self.assertEqual(rows[-1][0], 80)

    def test_model_inputs_preserve_case_and_correct_prefix(self):
        titles = {9: "Python (langage)", 3: "Marie Curie"}
        self.assertEqual(title_inputs(titles, "minilm_title"), ["Marie Curie", "Python (langage)"])
        self.assertEqual(title_inputs(titles, "e5_title"), ["query: Marie Curie", "query: Python (langage)"])

    def test_full_export_and_unchanged_v3_scores(self):
        scores = {(1, target): target / 100 for target in range(2, 82)}
        titles = {pid: f"Title {pid}" for pid in range(1, 82)}
        titles[81] = "<script> & test"
        variants = {key: dict(scores) for key in ("minilm_title", "e5_title", "e5_v3")}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_results(output, variants, titles)
            with (output / "scores.csv").open(encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 240)
            restored = {(int(row["source_id"]), int(row["target_id"])): float(row["cosine_score"])
                        for row in rows if row["variant"] == "e5_v3"}
            self.assertEqual(restored, scores)
            self.assertIn("&lt;script&gt; &amp; test", (output / "report.html").read_text())
            self.assertNotIn("<script>", (output / "report.html").read_text())

    def test_reject_different_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                write_results(Path(directory), {"e5_v3": {(1, 2): 0.5}, "minilm_title": {}}, {1: "A", 2: "B"})


if __name__ == "__main__":
    unittest.main()
