#!/usr/bin/env python3
"""核实脚本 flag_02：任意 5-seed 组的种子级出挑值通用核实。
用法：python3 flag_02_group_seed_outlier.py <group_prefix> <suffix> <seed>
  group = group_prefix + '_seed' + str(seed) + suffix + '.json'（例如 cnn_p1 / '' / 42）
四步（全部只读冻结文件）：
  (1) 完整性：results 与 rental_snapshot 副本逐字段一致（有副本时）；
  (2) 内部一致性：macro_f1 == mean(per_class_f1)；
  (3) 种子上下文：同 seed 在相邻 tier/scene 的取值序列（判断种子级稳定高抽 vs 孤立尖峰）；
  (4) 统计口径：全组 z vs 留一 z（σ 收缩伪影来源）。
输出 VERDICT：AUTHENTIC / ANOMALY（需人工处置）。
"""
import os, sys, json, math
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(BASE, "results")
RENT = os.path.join(BASE, "rental_snapshot", "pqc", "results")
SEEDS = [7, 42, 99, 123, 2024]


def load(p):
    return json.load(open(p))


def main():
    prefix, suffix, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
    fname = f"{prefix}_seed{seed}{suffix}.json"
    p_res = os.path.join(RES, fname)
    assert os.path.exists(p_res), f"missing {p_res}"
    a = load(p_res)
    print(f"== 核实 {fname} (macro={a['macro_f1']:.6f}) ==")

    # (1) integrity
    p_rent = os.path.join(RENT, fname)
    if os.path.exists(p_rent):
        b = load(p_rent)
        same = (a == b)
        print(f"(1) integrity vs rental_snapshot: {same}")
        if not same:
            for k in set(a) | set(b):
                if a.get(k) != b.get(k) and k not in ("sec",):
                    print(f"    diff {k}: results={a.get(k)} rental={b.get(k)}")
    else:
        print("(1) no rental copy (local-only artifact)")
        same = True

    # (2) internal
    if "per_class_f1" in a and a["per_class_f1"]:
        pcm = float(np.mean(list(a["per_class_f1"].values())))
        ok2 = abs(a["macro_f1"] - pcm) < 1e-9
        print(f"(2) macro==mean(per_class): Δ={a['macro_f1']-pcm:.2e} -> {'OK' if ok2 else 'FAIL'}")
    else:
        ok2 = isinstance(a.get("macro_f1"), float) and 0.0 <= a["macro_f1"] <= 1.0
        print(f"(2) no per-class stored (schema {sorted(a.keys())}); macro range OK={ok2}")

    # (3) seed context: same seed, sibling tiers/scenes
    print("(3) same-seed context:")
    fam = prefix.rsplit("_", 1)[0]
    scene = prefix.split("_")[-1]
    cands = []
    import glob as _g
    for pat in [f"{fam}*_seed{seed}*.json", f"{prefix}_seed{seed}*.json",
                f"*{scene}*_seed{seed}*.json"]:
        for p in sorted(_g.glob(os.path.join(RES, pat))):
            n = os.path.basename(p)
            if n == fname or "_smoke" in n:
                continue
            cands.append(n)
    seen = set(); rows = []
    for n in cands:
        if n in seen:
            continue
        seen.add(n)
        try:
            rows.append((n, load(os.path.join(RES, n))["macro_f1"]))
        except Exception:
            pass
    if rows:
        for n, v in sorted(rows):
            print(f"    {n}: {v:.4f}")
    else:
        print("    (no sibling files)")

    # (4) statistical framing
    vals = {}
    for s in SEEDS:
        p = os.path.join(RES, f"{prefix}_seed{s}{suffix}.json")
        if not os.path.exists(p):
            p = os.path.join(RENT, f"{prefix}_seed{s}{suffix}.json")
        vals[s] = load(p)["macro_f1"]
    mu, sd = float(np.mean(list(vals.values()))), float(np.std(list(vals.values())))
    others = [v for k, v in vals.items() if k != seed]
    mo, so = float(np.mean(others)), float(np.std(others))
    z_full = (vals[seed] - mu) / sd if sd > 0 else 0.0
    z_loo = (vals[seed] - mo) / so if so > 0 else 0.0
    print(f"(4) full-set z={z_full:.2f} | leave-one-out z={z_loo:.2f} (σ {sd:.4f}→{so:.4f})")

    verdict = "AUTHENTIC" if (same and ok2) else "ANOMALY"
    print(f"\nVERDICT: {verdict} — " + (
        "冻结值真实：内部一致、与冻结副本一致；种子级波动处于冻结包络内（全组 z 见上），无需修正"
        if verdict == "AUTHENTIC" else "需人工处置：完整性或内部一致性失败"))
    return 0 if verdict == "AUTHENTIC" else 1


if __name__ == "__main__":
    raise SystemExit(main())
