"""Material reading plan: the material tree, document kinds, which pages of long
PDFs are read, traceable labels, pre-read groups and their limits.

Caches, coverage state and the model calls stay in chat_workbench.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from local_document_library import LocalDocumentLibrary, MAX_SHORT_PDF_PAGES, MAX_VISUAL_BYTES_PER_FILE, SUPPORTED_DOCUMENT_EXTENSIONS, material_is_recommended, material_role, material_role_label
from workbench_i18n import UIMessage
from workbench_rules import split_text_in_half


def target_tree(folder: Path, maximum_nodes: int = 5000) -> tuple[dict, bool]:
    """Return a read-only, local folder tree without indexing any material."""
    count, truncated = 0, False

    def visit(path: Path) -> dict | None:
        nonlocal count, truncated
        if count >= maximum_nodes:
            truncated = True
            return None
        try:
            is_folder = path.is_dir()
        except OSError:
            return None
        count += 1
        if not is_folder:
            suffix = path.suffix.lower()
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            role = material_role(path)
            return {"type": "file", "name": path.name, "path": str(path),
                    "relative": path.relative_to(folder).as_posix(),
                    "supported": suffix in SUPPORTED_DOCUMENT_EXTENSIONS, "bytes": size,
                    "material_role": role, "material_role_label": material_role_label(role),
                    "recommended": suffix in SUPPORTED_DOCUMENT_EXTENSIONS and material_is_recommended(path)}
        children = []
        try:
            entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError:
            entries = []
        for child in entries:
            # Do not follow junctions/symlinks outside the selected BG folder.
            if child.is_symlink():
                continue
            item = visit(child)
            if item is not None:
                children.append(item)
        return {"type": "folder", "name": path.name, "path": str(path),
                "relative": "." if path == folder else path.relative_to(folder).as_posix(), "children": children}

    tree = visit(folder)
    return tree or {"type": "folder", "name": folder.name, "path": str(folder), "children": []}, truncated


def selected_target_files(folder: Path, values: list[str]) -> list[Path]:
    """Validate explicit UI selections and keep them inside the picked folder."""
    selected, seen = [], set()
    for value in values:
        candidate = Path(value).expanduser()
        candidate = candidate if candidate.is_absolute() else folder / candidate
        try:
            path = candidate.resolve()
            path.relative_to(folder)
            paths = sorted(path.rglob('*')) if path.is_dir() else [path]
            for item in paths:
                if item.is_symlink():
                    continue
                item = item.resolve()
                item.relative_to(folder)
                if item.is_file() and item.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS and str(item) not in seen:
                    selected.append(item)
                    seen.add(str(item))
        except (OSError, ValueError):
            continue
    return selected


MATERIAL_SUMMARY_CACHE_VERSION = "material-summary-v3"  # v2: pictures read with the text; v3: page choice, kinds, data-keeping format


BG_DOSSIER_CACHE_VERSION = "bg-dossier-v1"


# Material pre-reading prompts.  Output is bounded by form (number and length
# of bullet points) so a dense group fits its token budget instead of being cut.
MATERIAL_SUMMARY_SYSTEM = "You are a careful technical evidence extractor. Use only the supplied file content. Write concise Chinese factual notes. Do not classify the Baugruppe and do not invent missing information."


# Output ceilings are high on purpose: thinking models (e.g. Gemini 2.5 Pro)
# count their reasoning against maxOutputTokens, so a small ceiling cuts the
# answer before it starts.  The format rules below keep the notes short.
MATERIAL_GROUP_TOKENS = 8192


MATERIAL_MERGE_TOKENS = 8192


BG_DOSSIER_TOKENS = 8192


# Summaries keep the data a classification needs: part numbers and
# parameters are listed in full; only the prose parts are bounded.
PREREAD_SUMMARY_CHARS = 600


PREREAD_PARAMETER_LINES = 40


DOCUMENT_KINDS = {"datasheet": "数据表", "offer": "报价单", "catalog": "目录", "manual": "手册", "drawing": "图纸",
                  "bom": "BOM", "dfc": "DFC 结构图", "cad": "CAD 截图", "other": "其他"}


MATERIAL_KIND_LINE = ("第一行必须写：文件类型：<" + "/".join(DOCUMENT_KINDS.values()) + "> — <一句话说明主要内容>。")


MATERIAL_GROUP_FORMAT = ("输出格式（按以下栏目，没有内容的栏目省略，不写引言或总结）：\n"
                         "型号/订货号/制造商：原样列出，不翻译。\n"
                         f"关键参数：每行一项“名称：数值 单位 [来源标签]”，如行程、负载、力、速度、尺寸、电压、压力；不限条数，最多 {PREREAD_PARAMETER_LINES} 行。\n"
                         "结构与功能：最多 10 条要点，每条一句，句末用方括号注明来源页面/表格/图片标签。\n"
                         "不确定处：看不清、缺失或互相矛盾的信息。\n"
                         "只写文件中的事实，相同事实只写一次，表格只摘取关键行。")


MATERIAL_MERGE_FORMAT = ("输出格式：" + MATERIAL_KIND_LINE + "然后依次为“型号/订货号/制造商”“关键参数”“结构与功能”“不确定处”栏目；"
                         "型号和参数去重后全部保留，并保留来源标签；"
                         f"“结构与功能”和“不确定处”合计不超过约 {PREREAD_SUMMARY_CHARS} 字；必须保留冲突与不确定处；不写引言或总结。")


def guess_document_kind(document: dict) -> str:
    """Local first guess from file name, role and the first pages' words."""
    role = document.get("material_role")
    if role == "dfc_structure":
        return "dfc"
    if role == "cad_screenshot":
        return "cad"
    first = " ".join(str(chunk.get("text", "")) for chunk in document.get("chunks", [])
                     if (chunk.get("visual") or {}).get("page") in (None, 1, 2))[:6000]
    text = (str(document.get("name", "")) + " " + first).casefold()
    if role == "bom" or re.search(r"st(ü|ue)ckliste|parts? list|\batb\b", text):
        return "bom"
    if re.search(r"angebot|quotation|\boffer\b|offerte", text) or ("menge" in text and "preis" in text):
        return "offer"
    if re.search(r"datenblatt|data ?sheet|technische daten|technical data", text):
        return "datasheet"
    if re.search(r"katalog|catalog", text):
        return "catalog"
    if re.search(r"betriebsanleitung|bedienungsanleitung|manual|handbuch|montageanleitung", text):
        return "manual"
    if role == "technical_drawing" or re.search(r"zeichnungsnummer|zeichnungs-nr|ma(ß|ss)stab|drawing no", text):
        return "drawing"
    return "other"


