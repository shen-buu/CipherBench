#!/usr/bin/env python3
"""C_bytes x S1 damage on 16 primitives (trunc50/slide50, rf/hgb, P1, 5 seeds + E2 null). Output: results/bytes_s1_formal.json."""
import os, sys, glob, json, time
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
sys.path.insert(0, os.path.join(BASE, "host_package"))
from statistical import extract_full_features
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score

SEEDS = [7, 42, 99, 123, 2024]
WIN = 1024


def load_prims():
    import json as _j
    meta = _j.load(open(os.path.join(BASE, "data", "meta.json")))
    objs = {}
    for name, v in meta.items():
        if isinstance(v, dict) and v.get("type") == "primitives":
            d = os.path.join(BASE, "data", name)
            objs[name] = [open(f, "rb").read() for f in
                          sorted(glob.glob(os.path.join(d, "*.bin")) + glob.glob(os.path.join(d, "*.der")))]
    return objs


def damage(data, cond, rng):
    h = len(data) // 2
    if cond == "trunc50":
        # 均匀随机重填（禁零填充原则）：不埋长度标记
        return rng.bytes(h) + data[h:]
    return data[h:]          # slide50：头部 50% 被切掉，仅剩后半段


def window_p1(frag, rng):
    if len(frag) >= WIN:
        off = int(rng.integers(0, len(frag) - WIN + 1))
        return frag[off: off + WIN]
    n = len(frag)
    off = int(rng.integers(0, WIN - n + 1))
    w = bytearray(rng.bytes(WIN)); w[off: off + n] = frag
    return bytes(w)


def featurize(objs, cond, seed):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for cid, n in enumerate(objs):
        for d in objs[n]:
            X.append(extract_full_features(window_p1(damage(d, cond, rng), rng)))
            y.append(cid)
    return np.array(X), np.array(y)


def cv_macro(X, y, clf_factory, seed):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = clf_factory(seed)
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    return float(f1_score(yt, yp, average="macro"))


def main():
    objs = load_prims()
    assert len(objs) == 16 and all(len(v) == 300 for v in objs.values())
    out = {"protocol": "bytes_s1 v1", "seeds": SEEDS,
           "env": {"device": "cpu", "features": "170-dim statistical", "scene": "P1"},
           "conditions": {}}
    for cond in ["trunc50", "slide50"]:
        print(f"== {cond} ==", flush=True)
        cc = {"per_seed": {}}
        for seed in SEEDS:
            X, y = featurize(objs, cond, seed)
            cc["per_seed"][str(seed)] = {
                "rf": cv_macro(X, y, lambda s: RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=s), seed),
                "hgb": cv_macro(X, y, lambda s: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                                                               max_leaf_nodes=31, random_state=s), seed)}
            print(f"  seed {seed}: rf={cc['per_seed'][str(seed)]['rf']:.4f} hgb={cc['per_seed'][str(seed)]['hgb']:.4f}", flush=True)
        # E2 null（10 置换 × seed 42，同管线）
        null = {"rf": [], "hgb": []}
        X42, y42 = featurize(objs, cond, 42)
        for p in range(10):
            rngp = np.random.default_rng(5000 + p)
            yp = rngp.permutation(y42)
            null["rf"].append(cv_macro(X42, yp, lambda s: RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=s), 42))
            null["hgb"].append(cv_macro(X42, yp, lambda s: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                                                                          max_leaf_nodes=31, random_state=s), 42))
        cc["null"] = {k: {"mean": float(np.mean(v)), "std": float(np.std(v)), "values": v} for k, v in null.items()}
        print(f"  null rf {np.mean(null['rf']):.4f}±{np.std(null['rf']):.4f} | hgb {np.mean(null['hgb']):.4f}±{np.std(null['hgb']):.4f}", flush=True)
        out["conditions"][cond] = cc
    json.dump(out, open(os.path.join(BASE, "results", "bytes_s1_formal.json"), "w"), indent=1)
    print("→ results/bytes_s1_formal.json")


if __name__ == "__main__":
    main()
