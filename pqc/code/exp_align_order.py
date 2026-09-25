#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""C_align channel, B in {512,1024,4096}: exact / shifted / no-first-block, 5 seeds. Output: results/align_order.json."""
import os, sys, json, time
import numpy as np

sys.path.insert(0, os.path.join(BASE, "host_package"))
from train_baselines import load_dataset, make_window
from statistical import extract_full_features
from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score

DATA = os.path.join(BASE, "data")
RES = os.path.join(BASE, "results")
CACHE = os.path.join(RES, "align_cache")
SEEDS = [42, 123, 2024]           # 乱序段沿用 3 seed
SEEDS_ALIGN = [7, 42, 99, 123, 2024]  # §5.6 对齐信道：5 seeds（升级）
FOLDS = 5
OUT = os.path.join(RES, "align_order.json")


def save_out(out):
    os.makedirs(RES, exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2)


def load_out():
    if os.path.exists(OUT):
        return json.load(open(OUT))
    return {"classes": None, "c_align": {}, "order": {}}


def f1_1nn(X, y, seed):
    skf = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = KNeighborsClassifier(n_neighbors=1)
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    return float(f1_score(yt, yp, average="macro"))


def f1_rf(X, y, seed, n_est=100):
    skf = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = RandomForestClassifier(n_estimators=n_est, n_jobs=-1, random_state=seed)
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    return float(f1_score(yt, yp, average="macro"))


def mean_std(vals):
    return {"mean": float(np.mean(vals)), "std": float(np.std(vals)),
            "per_seed": [float(v) for v in vals]}


# ══════════════════════════════════════════════════════
# Part 1  C_align（全部 34 类，长度维度）
# ══════════════════════════════════════════════════════
def part1(out):
    objs, _ = load_dataset(DATA)          # 全部三组
    names = list(objs)
    lens, y = [], []
    for cid, n in enumerate(names):
        for d in objs[n]:
            lens.append(len(d)); y.append(cid)
    lens = np.array(lens); y = np.array(y)
    out["classes"] = len(names)
    out["n_objects"] = int(len(y))
    save_out(out)
    print(f"[C_align] {len(names)} 类 × {len(y)} 对象", flush=True)

    for B in [512, 1024, 4096]:
        # A1：精确对齐
        X = np.stack([np.ceil(lens / B), lens % B], axis=1).astype(np.float64)
        out["c_align"][f"A1_B{B}"] = mean_std([f1_1nn(X, y, s) for s in SEEDS_ALIGN])
        Xn = (np.ceil(lens / B)).reshape(-1, 1)
        out["c_align"][f"A1_B{B}_blocks_only"] = mean_std([f1_1nn(Xn, y, s) for s in SEEDS_ALIGN])
        Xr = (lens % B).reshape(-1, 1)
        out["c_align"][f"A1_B{B}_residue_only"] = mean_std([f1_1nn(Xr, y, s) for s in SEEDS_ALIGN])
        save_out(out)
        print(f"  A1 B={B}: full={out['c_align'][f'A1_B{B}']['mean']:.4f} "
              f"blocks={out['c_align'][f'A1_B{B}_blocks_only']['mean']:.4f} "
              f"residue={out['c_align'][f'A1_B{B}_residue_only']['mean']:.4f}", flush=True)

        # A2：移位对齐（3 个偏移实现）
        for tag, use_first in [("A2", True), ("A2_nt", False)]:
            f_all = []
            for seed in SEEDS_ALIGN:
                f_off = []
                for off_seed in [7, 77, 777]:
                    rng = np.random.default_rng(off_seed)
                    rows = []
                    for L in lens:
                        off = int(rng.integers(0, B))
                        total = off + L
                        nb = np.ceil(total / B)
                        ff = B - off
                        fl = total % B if total % B else B
                        rows.append([nb, ff, fl] if use_first else [nb, fl])
                    X = np.array(rows, dtype=np.float64)
                    f_off.append(f1_1nn(X, y, seed))
                f_all.append(float(np.mean(f_off)))     # 偏移实现平均
            out["c_align"][f"{tag}_B{B}"] = mean_std(f_all)
            save_out(out)
            print(f"  {tag} B={B}: F1 = {out['c_align'][f'{tag}_B{B}']['mean']:.4f} ± "
                  f"{out['c_align'][f'{tag}_B{B}']['std']:.4f}", flush=True)


