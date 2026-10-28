"""Prices from a Docupedia pricing page saved next to the program."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from code_chat_agent import PricingCatalog  # noqa: E402
import price_page  # noqa: E402

APP = Path(__file__).resolve().parents[1]

# Shaped like the saved Confluence page: Creator spans rows, prices contain
# promotions, cache prices, line breaks and one EUR row.
PAGE = """<html><body><h2>Text Generation</h2>
<table class="confluenceTable"><tbody>
<tr><th>Creator</th><th>Model</th><th>Provider</th><th>Input Price (1M Tokens)</th>
<th>Output Price (1M Tokens)</th><th>Reference</th></tr>
<tr><td rowspan="3">Anthropic</td><td>Claude Opus 5.5 (<strong>New</strong>)</td><td>Google Vertex AI (GCP)</td>
<td>$4.00</td><td>$20.00</td><td><a href="#">Agent Platform Pricing</a></td></tr>
<tr><td>Claude Sonnet 4.6</td><td>Google Vertex AI (GCP)</td><td>$3.00</td><td>$15.00</td><td>x</td></tr>
<tr><td>Claude Haiku 5.5 (<strong>New</strong>)</td><td>Google Vertex AI (GCP)</td><td>$0.10</td><td>$0.50</td><td>x</td></tr>
<tr><td rowspan="3">DeepSeek</td><td>DeepSeek-V4-Pro</td><td>Azure AI Foundry (Azure)</td><td>$1.74</td><td>$3.48</td><td>x</td></tr>
<tr><td>DeepSeek-V4-Flash</td><td>Azure AI Foundry (Azure)</td><td>(Cache: $0.028) $0.19</td><td>$0.51</td><td>x</td></tr>
<tr><td>DeepSeek-V4-Flash (<strong>New</strong>)</td><td>BD Model Serving Platform (Bosch)</td>
<td>(Cache: &euro;0.014) &euro;0.068</td><td>&euro;0.153</td><td>x</td></tr>
<tr><td rowspan="3">Google</td><td>Gemini 4 Argon (<strong>New</strong>)</td><td>Google Vertex AI (GCP)</td>
<td><p>Promo until 2026-11-30: $2.00</p><p>$4.00</p></td><td><p>Promo until 2026-11-30: $10.00</p><p>$20.00</p></td><td>x</td></tr>
<tr><td>Gemini 3.6 Flash</td><td>Google Vertex AI (GCP)</td><td>Promo until 2026-12-31: $0.75<br/>$1.50</td>
<td>Promo until 2026-12-31: $3.75<br/>$7.50</td><td>x</td></tr>
<tr><td>Gemini 3.5 Flash-Lite (New)</td><td>Google Vertex AI (GCP)</td><td>$0.30</td><td>$2.50</td><td>x</td></tr>
</tbody></table>
<h2>Document Processing</h2>
<table><tr><th>Model</th><th>Price (1000 Pages)</th></tr><tr><td>Mistral Document AI</td><td>$3.00</td></tr></table>
</body></html>"""


class PricePage(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        shutil.copy(APP / "model_pricing.json", self.folder / "model_pricing.json")

    def save_page(self, html=PAGE, name="Pricing - Bosch Model Farm (BMF) - Docupedia.html"):
        (self.folder / name).write_text(html, encoding="utf-8")

    def test_parses_rows_promotions_cache_and_skips_eur(self):
        rows = {row["display_name"]: row for row in price_page.parse_pricing_html(PAGE)}
        self.assertEqual(len(rows), 8)  # EUR duplicate and page-priced table skipped
        self.assertEqual(rows["Claude Opus 5.5 (New)"]["input_usd_per_million"], 4.0)
        self.assertEqual(rows["DeepSeek-V4-Flash"]["cache_read_usd_per_million"], 0.028)
        argon = rows["Gemini 4 Argon (New)"]
        self.assertEqual((argon["input_usd_per_million"], argon["output_usd_per_million"]), (2.0, 10.0))
        self.assertEqual((argon["standard_input_usd_per_million"], argon["standard_output_usd_per_million"]), (4.0, 20.0))
        self.assertEqual(argon["promotion_ends"], "2026-11-30")

    def test_saved_page_overrides_bundled_prices_and_adds_new_models(self):
        bundled = PricingCatalog(self.folder / "model_pricing.json")
        self.assertIsNone(bundled.price_for("gemini-4-argon"))
        self.assertEqual(bundled.source, {"kind": "bundled"})
        self.save_page()
        catalog = PricingCatalog(self.folder / "model_pricing.json")
        self.assertEqual(catalog.source["kind"], "page")
        self.assertEqual(catalog.source["models"], 8)
        self.assertEqual(catalog.price_for("gemini-4-argon")["input_price"], 2.0)
        flash = catalog.price_for("deepseek-v4-flash-2026-04-23")  # dated Farm ID
        self.assertEqual((flash["input_price"], flash["cache_read_price"]), (0.19, 0.028))
        self.assertEqual(catalog.price_for("claude-haiku-5-5")["output_price"], 0.5)  # known IDs kept
        self.assertEqual(catalog.price_for("gemini-3.5-flash-lite")["input_price"], 0.3)
        # Models missing from the page keep their bundled price.
        self.assertEqual(catalog.price_for("gemini-2.5-pro")["input_price"], 1.25)

    def test_cache_price_turns_cache_tokens_into_a_known_cost(self):
        self.save_page()
        catalog = PricingCatalog(self.folder / "model_pricing.json")
        usage = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 1_000_000}
        self.assertIsNotNone(catalog.estimate("deepseek-v4-flash", None, None, usage=usage))

    def test_unrecognized_page_keeps_bundled_prices(self):
        self.save_page("<html><table><tr><th>Model</th><th>Input Price (1M Tokens)</th>"
                       "<th>Output Price (1M Tokens)</th></tr><tr><td>X</td><td>$1</td><td>$2</td></tr></table></html>")
        catalog = PricingCatalog(self.folder / "model_pricing.json")
        self.assertEqual(catalog.source["kind"], "bundled")
        self.assertIn("1 rows", catalog.source["page_error"])
        self.assertEqual(catalog.price_for("gemini-3.6-flash")["input_price"], 0.75)

    def test_other_html_files_are_ignored(self):
        self.save_page("<html><body>Notes</body></html>", name="notes.html")
        self.assertEqual(PricingCatalog(self.folder / "model_pricing.json").source, {"kind": "bundled"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
