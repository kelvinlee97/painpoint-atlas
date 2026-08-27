import re


_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_URL = re.compile(r"\bhttps?://[^\s<>\"']+|\bwww\.[^\s<>\"']+", re.IGNORECASE)
_HANDLE = re.compile(r"(?<![\w.])@[A-Z0-9_][A-Z0-9_.-]{1,31}\b", re.IGNORECASE)
_SECRET = re.compile(
    r"\b(?:sk-[A-Z0-9_-]{20,}|github_pat_[A-Z0-9_]{20,}|gh[pousr]_[A-Z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|xox[baprs]-[A-Z0-9-]{20,})\b",
    re.IGNORECASE,
)
_PHONE = re.compile(
    r"(?<!\w)(?:\+\d{8,15}|(?:\+\d{1,3}[\s.-]*)?(?:\d{2,4}[\s.-]){2,4}\d{2,4})(?!\w)"
)


def _redact_url(match: re.Match[str]) -> str:
    value = match.group(0)
    punctuation = ""
    while value and value[-1] in ".,;:!?)]}":
        punctuation = value[-1] + punctuation
        value = value[:-1]
    return "[redacted-url]" + punctuation


def _redact_phone(match: re.Match[str]) -> str:
    # ponytail: heuristic phone detection; add locale-aware parsing if coverage requires it.
    if len(re.sub(r"\D", "", match.group(0))) < 9:
        return match.group(0)
    return "[redacted-phone]"


def sanitize_public_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = _SECRET.sub("[redacted-secret]", value)
    text = _EMAIL.sub("[redacted-email]", text)
    text = _URL.sub(_redact_url, text)
    text = _PHONE.sub(_redact_phone, text)
    return _HANDLE.sub("[redacted-handle]", text)
