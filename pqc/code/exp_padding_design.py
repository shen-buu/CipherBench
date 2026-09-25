#!/usr/bin/env python3
"""Offline 4096-grid / uniform-max padding; beta(G) re-run under the frozen S5.3 protocol with a bit-exact replay gate. Output: results/padding_design_formal.json."""
import os, json, glob, sys, platform, datetime
import numpy as np

DATA = os.path.join(BASE, "data")
RES = os.path.join(BASE, "results")
PAD = 4096
VERIFY = "--verify" in sys.argv

from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import f1_score


def load_lengths():
    """与 exp_s2s3.py 完全一致：data/meta.json 34 类 × 300 对象文件字节数。"""
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


def ladder(vals, y):
    """§5.3 冻结协议逐行复刻（50 draws / seed 2025 / 对称随机化 tie-breaking / 零带 10×seed42）。"""
    levels = {"exact": vals,
              "round16": np.round(vals / 16) * 16,
              "round64": np.round(vals / 64) * 64,
              "log2bin": np.floor(np.log2(np.maximum(vals, 1))),
              "size_class": np.digitize(vals, [1024, 2048, 4096, 8192])}
    out = {}
    for lv, lvals in levels.items():
        groups = {}
        for v, cid in zip(lvals, y):
            groups.setdefault(float(v), set()).add(cid)
        rng = np.random.default_rng(2025)
        betas = []
        for _ in range(50):
            yp = np.array([rng.choice(sorted(groups[float(v)])) for v in lvals])
            betas.append(f1_score(y, yp, average="macro"))
        beta = float(np.mean(betas))
        m, s = f1_1nn(lvals, y)
        nulls = []
        for p in range(10):
            ysh = np.random.default_rng(1000 + p).permutation(y)
            nm, _ = f1_1nn(lvals, ysh, seeds=(42,))
            nulls.append(nm)
        out[lv] = {"beta": beta, "nn_f1": m, "nn_std": s,
                   "nn_null_mean": float(np.mean(nulls)), "nn_null_std": float(np.std(nulls)),
                   "G": len(groups), "max_collision_group": max(len(g) for g in groups.values()),
                   "atoms": sorted(float(g) for g in groups)}
    return out


