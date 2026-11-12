"""Small shared release safety boundaries; no external services or state."""
import math
import os
import re
from typing import Any


# Separates the stable start of a prompt (identical across turns: locked rules,
# dossier) from the per-turn rest.  Claude caches everything before it; other
# providers receive a plain paragraph break and benefit from the stable prefix.
PROMPT_CACHE_BREAK = "\n\n<<<WORKBENCH_PROMPT_CACHE_BREAK>>>\n\n"


def token_count(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
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
    detail = raw.get('prompt_tokens_details')
    detail = detail if isinstance(detail, dict) else {}
    cache_read = (token_count(raw['cache_read_input_tokens']) if 'cache_read_input_tokens' in raw else
                  token_count(raw['cachedContentTokenCount']) if 'cachedContentTokenCount' in raw else
                  token_count(detail['cached_tokens']) if 'cached_tokens' in detail else 0)
    cache_write = token_count(raw['cache_creation_input_tokens']) if 'cache_creation_input_tokens' in raw else 0
    # Claude reports uncached input separately; OpenAI/Gemini include cache hits
    # in their prompt total. Canonical input is the total in every provider.
    if not raw.get('_usage_normalized') and 'input_tokens' in raw and 'prompt_tokens' not in raw and (
            'cache_read_input_tokens' in raw or 'cache_creation_input_tokens' in raw):
        uncached = incoming
        incoming = incoming + cache_read + cache_write if all(v is not None for v in (incoming, cache_read, cache_write)) else None
    else:
        uncached = token_count(raw.get('uncached_input_tokens')) if raw.get('_usage_normalized') else (
            incoming - cache_read - cache_write if all(v is not None for v in (incoming, cache_read, cache_write)) and incoming >= cache_read + cache_write else None)
    total = first('total_tokens', 'totalTokenCount')
    if total is None and incoming is not None and outgoing is not None:
        total = incoming + outgoing
    return {**raw, 'input_tokens': incoming, 'output_tokens': outgoing, 'total_tokens': total,
            'uncached_input_tokens': uncached, 'cache_read_input_tokens': cache_read,
            'cache_creation_input_tokens': cache_write,
            'usage_complete': incoming is not None and outgoing is not None and uncached is not None and cache_read is not None and cache_write is not None,
            '_usage_normalized': True}


def summarize_usage(records):
    """Keep unknown totals separate from known subtotals, including true zero."""
    records = [normalize_usage(record) for record in records]
    summary: dict[str, Any] = {'requests': len(records)}
    fields = {'input': 'input_tokens', 'output': 'output_tokens', 'total': 'total_tokens',
              'cache_read': 'cache_read_input_tokens', 'cache_write': 'cache_creation_input_tokens'}
    for name, key in fields.items():
        values = [record[key] for record in records]
        summary['known_' + name] = sum(value for value in values if value is not None)
        summary[name] = summary['known_' + name] if all(value is not None for value in values) else None
    summary['usage_complete'] = all(record['usage_complete'] for record in records)
    for name, key in [('reasoning', 'reasoning_tokens'), ('gemini_thinking', 'thoughtsTokenCount')]:
        values = []
        for record in records:
            detail = record.get('completion_tokens_details') or record.get('output_tokens_details') or {}
            source = detail if name == 'reasoning' and isinstance(detail, dict) else record
            values.append(token_count(source[key]) if key in source else 0)
        summary[name] = sum(values) if all(v is not None for v in values) else None
    def valid(cost):
        return isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0
    costs = [record.get('cost_usd') for record in records]
    # A request priced only in part contributes its priced part to the known
    # subtotal; the token types without a price are listed, never guessed.
    summary['known_cost_usd'] = math.fsum(cost if valid(cost) else record.get('known_cost_usd')
                                          for cost, record in zip(costs, records)
                                          if valid(cost) or valid(record.get('known_cost_usd')))
    summary['cost_complete'] = all(valid(cost) for cost in costs)
    summary['cost_usd'] = summary['known_cost_usd'] if summary['cost_complete'] else None
    summary['unpriced_detail'] = unpriced_detail(records)
    return summary


def unpriced_detail(records):
    """Token types (or requests) that could not be priced, by reason."""
    detail: dict[str, int] = {}
    for record in records:
        cost = record.get('cost_usd')
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            continue
        tokens = record.get('unpriced_tokens')
        if isinstance(tokens, dict) and tokens:
            for kind, count in tokens.items():
                detail[kind] = detail.get(kind, 0) + (token_count(count) or 0)
        elif not record.get('usage_complete'):
            detail['usage_missing_requests'] = detail.get('usage_missing_requests', 0) + 1
        else:
            detail['model_requests'] = detail.get('model_requests', 0) + 1
    return detail


def redact_secrets(value, key=None):
    """Replace the active Farm key values in text without truncating it.

    Only exact secret values are replaced, so ordinary engineering text is
    never rewritten. Short values are ignored to avoid accidental matches.
    """
    if type(value) is not str:  # Keep structured UI messages (str subclasses) intact.
        return value
    for secret in (key, os.getenv('BOSCH_FARM_SUBSCRIPTION_KEY'), os.getenv('BOSCH_FARM_API_KEY')):
        if isinstance(secret, str) and len(secret.strip()) >= 8:
            value = value.replace(secret.strip(), '[redacted]')
    return value


def safe_error(error, key=None):
    text = str(error)
    for secret in (key, os.getenv('BOSCH_FARM_SUBSCRIPTION_KEY'), os.getenv('BOSCH_FARM_API_KEY')):
        if secret:
            text = text.replace(secret, '[redacted]')
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
