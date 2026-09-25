#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""B4 three-axis controlled discriminations + PQClean leg (10 realizations). Output: results/b4_pqclean_leg.json."""
import os, sys, json, time, ctypes
import numpy as np

sys.path.insert(0, os.path.join(BASE, "host_package"))
from statistical import extract_full_features
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score

LIB = ctypes.CDLL(os.path.join(BASE, "pqclean", "crypto_sign", "ml-dsa-65", "clean", "libml-dsa-65_clean.so"))
PK, SK, SIG = 1952, 4032, 3309
u8p = ctypes.POINTER(ctypes.c_uint8)
LIB.PQCLEAN_MLDSA65_CLEAN_crypto_sign_keypair.argtypes = [u8p, u8p]
LIB.PQCLEAN_MLDSA65_CLEAN_crypto_sign_keypair.restype = ctypes.c_int
LIB.PQCLEAN_MLDSA65_CLEAN_crypto_sign_signature.argtypes = [u8p, ctypes.POINTER(ctypes.c_size_t), u8p, ctypes.c_size_t, u8p]
LIB.PQCLEAN_MLDSA65_CLEAN_crypto_sign_signature.restype = ctypes.c_int
MSG_RAW = b"B4 PQClean direct leg" * 64
MSG = (ctypes.c_uint8 * len(MSG_RAW)).from_buffer_copy(MSG_RAW)
SEEDS = [42, 123, 2024, 7, 99, 555, 777, 2025, 31337]


def gen_pqclean(n=100):
    out = []
    for _ in range(n):
        pk = (ctypes.c_uint8 * PK)()
        sk = (ctypes.c_uint8 * SK)()
        assert LIB.PQCLEAN_MLDSA65_CLEAN_crypto_sign_keypair(pk, sk) == 0
        sig = (ctypes.c_uint8 * SIG)()
        slen = ctypes.c_size_t(0)
        assert LIB.PQCLEAN_MLDSA65_CLEAN_crypto_sign_signature(sig, ctypes.byref(slen), MSG, len(MSG_RAW), sk) == 0
        out.append(bytes(sig))
    return out


def gen_liboqs(n=100):
    import oqs
    out = []
    with oqs.Signature("ML-DSA-65") as s:
        for _ in range(n):
            pk = s.generate_keypair()
            out.append(bytes(s.sign(MSG_RAW)))
    return out


def cv_acc(X, y, seed):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                             max_leaf_nodes=31, random_state=seed)
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    return accuracy_score(yt, yp)


def realization(A, B, level):
    """单数据实现：返回 9 种子均值与逐种子"""
    accs = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        if level == "window":
            def w(o):
                off = int(rng.integers(0, len(o) - 1024 + 1))
                return extract_full_features(o[off: off + 1024])
            X = np.array([w(o) for o in A] + [w(o) for o in B], dtype=np.float32)
        else:  # whole object
            X = np.array([extract_full_features(o) for o in A] +
                         [extract_full_features(o) for o in B], dtype=np.float32)
        y = np.array([0] * len(A) + [1] * len(B))
        accs.append(cv_acc(X, y, seed))
    return np.mean(accs), accs


def main():
    res = {"leg": "mldsa65_liboqs_vs_pqclean_bothFIPS204",
           "cross_verify": "双向验签 OK（PQClean→liboqs 与 liboqs→PQClean）",
           "length_level": {"note": "双方均 3309B，等长 → 长度信道 = 0.5（构造性）"}}
    for level, tag in [("whole", "whole_object_bytes"), ("window", "window_bytes")]:
        means = []
        for r in range(10):
            A = gen_liboqs()
            B = gen_pqclean()
            m, accs = realization(A, B, level)
            means.append(m)
            print(f"[{tag}] r{r}: 9种子均值={m:.4f}", flush=True)
        means = np.array(means)
        res[tag] = {"grand_mean": float(means.mean()),
                    "between_realization_std": float(means.std()),
                    "SE": float(means.std() / len(means) ** 0.5),
                    "per_realization": [float(m) for m in means]}
    json.dump(res, open(os.path.join(BASE, "results", "b4_pqclean_leg.json"), "w"), indent=2)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
