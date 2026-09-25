#!/usr/bin/env python3
"""Post-run analysis of the prim-group 60ep tier: env checks, macro / 15-class / ECDSA, escape flags. Output: results/prim60_summary_formal.json."""
import os, sys, json, glob, platform, datetime
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
SEEDS = [7, 42, 99, 123, 2024]
FROZEN_NULL = {"mean": 0.0630, "std": 0.0042, "ref": "prim P1 permutation null (S0 cell, rf; Table 4/§5.2)"}
CHANCE = 1.0 / 16.0
EXPECT_ENV = {"torch": "2.9.1+cu128", "device_prefix": "Tesla V100"}


def load(scene, seed):
    p = os.path.join(BASE, "results", f"cnn_{scene}_seed{seed}_g_prim_e60.json")
    assert os.path.exists(p), f"missing {p}"
    return json.load(open(p))


def main():
    out = {"protocol": "prim60_summary v1", "seeds": SEEDS, "scenes": {},
           "frozen_null": FROZEN_NULL, "chance": CHANCE, "env_check": []}
    for scene in ["p1", "p2"]:
        macs, ecdsas, others_mean = [], [], []
        per_class_acc = {}
        for seed in SEEDS:
            d = load(scene, seed)
            env = d["env"]
            ok_t = env.get("torch") == EXPECT_ENV["torch"]
            ok_d = env.get("device", "").startswith(EXPECT_ENV["device_prefix"])
            out["env_check"].append({"file": f"cnn_{scene}_seed{seed}_g_prim_e60.json",
                                     "torch": env.get("torch"), "device": env.get("device"),
                                     "match_torch": ok_t, "match_device": ok_d})
            assert ok_t and ok_d, f"env mismatch in cnn_{scene}_seed{seed}: {env}"
            pcf = d["per_class_f1"]
            assert set(pcf) and "ecdsa_p256_sig" in pcf and len(pcf) == 16
            macs.append(d["macro_f1"])
            ecdsas.append(pcf["ecdsa_p256_sig"])
            others_mean.append(float(np.mean([v for k, v in pcf.items() if k != "ecdsa_p256_sig"])))
            for k, v in pcf.items():
                per_class_acc.setdefault(k, []).append(v)
        macro_mean = float(np.mean(macs)); macro_sd = float(np.std(macs)); macro_se = macro_sd / np.sqrt(len(SEEDS))
        e_mean, e_sd = float(np.mean(ecdsas)), float(np.std(ecdsas))
        o_mean, o_sd = float(np.mean(others_mean)), float(np.std(others_mean))
        z_null = (macro_mean - FROZEN_NULL["mean"]) / FROZEN_NULL["std"]
        per_class_mean = {k: float(np.mean(v)) for k, v in per_class_acc.items()}
        for _k, _v in [("macro", macro_mean)] + [(k, v) for k, v in per_class_mean.items()]:
            assert 0.0 <= _v <= 1.0, f"invalid F1 {_k}={_v}"   # L4：NaN/越界不落盘
        per_class_sd = {k: float(np.std(v)) for k, v in per_class_acc.items()}
        per_class_se = {k: float(np.std(v) / np.sqrt(len(SEEDS))) for k, v in per_class_acc.items()}
        escapes = sorted([(k, round(v, 4)) for k, v in per_class_mean.items()
                          if k != "ecdsa_p256_sig" and v > CHANCE], key=lambda kv: -kv[1])
        # 种子稳定逃逸：均值 > chance 且 (mean-chance)/SE ≥ 2（SE==0 时 z 置 None 防除零）
        def zse(k):
            se = per_class_se[k]
            return (per_class_mean[k] - CHANCE) / se if se > 0 else None
        stable = sorted([(k, (round(zse(k), 1) if zse(k) is not None else None))
                         for k, _ in escapes if (zse(k) is not None and zse(k) >= 2.0)],
                        key=lambda kv: -kv[1])
        max_other = max((k for k in per_class_mean if k != "ecdsa_p256_sig"),
                        key=lambda k: per_class_mean[k])
        out["scenes"][scene] = {
            "macro": {"mean": macro_mean, "sd": macro_sd, "se": macro_se},
            "z_vs_null_band": round(z_null, 1),
            "non_ecdsa_15_mean": {"mean": o_mean, "sd": o_sd, "vs_chance": round(o_mean - CHANCE, 4)},
            "ecdsa_f1": {"mean": e_mean, "sd": e_sd},
            "max_non_ecdsa_class": {max_other: round(per_class_mean[max_other], 4)},
            "non_ecdsa_escapes_above_chance": escapes,
            "seed_stable_escapes_zse": stable,
            "per_class_mean": per_class_mean, "per_class_sd": per_class_sd, "per_class_se": per_class_se}
        print(f"cnn {scene} 60ep: macro {macro_mean:.4f} ± {macro_sd:.4f} (SE {macro_se:.4f}) | "
              f"z vs null {z_null:+.1f} | non-ECDSA15 {o_mean:.4f} ± {o_sd:.4f} (vs chance {o_mean-CHANCE:+.4f}) | "
              f"ECDSA {e_mean:.4f} ± {e_sd:.4f} | escapes: {escapes or 'none'} | stable: {stable or 'none'}", flush=True)
    out["env"] = {"script": os.path.basename(__file__),
                  "python": platform.python_version(), "numpy": np.__version__,
                  "platform": platform.platform(), "date": datetime.date.today().isoformat(),
                  "expected_env": EXPECT_ENV, "seeds": SEEDS,
                  "30ep_reference": {"P2 ECDSA": 0.9455, "P2 non-ECDSA mean": 0.036,
                                     "P1 overall": 0.0295, "ref": "§4.4 point 2 (frozen)"}}
    json.dump(out, open(os.path.join(BASE, "results", "prim60_summary_formal.json"), "w"), indent=2)
    print("→ results/prim60_summary_formal.json")


if __name__ == "__main__":
    main()
