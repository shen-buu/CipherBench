#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""B5 补充格：头窗可辨识 + 4 随机窗（5 碎片同窗数域）——乱序保留率的同域分母。
X = concat(f(head), mean(f(w0..w4)))，rf300 × 5 折 × 3 seeds，特征缓存复用 align_cache/。
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(BASE, "host_package"))
from sklearn.model_selection import StratifiedKFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score
from train_baselines import load_dataset

DATA = os.path.join(BASE, "data")
CACHE = os.path.join(BASE, "results", "align_cache")
OUT = os.path.join(BASE, "results", "align_order.json")
SEEDS = [42, 123, 2024]

out = json.load(open(OUT))
out.setdefault("order", {})
for group in ["pkcs8", "cert"]:
    objs, _ = load_dataset(DATA, groups=(group,))
    names = list(objs)
    y = np.array([c for c, n in enumerate(names) for _ in objs[n]])
    f_seeds = []
    for seed in SEEDS:
        F = np.load(os.path.join(CACHE, f"{group}_seed{seed}.npz"))["F"]
        X = np.concatenate([F[:, 5], F[:, :5].mean(axis=1)], axis=1)
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
        yt, yp = [], []
        for tr, te in skf.split(X, y):
            clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
            clf.fit(X[tr], y[tr])
            yt.extend(y[te]); yp.extend(clf.predict(X[te]))
        f_seeds.append(float(f1_score(yt, yp, average="macro")))
        print(f"{group} seed{seed}: {f_seeds[-1]:.4f}", flush=True)
    out["order"][f"{group}_B5_head_identified_rf300"] = {
        "mean": float(np.mean(f_seeds)), "std": float(np.std(f_seeds)),
        "per_seed": f_seeds, "clf": "rf300"}
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"-> {group} B5: {out['order'][f'{group}_B5_head_identified_rf300']['mean']:.4f} ± "
          f"{out['order'][f'{group}_B5_head_identified_rf300']['std']:.4f}", flush=True)
print("B5 done")
