#!/usr/bin/env python3
"""C_struct × S3：18 容器类长度按 G=16B/64B 量化后 1-NN（Table 4 补格）
5 seeds × 5-fold CV；E14（mean ± SD，SE 括号）。
输出：results/struct_s3_formal.json
"""
import os, sys, glob, json
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score

SEEDS = [7, 42, 99, 123, 2024]


def load_containers():
    meta = json.load(open(os.path.join(BASE, "data", "meta.json")))
    objs = {}
    for name, v in meta.items():
        if isinstance(v, dict) and v.get("type") in ("pkcs8", "cert"):
            d = os.path.join(BASE, "data", name)
            objs[name] = [open(f, "rb").read() for f in sorted(glob.glob(os.path.join(d, "*.der")))]
    return objs


def main():
    objs = load_containers()
    assert len(objs) == 18 and all(len(v) == 300 for v in objs.values())
    out = {"protocol": "struct_s3 v1", "seeds": SEEDS,
           "env": {"device": "cpu", "clf": "1-NN on quantized length"}, "levels": {}}
    for G in [16, 64]:
        print(f"== G={G} ==", flush=True)
        per_seed = {}
        for seed in SEEDS:
            X, y = [], []
            for cid, n in enumerate(objs):
                for d in objs[n]:
                    X.append([float(round(len(d) / G) * G)]); y.append(cid)
            X, y = np.array(X), np.array(y)
            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
            yt, yp = [], []
            for tr, te in skf.split(X, y):
                clf = KNeighborsClassifier(n_neighbors=1)
                clf.fit(X[tr], y[tr])
                yt.extend(y[te]); yp.extend(clf.predict(X[te]))
            per_seed[str(seed)] = float(f1_score(yt, yp, average="macro"))
            print(f"  seed {seed}: {per_seed[str(seed)]:.4f}", flush=True)
        vals = np.array(list(per_seed.values()))
        out["levels"][str(G)] = {"per_seed": per_seed,
                                 "mean": float(vals.mean()), "std": float(vals.std()),
                                 "SE": float(vals.std() / len(vals) ** 0.5)}
    json.dump(out, open(os.path.join(BASE, "results", "struct_s3_formal.json"), "w"), indent=1)
    print("→ results/struct_s3_formal.json")


if __name__ == "__main__":
    main()
