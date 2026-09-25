#!/usr/bin/env python3
"""
开集拒绝校准实验（§5.9）—— CipherBench-PQC
====================================================
设计（内部审核会定稿）：
- 34 类中每 seed 分层留出 8 类 unknown（2 ML-KEM / 2 ML-DSA / 1 SLH-DSA /
  1 ECDSA / 1 RSA / 1 AES-GCM），仅测试时出现；剩余 26 类为 known。
- 5 seeds（冻结约定 7/42/99/123/2024）× 窗口协议 P1/P2。
- 拒绝基线：(a) MSP（RF 最大概率阈值）(b) 马氏距离（170 维特征，逐折高斯）
  (c) 熵阈值。RF = 300 树，170 维统计特征，5-fold CV out-of-fold 打分
  （known 对象由未见折打分；unknown 对象取 5 折模型平均分）。
- 指标：AUROC、FPR@95TPR、拒绝率 5%/10%/20% 下的 known macro-F1（选择性预测衰减）。
- E2：10 次标签置换 × 1 seed（42）× 协议 → AUROC 零带（与论文 E2 惯例一致）。
输出：results/open_set_formal.json（含 env 字段）。
"""
import json, os, sys, glob, time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "host_package"))
from statistical import extract_full_features          # noqa: E402
from train_baselines import make_window                # noqa: E402

from sklearn.ensemble import RandomForestClassifier   # noqa: E402
from sklearn.model_selection import StratifiedKFold   # noqa: E402
from sklearn.metrics import f1_score, roc_auc_score   # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
SEEDS = [7, 42, 99, 123, 2024]
NULL_PERMS = 10
NULL_SEED = 42
REJ_RATES = [0.05, 0.10, 0.20]

FAMILIES = {
    "mlkem":  ["mlkem512_ct", "mlkem768_ct", "mlkem1024_ct"],
    "mldsa":  ["mldsa44_sig", "mldsa65_sig", "mldsa87_sig"],
    "slhdsa": ["slhdsa_128s", "slhdsa_128f", "slhdsa_192s", "slhdsa_256s"],
    "ecdsa":  ["ecdsa_p256_sig"],
    "rsa":    ["rsa2048_ct"],
    "aes":    ["aes256gcm_ct_768", "aes256gcm_ct_784"],
}
PICKS = {"mlkem": 2, "mldsa": 2, "slhdsa": 1, "ecdsa": 1, "rsa": 1, "aes": 1}


def load_objects():
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    objs, names = {}, []
    for name, v in meta.items():
        if not isinstance(v, dict):
            continue
        names.append(name)
        d = os.path.join(DATA, name)
        files = sorted(glob.glob(os.path.join(d, "*.bin")) + glob.glob(os.path.join(d, "*.der")))
        objs[name] = [open(f, "rb").read() for f in files]
    return objs, names


def pick_unknown(rng):
    u = []
    for fam, pool in FAMILIES.items():
        k = PICKS[fam]
        idx = rng.choice(len(pool), size=k, replace=False)
        u.extend([pool[i] for i in sorted(idx)])
    return sorted(u)


def featurize_windowed(objs, classes, scene, rng):
    """classes: list of class names; returns X (n,170), y (int ids), per-object rng stream."""
    X, y = [], []
    for cid, name in enumerate(classes):
        for d in objs[name]:
            w = make_window(d, scene, rng)
            X.append(extract_full_features(w))
            y.append(cid)
    return np.array(X, dtype=np.float64), np.array(y)


def mahalanobis_model(Xtr, ytr):
    """per-class means + shared covariance (+ridge), returns (means, inv_cov)."""
    means = np.array([Xtr[ytr == c].mean(axis=0) for c in np.unique(ytr)])
    cov = np.cov(Xtr, rowvar=False) + 1e-6 * np.eye(Xtr.shape[1])
    inv = np.linalg.inv(cov)
    return means, inv


