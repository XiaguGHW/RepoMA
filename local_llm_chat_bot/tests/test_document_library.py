"""Document index: images, corrupt index, sparse Excel sources, atomic writes."""

from __future__ import annotations

from pathlib import Path
import sys

APP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(APP), str(APP / "tests")]

import json  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest.mock import patch  # noqa: E402
import chat_workbench as w  # noqa: E402
from local_document_library import LocalDocumentLibrary  # noqa: E402
from api_cases import DirectSessionCase  # noqa: E402


class DocumentIndexing(DirectSessionCase):
    def test_invalid_image_is_not_indexed_as_valid_evidence(self):
        path = self.root / 'broken.png'
        path.write_bytes(b'not an image')
        with self.assertRaises(Exception):
            w.ACTIVE['documents'].add(str(path))

    def test_corrupt_document_index_type(self):
        path = self.root / 'documents.json'
        path.write_text('[]')
        self.assertEqual(LocalDocumentLibrary(path).list(), [])

    def test_sparse_excel_preserves_source_row_coordinates(self):
        from openpyxl import Workbook
        path = self.root / 'sparse.xlsx'
        book = Workbook()
        book.active['A100'] = 'EVIDENCE'
        book.save(path)
        book.close()
        doc = w.ACTIVE['documents'].add(str(path))
        chunk = next(c for c in doc['chunks'] if 'EVIDENCE' in c['text'])
        self.assertLessEqual(chunk['visual']['start_row'], 100)
        self.assertGreaterEqual(chunk['visual']['end_row'], 100)


class DocumentIndexAtomicWrite(unittest.TestCase):
    def test_save_replaces_valid_json_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "documents.json"
            library = LocalDocumentLibrary(path)
            for number in range(3):
                library.data = {"version": 1, "documents": [{"id": str(number)}]}
                library._save()
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["documents"][0]["id"], str(number))
                self.assertFalse(list(path.parent.glob(f".{path.name}.*.tmp")))

            previous = path.read_text(encoding="utf-8")
            library.data = {"version": 1, "documents": [{"id": "new"}]}
            with patch("local_document_library.os.replace", side_effect=OSError("simulated interruption")):
                with self.assertRaises(OSError):
                    library._save()
            # An interrupted replacement leaves the old complete file intact;
            # the sibling temporary file never becomes the final index.
            self.assertEqual(path.read_text(encoding="utf-8"), previous)
            self.assertFalse(list(path.parent.glob(f".{path.name}.*.tmp")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
