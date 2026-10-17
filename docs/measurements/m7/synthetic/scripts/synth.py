"""Synthetic inputs for the M7 VRAM / num_ctx measurement (no lecture text).

Words come from a fixed generic Urdu-script and English vocabulary written here, not from any transcript. A synthetic
window matches a target's Arabic-script and other character counts, so token estimates and real tokenisation see the
same script mix as the Day 4 windows without their content.

  synth.py shape  <day4_windows.json> <out.json>          23 windows, same ids/times/per-script char counts
  synth.py fill   <out.json> <arabic_chars> <other_chars>  one window (id 0) of the given size
  synth.py prompt <out.txt> <chars>                        placeholder English system prompt (not the real prompt)
"""

import json
import random
import sys

URDU = ("یہ ہے کہ اور میں کے لیے بھی تو اب آپ ہم وہ کیا ہو گا نہیں ایک دو بات کام وقت طرح دیکھیں سمجھ پھر یہاں "
        "اس کو سے پر جو ہوتا ہیں تھا کر رہے کچھ زیادہ کم بہت اچھا ٹھیک چیز سوال جواب").split()
ENGLISH = ("so the we this is a and of to now here you see one more thing then what about example value take next "
           "step simple okay point case way part right first second number order basically actually just").split()
PROMPT_WORDS = ("extract each concept the speaker explains in this window give its canonical English label and every "
                "other name used as aliases record relations only between labelled concepts using the allowed types "
                "mark the window important only when the speaker says so and copy the cue follow the schema exactly "
                "do not invent concepts that are not explained a passing mention is not a concept").split()


def is_arabic(ch: str) -> bool:
    o = ord(ch)
    return 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def make_text(arabic: int, other: int, rng: random.Random) -> str:
    out, a, o = [], 0, 0
    while a < arabic or o < other:
        want_urdu = a < arabic and (o >= other or a / max(arabic, 1) <= o / max(other, 1))
        w = rng.choice(URDU if want_urdu else ENGLISH)
        if out:
            out.append(" ")
            o += 1
        out.append(w)
        if want_urdu:
            a += len(w)
        else:
            o += len(w)
    return "".join(out)


def main(argv: list[str]) -> None:
    rng = random.Random(7)
    if argv[0] == "shape":
        src = json.load(open(argv[1], encoding="utf-8"))["windows"]
        wins = []
        for w in src:
            a = sum(is_arabic(c) for c in w["text"])
            wins.append({"id": w["id"], "start": w["start"], "end": w["end"],
                         "text": make_text(a, len(w["text"]) - a, rng)})
        json.dump({"windows": wins, "synthetic": True}, open(argv[2], "w", encoding="utf-8"), ensure_ascii=False)
    elif argv[0] == "fill":
        text = make_text(int(argv[2]), int(argv[3]), rng)
        json.dump({"windows": [{"id": 0, "start": 0.0, "end": 30.0, "text": text}], "synthetic": True},
                  open(argv[1], "w", encoding="utf-8"), ensure_ascii=False)
    elif argv[0] == "prompt":
        words, n = [], 0
        while n < int(argv[2]):
            w = rng.choice(PROMPT_WORDS)
            words.append(w)
            n += len(w) + 1
        open(argv[1], "w", encoding="utf-8").write("PLACEHOLDER, NOT THE M7 PROMPT. " + " ".join(words) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
