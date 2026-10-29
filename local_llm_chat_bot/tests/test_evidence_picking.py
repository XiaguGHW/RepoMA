"""Document types from content, and evidence picking that uses the pre-read plan."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image  # noqa: E402
import chat_workbench as w  # noqa: E402
from local_document_library import LocalDocumentLibrary  # noqa: E402


def doc(name, texts, role="other"):
    return {"id": name, "name": name, "material_role": role,
            "chunks": [{"label": f"{name} — page {n}", "text": text, "visual": {"kind": "pdf_page", "page": n}}
                       for n, text in enumerate(texts, start=1)]}


class DocumentKinds(unittest.TestCase):
    def test_local_guess_reads_the_first_pages_not_only_the_name(self):
        self.assertEqual(w.guess_document_kind(doc("scan_001.pdf", ["Angebot Nr. 4711\nPos. Menge Preis"])), "offer")
        self.assertEqual(w.guess_document_kind(doc("x.pdf", ["Technische Daten Zylinder DSBC"])), "datasheet")
        self.assertEqual(w.guess_document_kind(doc("Katalog_2026.pdf", ["Inhalt"])), "catalog")
        self.assertEqual(w.guess_document_kind(doc("y.pdf", ["Zeichnungsnummer 123 Maßstab 1:2"])), "drawing")
        self.assertEqual(w.guess_document_kind(doc("z.pdf", ["Nichts Besonderes"])), "other")

    def test_model_kind_line_is_read_from_the_summary(self):
        self.assertEqual(w.model_document_kind("文件类型：报价单 — 供应商报价\n型号/订货号：..."), "offer")
        self.assertEqual(w.model_document_kind("文件类型: DFC 结构图 — 层级"), "dfc")
        self.assertIsNone(w.model_document_kind("没有类型行"))


class EvidencePicking(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.library = LocalDocumentLibrary(self.root / "documents.json")

    def test_representative_chunk_comes_from_pre_read_pages(self):
        manual = doc("manual.pdf", [f"Seite {n}" for n in range(1, 41)])
        self.library.data["documents"] = [manual]
        picked = self.library.search("Wozu dient das?", preferred_ids=["manual.pdf"], classification=True,
                                     preferred_pages={"manual.pdf": [12, 30]})
        self.assertEqual(picked[0]["label"], "manual.pdf — page 12")

    def test_bom_terms_lift_the_matching_page(self):
        manual = doc("manual.pdf", ["Einleitung"] + ["Allgemein"] * 20 + ["Bestellnummer DSBC-32-100-PPVA"])
        self.library.data["documents"] = [manual]
        picked = self.library.search("Wozu?", extra_terms={"dsbc-32-100-ppva"})
        self.assertIn("manual.pdf — page 22", [item["label"] for item in picked])
        self.assertNotIn("manual.pdf — page 1", [item["label"] for item in picked])

    def test_every_file_gets_one_picture_before_any_gets_a_second(self):
        paths = []
        for name in ("a.png", "b.png", "c.png"):
            Image.new("RGB", (600, 400), "white").save(self.root / name)
            paths.append(self.root / name)
        snippets = [{"id": path.name, "visual": {"kind": "image", "path": str(path)}} for path in paths]
        out = self.library.visual_paths(snippets, self.root / "cache", first_per_file_ids={"a.png", "b.png", "c.png"})
        self.assertEqual(len(out), 3)
        self.assertEqual(len(set(out)), 3)  # no picture is sent twice


if __name__ == "__main__":
    unittest.main(verbosity=2)
