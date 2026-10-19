import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import types
import zlib

import numpy as np

import encode_full as encoder


class EncoderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "vectors.sqlite"
        self.db = sqlite3.connect(self.path)
        self.db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)")
        self.db.execute("CREATE TABLE pages(page_id INTEGER PRIMARY KEY,title TEXT,revision_id INTEGER,vector BLOB,title_only INTEGER)")
        self.db.executemany("INSERT INTO pages(page_id,title) VALUES (?,?)", [(3, "A"), (7, "B")])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def vector(self, count=1):
        data = np.zeros((count, 384), dtype=np.float32)
        data[:, 0] = 1
        return data

    def test_committed_vectors_and_cursor_survive_reopen(self):
        encoder.save_vectors(self.db, [(3, 8, "query: A", False)], self.vector())
        with sqlite3.connect(self.path) as other:
            self.assertEqual(encoder.get_meta(other, "last_encoded_id"), 3)
            self.assertEqual(encoder.get_meta(other, "encoded"), 1)
            self.assertEqual(other.execute("SELECT length(vector) FROM pages WHERE page_id=3").fetchone()[0], 1536)
            self.assertEqual(other.execute("SELECT page_id FROM pages WHERE page_id>3").fetchall(), [(7,)])

    def test_failed_checkpoint_rolls_back_vectors(self):
        self.db.execute("CREATE TRIGGER fail_cursor BEFORE INSERT ON metadata WHEN NEW.name='last_encoded_id' BEGIN SELECT RAISE(ABORT,'simulated crash'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            encoder.save_vectors(self.db, [(3, 8, "query: A", False)], self.vector())
        self.assertIsNone(self.db.execute("SELECT vector FROM pages WHERE page_id=3").fetchone()[0])
        self.assertIsNone(encoder.get_meta(self.db, "last_encoded_id"))

    def test_process_crash_preserves_previous_checkpoint(self):
        encoder.save_vectors(self.db, [(3, 8, "query: A", False)], self.vector())
        code = """
import sqlite3, sys, os
db = sqlite3.connect(sys.argv[1])
db.execute('BEGIN IMMEDIATE')
db.execute('UPDATE pages SET vector=zeroblob(1536) WHERE page_id=7')
db.execute("UPDATE metadata SET value='7' WHERE name='last_encoded_id'")
os._exit(99)
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.path)], check=False)
        self.assertEqual(result.returncode, 99)
        with sqlite3.connect(self.path) as check:
            self.assertEqual(encoder.get_meta(check, "last_encoded_id"), 3)
            self.assertIsNone(check.execute("SELECT vector FROM pages WHERE page_id=7").fetchone()[0])

    def test_invalid_vectors_cannot_advance_checkpoint(self):
        for array in [np.zeros((1, 384)), np.full((1, 384), float("nan")), np.ones((1, 12))]:
            with self.assertRaises(ValueError):
                encoder.save_vectors(self.db, [(3, 8, "query: A", False)], array)
        self.assertIsNone(encoder.get_meta(self.db, "last_encoded_id"))

    def test_exact_v3_input_and_title_fallback(self):
        encoder.PREPARER = lambda text, title: {"introduction": "L" * 7000}
        prepared = encoder.prepare_one((3, "Titre", 8, zlib.compress(b"wiki")))
        self.assertEqual(prepared[2], "query: Titre\n" + "L" * 6000)
        fallback = encoder.prepare_one((7, "Sans texte", None, None))
        self.assertEqual(fallback[2], "query: Sans texte\n")
        self.assertTrue(fallback[3])

    def test_corrupt_wikitext_is_not_silently_skipped(self):
        with self.assertRaisesRegex(RuntimeError, "page 3"):
            encoder.prepare_one((3, "A", 8, b"broken-zlib"))

    def test_node_ingest_resume(self):
        path = Path(self.temp.name) / "nodes.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerows([["page_id:ID(Page)", "title"], [3, "A"], [7, "B"], [9, "C"]])
        with self.db:
            encoder.set_meta(self.db, "nodes_loaded", 2)
        encoder.load_nodes(self.db, path)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 3)
        self.assertTrue(encoder.get_meta(self.db, "nodes_complete"))
        encoder.load_nodes(self.db, path)
        self.assertEqual(self.db.execute("SELECT count(*) FROM pages").fetchone()[0], 3)

    def test_cli_two_runs_finish_without_reencoding_first_page(self):
        root = Path(self.temp.name)
        nodes, articles, prepare, meta, output = [root / name for name in
            ("input.csv", "articles.sqlite", "prepare_text.py", "metadata.json", "full.sqlite")]
        nodes.write_text("page_id:ID(Page),title\n3,A\n7,B\n", encoding="utf-8")
        with sqlite3.connect(articles) as db:
            db.execute("CREATE TABLE articles(page_id INTEGER PRIMARY KEY,revision_id INTEGER,wikitext_zlib BLOB)")
            db.execute("INSERT INTO articles VALUES (3,8,?)", (zlib.compress(b"lead"),))
        prepare.write_text("def prepare(wikitext, title):\n    return {'introduction': wikitext}\n", encoding="utf-8")
        meta.write_text(json.dumps({"model": encoder.MODEL, "model_revision": "a" * 40,
                                   "variants": {"v3": "test"}, "preparation_sha256": hashlib.sha256(prepare.read_bytes()).hexdigest()}))
        encoded_texts = []
        vector = self.vector
        class FakeModel:
            def __init__(self, *args, **kwargs): pass
            def float(self): pass
            def encode(self, texts, **kwargs):
                encoded_texts.extend(texts)
                return vector(len(texts))
        torch = types.ModuleType("torch")
        sentence_transformers = types.ModuleType("sentence_transformers")
        sentence_transformers.SentenceTransformer = FakeModel
        arguments = ["encode_full.py", "--nodes", str(nodes), "--articles", str(articles),
                     "--prepare", str(prepare), "--reference-metadata", str(meta),
                     "--output", str(output), "--device", "cpu", "--workers", "1"]
        with patch.dict(sys.modules, {"torch": torch, "sentence_transformers": sentence_transformers}), patch.object(
            encoder, "runtime_versions", return_value={"test": "1"}
        ):
            with patch.object(sys, "argv", arguments + ["--max-pages", "1"]):
                encoder.main()
            with sqlite3.connect(output) as db:
                self.assertEqual(encoder.get_meta(db, "encoded"), 1)
                self.assertFalse(encoder.get_meta(db, "complete", False))
            with patch.object(sys, "argv", arguments):
                encoder.main()
        with sqlite3.connect(output) as db:
            self.assertTrue(encoder.get_meta(db, "complete"))
            self.assertEqual(encoder.get_meta(db, "encoded"), 2)
        self.assertEqual(encoded_texts, ["query: A\nlead", "query: B\n"])


if __name__ == "__main__":
    unittest.main()
