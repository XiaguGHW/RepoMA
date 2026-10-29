"""Pre-reading looks at pictures: CAD screenshots, DFC crops (with their OCR) and drawing pages."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import chat_workbench as w  # noqa: E402
from local_document_library import LocalDocumentLibrary  # noqa: E402
from fixture_support import FixtureEnvironment  # noqa: E402


def images_in(body: dict) -> int:
    return sum(1 for content in body.get("contents", []) for part in content.get("parts", []) if "inlineData" in part)


def text_of(body: dict) -> str:
    return "\n".join(part.get("text", "") for content in body.get("contents", []) for part in content.get("parts", []))


class VisualPreread(unittest.TestCase):
    def setUp(self):
        self.f = FixtureEnvironment().__enter__()
        self.addCleanup(self.f.__exit__, None, None, None)
        (self.f.bg_a / "Bilder").mkdir()
        Image.new("RGB", (900, 600), "white").save(self.f.bg_a / "Bilder" / "BG_Screenshot_1.png")
        Image.new("RGB", (900, 3600), "white").save(self.f.bg_a / "BG_DFC_Struktur.png")  # tall: cut into crops
        self.client = TestClient(w.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.post("/api/setup", {"model": "gemini-2.5-pro", "language": "de"})
        self.post("/api/codebook/prepare", {"path": str(self.f.rules)})
        self.post("/api/codebook/lock", {})

    def post(self, path, body):
        response = self.client.post(path, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def preread_calls(self, start):
        return [call["body"] for call in self.f.calls[start:]
                if w.MATERIAL_SUMMARY_SYSTEM in text_of({"contents": [call["body"].get("system_instruction", {})]})]

    def confirm(self, files):
        self.post("/api/target", {"target": str(self.f.bg_a), "selected_paths": files})

    def test_screenshot_and_dfc_are_read_as_pictures(self):
        with patch.object(LocalDocumentLibrary, "_ocr_page_image", return_value=("Antriebseinheit Motor M1", "ok")):
            self.confirm(["facts.txt", "Bilder/BG_Screenshot_1.png", "BG_DFC_Struktur.png"])
            before = len(self.f.calls)
            self.post("/api/chat", {"question": "Classify this Baugruppe"})
        calls = self.preread_calls(before)
        shot = [body for body in calls if "BG_Screenshot_1.png" in text_of(body)]
        dfc = [body for body in calls if "BG_DFC_Struktur.png" in text_of(body)]
        facts = [body for body in calls if "facts.txt" in text_of(body)]
        self.assertTrue(shot and images_in(shot[0]) == 1)
        self.assertIn("随附图片", text_of(shot[0]))
        self.assertTrue(dfc and all(1 <= images_in(body) <= w.PREREAD_DFC_SEGMENTS_PER_CALL for body in dfc))
        self.assertIn("Antriebseinheit Motor M1", text_of(dfc[0]))  # DFC OCR now reaches the pre-read
        self.assertTrue(facts and images_in(facts[0]) == 0)  # plain text stays text only
        report = self.client.get("/api/coverage").json()
        by_name = {item["name"]: item for item in report["files"]}
        self.assertEqual(by_name["BG_Screenshot_1.png"]["images_read"], ["BG_Screenshot_1.png"])
        self.assertTrue(by_name["BG_DFC_Struktur.png"]["images_read"])
        self.assertTrue(report["complete"])

    def test_refused_pictures_fall_back_to_text(self):
        self.confirm(["facts.txt", "Bilder/BG_Screenshot_1.png"])
        llm = w.ACTIVE["llm"]
        original = llm.ask_about_files

        def refuse_pictures(files, *args, **kwargs):
            return "HTTP error 400: images are not supported" if files else original(files, *args, **kwargs)

        with patch.object(llm, "ask_about_files", side_effect=refuse_pictures):
            report = w.prepare_coverage(w.ACTIVE)
        shot = next(item for item in report["files"] if item["name"] == "BG_Screenshot_1.png")
        self.assertTrue(shot["complete"])
        self.assertTrue(shot["images_fallback"])

    def test_pdf_pages_read_as_pictures(self):
        document = {"name": "Zeichnung.pdf", "path": "/x/Zeichnung.pdf", "material_role": "technical_drawing",
                    "chunks": [{"label": f"Zeichnung.pdf — page {n}", "text": "Maßstab 1:2",
                                "visual": {"kind": "pdf_page", "path": "/x/Zeichnung.pdf", "page": n}} for n in (1, 2)]}
        self.assertEqual(w.pdf_preread_pages(document, [1, 2]), [1, 2])
        manual = {"name": "Handbuch.pdf", "material_role": "other",
                  "chunks": [{"label": f"p{n}", "text": "x", "visual": {"kind": "pdf_page", "page": n}} for n in range(1, 41)],
                  "page_inventory": [{"page": n, "page_type": "visual" if n in (7, 9) else "text"} for n in range(1, 41)]}
        self.assertEqual(w.pdf_preread_pages(manual, list(range(1, 16))), [7, 9])
        library = LocalDocumentLibrary(self.f.root / "docs.json")
        rendered = self.f.root / "page.jpg"
        Image.new("RGB", (800, 600), "white").save(rendered)
        with patch.object(LocalDocumentLibrary, "_render_pdf_page", return_value=rendered):
            groups, skipped = w.preread_groups(library, document, document["chunks"], None, self.f.root / "cache")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["labels"], ["Zeichnung.pdf — page 1", "Zeichnung.pdf — page 2"])
        self.assertEqual(skipped, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