def mahal_score(X, means, inv):
    """min over classes of squared Mahalanobis distance."""
    d = np.full(len(X), np.inf)
    for m in means:
        z = X - m
        d = np.minimum(d, np.einsum("ij,jk,ik->i", z, inv, z))
    return np.sqrt(d)


def run_comb(objs, unknown_names, seed, scene):
    """One (seed, scene) combination. Returns dict with metrics + null placeholder.

    协议（v2，修正 v1 的打分不对称缺陷）：单模型 80/20 划分 —— known 类按 240/60
    划分为训练/测试，unknown 全部入测试；所有对象（known-test 与 unknown）由同一个
    模型打分，保证 ID/OOD 打分对称，置换零带因此回归 0.5 语义。
    """
    known_names = [n for n in objs if n not in set(unknown_names)]

    rng_x = np.random.default_rng(seed)
    Xk, yk = featurize_windowed(objs, known_names, scene, rng_x)
    rng_u = np.random.default_rng(1000 + seed)
    Xu, _ = featurize_windowed(objs, unknown_names, scene, rng_u)

    # per-class 80/20 split (240 train / 60 test), single model
    rng_sp = np.random.default_rng(2000 + seed)
    tr_idx, te_idx = [], []
    for c in np.unique(yk):
        idx = np.where(yk == c)[0]
        perm = rng_sp.permutation(len(idx))
        tr_idx.append(idx[perm[:240]])
        te_idx.append(idx[perm[240:]])
    tr_idx = np.concatenate(tr_idx); te_idx = np.concatenate(te_idx)

    clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
    clf.fit(Xk[tr_idx], yk[tr_idx])
    proba_k = clf.predict_proba(Xk[te_idx])
    yk_te = yk[te_idx]
    proba_u = clf.predict_proba(Xu)
    means, inv = mahalanobis_model(Xk[tr_idx], yk[tr_idx])
    mahal_k = mahal_score(Xk[te_idx], means, inv)
    mahal_u = mahal_score(Xu, means, inv)
    n_known = len(yk_te)

    msp_k = proba_k.max(axis=1)
    msp_u = proba_u.max(axis=1)
    ent_k = -np.sum(proba_k * np.log(np.clip(proba_k, 1e-12, 1.0)), axis=1)
    ent_u = -np.sum(proba_u * np.log(np.clip(proba_u, 1e-12, 1.0)), axis=1)

    # known-class macro-F1 baseline (no rejection)
    pred_k = proba_k.argmax(axis=1)
    f1_base = f1_score(yk_te, pred_k, average="macro")

    res = {}
    for tag, s_k_id, s_u_id in [  # (higher = more ID-like)
        ("msp", msp_k, msp_u),
        ("mahal", -mahal_k, -mahal_u),
        ("entropy", -ent_k, -ent_u),
    ]:
        y_bin = np.concatenate([np.ones(n_known), np.zeros(len(Xu))])
        s_all = np.concatenate([s_k_id, s_u_id])
        auroc = float(roc_auc_score(y_bin, s_all))
        thr = np.quantile(s_k_id, 0.05)  # 95% of known accepted
        fpr95 = float(np.mean(s_u_id >= thr))
        # selective-prediction F1 decay over the combined pool
        oodness = -s_all  # reject the most OOD-looking
        order = np.argsort(-oodness)
        decay = {}
        for r in REJ_RATES:
            n_rej = int(round(r * len(order)))
            keep = np.sort(order[n_rej:])
            keep_k = keep[keep < n_known]
            if len(keep_k) == 0:
                decay[str(r)] = None
                continue
            # macro-F1 over known classes restricted to remaining known objects
            f1 = f1_score(yk_te[keep_k], pred_k[keep_k], average="macro",
                         labels=range(len(known_names)), zero_division=0)
            decay[str(r)] = float(f1)
        res[tag] = {"auroc": auroc, "fpr95": fpr95, "f1_decay": decay}

    return {"unknown_classes": unknown_names, "n_known": len(known_names),
            "closed_f1": float(f1_base), "baselines": res}


