import re


_LOCAL_FAST_INPUTS = {
    "hallo": "Hallo. Ich bin da.",
    "hallo isaac": "Hallo. Ich bin da.",
    "hi": "Hallo. Ich bin da.",
    "hi isaac": "Hallo. Ich bin da.",
    "hey": "Hallo. Ich bin da.",
    "hey isaac": "Hallo. Ich bin da.",
    "danke": "Gern. Ich bin da.",
    "danke isaac": "Gern. Ich bin da.",
    "guten morgen": "Guten Morgen. Ich bin da.",
    "guten morgen isaac": "Guten Morgen. Ich bin da.",
    "ist nur eine begrüßung": "Alles gut. Verstanden.",
    "war nur ein test": "Alles gut. Ich antworte stabil.",
    "nur kurz hallo": "Hallo. Ich bin da.",
    "ich wollte nur testen ob du antwortest": "Ja. Ich antworte.",
}


def normalize_low_complexity(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\wäöüß\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_low_complexity_local_input(text: str) -> bool:
    return normalize_low_complexity(text) in _LOCAL_FAST_INPUTS


def local_fast_response(text: str) -> str:
    return _LOCAL_FAST_INPUTS.get(normalize_low_complexity(text), "Ich bin da.")
