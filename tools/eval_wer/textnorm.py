"""Romanisation and text normalisation for the M4 WER gate.

One deterministic path for every config and for the reference. No LLM, no
per-word spelling tables. Every rule below is general.

romanise_word: uroman (Devanagari and Urdu/Arabic script -> Latin; Latin passes through).
L1 (light):    NFKD + strip accents, lowercase, non-alphanumerics -> space,
               collapse runs of the same letter ("theek" -> "thek"), unify whitespace.
L2 (phonetic key, revision 2, FINAL: frozen, never change after seeing results):
               L1, then in this order
                 1. "tc" -> "c", then "ch" -> "c"
                 2. drop an aspirate "h" after b p t d k g j (bh ph th dh kh gh jh)
                 3. final vowel class: the trailing run of vowel letters (a e i o u y w)
                    is mapped to one class symbol (the run never includes a word-initial
                    y/w, which is a consonant there):
                      A: a aa            E: e ai ae ay ye ey
                      I: i ee ie iy      O: o oo u ou w ow
                    A run not in the table takes the class of its last letter
                    (a -> A, e -> E, i/y -> I, o/u/w -> O).
                    L1 already collapses repeats, so aa/ee/oo reach this step as a/e/o.
                 4. word-internal vowels and y/w are dropped; a word-initial vowel is kept
                    as its class letter (same single-letter mapping), word-initial y/w stay
                 5. collapse repeated lowercase letters again
               Urdu script writes the final vowel but omits short internal vowels, and
               uroman spells long vowels with y/w (hye, kia); the key makes Urdu-script and
               Roman text comparable while keeping hai/ho/hu and ke/ki/ka apart.
               Digit-only tokens are left unchanged.
Known limitation: the key still collides some distinct words (rate recorded in the ADR).
Reference spans "[unclear]" are not normalised; the aligner treats them as wildcards.
"""
import re
import unicodedata

_VOWELS = set("aeiou")
_VOWEL_LETTERS = set("aeiouyw")
_RUN_CLASS = {"a": "A", "aa": "A",
              "e": "E", "ai": "E", "ae": "E", "ay": "E", "ye": "E", "ey": "E",
              "i": "I", "ee": "I", "ie": "I", "iy": "I",
              "o": "O", "oo": "O", "u": "O", "ou": "O", "w": "O", "ow": "O"}
_LETTER_CLASS = {"a": "A", "e": "E", "i": "I", "y": "I", "o": "O", "u": "O", "w": "O"}
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
    lo = 1 if tok[0] in "yw" else 0  # a word-initial y/w is a consonant, not part of the run
    i0 = len(tok)
    while i0 > lo and tok[i0 - 1] in _VOWEL_LETTERS:
        i0 -= 1
    run, stem = tok[i0:], tok[:i0]
    cls = (_RUN_CLASS.get(run) or _LETTER_CLASS[run[-1]]) if run else ""
    if stem:
        head = _LETTER_CLASS[stem[0]] if stem[0] in _VOWELS else stem[0]
        stem = head + "".join(c for c in stem[1:] if c not in _VOWEL_LETTERS)
    return re.sub(r"([a-z])\1+", r"\1", stem + cls)


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
