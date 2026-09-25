#!/usr/bin/env python3
"""slide50 per-class attribution: labels-only 15-class macro + 15-class null band; frozen-macro gate (|delta|=0). Output: results/slide50_perclass_attribution.json."""
import os, sys, glob, json
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
    meta = json.load(open(os.path.join(BASE, "data", "meta.json")))
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
        return rng.bytes(h) + data[h:]
    return data[h:]          # slide50


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


def cv_details(X, y, clf_factory, seed, labels15=None, names=None):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = clf_factory(seed)
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    yt, yp = np.array(yt), np.array(yp)
    macro = float(f1_score(yt, yp, average="macro"))
    pcls = f1_score(yt, yp, average=None, labels=list(range(16)))
    # M3 修正（audit #43）：labels-only 口径——只按 15 个非 ECDSA 标签聚合，
    # 不剔除任何对象（保留误判为 ECDSA 的错误），与旧 mask 版相比无系统性上偏。
    macro15 = float(f1_score(yt, yp, labels=labels15, average="macro", zero_division=0))
    return macro, dict(zip(names, [float(x) for x in pcls])), macro15, yt.tolist(), yp.tolist()


def main():
    import platform as _platform, sklearn as _sklearn, datetime as _dt
    objs = load_prims()
    names = list(objs)
    ecdsa_idx = names.index("ecdsa_p256_sig")
    labels15 = [i for i in range(16) if i != ecdsa_idx]
    frozen = json.load(open(os.path.join(BASE, "results", "bytes_s1_formal.json")))
    out = {"protocol": "slide50_perclass_attribution v2 (M3-corrected labels-only 15-class macro)",
           "seeds": SEEDS, "per_seed": {}, "gate": [],
           "env": {"python": _platform.python_version(), "numpy": np.__version__,
                   "sklearn": _sklearn.__version__, "date": _dt.date.today().isoformat(),
                   "frozen_ref": "results/bytes_s1_formal.json", "read_only": True}}
    for seed in SEEDS:
        X, y = featurize(objs, "slide50", seed)
        for mname, factory in [("rf", lambda s: RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=s)),
                               ("hgb", lambda s: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                                                                max_leaf_nodes=31, random_state=s))]:
            macro, pcls, macro15, yts, yps = cv_details(X, y, factory, seed, labels15, names)
            fz = frozen["conditions"]["slide50"]["per_seed"][str(seed)][mname]
            d = abs(macro - fz)
            out["gate"].append({"seed": seed, "model": mname, "local_macro": macro, "frozen": fz, "abs_delta": d})
            assert d <= 1e-6, f"slide50 {mname} seed{seed} replay mismatch: {d}"
            out["per_seed"].setdefault(str(seed), {})[mname] = {
                "macro": macro, "macro_without_ecdsa_labels_only": macro15, "per_class": pcls,
                "y_true": yts, "y_pred": yps}
            print(f"seed{seed} {mname}: macro={macro:.4f} (frozen {fz:.4f}, Δ={d:.2e}) | "
                  f"15-class(labels-only)={macro15:.4f} | ECDSA={pcls['ecdsa_p256_sig']:.4f} | "
                  f"max-non-ECDSA={max(v for k, v in pcls.items() if k != 'ecdsa_p256_sig'):.4f}", flush=True)
    # 15 类置换零带（与 labels-only 口径同分母）：10 置换 × seed42 × 模型，
    # 在非 ECDSA 15 类子集上重训 CV（chance = 1/15 = 0.0667）
    print("15-class null band (10 perms × seed42):", flush=True)
    X42, y42 = featurize(objs, "slide50", 42)
    keep = np.isin(y42, labels15)
    X15, y15 = X42[keep], np.array(y42)[keep]
    null15 = {}
    for mname, factory in [("rf", lambda s: RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=s)),
                           ("hgb", lambda s: HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                                                            max_leaf_nodes=31, random_state=s))]:
        vals = []
        for p in range(10):
            rngp = np.random.default_rng(5000 + p)
            yp_ = rngp.permutation(y15)
            mac15, _, _, _, _ = cv_details(X15, yp_, factory, 42, labels15, names)
            vals.append(mac15)
        null15[mname] = {"mean": float(np.mean(vals)), "std": float(np.std(vals)), "values": vals}
        print(f"  15-class null {mname}: {np.mean(vals):.4f}±{np.std(vals):.4f}", flush=True)
    out["null_15class"] = null15

    # 汇总：逐类 mean±SD、去 ECDSA 宏均值 vs 冻结零带
    summ = {}
    for mname in ["rf", "hgb"]:
        pcs = {k: [] for k in names}
        m15 = []
        for seed in SEEDS:
            r = out["per_seed"][str(seed)][mname]
            m15.append(r["macro_without_ecdsa_labels_only"])
            for k in names:
                pcs[k].append(r["per_class"][k])
        summ[mname] = {"per_class_mean": {k: float(np.mean(pcs[k])) for k in names},
                       "per_class_sd": {k: float(np.std(pcs[k])) for k in names},
                       "macro_without_ecdsa_mean": float(np.mean(m15)),
                       "macro_without_ecdsa_sd": float(np.std(m15))}
        nz = null15[mname]
        print(f"\n{mname}: 15-class macro(labels-only) {np.mean(m15):.4f}±{np.std(m15):.4f} "
              f"vs 15-class null {nz['mean']:.4f}±{nz['std']:.4f} "
              f"(z={(np.mean(m15)-nz['mean'])/nz['std']:.1f})")
        srt = sorted(summ[mname]["per_class_mean"].items(), key=lambda kv: kv[1], reverse=True)
        print(f"  top per-class: " + " | ".join(f"{k}={v:.4f}" for k, v in srt[:5]))
    out["summary"] = summ
    out["frozen_null"] = frozen["conditions"]["slide50"]["null"]
    json.dump(out, open(os.path.join(BASE, "results", "slide50_perclass_attribution.json"), "w"), indent=1)
    print("\n→ results/slide50_perclass_attribution.json")


if __name__ == "__main__":
    main()
