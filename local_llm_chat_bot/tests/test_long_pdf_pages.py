"""Long PDFs: pages are chosen by page count and content, not by file name."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat_workbench as w  # noqa: E402


def pdf(name, pages, text=lambda n: f"Allgemeine Beschreibung Seite {n}", graphic=()):
    return {"name": name, "material_role": "other",
            "chunks": [{"label": f"{name} — page {n}", "text": text(n), "visual": {"kind": "pdf_page", "page": n}}
                       for n in range(1, pages + 1)],
            "page_inventory": [{"page": n, "page_type": "visual" if n in graphic else "text"} for n in range(1, pages + 1)]}


class LongPdfPages(unittest.TestCase):
    def test_up_to_twenty_pages_everything_is_read_whatever_the_name(self):
        plan = w.reading_plan(pdf("Datenblatt_Zylinder.pdf", 20), hints={})
        self.assertEqual(plan["scope"], w.SCOPE_FULL)
        self.assertEqual(len(plan["read"]), 20)
        self.assertEqual(plan["unread"], [])

    def test_long_file_with_unclear_name_reads_fifteen_chosen_pages(self):
        def text(n):
            if n == 37:
                return "Bestellnummer DSBC-32-100-PPVA-N3 Hub 100 mm"
            if n == 52:
                return "Linearachse Linearachse Antriebseinheit Zahnriemen"
            return "Allgemeine Beschreibung"
        document = pdf("scan_0042.pdf", 80, text, graphic=(5, 60, 61, 62, 63))
        hints = {"bom_terms": {"dsbc-32-100-ppva-n3"}, "rule_terms": {"linearachse", "antriebseinheit"}, "bom_found": True}
        plan = w.reading_plan(document, hints=hints)
        self.assertEqual(plan["scope"], w.SCOPE_SELECTED)
        self.assertEqual(len(plan["read"]), w.LONG_PDF_READ_PAGES)
        self.assertEqual(len(plan["unread"]), 80 - w.LONG_PDF_READ_PAGES)
        for page in (1, 2, 3):
            self.assertIn("start", plan["reasons"][page])
        self.assertIn("bom", plan["reasons"][37])
        self.assertIn("rules", plan["reasons"][52])
        graphic = [page for page, reasons in plan["reasons"].items() if "graphic" in reasons]
        self.assertEqual(graphic, [5, 60, 61])  # at most three graphic pages
        self.assertEqual({chunk["visual"]["page"] for chunk in plan["chunks"]}, set(plan["read"]))
        self.assertEqual(w.pdf_preread_pages(document, plan["read"]), [5, 60, 61])

    def test_without_a_bom_rule_words_and_graphics_fill_the_pages(self):
        document = pdf("Angebot.pdf", 30, lambda n: "Greifer Greifereinheit" if n == 20 else "x" * n)
        plan = w.reading_plan(document, hints={"bom_terms": set(), "rule_terms": {"greifer", "greifereinheit"}, "bom_found": False})
        self.assertIn("rules", plan["reasons"][20])
        self.assertEqual(len(plan["read"]), w.LONG_PDF_READ_PAGES)

    def test_read_all_pages_still_reads_everything(self):
        plan = w.reading_plan(pdf("x.pdf", 60), full=True)
        self.assertEqual(len(plan["read"]), 60)

    def test_part_numbers_from_a_bom(self):
        found = w.part_numbers("Pos 1 | 8941234567 | DSBC-32-100-PPVA-N3 | R412010286 | 2026-10-29 | M8x20 | Menge 2")
        self.assertTrue({"8941234567", "dsbc-32-100-ppva-n3", "r412010286"} <= found)
        self.assertNotIn("2026-10-29", found)


if __name__ == "__main__":
    unittest.main(verbosity=2)
