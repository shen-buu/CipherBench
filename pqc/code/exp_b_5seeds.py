#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""Align-order B-grid upgrade to 5 seeds (reuses exp_align_order; checkpointed)."""
import json, os, sys
import numpy as np

sys.path.insert(0, BASE)
import exp_align_order as eao

DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "results", "align_order.json")
NEW_SEEDS = [7, 99]
OLD_N = 3

out = json.load(open(OUT))
order = out["order"]

for group in ["pkcs8", "cert"]:
    objs, _ = eao.load_dataset(DATA, groups=(group,))
    names = list(objs)
    y = np.array([c for c, n in enumerate(names) for _ in objs[n]])
    keys_rf = ([f"{group}_{t}_rf300" for t in
                ["B0_single", "B1_bag", "B2_head_shuffled", "B3_head_single"]] +
               [f"{group}_B5_head_identified_rf300"])
    keys_1nn = [f"{group}_{t}" for t in
                ["B0_single", "B1_bag", "B2_head_shuffled", "B3_head_single"]]
    # 全部键补齐 per_seed 结构
    for k in keys_rf + keys_1nn:
        v = order.setdefault(k, {})
        if "per_seed" not in v:
            v["per_seed"] = [None] * OLD_N
    for seed in NEW_SEEDS:
        if all(len(order[k]["per_seed"]) >= OLD_N + 2 for k in keys_rf + keys_1nn):
            print(f"{group}: 5-seed 已齐，跳过", flush=True)
            break
        F = eao.build_cache(group, objs, seed)
        Xs = {"B0_single": F[:, 0],
              "B1_bag": F[:, :5].mean(axis=1),
              "B2_head_shuffled": np.concatenate([F[:, 5:6], F[:, :4]], axis=1).mean(axis=1),
              "B3_head_single": F[:, 5]}
        for tag, X in Xs.items():
            k1 = f"{group}_{tag}"
            if len(order[k1]["per_seed"]) < OLD_N + 2:
                order[k1]["per_seed"].append(float(eao.f1_1nn(X, y, seed)))
            k2 = f"{group}_{tag}_rf300"
            if len(order[k2]["per_seed"]) < OLD_N + 2:
                order[k2]["per_seed"].append(float(eao.f1_rf(X, y, seed, n_est=300)))
                print(f"{k2} seed{seed}: {order[k2]['per_seed'][-1]:.4f}", flush=True)
        Xb5 = np.concatenate([F[:, 5], F[:, :5].mean(axis=1)], axis=1)
        k5 = f"{group}_B5_head_identified_rf300"
        if len(order[k5]["per_seed"]) < OLD_N + 2:
            order[k5]["per_seed"].append(float(eao.f1_rf(Xb5, y, seed, n_est=300)))
            print(f"{k5} seed{seed}: {order[k5]['per_seed'][-1]:.4f}", flush=True)
        json.dump(out, open(OUT, "w"), indent=2)

for k, v in order.items():
    if isinstance(v, dict) and "per_seed" in v:
        vals = [x for x in v["per_seed"] if x is not None]
        v["mean"] = float(np.mean(vals))
        v["std"] = float(np.std(vals))
        v["n_seeds"] = len(vals)
json.dump(out, open(OUT, "w"), indent=2)
print("align_order.json: B 网格汇总更新完毕")
