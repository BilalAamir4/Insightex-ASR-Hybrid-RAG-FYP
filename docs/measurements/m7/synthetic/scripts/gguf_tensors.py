"""List a GGUF file's tensors (name, shape, type, bytes) from its header; reads only the header. Standalone.

  gguf_tensors.py <file.gguf>
"""

import struct
import sys
from collections import defaultdict

# ggml type -> (block elements, block bytes)
TYPES = {0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20), 6: (32, 22), 7: (32, 24), 8: (32, 34), 9: (32, 36),
         10: (256, 84), 11: (256, 110), 12: (256, 144), 13: (256, 176), 14: (256, 210), 15: (256, 292),
         30: (1, 2)}
NAMES = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 10: "Q2_K", 11: "Q3_K",
         12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K", 30: "BF16"}
SCALAR = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}


def main(path: str) -> None:
    f = open(path, "rb")  # noqa: SIM115

    def rd(fmt):
        size = struct.calcsize("<" + fmt)
        return struct.unpack("<" + fmt, f.read(size))[0]

    def rstr():
        return f.read(rd("Q")).decode("utf-8", "replace")

    def skip_value(t):
        if t in SCALAR:
            rd(SCALAR[t])
        elif t == 8:
            rstr()
        elif t == 9:
            et, n = rd("I"), rd("Q")
            for _ in range(n):
                skip_value(et)
        else:
            raise ValueError(f"unknown kv type {t}")

    assert f.read(4) == b"GGUF"
    rd("I")
    n_tensors, n_kv = rd("Q"), rd("Q")
    for _ in range(n_kv):
        rstr()
        skip_value(rd("I"))
    groups = defaultdict(lambda: [0, 0])
    rows = []
    for _ in range(n_tensors):
        name = rstr()
        dims = [rd("Q") for _ in range(rd("I"))]
        t = rd("I")
        rd("Q")
        n = 1
        for d in dims:
            n *= d
        be, bb = TYPES[t]
        size = n // be * bb
        rows.append((name, dims, NAMES.get(t, t), size))
        g = "blk.*" if name.startswith("blk.") else name
        groups[g][0] += size
        groups[g][1] += 1
    total = sum(r[3] for r in rows)
    print(f"{n_tensors} tensors, {total / 2**20:.2f} MiB")
    for g, (size, count) in sorted(groups.items(), key=lambda x: -x[1][0]):
        detail = next(((d, ty) for nm, d, ty, _ in rows if nm == g), ("", ""))
        print(f"{size / 2**20:10.2f} MiB  {count:4d}  {g}  {detail[0]} {detail[1]}")


if __name__ == "__main__":
    main(sys.argv[1])
