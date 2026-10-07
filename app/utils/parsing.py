"""Tolerant parsing helpers: LLM JSON, prices, Hindi/Hinglish numerals."""
import json
import re
from typing import Any, Dict, List, Optional

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

HINDI_NUMBER_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "dus": 10,
    "bees": 20, "pachas": 50, "pachaas": 50, "sau": 100, "hazar": 1000, "hajar": 1000,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "hundred": 100,
}


def extract_json(text: str) -> Optional[Any]:
    """LLMs love markdown fences and preambles. Dig the JSON object out anyway."""
    if not text:
        return None
    candidates: List[str] = []
    fenced = _JSON_FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)
    for chunk in candidates:
        chunk = chunk.strip()
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass
        start, end = chunk.find("{"), chunk.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(chunk[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def extract_json_object(text: str) -> Dict:
    data = extract_json(text)
    return data if isinstance(data, dict) else {}


def parse_price(text: str) -> Optional[float]:
    """'₹30', 'Rs. 30', '30 rupaye', '30/-' -> 30.0"""
    if not text:
        return None
    cleaned = text.replace(",", "")
    match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
    if not match:
        return None
    value = float(match.group(1))
    return value if 0 < value < 10_000_000 else None


def parse_amount_words(text: str) -> Optional[float]:
    """'paanch sau rupaye' -> 500. Used as a safety net behind the LLM."""
    if not text:
        return None
    direct = parse_price(text)
    if direct is not None:
        return direct
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    total, current = 0.0, 0.0
    matched = False
    for token in tokens:
        value = HINDI_NUMBER_WORDS.get(token)
        if value is None:
            continue
        matched = True
        if value >= 100:
            current = (current or 1) * value
            total += current
            current = 0.0
        else:
            current += value
    total += current
    return total if matched and total > 0 else None


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def clamp_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