def run_null(objs, unknown_names, scene, perms=NULL_PERMS, seed=NULL_SEED):
    """E2 label-permutation null for AUROC (10 perms x 1 seed, v2 对称打分协议)."""
    known_names = [n for n in objs if n not in set(unknown_names)]
    rng_x = np.random.default_rng(seed)
    Xk, yk = featurize_windowed(objs, known_names, scene, rng_x)
    rng_u = np.random.default_rng(1000 + seed)
    Xu, _ = featurize_windowed(objs, unknown_names, scene, rng_u)
    rng_sp = np.random.default_rng(2000 + seed)
    tr_idx, te_idx = [], []
    for c in np.unique(yk):
        idx = np.where(yk == c)[0]
        perm = rng_sp.permutation(len(idx))
        tr_idx.append(idx[perm[:240]])
        te_idx.append(idx[perm[240:]])
    tr_idx = np.concatenate(tr_idx); te_idx = np.concatenate(te_idx)
    null = {"msp": [], "mahal": [], "entropy": []}
    for p in range(perms):
        rngp = np.random.default_rng(5000 + p)
        yp = rngp.permutation(yk)
        clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
        clf.fit(Xk[tr_idx], yp[tr_idx])
        pk = clf.predict_proba(Xk[te_idx]); pu = clf.predict_proba(Xu)
        means, inv = mahalanobis_model(Xk[tr_idx], yp[tr_idx])
        mk = mahal_score(Xk[te_idx], means, inv); mu = mahal_score(Xu, means, inv)
        msp = np.concatenate([pk.max(1), pu.max(1)])
        P = np.clip(np.concatenate([pk, pu]), 1e-12, 1.0)
        ent = -np.sum(P * np.log(P), axis=1)
        mah = np.concatenate([mk, mu])
        y_bin = np.concatenate([np.ones(len(te_idx)), np.zeros(len(Xu))])
        null["msp"].append(float(roc_auc_score(y_bin, msp)))
        null["mahal"].append(float(roc_auc_score(y_bin, -mah)))
        null["entropy"].append(float(roc_auc_score(y_bin, -ent)))
    out = {}
    for k, v in null.items():
        out[k] = {"mean": float(np.mean(v)), "std": float(np.std(v)), "values": v}
    return out


def main():
    import platform, sklearn
    t0 = time.time()
    objs, names = load_objects()
    assert len(names) == 34 and all(len(objs[n]) == 300 for n in names)
    out = {"protocol": "open-set v2 (symmetric 80/20 single-model scoring)", "seeds": SEEDS, "n_unknown": 8,
           "env": {"device": "cpu", "python": platform.python_version(),
                   "sklearn": sklearn.__version__, "numpy": np.__version__,
                   "rf_n_estimators": 300, "features": "170-dim statistical (host_package/statistical.py)", "split": "80/20 per class (240/60)", "scoring": "single-model, symmetric ID/OOD"},
           "splits": {}}
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        unknown = pick_unknown(rng)
        assert len(unknown) == 8 and len(set(unknown)) == 8
        print(f"[seed {seed}] unknown: {unknown}", flush=True)
        out["splits"][str(seed)] = {}
        for scene in ["p1", "p2"]:
            res = run_comb(objs, unknown, seed, scene)
            if seed == NULL_SEED:
                res["null"] = run_null(objs, unknown, scene)
            out["splits"][str(seed)][scene] = res
            b = res["baselines"]
            print(f"  {scene}: closed_f1={res['closed_f1']:.4f} | "
                  f"msp AUROC={b['msp']['auroc']:.4f} FPR95={b['msp']['fpr95']:.4f} | "
                  f"mahal AUROC={b['mahal']['auroc']:.4f} FPR95={b['mahal']['fpr95']:.4f} | "
                  f"ent AUROC={b['entropy']['auroc']:.4f} FPR95={b['entropy']['fpr95']:.4f}", flush=True)
    json.dump(out, open(os.path.join(RES, "open_set_formal.json"), "w"), indent=1)
    print(f"→ results/open_set_formal.json ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
