#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""NIST SP 800-22 battery on the 16 primitives (300 sequences each)."""
import os, json, glob, sys, math
import numpy as np

sys.path.insert(0, os.path.join(BASE, "host_package"))
from nist_battery import TESTS, to_bits_stack

DATA = os.path.join(BASE, "data")
RES = os.path.join(BASE, "results")
PRIMS = ['mlkem512_ct', 'mlkem768_ct', 'mlkem1024_ct', 'mldsa44_sig', 'mldsa65_sig', 'mldsa87_sig',
         'slhdsa_128s', 'slhdsa_128f', 'slhdsa_192s', 'slhdsa_256s', 'rsa2048_ct', 'ecdsa_p256_sig',
         'ed25519_sig', 'aes256gcm_ct_768', 'aes256gcm_ct_784', 'urandom_768']


def main():
    out = {}
    for name in PRIMS:
        d = os.path.join(DATA, name)
        files = sorted(glob.glob(os.path.join(d, "*.bin")))[:300]
        objs = [open(f, "rb").read() for f in files]
        lens = {len(o) for o in objs}
        rec = {}
        if len(lens) == 1:
            bits = to_bits_stack(objs)
            for t, fn in TESTS:
                ps = np.asarray(fn(bits), dtype=np.float64)
                rec[t] = {"pass_rate": float(np.mean(ps >= 0.01)), "mean_p": float(np.mean(ps))}
        else:
            ps_all = {t: [] for t, _ in TESTS}
            for o in objs:
                arr = np.unpackbits(np.frombuffer(o, dtype=np.uint8)).astype(np.int32).reshape(1, -1)
                for t, fn in TESTS:
                    ps_all[t].append(float(np.asarray(fn(arr))[0]))
            for t, _ in TESTS:
                ps = np.array(ps_all[t])
                rec[t] = {"pass_rate": float(np.mean(ps >= 0.01)), "mean_p": float(np.mean(ps))}
        rec["deviation_score"] = float(np.mean([rec[t]["mean_p"] < 0.01 for t, _ in TESTS]))
        out[name] = rec
        print(f"[{name}] dev={rec['deviation_score']:.2f} freq={rec['frequency']['pass_rate']:.2f} "
              f"runs={rec['runs']['pass_rate']:.2f} serial_p1={rec['serial_p1']['pass_rate']:.2f}", flush=True)
    json.dump(out, open(os.path.join(RES, "table3_nist_formal.json"), "w"), indent=2)
    print("→ results/table3_nist_formal.json")


if __name__ == "__main__":
    main()
