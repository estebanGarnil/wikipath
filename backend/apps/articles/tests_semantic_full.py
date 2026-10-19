import json
from pathlib import Path
import sqlite3
import tempfile

from django.test import SimpleTestCase
import numpy as np

from .management.commands.import_semantic_full import VectorStore, write_batch


class Result(list):
    def single(self):
        return self[0] if self else None

    def consume(self):
        return None


class FakeTransaction:
    def __init__(self, records, last_id=0):
        self.records = records
        self.last_id = last_id
        self.calls = []

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if "lock_counter" in query:
            return Result([{"last_id": self.last_id}])
        if "UNWIND" in query:
            return Result(self.records)
        return Result()


class FullSemanticTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "vectors.sqlite"
        vector = np.zeros(384, dtype="<f4")
        vector[0] = 1
        orthogonal = np.zeros(384, dtype="<f4")
        orthogonal[1] = 1
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
            db.execute("CREATE TABLE pages(page_id INTEGER PRIMARY KEY,vector BLOB)")
            for key, value in {"config": {"schema": 1, "dimensions": 384, "pipeline": "title-lead-v3-query-symmetric"},
                               "complete": True, "version": "test"}.items():
                db.execute("INSERT INTO metadata VALUES (?,?)", (key, json.dumps(value)))
            db.executemany("INSERT INTO pages VALUES (?,?)", [(3, vector.tobytes()), (7, vector.tobytes()), (9, orthogonal.tobytes())])

    def tearDown(self):
        self.directory.cleanup()

    def test_cosines_and_cache(self):
        store = VectorStore(self.path)
        try:
            self.assertEqual(store.score_page(3, [7, 9]), {"7": 1.0, "9": 0.0})
            self.assertEqual(store.score_page(3, []), {})
            self.assertEqual(set(store.cache), {3, 7, 9})
        finally:
            store.close()

    def test_missing_vector_stops_batch(self):
        store = VectorStore(self.path)
        try:
            with self.assertRaises(ValueError):
                store.score_page(3, [999])
        finally:
            store.close()

    def test_incomplete_encoding_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE metadata SET value='false' WHERE name='complete'")
        with self.assertRaisesRegex(ValueError, "incomplet"):
            VectorStore(self.path)

    def test_checkpoint_only_after_all_pages_validated(self):
        pages = [{"id": 3, "total": 2, "scores": {"7": 1., "9": 0.}}, {"id": 7, "total": 0, "scores": {}}]
        tx = FakeTransaction([{"page_id": 3, "actual": 2, "matched": 2, "relationships": 3},
                              {"page_id": 7, "actual": 0, "matched": 0, "relationships": 0}])
        self.assertEqual(write_batch(tx, "test", 0, pages), 3)
        self.assertEqual(tx.calls[-1][1]["last_id"], 7)
        self.assertEqual(tx.calls[-1][1]["pages"], 2)

    def test_changed_neighbors_abort_before_checkpoint(self):
        for row in [dict(page_id=3, actual=3, matched=2, relationships=3),
                    dict(page_id=3, actual=2, matched=1, relationships=2)]:
            tx = FakeTransaction([row])
            with self.assertRaises(ValueError):
                write_batch(tx, "test", 0, [{"id": 3, "total": 2, "scores": {"7": 1., "9": 0.}}])
            self.assertEqual(len(tx.calls), 2)

    def test_concurrent_resume_rejected_before_writes(self):
        tx = FakeTransaction([], last_id=7)
        with self.assertRaises(ValueError):
            write_batch(tx, "test", 0, [{"id": 3, "total": 0, "scores": {}}])
        self.assertEqual(len(tx.calls), 1)

    def test_missing_source_aborts_before_checkpoint(self):
        tx = FakeTransaction([])
        with self.assertRaises(ValueError):
            write_batch(tx, "test", 0, [{"id": 3, "total": 0, "scores": {}}])
        self.assertEqual(len(tx.calls), 2)
