import tempfile
import unittest
from pathlib import Path
from compare_variants import rank_links, write_results


class ComparisonTests(unittest.TestCase):
    def test_all_neighbors_and_ties(self):
        links = [(1, n) for n in range(70, 1, -1)]
        rows = rank_links([1], links, lambda a, b: 0.5)[1]
        self.assertEqual(len(rows), 69)
        self.assertEqual(rows[0]['target_id'], 2)
        self.assertEqual(rows[20]['target_id'], 22)
        self.assertEqual(rows[-1]['rank'], 69)

    def test_descending_score(self):
        rows = rank_links([1, 9], [(1, 2), (1, 3)], lambda a, b: b / 10)
        self.assertEqual(rows[1][0]['target_id'], 3)
        self.assertEqual(rows[9], [])

    def test_report_escaping_and_full_csv(self):
        links = [(1, n) for n in range(2, 75)]
        rankings = {v: rank_links([1], links, lambda a, b: 1/b) for v in ['v1','v2','v3']}
        titles = {n: '<script> & titre' for n in range(1,75)}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_results(output, rankings, titles)
            report = (output/'report.html').read_text()
            self.assertNotIn('<script>', report)
            self.assertIn('&lt;script&gt;', report)
            self.assertEqual(len((output/'scores.csv').read_text(encoding='utf-8-sig').splitlines()), 1 + 73*3)
            self.assertEqual(len((output/'evaluation.csv').read_text(encoding='utf-8-sig').splitlines()), 74)


if __name__ == '__main__':
    unittest.main()
