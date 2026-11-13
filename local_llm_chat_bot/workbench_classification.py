"""Classification answers: rule text and page evidence for the prompt, class-name
aliases, validation of the model's classification and the repair prompt.

The prompt assembly and model call itself (call_model) stay in chat_workbench.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from code_chat_agent import classification_manifest, parse_json
from local_document_library import LocalDocumentLibrary
from workbench_i18n import UIMessage
from workbench_materials import document_pages
from workbench_messages import ui_message


def codebook_text(documents: LocalDocumentLibrary, bg_context: dict | None) -> str:
    profile = (bg_context or {}).get("locked_profile") or {}
    profile_text = json.dumps(profile, ensure_ascii=False)
    codebook_id = (bg_context or {}).get("codebook_id")
    document = next((item for item in documents.list() if item.get("id") == codebook_id), None)
    return profile_text + "\n" + "\n".join(str(chunk.get("text", "")) for chunk in (document or {}).get("chunks", []))


CODEBOOK_CLASS_ALIASES = {
    "linear einheit": ("linear einheit", "lineareinheit", "linear unit", "linear axis", "线性单元", "直线单元", "平移单元"),
    "gantry": ("gantry", "gantry system", "portal", "portalachse", "龙门", "桁架"),
    "roboter": ("roboter", "robot", "robotic", "机器人"),
    "greifer/endeffektor": ("greifer/endeffektor", "greifer", "endeffektor", "end-effektor", "end effector", "gripper", "夹爪", "末端执行器"),
    "handhabungsbaugruppe": ("handhabungsbaugruppe", "handhabung", "handling assembly", "handling module", "搬运装配体", "搬运模块", "搬运单元"),
    "rotationseinheit": ("rotationseinheit", "rotation unit", "rotary unit", "旋转单元", "转动单元"),
    "kombinierte einheit": ("kombinierte einheit", "combined unit", "combined assembly", "组合单元", "组合装配体", "复合单元"),
}


def _codebook_name_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")).strip()


def _codebook_aliases(class_name: str) -> tuple[str, ...]:
    key = _codebook_name_key(class_name)
    aliases = [class_name]
    for known_name, known_aliases in CODEBOOK_CLASS_ALIASES.items():
        if key == _codebook_name_key(known_name):
            aliases.extend(known_aliases)
            break
    return tuple(dict.fromkeys(alias.casefold() for alias in aliases if str(alias).strip()))


def _rule_pages(rule: dict) -> list[int]:
    return [int(page) for page in rule.get("pages", []) if str(page).isdigit() and int(page) > 0]


def relevant_codebook_page_evidence(question: str, bg_context: dict | None, maximum_pages: int = 3) -> list[dict]:
    """Attach original pages for the rules most relevant to this question.

    The locked profile remains the normal prompt context.  These page images
    are a targeted audit trail for the model, not a repeated full Codebook
    upload.
    """
    profile = (bg_context or {}).get("locked_profile") or {}
    path = Path(str((bg_context or {}).get("codebook_path", "")))
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return []
    limit = max(0, int(maximum_pages))
    if not limit:
        return []
    query = question.casefold()
    words = {word for word in re.findall(r"[\wäöüß-]{3,}", query)}
    # Candidate tuples retain their source relation.  This allows a Chinese
    # question to select a German source page through a class alias, while the
    # visual page label remains strictly grounded in the locked profile.
    candidates: list[tuple[int, float, list[int], str, str]] = []
    for class_index, cls in enumerate(profile.get("classes", [])):
        if not isinstance(cls, dict):
            continue
        name = str(cls.get("name", "")).strip()
        aliases = _codebook_aliases(name)
        alias_hits = sum(1 for alias in aliases if alias and alias in query)
        class_text = " ".join([name, str(cls.get("definition", ""))] + [str(rule.get("text", "")) for group in ("decision_rules", "boundaries") for rule in cls.get(group, []) if isinstance(rule, dict)])
        lexical_hits = sum(word in class_text.casefold() for word in words)
        class_score = alias_hits * 100 + lexical_hits
        definition_pages = [int(page) for page in cls.get("evidence_pages", []) if str(page).isdigit() and int(page) > 0]
        # A named class is the strongest signal. Its evidence/definition page
        # is deliberately considered before narrower rules to yield an
        # explainable, stable fallback for short multilingual questions.
        if definition_pages:
            candidates.append((class_score, class_index * 10, definition_pages, f"class {name}", str(cls.get("definition", ""))))
        for group_index, group_name in enumerate(("decision_rules", "boundaries"), start=1):
            for rule_index, rule in enumerate(cls.get(group_name, [])):
                if not isinstance(rule, dict):
                    continue
                pages = _rule_pages(rule)
                if not pages:
                    continue
                rule_id, text = str(rule.get("id", "")).strip(), str(rule.get("text", ""))
                rule_id_hit = bool(rule_id and rule_id.casefold() in query)
                rule_hits = sum(word in text.casefold() for word in words)
                score = class_score + (80 if rule_id_hit else 0) + rule_hits
                candidates.append((score, class_index * 10 + group_index + rule_index / 1000,
                                   pages, f"class {name}, {group_name[:-1]} {rule_id or rule_index + 1}", text))
    for group_offset, group_name in enumerate(("global_rules", "table_rules"), start=1000):
        for rule_index, rule in enumerate(profile.get(group_name, [])):
            if not isinstance(rule, dict):
                continue
            pages = _rule_pages(rule)
            if not pages:
                continue
            rule_id, text = str(rule.get("id", "")).strip(), str(rule.get("text", ""))
            score = (80 if rule_id and rule_id.casefold() in query else 0) + sum(word in text.casefold() for word in words)
            candidates.append((score, group_offset + rule_index / 1000, pages,
                               f"{group_name[:-1]} {rule_id or rule_index + 1}", text))

    # When there is no reliable hit, retain only definition/core-rule pages in
    # profile order.  This is deterministic and meaningful, unlike selecting
    # arbitrary rule IDs merely because their lexical scores all equal zero.
    reliable = [item for item in candidates if item[0] > 0]
    ranked = sorted(reliable or candidates, key=lambda item: (-item[0], item[1]))
    selected, seen = [], set()
    for _score, _order, pages, relation, text in ranked:
        for page in pages:
            if page in seen:
                continue
            selected.append({"id": "locked-codebook-page", "name": path.name,
                             "label": f"{path.name} — Codebook {relation}, page {page}",
                             "text": text, "visual": {"kind": "pdf_page", "path": str(path), "page": page}})
            seen.add(page)
            if len(selected) >= limit:
                return selected
    return selected


def classification_scope(documents, context):
    if not context:
        return None
    scope = dict(context)
    source = next((item for item in documents.list() if item["id"] == context["codebook_id"]), None)
    scope["_codebook_pages"] = document_pages(source) if source else []
    return scope


def validate_classification(action: dict, evidence: list[dict], codebook: str,
                            profile: dict | None = None, bg_context: dict | None = None) -> str | None:
    """Check schema, fixed labels and provenance, not engineering semantics."""
    classification = action.get("classification")
    if not isinstance(classification, dict):
        return "Missing classification object"
    if not isinstance(profile, dict):
        return "No locked Codebook rules are available"
    names = {item["name"] for item in profile.get("classes", [])
             if isinstance(item, dict) and isinstance(item.get("name"), str)}
    label = classification.get("label")
    if not isinstance(label, str) or not label or label not in names:
        return "Class label must exactly match one locked Codebook class"
    confidence = classification.get("confidence")
    if not isinstance(confidence, str) or confidence not in {"high", "medium", "low"}:
        return "confidence must be high, medium or low"
    alternative = classification.get("alternative_label", "")
    if not isinstance(alternative, str) or (alternative and alternative not in names):
        return "alternative_label must be empty or one exact locked class"
    uncertainties = classification.get("uncertainties", [])
    if not isinstance(uncertainties, list) or any(not isinstance(item, str) for item in uncertainties):
        return "uncertainties must be a string list"

    manifest = classification_manifest(evidence, bg_context)
    supplied = {item.get("label") for item in evidence if isinstance(item.get("label"), str)}
    labels = classification.get("evidence_labels")
    if not isinstance(labels, list) or not labels or any(not isinstance(item, str) or item not in supplied for item in labels):
        return "evidence_labels must copy supplied evidence labels exactly"
    bg_refs = classification.get("bg_evidence_pages")
    if not isinstance(bg_refs, list) or not bg_refs or any(
        not isinstance(item, str) or item not in manifest["bg_labels"] or item not in labels for item in bg_refs
    ):
        return "bg_evidence_pages must copy cited BG page/sheet/row/chunk labels; Codebook-only evidence is not BG evidence"

    rules: dict[str, dict] = {}
    groups = [profile.get("global_rules", []), profile.get("table_rules", [])]
    for item in profile.get("classes", []):
        if isinstance(item, dict):
            groups.extend([item.get("decision_rules", []), item.get("boundaries", [])])
    for group in groups:
        for rule in group if isinstance(group, list) else []:
            if isinstance(rule, dict) and isinstance(rule.get("id"), str) and rule["id"]:
                if rule["id"] in rules and rules[rule["id"]] != rule:
                    return "The locked profile contains an ambiguous rule ID"
                rules[rule["id"]] = rule
    rule_ids = classification.get("codebook_rule_ids")
    if not isinstance(rule_ids, list) or not rule_ids or any(not isinstance(item, str) or item not in rules for item in rule_ids):
        return "codebook_rule_ids must reference existing string IDs from the locked rules"

    pages = classification.get("codebook_rule_pages")
    if not isinstance(pages, list) or any(type(page) is not int or page < 1 for page in pages):
        return "codebook_rule_pages must be positive integer pages, or an empty list for nonpaged rules"
    rule_refs = classification.get("codebook_rule_refs", [])
    if not isinstance(rule_refs, list) or any(not isinstance(item, str) or item not in manifest["codebook_labels"] for item in rule_refs):
        return "codebook_rule_refs must copy supplied Codebook source labels"
    if bg_context and manifest["codebook_source_kind"] == "nonpaged":
        if pages or not rule_refs:
            return "Nonpaged Codebooks require actual section/chunk refs and empty codebook_rule_pages"
    else:
        allowed_pages = {page for rule_id in rule_ids for page in rules[rule_id].get("pages", [])
                         if type(page) is int and page > 0}
        if not pages or not set(pages).issubset(allowed_pages):
            return "Codebook pages must belong to the cited rule or boundary-rule sources"
        if bg_context and not set(pages).issubset(set(bg_context.get("_codebook_pages", []))):
            return "Codebook page reference is outside the actual source document"
    return None


class ClassificationValidationError(ValueError):
    """An unvalidated classification must never become a fallback answer/plan."""


def classification_repair_prompt(base_prompt: str, reason: str, *, required: bool = True) -> str:
    obligation = ("A complete valid classification object is required; do not omit it."
                  if required else "Classification may be null in explanation mode; any non-null object must pass all rules.")
    return base_prompt + f"""