def model_document_kind(summary: str) -> str | None:
    match = re.search(r"文件类型\s*[:：]\s*([^\n—]+)", summary or "")
    if not match:
        return None
    value = match.group(1)
    for key, label in sorted(DOCUMENT_KINDS.items(), key=lambda item: -len(item[1])):
        if label.casefold() in value.casefold():
            return key
    return None


# Changing a prompt or budget above invalidates cached group notes, never a
# completed per-file summary (those stay tied to source hash, model and scope).
MATERIAL_GROUP_NOTE_VERSION = hashlib.sha256(json.dumps(
    ["material-group-v2-visual", MATERIAL_SUMMARY_SYSTEM, MATERIAL_GROUP_FORMAT, MATERIAL_GROUP_TOKENS],
    ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


# Output-limit recovery for material pre-reading.  Only a group that was cut
# at its output limit is split, exactly once, into two halves that keep the
# same budget; no group is split twice and no budget is raised.  Each split
# costs two extra calls, and one scan may spend at most material_retry_limit()
# extra calls; beyond that a cut group stays an honestly reported gap.
MATERIAL_MIN_SPLIT_CHARS = 800


MATERIAL_RETRY_SHARE = 0.2


MATERIAL_RETRY_MIN_CALLS = 2


MATERIAL_RETRY_MAX_CALLS = 10


def material_retry_limit(total_groups: int) -> int:
    """Extra calls one scan may spend: 20 % of its groups, at least 2, at most 10."""
    share = -(-max(0, total_groups) * MATERIAL_RETRY_SHARE // 1)
    return int(min(MATERIAL_RETRY_MAX_CALLS, max(MATERIAL_RETRY_MIN_CALLS, share)))


def split_material_group(group: str) -> tuple[str, str] | None:
    """Two halves of one summary group, each keeping its evidence label.

    Split between labelled chunks near the middle; a single long chunk is
    split in its text and its label line is repeated on the second half.
    """
    headers = [match.start() for match in re.finditer(r"(?m)^--- .+ ---$", group)]
    if len(headers) >= 2:
        middle = len(group) // 2
        cut = min(headers[1:], key=lambda index: abs(index - middle))
        return group[:cut], group[cut:]
    if len(group) < 2 * MATERIAL_MIN_SPLIT_CHARS:
        return None
    header, _newline, body = group.partition("\n") if group.startswith("--- ") else ("", "", group)
    first, second = split_text_in_half(body)
    if not first or not second:
        return None
    prefix = header + "\n" if header else ""
    return prefix + first + "\n", prefix + second + "\n"


def bg_dossier_identity(coverage: dict, model: str) -> dict:
    """Only source facts belong here; Codebook stays independently versioned."""
    files = [{"sha256": item.get("sha256"), "name": item.get("name"),
              "pages_read": item.get("pages_read", []), "pages_unread": item.get("pages_unread", []),
              "reading_scope": item.get("reading_scope", "")}
             for item in coverage.get("files", []) if isinstance(item, dict)]
    return {"version": BG_DOSSIER_CACHE_VERSION, "model": model,
            "files": sorted(files, key=lambda item: (str(item["sha256"]), str(item["name"]))) }


def document_ocr_audit(document: dict) -> str:
    if document.get("image_type") == "dfc_structure_screenshot":
        audit = LocalDocumentLibrary.dfc_audit(document) or {}
        return "DFC " + str(audit.get("ocr_status", "not requested"))
    pages = document.get("page_inventory", [])
    if not pages:
        return "不需要 / 无 PDF 页"
    statuses = [str(item.get("ocr_status", "not_requested")) for item in pages if item.get("page_type") != "text"]
    if not statuses:
        return "不需要（原生文字页）"
    if all(status == "ok" for status in statuses):
        return "已完成"
    if any(status == "ok" for status in statuses):
        return "部分完成"
    return statuses[0]


def document_pages(document: dict) -> list[int]:
    pages = []
    for chunk in document.get("chunks", []):
        page = (chunk.get("visual") or {}).get("page")
        if isinstance(page, int) and page not in pages:
            pages.append(page)
    return sorted(pages)


# Long PDFs: what decides how much is read is the page count and the content,
# never the file name (names are often unclear).  Up to LONG_PDF_PAGES pages
# everything is read; longer files read LONG_PDF_READ_PAGES chosen pages.
LONG_PDF_PAGES = 20


LONG_PDF_READ_PAGES = 15


LONG_PDF_START_PAGES = 3


LONG_PDF_GRAPHIC_PAGES = 3


SCOPE_FULL = "完整文本预读"


SCOPE_SELECTED = "长文件挑页预读"


_PART_NUMBER = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9./-]{3,}[A-Za-z0-9](?![A-Za-z0-9])")


_RULE_STOPWORDS = {"baugruppe", "baugruppen", "function", "funktion", "primary", "object", "objekt", "werden",
                   "wird", "einer", "eines", "diese", "dieser", "durch", "sowie", "assembly", "component", "komponente"}


def part_numbers(text: str) -> set[str]:
    """Order codes and type keys as they appear in a BOM: 8941234567, DSBC-32-100-PPVA, R412010286."""
    found = set()
    for token in _PART_NUMBER.findall(text):
        digits = sum(ch.isdigit() for ch in token)
        letters = sum(ch.isalpha() for ch in token)
        if digits >= 6 or (digits >= 2 and letters >= 2 and len(token) >= 6 and any(ch in token for ch in "-./")):
            if not re.fullmatch(r"(19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}", token):  # dates are not part numbers
                found.add(token.casefold())
    return found


def reading_hints(data: dict[str, Any], selected: list[dict]) -> dict[str, Any]:
    """Local signals for choosing pages of long files: BOM part numbers and rule words."""
    bom = [item for item in selected if item.get("material_role") == "bom"]
    bom_terms: set[str] = set()
    for item in bom:
        for chunk in item.get("chunks", []):
            bom_terms |= part_numbers(str(chunk.get("text", "")))
    rule_terms: set[str] = set()
    state = data.get("state")
    profile = ((state.data.get("bg_context") or {}).get("locked_profile") if state else None) or {}
    for item in profile.get("classes", []) if isinstance(profile, dict) else []:
        if not isinstance(item, dict):
            continue
        for word in re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", str(item.get("name", ""))):
            rule_terms.add(word.casefold())
        texts = [str(item.get("definition", ""))] + [str(rule.get("text", "")) for rule in item.get("decision_rules", []) if isinstance(rule, dict)]
        for word in re.findall(r"[A-Za-zÄÖÜäöüß]{8,}", " ".join(texts)):
            rule_terms.add(word.casefold())
    rule_terms -= _RULE_STOPWORDS
    return {"bom_terms": bom_terms, "rule_terms": set(sorted(rule_terms)[:300]), "bom_found": bool(bom)}


def page_texts(document: dict) -> dict[int, str]:
    pages: dict[int, str] = {}
    for chunk in document.get("chunks", []):
        page = (chunk.get("visual") or {}).get("page")
        if isinstance(page, int):
            pages[page] = pages.get(page, "") + "\n" + str(chunk.get("text", ""))
    return pages


def choose_long_pages(document: dict, hints: dict[str, Any] | None) -> tuple[list[int], dict[int, list[str]]]:
    """Up to LONG_PDF_READ_PAGES pages of a long PDF, each with the reasons it was chosen."""
    hints = hints or {}
    texts = page_texts(document)
    pages = sorted(texts)
    inventory = {item.get("page"): item for item in document.get("page_inventory", []) if isinstance(item, dict)}
    reasons: dict[int, list[str]] = {}
    order: list[int] = []

    def take(page: int, reason: str, limit: int = LONG_PDF_READ_PAGES) -> None:
        reasons.setdefault(page, [])
        if reason not in reasons[page]:
            reasons[page].append(reason)
        if page not in order and len(order) < limit:
            order.append(page)

    for page in pages[:LONG_PDF_START_PAGES]:
        take(page, "start")
    bom_terms, rule_terms = hints.get("bom_terms") or set(), hints.get("rule_terms") or set()
    if bom_terms:
        scored = sorted(((sum(1 for term in bom_terms if term in texts[page].casefold()), page) for page in pages), key=lambda item: (-item[0], item[1]))
        for score, page in scored:
            if score:
                take(page, "bom")
    if rule_terms:
        scored = sorted(((sum(1 for term in rule_terms if term in texts[page].casefold()), page) for page in pages), key=lambda item: (-item[0], item[1]))
        for score, page in scored[:LONG_PDF_READ_PAGES]:
            if score >= 2:
                take(page, "rules")
    graphic = [page for page in pages if (inventory.get(page) or {}).get("page_type") in {"visual", "mixed"}]
    taken_graphic = 0
    for page in graphic:
        if page in order:
            take(page, "graphic")  # already chosen: only note that it is a graphic page
            continue
        if taken_graphic >= LONG_PDF_GRAPHIC_PAGES or len(order) >= LONG_PDF_READ_PAGES:
            break
        take(page, "graphic")
        taken_graphic += 1
    for page in sorted(pages, key=lambda page: (-len(texts[page].strip()), page)):
        if len(order) >= LONG_PDF_READ_PAGES:
            break
        take(page, "dense")
    chosen = sorted(order)
    return chosen, {page: reasons[page] for page in chosen}


def reading_plan(document: dict, full: bool = False, hints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Which chunks/pages of one file are pre-read, and why (local, no model call)."""
    chunks = list(document.get("chunks", []))
    all_pages = document_pages(document)
    if full or len(all_pages) <= LONG_PDF_PAGES:
        return {"chunks": chunks, "scope": SCOPE_FULL, "read": all_pages, "unread": [], "reasons": {}}
    chosen, reasons = choose_long_pages(document, hints)
    picked = set(chosen)
    selected = [chunk for chunk in chunks if (chunk.get("visual") or {}).get("page") in picked]
    return {"chunks": selected, "scope": SCOPE_SELECTED, "read": chosen,
            "unread": [page for page in all_pages if page not in picked], "reasons": reasons}


def scope_message(plan: dict[str, Any], total: int) -> dict:
    if plan["scope"] == SCOPE_SELECTED:
        return UIMessage("material.scope_selected", read=len(plan["read"]), total=total).payload()
    return UIMessage("material.scope_full").payload()


def selected_reading_chunks(document: dict, full: bool = False, hints: dict[str, Any] | None = None) -> tuple[list[dict], str, list[int], list[int]]:
    plan = reading_plan(document, full, hints)
    return plan["chunks"], plan["scope"], plan["read"], plan["unread"]


def material_folder(data: dict[str, Any]) -> Path | None:
    """The confirmed BG/material folder that evidence labels are relative to."""
    state = data["state"].data
    folder = (state.get("bg_context") or {}).get("folder")
    target = state.get("selected_target") or {}
    if not folder and target.get("kind") == "文件夹":
        folder = target.get("path")
    return Path(folder) if folder else None


def traceable_label(document: dict, label: str, folder: Path | None) -> str:
    """Prefix a file-name label with its path inside the material folder.

    Same-named files in different subfolders (e.g. two notes.txt) otherwise
    produce identical, untraceable citations.
    """
    name = str(document.get("name", ""))
    if not folder or not name or not isinstance(label, str) or not label.startswith(name):
        return label
    try:
        relative = Path(str(document.get("path", ""))).relative_to(folder).as_posix()
    except ValueError:
        return label
    return relative + label[len(name):] if relative != name else label


def traceable_evidence(data: dict[str, Any], evidence: list[dict]) -> list[dict]:
    folder = material_folder(data)
    if not folder:
        return evidence
    documents = {item.get("id"): item for item in data["documents"].list()}
    result = []
    for item in evidence:
        document = documents.get(item.get("id"))
        label = traceable_label(document, item.get("label", ""), folder) if document else item.get("label")
        result.append(dict(item, label=label) if label != item.get("label") else item)
    return result


def summary_groups(document: dict, chunks: list[dict], limit: int = 24_000, folder: Path | None = None) -> list[str]:
    groups, current = [], ""
    for chunk in chunks:
        label = traceable_label(document, chunk.get('label', document.get('name', 'file')), folder)
        part = f"--- {label} ---\n{chunk.get('text', '')}\n"
        if current and len(current) + len(part) > limit:
            groups.append(current)
            current = part
        else:
            current += part
    if current:
        groups.append(current)
    return groups


# Pictures read together with the text during pre-reading.  The same
# per-request budget as an answer (count and bytes) keeps Farm uploads safe.
PREREAD_IMAGES_PER_CALL = 5


PREREAD_IMAGE_BYTES_PER_CALL = 2_400_000


PREREAD_PDF_IMAGE_PAGES = 5


PREREAD_DFC_SEGMENTS_PER_CALL = 4


PREREAD_VISUAL_INSTRUCTION = ("本组随附 {count} 张图片（清单见文本开头）。请同时描述图中可见的视图、零件、结构层级、"
                              "标题栏信息（图号、名称、版本）和关键尺寸；来自图片的要点请标注对应的图片标签。")


def pdf_preread_pages(document: dict, read_pages: list[int]) -> list[int]:
    """Which read pages of a PDF are also looked at as pictures.

    A short PDF or a technical drawing: every page (its views, title block
    and BOM can sit on different sheets).  Otherwise the pages whose local
    inventory says they are mostly graphics (drawings, scans, mixed pages)."""
    inventory = {item.get("page"): item for item in document.get("page_inventory", []) if isinstance(item, dict)}
    total = len(document_pages(document))
    if total <= MAX_SHORT_PDF_PAGES or document.get("material_role") == "technical_drawing":
        pages = list(read_pages)
    else:
        pages = [page for page in read_pages if (inventory.get(page) or {}).get("page_type") in {"visual", "mixed"}]
        if total > LONG_PDF_PAGES:
            return pages[:LONG_PDF_GRAPHIC_PAGES]
    return pages[:PREREAD_PDF_IMAGE_PAGES]


def preread_groups(documents: "LocalDocumentLibrary", document: dict, read_chunks: list[dict],
                   folder: Path | None, cache_dir: Path) -> tuple[list[dict], list[str]]:
    """Pre-read groups of one file: text plus the pictures that belong to it.

    Returns ([{"text", "images": [path], "labels": [str]}], skipped labels).
    Text is grouped exactly as before; a PDF page picture rides with the
    group that holds that page, an image file or DFC crop forms its own
    group.  The picture list is written into the group text, so a cached
    note is only reused for the same text and the same pictures."""
    skipped: list[str] = []
    suffix = Path(str(document.get("path", ""))).suffix.casefold()
    name = document.get("name", "file")

    def prepared(make, label, max_bytes=MAX_VISUAL_BYTES_PER_FILE) -> str | None:
        try:
            output = make()
        except Exception:
            output = None
        if not output or not Path(output).is_file() or Path(output).stat().st_size > max(max_bytes, PREREAD_IMAGE_BYTES_PER_CALL):
            skipped.append(label)
            return None
        return str(output)

    def finish(text: str, images: list[str], labels: list[str]) -> dict:
        kept: list[str] = []
        kept_labels: list[str] = []
        used = 0
        for path, label in zip(images, labels):
            size = Path(path).stat().st_size
            if len(kept) >= PREREAD_IMAGES_PER_CALL or used + size > PREREAD_IMAGE_BYTES_PER_CALL:
                skipped.append(label)
                continue
            kept.append(path)
            kept_labels.append(label)
            used += size
        if kept:
            listing = "; ".join(f"图{i} = {label}" for i, label in enumerate(kept_labels, start=1))
            text = f"[随附图片：{listing}]\n{text}"
        return {"text": text, "images": kept, "labels": kept_labels}

    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        source = Path(str(document.get("path", "")))
        structure = document.get("dfc_structure")
        manifest: dict[str, Any] = structure if isinstance(structure, dict) else {}
        segments = [item for item in manifest.get("segments", []) if isinstance(item, dict) and item.get("path")]
        base = "\n".join(f"--- {traceable_label(document, chunk.get('label', name), folder)} ---\n{chunk.get('text', '')}"
                         for chunk in read_chunks)
        if not segments:
            image = prepared(lambda: documents._prepare_image(source, cache_dir), name)
            return [finish(base, [image] if image else [], [name] if image else [])], skipped
        groups = []
        for start in range(0, len(segments), PREREAD_DFC_SEGMENTS_PER_CALL):
            batch = segments[start:start + PREREAD_DFC_SEGMENTS_PER_CALL]
            images, labels, texts = [], [], [base]
            for segment in batch:
                label = f"{name} DFC Abschnitt {segment.get('part')}"
                image = prepared(lambda: documents._prepare_image(Path(str(segment["path"])), cache_dir,
                                                                 max_bytes=520_000, max_edge=2600), label, 520_000)
                if image:
                    images.append(image)
                    labels.append(label)
                ocr = str(segment.get("ocr_text", "")).strip()
                if ocr:  # the DFC OCR now reaches the pre-read, not only answers
                    texts.append(f"[DFC Struktur OCR, Abschnitt {segment.get('part')}]\n{ocr}")
            groups.append(finish("\n\n".join(texts), images, labels))
        return groups, skipped

    texts = summary_groups(document, read_chunks, folder=folder)
    pages_of: list[set[int]] = [set() for _ in texts]
    # Same grouping walk as summary_groups, recording which pages each group holds.
    index, current = 0, ""
    for chunk in read_chunks:
        part = f"--- {traceable_label(document, chunk.get('label', name), folder)} ---\n{chunk.get('text', '')}\n"
        if current and len(current) + len(part) > 24_000:
            index, current = index + 1, part
        else:
            current += part
        page = (chunk.get("visual") or {}).get("page")
        if isinstance(page, int) and index < len(pages_of):
            pages_of[index].add(page)
    images_of: list[list[str]] = [[] for _ in texts]
    labels_of: list[list[str]] = [[] for _ in texts]
    if suffix == ".pdf":
        read_pages = sorted(set().union(*pages_of)) if pages_of else []
        for page in pdf_preread_pages(document, read_pages):
            label = f"{name} — page {page}"
            image = prepared(lambda: documents._render_pdf_page(Path(str(document["path"])), page, cache_dir), label)
            if not image:
                continue
            target = next((i for i, pages in enumerate(pages_of) if page in pages), None)
            if target is not None:
                images_of[target].append(image)
                labels_of[target].append(label)
    return [finish(text, images_of[i], labels_of[i]) for i, text in enumerate(texts)], skipped


def coverage_summary_for_answer(coverage: dict | None) -> dict | None:
    """Local, auditable reading facts shown next to a classification answer."""
    if not coverage or not coverage.get("files"):
        return None
    files = []
    for item in coverage.get("files", []):
        if not isinstance(item, dict):
            continue
        files.append({
            "name": item.get("name", "未知文件"),
            "scope": item.get("reading_scope", "已读取"),
            "scope_message": item.get("reading_scope_message"),
            "pages_total": item.get("pages_total", 0),
            "pages_read": item.get("pages_read", []),
            "pages_unread": item.get("pages_unread", []),
            "cache_status": item.get("cache_status", ""),
            "complete": bool(item.get("complete")),
        })
    return {"files": files, "complete": bool(coverage.get("complete")),
            "reused_files": int(coverage.get("reused_files", 0)),
            "created_files": int(coverage.get("created_files", 0)),
            "model_calls": int(coverage.get("model_calls", 0))}
