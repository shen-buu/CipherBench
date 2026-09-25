#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""Synthetic 5-class signal-density ladder (lambda in {0, 0.0625, ..., 1.0})."""
import os, json, argparse
import numpy as np

SEED = 20250917
W, SLOT, N_CLASSES, N_PER = 1024, 8, 5, 300
LAMS = [0.0, 0.0625, 0.125, 0.25, 0.5, 1.0]


def gen_level(base, lam):
    rng = np.random.default_rng(SEED)
    ddir = os.path.join(base, f"L{lam}", "data")
    os.makedirs(ddir, exist_ok=True)
    meta = {}
    nslots = W // SLOT
    for c in range(N_CLASSES):
        cdir = os.path.join(ddir, f"syn{c}")
        os.makedirs(cdir, exist_ok=True)
        token = bytes([0xA0 + 8 * c]) * SLOT
        for i in range(N_PER):
            buf = bytearray(rng.bytes(W))
            mask = rng.random(nslots) < lam
            for s in range(nslots):
                if mask[s]:
                    buf[s * SLOT:(s + 1) * SLOT] = token
            with open(os.path.join(cdir, f"{i}.bin"), "wb") as f:
                f.write(bytes(buf))
        meta[f"syn{c}"] = {"type": "primitives", "n": N_PER}
    with open(os.path.join(ddir, "meta.json"), "w") as f:
        json.dump(meta, f)
    print(f"L{lam}: 5 类 × 300 × 1024B 就绪", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    a = ap.parse_args()
    for lam in LAMS:
        gen_level(a.base, lam)
