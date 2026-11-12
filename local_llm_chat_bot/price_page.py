"""Read model prices from a saved Bosch Model Farm "Pricing" page (Docupedia).

Save the Docupedia page as HTML (Ctrl+S) into the program folder.  The
Workbench then prefers its prices over the bundled model_pricing.json.  Only
the standard library is used; nothing is downloaded.

A page is accepted only when it clearly is the pricing table and enough rows
parse; otherwise the bundled prices stay in effect.  Rows priced in another
currency than USD (e.g. EUR on the BD Model Serving Platform) are skipped,
because costs are added up in USD.
"""
from __future__ import annotations

from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

PAGE_PATTERNS = ("*.html", "*.htm")
MARKER = "input price"
MIN_ROWS = 5
MAX_PAGE_BYTES = 20_000_000
_AMOUNT = re.compile(r"([$€])\s*(\d+(?:[.,]\d+)?)")
_CACHE = re.compile(r"\(\s*cache\s*:\s*([$€])\s*(\d+(?:[.,]\d+)?)\s*\)", re.I)
_PROMO = re.compile(r"promo\w*\s+until\s+(\d{4}-\d{2}-\d{2})", re.I)


class _Tables(HTMLParser):
    """Collect every table as rows of (text, rowspan, colspan) cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, int, int]]]] = []
        self._stack: list[list[list[tuple[str, int, int]]]] = []
        self._cell: list[str] | None = None
        self._span = (1, 1)

    @staticmethod
    def _int(value: str | None) -> int:
        try:
            return max(1, min(50, int(value or 1)))
        except ValueError:
            return 1

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack and self._stack[-1]:
            values = dict(attrs)
            self._cell, self._span = [], (self._int(values.get("rowspan")), self._int(values.get("colspan")))
        elif tag in ("br", "p", "div", "li") and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack and self._stack[-1]:
            text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._stack[-1][-1].append((text, *self._span))
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _grid(rows: list[list[tuple[str, int, int]]]) -> list[list[str]]:
    """Expand rowspan/colspan so every row has its cells in the right columns."""
    grid: list[list[str]] = []
    carry: dict[int, tuple[str, int]] = {}
    for row in rows:
        out: list[str] = []
        cells = iter(row)
        column = 0
        pending = list(cells)
        while pending or column in carry:
            if column in carry:
                text, left = carry[column]
                out.append(text)
                carry[column] = (text, left - 1)
                if left - 1 <= 0:
                    del carry[column]
                column += 1
                continue
            text, rowspan, colspan = pending.pop(0)
            for _ in range(colspan):
                out.append(text)
                if rowspan > 1:
                    carry[column] = (text, rowspan - 1)
                column += 1
        grid.append(out)
    return grid


def _number(text: str) -> float:
    return float(text.replace(",", "."))


def parse_price(cell: str) -> dict[str, Any] | None:
    """'$4.00', '(Cache: $0.028) $0.19', 'Promo until 2026-11-30: $2.00 $4.00'."""
    result: dict[str, Any] = {}
    cache = _CACHE.search(cell)
    if cache:
        result["cache_currency"], result["cache"] = cache.group(1), _number(cache.group(2))
        cell = cell[:cache.start()] + cell[cache.end():]
    promo = _PROMO.search(cell)
    amounts = _AMOUNT.findall(cell)
    if not amounts:
        return None
    result["currency"] = amounts[0][0]
    if promo and len(amounts) >= 2:
        result["price"], result["standard"], result["promotion_ends"] = (
            _number(amounts[0][1]), _number(amounts[1][1]), promo.group(1))
    else:
        result["price"] = _number(amounts[0][1])
    if any(currency != result["currency"] for currency, _ in amounts):
        return None
    return result


def model_key(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\(\s*new\s*\)", "", name, flags=re.I)).strip().casefold()


def model_ids(name: str) -> list[str]:
    """Farm model IDs guessed from a display name: 'Claude Opus 5.5' -> claude-opus-5.5 / claude-opus-5-5."""
    slug = re.sub(r"[^a-z0-9.\-]+", "-", model_key(name)).strip("-")
    return list(dict.fromkeys([slug, slug.replace(".", "-")]))


def parse_pricing_html(html: str) -> list[dict[str, Any]]:
    """Text-generation rows of the BMF pricing table, as model_pricing.json entries."""
    parser = _Tables()
    parser.feed(html)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for table in parser.tables:
        grid = _grid(table)
        if not grid:
            continue
        header = [cell.casefold() for cell in grid[0]]
        try:
            model_col = next(i for i, h in enumerate(header) if h.startswith("model"))
            input_col = next(i for i, h in enumerate(header) if h.startswith(MARKER))
            output_col = next(i for i, h in enumerate(header) if h.startswith("output price"))
        except StopIteration:
            continue
        unit = "per_1000_pages" if "page" in header[input_col] else "per_1m_tokens"
        if unit != "per_1m_tokens":
            continue
        for row in grid[1:]:
            if len(row) <= max(model_col, input_col, output_col):
                continue
            name = row[model_col]
            prices_in, prices_out = parse_price(row[input_col]), parse_price(row[output_col])
            if not name or not prices_in or not prices_out:
                continue
            if prices_in["currency"] != "$" or prices_out["currency"] != "$":
                continue  # EUR rows cannot be added to USD totals
            key = model_key(name)
            if key in seen:
                continue
            seen.add(key)
            entry: dict[str, Any] = {
                "display_name": re.sub(r"\s+", " ", name).strip(),
                "input_usd_per_million": prices_in["price"],
                "output_usd_per_million": prices_out["price"],
            }
            ends = prices_in.get("promotion_ends") or prices_out.get("promotion_ends")
            if ends:
                entry["promotion_ends"] = ends
                entry["standard_input_usd_per_million"] = prices_in.get("standard", prices_in["price"])
                entry["standard_output_usd_per_million"] = prices_out.get("standard", prices_out["price"])
            if prices_in.get("cache_currency") == "$":
                entry["cache_read_usd_per_million"] = prices_in["cache"]
            entries.append(entry)
    return entries


def find_price_page(folder: Path) -> Path | None:
    """The newest saved pricing page in the program folder, if any."""
    candidates = []
    for pattern in PAGE_PATTERNS:
        for path in folder.glob(pattern):
            try:
                if path.is_file() and path.stat().st_size <= MAX_PAGE_BYTES:
                    candidates.append(path)
            except OSError:
                continue
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if MARKER in text.casefold() and "output price" in text.casefold():
            return path
    return None


def merge_page_prices(entries: list[dict[str, Any]], folder: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Overlay prices from a saved page onto the bundled entries.

    Known models keep their 'match' IDs; new models get IDs guessed from the
    page name.  Returns (entries, source description for the interface)."""
    source: dict[str, Any] = {"kind": "bundled"}
    path = find_price_page(folder)
    if not path:
        return entries, source
    try:
        page = parse_pricing_html(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # a broken page must never break pricing
        return entries, {"kind": "bundled", "page_error": f"{path.name}: {type(exc).__name__}"}
    if len(page) < MIN_ROWS:
        return entries, {"kind": "bundled", "page_error": f"{path.name}: {len(page)} rows"}
    merged = [dict(entry) for entry in entries]
    by_name = {model_key(str(entry.get("display_name", ""))): entry for entry in merged}
    price_keys = ("input_usd_per_million", "output_usd_per_million", "promotion_ends", "pricing_note",
                  "standard_input_usd_per_million", "standard_output_usd_per_million", "cache_read_usd_per_million")
    updated = added = 0
    for row in page:
        target = by_name.get(model_key(row["display_name"]))
        if target is None:
            target = {"display_name": row["display_name"], "match": model_ids(row["display_name"])}
            merged.append(target)
            by_name[model_key(row["display_name"])] = target
            added += 1
        else:
            updated += 1
        for key in price_keys:
            target.pop(key, None)
        target.update({key: value for key, value in row.items() if key != "display_name"})
        if row.get("promotion_ends"):
            target["pricing_note"] = (f"Promotional price until {row['promotion_ends']}; then USD "
                                      f"{row['standard_input_usd_per_million']:g} input / USD "
                                      f"{row['standard_output_usd_per_million']:g} output per 1M tokens.")
    saved = date.fromtimestamp(path.stat().st_mtime).isoformat()
    return merged, {"kind": "page", "file": path.name, "date": saved, "models": len(page),
                    "updated": updated, "added": added}
