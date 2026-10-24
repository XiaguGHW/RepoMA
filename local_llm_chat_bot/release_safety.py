"""Small shared release safety boundaries; no external services or state."""
import math
import os
import re


def token_count(value):
    try:
        if value is None or isinstance(value, bool): return None
        number = float(value)
        return int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_usage(raw):
    raw = dict(raw) if isinstance(raw, dict) else {}
    def first(*keys):
        return next((v for key in keys if (v := token_count(raw.get(key))) is not None), None)
    incoming = first('input_tokens', 'prompt_tokens', 'promptTokenCount', 'inputTokenCount')
    outgoing = first('output_tokens', 'completion_tokens', 'candidatesTokenCount', 'outputTokenCount')
    if 'candidatesTokenCount' in raw and not raw.get('_usage_normalized') and outgoing is not None:
        outgoing += token_count(raw.get('thoughtsTokenCount')) or 0
    total = first('total_tokens', 'totalTokenCount')
    if total is None and incoming is not None and outgoing is not None: total = incoming + outgoing
    return {**raw, 'input_tokens': incoming, 'output_tokens': outgoing, 'total_tokens': total,
            'usage_complete': incoming is not None and outgoing is not None, '_usage_normalized': True}


def safe_error(error, key=None):
    text = str(error)
    for secret in (key, os.getenv('BOSCH_FARM_SUBSCRIPTION_KEY'), os.getenv('BOSCH_FARM_API_KEY')):
        if secret: text = text.replace(secret, '[redacted]')
    text = re.sub(r'(?i)(bearer\s+|subscription-key[\s\x22\x27:=]+)[^\s,}\x22\x27]+', r'\1[redacted]', text)
    return text[:1200]


def string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def valid_rule_list(values):
    if not isinstance(values, list):
        return False
    for rule in values:
        if isinstance(rule, str):
            continue
        if not isinstance(rule, dict) or not isinstance(rule.get("text"), str):
            return False
        if "id" in rule and not isinstance(rule["id"], str):
            return False
        pages = rule.get("pages", [])
        if not isinstance(pages, list) or any(type(page) is not int for page in pages):
            return False
        if rule.get("table") is not None and not isinstance(rule["table"], dict):
            return False
    return True


def valid_rule_profile(profile):
    if not isinstance(profile, dict) or not isinstance(profile.get("classes"), list) or not profile["classes"]:
        return False
    for item in profile["classes"]:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip()
                                               for key in ("name", "definition")):
            return False
        for key in ("decision_rules", "boundaries"):
            if not valid_rule_list(item.get(key, [])):
                return False
        pages = item.get("evidence_pages", [])
        if not isinstance(pages, list) or any(type(page) is not int for page in pages):
            return False
    return (valid_rule_list(profile.get("global_rules", []))
            and valid_rule_list(profile.get("table_rules", []))
            and isinstance(profile.get("uncertainties", []), list))


def context_state_error(data):
    """Versioned persisted scope; optional legacy fields may be absent."""
    if type(data.get("context_schema_version", 1)) is not int or data.get("context_schema_version", 1) != 1:
        return "Unsupported context version"
    ids = data.get("active_source_ids", [])
    if not string_list(ids) or len(ids) != len(set(ids)):
        return "Invalid material ID list"
    for key in ("selected_codebook_path", "context_issue", "context_revision"):
        if key in data and not isinstance(data[key], str):
            return "Invalid " + key
    target = data.get("selected_target")
    if target is not None and (
        not isinstance(target, dict) or not isinstance(target.get("path"), str)
        or not target.get("path") or target.get("kind") not in ("文件", "文件夹")
        or not string_list(target.get("selected_paths", []))
        or not isinstance(target.get("codebook_path", ""), str)
    ):
        return "Invalid selected target"
    context = data.get("bg_context")
    if context is not None:
        if not isinstance(context, dict):
            return "Invalid BG context"
        if any(not isinstance(context.get(key), str) or not context[key]
               for key in ("folder", "codebook_id", "codebook_name", "codebook_path", "codebook_sha256")):
            return "Incomplete BG context"
        if not context.get("source_ids") or not string_list(context.get("source_ids")) or set(context["source_ids"]) != set(ids):
            return "BG/material scope mismatch"
        if not valid_rule_profile(context.get("locked_profile")):
            return "Invalid locked rules"
    binding = data.get("source_binding")
    if binding is not None and (
        not isinstance(binding, list)
        or any(not isinstance(item, dict) or any(not isinstance(item.get(key), str) or not item[key]
                                                for key in ("id", "path", "sha256")) for item in binding)
    ):
        return "Invalid material version binding"
    return None


def valid_document_record(document):
    if not isinstance(document, dict) or any(not isinstance(document.get(key), str) or not document[key]
                                             for key in ("id", "path", "name", "sha256")):
        return False
    chunks = document.get("chunks")
    if ("bytes" in document and (type(document["bytes"]) is not int or document["bytes"] < 0)):
        return False
    for key in ("page_inventory",):
        if key in document and (
            not isinstance(document[key], list)
            or any(not isinstance(item, dict) or type(item.get("page")) is not int or item["page"] < 1
                   for item in document[key])
        ):
            return False
    if "dfc_structure" in document and not isinstance(document["dfc_structure"], dict):
        return False
    if not isinstance(chunks, list) or not chunks:
        return False
    for chunk in chunks:
        if not isinstance(chunk, dict) or any(not isinstance(chunk.get(key), str) for key in ("label", "text")):
            return False
        visual = chunk.get("visual")
        if visual is not None and (
            not isinstance(visual, dict)
            or not isinstance(visual.get("kind"), str)
            or not isinstance(visual.get("path"), str)
            or ("page" in visual and (type(visual["page"]) is not int or visual["page"] < 1))
        ):
            return False
    return True
