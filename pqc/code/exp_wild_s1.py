#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""Wild-set single-certificate S1 trajectory with a frozen-pipeline reproduction gate."""
import os, sys, json, glob
import numpy as np

sys.path.insert(0, BASE)
import exp_s1 as S1                      # 冻结管线本体（不复制代码，直接复用）
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold

SEEDS = [42, 123]
WILD = os.path.join(BASE, "wild", "raw", "ct_log", "identrust_known.der")
FALSE = os.path.join(BASE, "wild", "raw", "ct_log", "dilithiumnetworks.der")
OUT = os.path.join(BASE, "results", "wild_s1_trajectory.json")


def main():
    objs = S1.load_objects()
    names = list(objs)
    print(f"冻结容器 {len(names)} 类 × {sum(len(v) for v in objs.values())} 对象", flush=True)
    wild_der = open(WILD, "rb").read()
    false_der = open(FALSE, "rb").read()
    print(f"wild {len(wild_der)}B / false-pos {len(false_der)}B", flush=True)

    gate = {}
    traj = {"objects": {"genuine": os.path.basename(WILD), "false_positive": os.path.basename(FALSE)},
            "conditions": {}}

    for cond in S1.CONDITIONS:
        traj["conditions"][cond] = {}
        for seed in SEEDS:
            rng = np.random.default_rng(seed)
            X, y = [], []
            for cid, name in enumerate(names):
                for d in objs[name]:
                    X.append(np.frombuffer(S1.make_window(d, cond, rng),
                                           dtype=np.uint8).astype(np.float32) / 255.0)
                    y.append(cid)
            X, y = np.array(X, dtype=np.float32), np.array(y)
            # 冻结折划分
            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
            # wild 窗口（独立 rng 流位置 0；oid 前缀由 find_oid 按内容定位）
            wr = np.random.default_rng(seed)
            ww = S1.make_window(wild_der, cond, wr)
            fw = S1.make_window(false_der, cond, wr)
            wX = np.frombuffer(ww, dtype=np.uint8).astype(np.float32)[None, :] / 255.0
            fX = np.frombuffer(fw, dtype=np.uint8).astype(np.float32)[None, :] / 255.0
            yt, yp = [], []
            wp, fp = [], []           # proba(mldsa87_cert) 逐折
            wl, fl = [], []           # 预测标签逐折
            for tr, te in skf.split(X, y):
                clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
                clf.fit(X[tr], y[tr])
                yt.extend(y[te]); yp.extend(clf.predict(X[te]))
                wprob = clf.predict_proba(wX)[0]
                fprob = clf.predict_proba(fX)[0]
                wp.append(float(wprob[names.index("mldsa87_cert")]))
                fp.append(float(fprob[names.index("mldsa87_cert")]))
                wl.append(names[int(clf.predict(wX)[0])])
                fl.append(names[int(clf.predict(fX)[0])])
            mac = float(__import__("sklearn.metrics", fromlist=["f1_score"])
                        .f1_score(yt, yp, average="macro"))
            # 复现门：与冻结文件逐位比对
            frozen = json.load(open(os.path.join(BASE, "results", f"s1_{cond}_seed{seed}.json")))
            gate[f"{cond}_s{seed}"] = {
                "repro": mac, "frozen": frozen["macro_f1"],
                "match": abs(mac - frozen["macro_f1"]) < 1e-12}
            traj["conditions"][cond][f"seed{seed}"] = {
                "genuine": {"label_votes": wl,
                            "proba_mldsa87_cert": [round(v, 4) for v in wp],
                            "proba_mean": round(float(np.mean(wp)), 4),
                            "proba_std": round(float(np.std(wp)), 4)},
                "false_positive": {"label_votes": fl,
                                   "proba_mldsa87_cert": [round(v, 4) for v in fp],
                                   "proba_mean": round(float(np.mean(fp)), 4)}}
            print(f"[{cond} s{seed}] gate={'OK' if gate[f'{cond}_s{seed}']['match'] else 'FAIL'}"
                  f" genuine proba={traj['conditions'][cond][f'seed{seed}']['genuine']['proba_mean']:.4f}"
                  f" labels={wl}", flush=True)
            json.dump({"gate": gate, "trajectory": traj}, open(OUT, "w"), indent=2)
    ok = sum(1 for v in gate.values() if v["match"])
    print(f"复现门 {ok}/{len(gate)} 逐位一致 → {OUT}", flush=True)


if __name__ == "__main__":
    main()
