#!/usr/bin/env python3
"""Test-prior skew (uniform / 80-20 / 95-5) with balanced training; macro and prior-weighted F1; frozen-replay gates. Output: results/prior_skew_formal.json."""
import os, sys, json, glob, platform, datetime
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
sys.path.insert(0, os.path.join(BASE, "host_package"))
from train_baselines import load_dataset, build_data, make_clf   # noqa: E402
from sklearn.model_selection import StratifiedKFold               # noqa: E402
from sklearn.neighbors import KNeighborsClassifier                # noqa: E402
from sklearn.metrics import f1_score                              # noqa: E402
import sklearn                                                    # noqa: E402

SEEDS = [42, 123, 2024, 7, 99]
N_SAMPLE = 10200
FROZEN = os.path.join(BASE, "results")

CLASSICAL = ["aes256gcm_ct_768", "aes256gcm_ct_784", "ecdsa_p256_sig",
             "ecdsap256_cert", "ecdsap256_pkcs8", "ed25519_cert",
             "ed25519_pkcs8", "ed25519_sig", "rsa2048_cert",
             "rsa2048_ct", "rsa2048_pkcs8"]
CONTROL = ["urandom_768"]


def priors(names):
    cidx = [names.index(c) for c in CLASSICAL]
    other = [i for i in range(len(names)) if i not in cidx]
    p = {}
    p["uniform"] = np.full(len(names), 1.0 / len(names))
    p80 = np.zeros(len(names)); p95 = np.zeros(len(names))
    p80[cidx] = 0.80 / len(cidx); p80[other] = 0.20 / len(other)
    p95[cidx] = 0.95 / len(cidx); p95[other] = 0.05 / len(other)
    p["skew80_20"] = p80; p["skew95_5"] = p95
    return p


def fit_eval_pairs(X, y, factory, seed):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = factory()
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    return np.array(yt), np.array(yp)


def prior_eval(yt, yp, p, names, seed):
    rng = np.random.default_rng(seed)
    # 从池化测试预测对 (yt, yp) 按先验重采样（无训练泄漏：每对象仅作为测试出现一次）
    c = rng.choice(len(names), size=N_SAMPLE, p=p)
    pool = {i: np.where(yt == i)[0] for i in range(len(names))}
    idx = np.array([rng.choice(pool[ci]) for ci in c])
    ys, yps = yt[idx], yp[idx]
    mac = f1_score(ys, yps, labels=list(range(len(names))), average="macro", zero_division=0)
    pcls = f1_score(ys, yps, labels=list(range(len(names))), average=None, zero_division=0)
    wtd = float(np.sum(p * pcls))
    return {"macro_f1": float(mac), "weighted_f1": wtd,
            "per_class_f1_sampled": dict(zip(names, [float(x) for x in pcls])),
            "n_sampled": int(len(ys))}


