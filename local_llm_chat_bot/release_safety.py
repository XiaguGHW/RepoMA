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