def main():
    lens = load_lengths()
    names = list(lens)
    y = np.concatenate([[i] * len(lens[n]) for i, n in enumerate(names)])
    orig = np.concatenate([[l] for n in names for l in lens[n]]).astype(np.float64)
    padded = np.ceil(orig / PAD) * PAD

    # ---- 口径一致性闸门：原始长度重放必须与冻结文件逐位一致 ----
    frozen = json.load(open(os.path.join(RES, "s2s3_formal.json")))
    replay = ladder(orig, y)
    gate = []
    for lv in ["exact", "round16", "round64", "log2bin", "size_class"]:
        f = frozen["s3"][lv]
        r = replay[lv]
        same = (abs(f["beta"] - r["beta"]) < 1e-12 and abs(f["nn_f1"] - r["nn_f1"]) < 1e-12
                and abs(f["nn_null_mean"] - r["nn_null_mean"]) < 1e-12
                and f["G"] == r["G"])
        gate.append((lv, same))
        print(f"gate {lv:10s} beta={r['beta']:.4f} (frozen {f['beta']:.4f}) match={same}")
    assert all(s for _, s in gate), f"协议重放不一致：{gate}"
    print("口径闸门通过：原始长度重放与 results/s2s3_formal.json 逐位一致 ✓")

    # ---- (a) 填充代价 ----
    per_class = {}
    tot_o, tot_p = 0.0, 0.0
    for n in names:
        o = np.array(lens[n], dtype=np.float64)
        p = np.ceil(o / PAD) * PAD
        per_class[n] = {"orig_mean": float(o.mean()), "padded_len": float(p[0]) if len(set(p)) == 1 else sorted(set(p.tolist())),
                        "ratio": float(p.sum() / o.sum()), "n": int(len(o))}
        tot_o += o.sum(); tot_p += p.sum()
    agg = {"total_orig_bytes": tot_o, "total_padded_bytes": tot_p,
           "overall_ratio": tot_p / tot_o,
           "mean_class_ratio": float(np.mean([v["ratio"] for v in per_class.values()])),
           "median_class_ratio": float(np.median([v["ratio"] for v in per_class.values()])),
           "max_class_ratio": float(max(v["ratio"] for v in per_class.values())),
           "max_class_ratio_class": max(names, key=lambda n: per_class[n]["ratio"]),
           "n_distinct_padded_atoms": len(set(np.ceil(orig / PAD) * PAD)),
           "padded_atoms": sorted(set(float(x) for x in np.ceil(orig / PAD) * PAD))}

    # 统一最大长度填充（完全等长的另一设计点，敏感性对照）
    max_pad = float(np.ceil(orig.max() / PAD) * PAD)
    padded_uni = np.full_like(orig, max_pad)
    agg_uni = {"max_padded_len": max_pad, "overall_ratio": (max_pad * len(orig)) / tot_o}

    # ---- (b) 填充后 β(G) ----
    pad_ladder = ladder(padded, y)
    uni_ladder = ladder(padded_uni, y)

    out = {"protocol": "padding_design v1",
           "protocol_ref": "§5.3 frozen ladder protocol (50 MC draws, symmetric randomized tie-breaking, seed 2025; 1-NN seeds (42,123,2024); null 10 perms seed 42)",
           "padding": "ceil(L/4096)*4096 for all 34 classes",
           "gate": [{"level": lv, "replay_matches_frozen": s} for lv, s in gate],
           "per_class": per_class, "aggregate": agg, "aggregate_uniform_max": agg_uni,
           "ladder_orig_frozen": {lv: {k: frozen["s3"][lv][k] for k in ("beta", "nn_f1", "G", "nn_null_mean", "nn_null_std")} for lv in frozen["s3"]},
           "ladder_padded": pad_ladder,
           "ladder_uniform_max": uni_ladder,
           "env": {"script": os.path.basename(__file__),
                   "python": platform.python_version(), "numpy": np.__version__,
                   "platform": platform.platform(), "date": datetime.date.today().isoformat(),
                   "data_snapshot": DATA, "frozen_ref": "results/s2s3_formal.json",
                   "seeds": {"tie_break": 2025, "nn": [42, 123, 2024], "null_perm": [1000 + p for p in range(10)]},
                   "no_training": True, "frozen_files_modified": False}}
    json.dump(out, open(os.path.join(RES, "padding_design_formal.json"), "w"), indent=2)
    print(f"\n聚合：总体膨胀率 {agg['overall_ratio']:.3f}；类中位 {agg['median_class_ratio']:.3f}；"
          f"最坏 {agg['max_class_ratio_class']} {agg['max_class_ratio']:.3f}；"
          f"不同填充原子数 {agg['n_distinct_padded_atoms']} {agg['padded_atoms']}")
    print(f"统一最大长度填充：{agg_uni['max_padded_len']:.0f}B，总体膨胀率 {agg_uni['overall_ratio']:.3f}")
    for lv in pad_ladder:
        v = pad_ladder[lv]
        print(f"填充后 {lv:10s} G'={v['G']:2d} β'={v['beta']:.4f} | 1-NN'={v['nn_f1']:.4f} | "
              f"零带'={v['nn_null_mean']:.4f}±{v['nn_null_std']:.4f}")
    for lv in uni_ladder:
        v = uni_ladder[lv]
        print(f"统一等长 {lv:10s} G'={v['G']:2d} β'={v['beta']:.4f} | 1-NN'={v['nn_f1']:.4f} | "
              f"零带'={v['nn_null_mean']:.4f}±{v['nn_null_std']:.4f}")
    print("→ results/padding_design_formal.json")


if __name__ == "__main__":
    main()