def main():
    objs, meta = load_dataset(os.path.join(BASE, "data"),
                              groups=("primitives", "pkcs8", "cert"))
    names = list(objs)
    assert len(names) == 34, len(names)
    P = priors(names)

    out = {"protocol": "prior_skew v1", "n_classes": len(names),
           "classical": CLASSICAL, "control": CONTROL,
           "prior_defs": {k: {names[i]: round(float(v[i]), 6) for i in range(len(names))}
                          for k, v in P.items()},
           "channels": {}, "gate": [], "deterministic_from_frozen": {}}

    # ---- C_len: 1-NN ----
    Xlen, ylen = build_data(objs, "len", 42, "stats")[1:]
    y = np.array(ylen)
    out["channels"]["C_len"] = {}
    for seed in SEEDS:
        factory = lambda: KNeighborsClassifier(n_neighbors=1)
        yt, yp = fit_eval_pairs(Xlen, y, factory, seed)
        frozen = json.load(open(os.path.join(FROZEN, f"nn_len_seed{seed}.json")))
        d = abs(float(np.mean([f1_score(yt, yp, average='macro')])) - frozen["macro_f1"])
        out["gate"].append({"channel": "C_len", "seed": seed, "local_macro": float(f1_score(yt, yp, average='macro')),
                            "frozen": frozen["macro_f1"], "abs_delta": d})
        assert d <= 1e-6, f"C_len seed{seed} replay mismatch: {d}"
        out["channels"]["C_len"][str(seed)] = {
            k: prior_eval(yt, yp, P[k], names, seed) for k in P}
        print(f"C_len seed{seed}: macro(replay)={f1_score(yt,yp,average='macro'):.4f} gate OK | "
              + " | ".join(f"{k}: m={v['macro_f1']:.4f} w={v['weighted_f1']:.4f}"
                           for k, v in out["channels"]["C_len"][str(seed)].items()), flush=True)

    # ---- C_bytes: rf P1 ----
    out["channels"]["C_bytes"] = {}
    for seed in SEEDS:
        _, Xp1, yp1 = build_data(objs, "p1", seed, "stats")
        y = np.array(yp1)
        factory = lambda: make_clf("rf", seed, len(names), "cpu")
        yt, yp = fit_eval_pairs(Xp1, y, factory, seed)
        frozen = json.load(open(os.path.join(FROZEN, f"rf_p1_seed{seed}.json")))
        local_mac = float(f1_score(yt, yp, average='macro'))
        d = abs(local_mac - frozen["macro_f1"])
        out["gate"].append({"channel": "C_bytes", "seed": seed, "local_macro": local_mac,
                            "frozen": frozen["macro_f1"], "abs_delta": d})
        assert d <= 0.002, f"C_bytes seed{seed} replay mismatch: {d}"
        out["channels"]["C_bytes"][str(seed)] = {
            k: prior_eval(yt, yp, P[k], names, seed) for k in P}
        print(f"C_bytes seed{seed}: macro(replay)={local_mac:.4f} gate OK | "
              + " | ".join(f"{k}: m={v['macro_f1']:.4f} w={v['weighted_f1']:.4f}"
                           for k, v in out["channels"]["C_bytes"][str(seed)].items()), flush=True)

    # ---- 确定性对照：冻结 per-class F1 直接加权（Σ p_c F1_c）----
    for ch, prefix in [("C_len", "nn_len"), ("C_bytes", "rf_p1")]:
        det = {}
        for k in P:
            vals = []
            for seed in SEEDS:
                fz = json.load(open(os.path.join(FROZEN, f"{prefix}_seed{seed}.json")))
                pcf = fz["per_class_f1"]
                vals.append(float(sum(P[k][i] * pcf[names[i]] for i in range(len(names)))))
            det[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals)),
                      "per_seed": {str(s): float(v) for s, v in zip(SEEDS, vals)}}
        out["deterministic_from_frozen"][ch] = det
        print(f"{ch} deterministic: " + " | ".join(f"{k}: {v['mean']:.4f}±{v['std']:.4f}"
                                                   for k, v in det.items()), flush=True)

    out["env"] = {"script": os.path.basename(__file__),
                  "python": platform.python_version(), "numpy": np.__version__,
                  "sklearn": sklearn.__version__, "platform": platform.platform(),
                  "date": datetime.date.today().isoformat(),
                  "seeds": SEEDS, "n_sampled_per_run": N_SAMPLE,
                  "sampling": "prior-weighted resampling with replacement from pooled held-out (y, yhat); weighted-F1 = sum_c p_c F1_c(sampled)",
                  "frozen_ref": "rental_snapshot/pqc/results/{nn_len,rf_p1}_seed*.json",
                  "gate_tolerance": {"C_len": 1e-6, "C_bytes": 0.002},
                  "training": "balanced 300/class, frozen protocol v2.2 unchanged",
                  "frozen_files_modified": False}
    json.dump(out, open(os.path.join(BASE, "results", "prior_skew_formal.json"), "w"), indent=2)
    print("→ results/prior_skew_formal.json")


if __name__ == "__main__":
    main()