# ══════════════════════════════════════════════════════
# Part 2  乱序鲁棒性（分组建模）
# ══════════════════════════════════════════════════════
def build_cache(group, objs, seed):
    """每对象 6 窗口（5 随机 + 1 头）→ (n,6,170) 特征，缓存到磁盘"""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{group}_seed{seed}.npz")
    if os.path.exists(path):
        return np.load(path)["F"]
    rng = np.random.default_rng(seed)
    names = list(objs)
    F, y = [], []
    for cid, n in enumerate(names):
        for d in objs[n]:
            ws = [make_window(d, "p1", rng) for _ in range(5)]
            h = make_window(d, "p2", rng)
            feats = [extract_full_features(w) for w in ws]
            feats.append(extract_full_features(h))
            F.append(np.stack(feats))
            y.append(cid)
    F = np.array(F, dtype=np.float32)
    np.savez(path, F=F, y=np.array(y))
    return F


def part2(out):
    anchors = {"pkcs8": (0.5519, 0.6953, 1 / 11), "cert": (0.6031, 0.8488, 1 / 7)}
    for group, (a_p1, a_p2, chance) in anchors.items():
        objs, _ = load_dataset(DATA, groups=(group,))
        n_cls = len(objs)
        print(f"[乱序] {group}: {n_cls} 类 × {sum(len(v) for v in objs.values())} 对象，"
              f"锚点 P1={a_p1} P2={a_p2} chance={chance:.4f}", flush=True)
        for seed in SEEDS:
            F = build_cache(group, objs, seed)
            y = np.array([c for c, n in enumerate(list(objs)) for _ in objs[n]])
            Xs = {"B0_single": F[:, 0],
                  "B1_bag": F[:, :5].mean(axis=1),
                  "B2_head_shuffled": np.concatenate(
                      [F[:, 5:6], F[:, :4]], axis=1).mean(axis=1),
                  "B3_head_single": F[:, 5]}
            for tag, X in Xs.items():
                key = f"{group}_{tag}"
                entry = out["order"].setdefault(key, {"per_seed": {}, "clf": "1nn"})
                ps = entry["per_seed"]
                if isinstance(ps, list):        # 旧格式迁移：按位置对齐 SEEDS
                    entry["per_seed"] = ps = {str(s): v for s, v in zip(SEEDS, ps)}
                ps[str(seed)] = f1_1nn(X, y, seed)
                save_out(out)
            print(f"  {group} seed={seed}: 1-NN done", flush=True)
        # 汇总 1-NN
        for tag in ["B0_single", "B1_bag", "B2_head_shuffled", "B3_head_single"]:
            key = f"{group}_{tag}"
            ps = out["order"][key]["per_seed"]
            vals = [ps[str(s)] for s in SEEDS if str(s) in ps]
            if len(vals) == len(SEEDS):
                out["order"][key] = mean_std(vals)
                out["order"][key]["clf"] = "1nn"
        save_out(out)


def part2_rf(out, n_est, suffix):
    """RF 交叉验证锚定（对照冻结 rf300 组级数字）；n_est/suffix 控制命名"""
    for group in ["pkcs8", "cert"]:
        objs, _ = load_dataset(DATA, groups=(group,))
        for tag in ["B0_single", "B1_bag", "B2_head_shuffled", "B3_head_single"]:
            key = f"{group}_{tag}_{suffix}"
            if key in out["order"] and "mean" in out["order"][key]:
                continue
            f_seeds = []
            for seed in SEEDS:
                F = build_cache(group, objs, seed)
                y = np.array([c for c, n in enumerate(list(objs)) for _ in objs[n]])
                if tag == "B0_single":
                    X = F[:, 0]
                elif tag == "B1_bag":
                    X = F[:, :5].mean(axis=1)
                elif tag == "B2_head_shuffled":
                    X = np.concatenate([F[:, 5:6], F[:, :4]], axis=1).mean(axis=1)
                else:
                    X = F[:, 5]
                f_seeds.append(f1_rf(X, y, seed, n_est=n_est))
            out["order"][key] = mean_std(f_seeds)
            out["order"][key]["clf"] = f"rf{n_est}"
            save_out(out)
            print(f"  {group} {tag} {suffix}: {out['order'][key]['mean']:.4f} ± "
                  f"{out['order'][key]['std']:.4f}", flush=True)


def main():
    t0 = time.time()
    out = load_out()
    if os.environ.get("FORCE_ALIGN") == "1" or "A2_B4096" not in out["c_align"]:
        part1(out)
    skip_rf = os.environ.get("SKIP_RF100") == "1"
    if skip_rf:
        if "cert_B3_head_single" not in out["order"]:
            part2(out)
    else:
        if "cert_B3_head_single" not in out["order"]:
            part2(out)
        part2_rf(out, 100, "rf100")
        part2_rf(out, 300, "rf300")
    save_out(out)
    print(f"全部完成，共 {time.time() - t0:.0f}s → {OUT}", flush=True)


if __name__ == "__main__":
    main()