IMPORTANT: The preceding JSON action was rejected locally: {reason}.
Return the complete valid JSON action again. {obligation}
Copy exact locked class names, existing string rule IDs, and supplied reference-manifest labels.
Use physical Codebook pages only for PDF sources and only for the cited rule pages.
For nonpaged Codebooks use actual section/chunk labels in codebook_rule_refs, with codebook_rule_pages=[].
BG evidence must use BG labels, not Codebook labels. Do not add commentary outside JSON.
"""


def complete_model_action(raw):
    """Require the whole action, rather than extracting a complete inner object."""
    text = raw.strip()
    if text.startswith("```"):
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.I | re.S)
        if not fenced:
            raise ValueError("Incomplete fenced JSON action")
        text = fenced.group(1)
    if not isinstance(json.loads(text), dict):
        raise ValueError("Model action must be one complete object")
    return parse_json(text)


def validated_model_action(raw, prompt, *, evidence, scope, validation, repair, notices, language="zh"):
    """One validator for every round; one repair budget for the entire answer."""
    while True:
        action = None
        try:
            action = complete_model_action(raw)
            stray = action.get("classification")
            if not scope and stray is not None and (not isinstance(stray, dict) or not stray):
                # An empty/non-object value outside BG mode is not a classification:
                # keep the ordinary answer. A real object is still rejected below.
                action["classification"] = None
                notices.append(UIMessage('notice.classification_ignored', language))
            if action.get("classification") is not None:
                validation["required"] = True
            problem = validate_classification(
                action, evidence, "", (scope or {}).get("locked_profile"), scope
            ) if validation["required"] else None
        except (ValueError, TypeError) as exc:
            problem = str(exc)
        if not problem:
            return action
        if not scope and not validation["required"]:
            raise ValueError(problem)
        if validation["repairs"] >= 1 or not scope:
            raise ClassificationValidationError("Classification/action validation failed: " + problem)
        validation["repairs"] += 1
        notices.append(UIMessage('notice.repair', language, detail=problem))
        raw = repair(classification_repair_prompt(prompt, problem, required=validation["required"]))


def image_group_notices(data, report):
    return [ui_message(data, 'notice.image_group_overview' if item['overview'] else 'notice.image_group_full',
                       name=item['name'], count=item['count'], details=item.get('details', 0))
            for item in report.get('image_group_details', [])]


# Answer output limits.  max_tokens is a ceiling, not a charge: only generated
# tokens cost.  Answers start at the full 8192 ceiling.  An answer cut at that
# ceiling is never used; it is asked for once more, explicitly shortened.
# That bounded retry is the only extra call, and only for an answer that was
# actually cut.
ANSWER_OUTPUT_TOKENS = 8192


ANSWER_RETRY_OUTPUT_TOKENS = 8192


ANSWER_SHORTEN_INSTRUCTION = (
    "\n\nIMPORTANT: Your previous reply to this request exceeded the output limit and was discarded. "
    "Reply again with the same JSON fields, but keep \"answer\" within about 800 Chinese characters "
    "(or equivalent) and at most 3 short points per section. The JSON, including any classification "
    "object, must be complete.")
