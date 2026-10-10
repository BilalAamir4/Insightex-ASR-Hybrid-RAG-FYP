"""Romanisation and text normalisation for the M4 WER gate.

One deterministic path for every config and for the reference. No LLM, no
per-word spelling tables. Every rule below is general.

romanise_word: uroman (Devanagari and Urdu/Arabic script -> Latin; Latin passes through).
L1 (light):    NFKD + strip accents, lowercase, non-alphanumerics -> space,
               collapse runs of the same letter ("theek" -> "thek"), unify whitespace.
L2 (phonetic key, FROZEN before the gate run; do not change after seeing results):
               L1, then in this order
                 1. "tc" -> "c", then "ch" -> "c"
                 2. drop an aspirate "h" after b p t d k g j (bh ph th dh kh gh jh)
                 3. drop every vowel (a e i o u) and every y/w, except a word-initial
                    vowel (word-initial y/w stay: they are consonants there)
                 4. collapse repeated letters again
               Urdu script omits short vowels, and uroman spells long vowels with y/w
               (hye, kia); the key makes Urdu-script and Roman text comparable.
               Digit-only tokens are left unchanged.
Reference spans "[unclear]" are not normalised; the aligner treats them as wildcards.
"""
import re
import unicodedata

_VOWELS = set("aeiou")
_DROP = set("aeiouyw")
_uroman = None


def romanise_word(word: str) -> str:
    global _uroman
    if word.isascii():
        return word
    if _uroman is None:
        import uroman
        _uroman = uroman.Uroman()
    return _uroman.romanize_string(word)


def is_latin_word(word: str) -> bool:
    letters = [c for c in word if c.isalpha()]
    return bool(letters) and all("LATIN" in unicodedata.name(c, "") for c in letters)


def l1_tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"([a-z])\1+", r"\1", text)
    return text.split()


def l2_token(tok: str) -> str:
    if tok.isdigit():
        return tok
    tok = tok.replace("tc", "c").replace("ch", "c")
    tok = re.sub(r"(?<=[bptdkgj])h", "", tok)
    tok = tok[:1] + "".join(c for c in tok[1:] if c not in _DROP)
    return re.sub(r"([a-z])\1+", r"\1", tok)


def collision_rate(ref_l1: list[str]) -> tuple[float, int, int]:
    """Share of distinct reference L1 words whose L2 key equals the key of a different one."""
    keys: dict[str, set[str]] = {}
    for t in set(ref_l1):
        keys.setdefault(l2_token(t), set()).add(t)
    n = sum(len(v) for v in keys.values())
    colliding = sum(len(v) for v in keys.values() if len(v) > 1)
    return colliding / n, colliding, n


def l2_tokens(l1: list[str]) -> list[str]:
    return [l2_token(t) for t in l1]
