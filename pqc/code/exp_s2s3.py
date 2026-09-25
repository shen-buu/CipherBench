#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""S2 outer encryption and S3 coarse-telemetry ladder (34 classes, 1-NN on lengths).
Frozen beta(G) protocol: 50 MC draws, symmetric tie-break, seed 2025; 1-NN seeds (42,123,2024); null 10 perms x seed 42. Output: results/s2s3_formal.json."""
import os, json, glob
import numpy as np

DATA = os.path.join(BASE, "data")
RES = os.path.join(BASE, "results")
os.makedirs(RES, exist_ok=True)

from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import f1_score


def load_lengths():
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    lens = {}
    for name, v in meta.items():
        if not isinstance(v, dict):
            continue
        d = os.path.join(DATA, name)
        files = sorted(glob.glob(os.path.join(d, "*.bin")) + glob.glob(os.path.join(d, "*.der")))
        lens[name] = [os.path.getsize(f) for f in files]
    return lens


def f1_1nn(X, y, seeds=(42, 123, 2024)):
    X = np.array(X, dtype=np.float64).reshape(-1, 1)
    y = np.array(y)
    macs = []
    for seed in seeds:
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
        yt, yp = [], []
        for tr, te in skf.split(X, y):
            clf = KNeighborsClassifier(n_neighbors=1)
            clf.fit(X[tr], y[tr])
            yt.extend(y[te]); yp.extend(clf.predict(X[te]))
        macs.append(f1_score(yt, yp, average="macro"))
    return float(np.mean(macs)), float(np.std(macs))


def main():
    lens = load_lengths()
    names = list(lens)
    y = np.concatenate([[i] * len(lens[n]) for i, n in enumerate(names)])
    out = {"classes": names, "n_classes": len(names), "s2": {}, "s3": {}}
    print(f"类数 {len(names)}，对象总数 {len(y)}")

    # ---- S2 ----
    X_inner = np.concatenate([[l] for n in names for l in lens[n]]).astype(np.float64)
    m, s = f1_1nn(X_inner, y)
    out["s2"]["inner"] = {"f1": m, "std": s}
    print(f"S2 内层长度 1-NN：{m:.4f} ± {s:.4f}")
    for pad, desc in [("none", "ct=len+16"), ("rand255", "随机填充 0-255B"), ("rand1024", "随机填充 0-1023B")]:
        rng = np.random.default_rng(7)
        Xo = []
        for n in names:
            for l in lens[n]:
                extra = 0 if pad == "none" else int(rng.integers(0, 256 if pad == "rand255" else 1024))
                Xo.append(float(l + extra + 16))
        m, s = f1_1nn(Xo, y)
        out["s2"][pad] = {"f1": m, "std": s}
        print(f"S2 外层（{desc}）：{m:.4f} ± {s:.4f}")

    # ---- S3（E6 三列：β(G) + 1-NN + 置换带）----
    exact = X_inner
    levels = {"exact": exact, "round16": np.round(exact / 16) * 16, "round64": np.round(exact / 64) * 64,
              "log2bin": np.floor(np.log2(np.maximum(exact, 1))), "size_class": np.digitize(exact, [1024, 2048, 4096, 8192])}
    for lv, vals in levels.items():
        groups = {}
        for v, cid in zip(vals, y):
            groups.setdefault(float(v), set()).add(cid)
        rng = np.random.default_rng(2025)
        betas = []
        for _ in range(50):
            yp = np.array([rng.choice(sorted(groups[float(v)])) for v in vals])
            betas.append(f1_score(y, yp, average="macro"))
        beta = float(np.mean(betas))
        m, s = f1_1nn(vals, y)
        # 乱标签置换带（10 置换 × 1 种子）
        nulls = []
        for p in range(10):
            ysh = np.random.default_rng(1000 + p).permutation(y)
            nm, _ = f1_1nn(vals, ysh, seeds=(42,))
            nulls.append(nm)
        out["s3"][lv] = {"beta": beta, "nn_f1": m, "nn_std": s,
                         "nn_null_mean": float(np.mean(nulls)), "nn_null_std": float(np.std(nulls)),
                         "G": len(groups), "max_collision_group": max(len(g) for g in groups.values())}
        print(f"S3 {lv:10s} β={beta:.4f} | 1-NN={m:.4f} | 零带={np.mean(nulls):.4f}±{np.std(nulls):.4f} | G={len(groups)}")
    json.dump(out, open(os.path.join(RES, "s2s3_formal.json"), "w"), indent=2)
    print("→ results/s2s3_formal.json")


if __name__ == "__main__":
    main()
