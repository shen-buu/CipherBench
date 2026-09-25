#!/usr/bin/env python3
"""Acceptance assertions for results/open_set_formal.json."""
import json, os
import numpy as np

RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
d = json.load(open(os.path.join(RES, "open_set_formal.json")))

assert d["protocol"].startswith("open-set v2")
assert d["seeds"] == [7, 42, 99, 123, 2024], d["seeds"]
assert d["n_unknown"] == 8
assert d["env"]["device"] == "cpu" and "sklearn" in d["env"] and "python" in d["env"]

agg = {"p1": {"msp": [], "mahal": [], "entropy": []},
       "p2": {"msp": [], "mahal": [], "entropy": []}}
for s in d["seeds"]:
    sp = d["splits"][str(s)]
    assert len(sp["p1"]["unknown_classes"]) == 8
    for scene in ["p1", "p2"]:
        b = sp[scene]["baselines"]
        for tag in ["msp", "mahal", "entropy"]:
            assert 0.0 <= b[tag]["auroc"] <= 1.0
            assert 0.0 <= b[tag]["fpr95"] <= 1.0
            for r in ["0.05", "0.1", "0.2"]:
                v = b[tag]["f1_decay"][r]
                assert v is None or 0.0 <= v <= 1.0, (s, scene, tag, r, v)
            agg[scene][tag].append(b[tag]["auroc"])
    # null only on seed 42
    if s == 42:
        for scene in ["p1", "p2"]:
            n = sp[scene]["null"]
            for tag in ["msp", "mahal", "entropy"]:
                assert len(n[tag]["values"]) == 10
                assert abs(n[tag]["mean"] - np.mean(n[tag]["values"])) < 1e-9
                assert abs(n[tag]["std"] - np.std(n[tag]["values"])) < 1e-9

print("== 聚合（mean ± seed SD / SE）==")
for scene in ["p1", "p2"]:
    for tag in ["msp", "mahal", "entropy"]:
        v = np.array(agg[scene][tag])
        print(f"{scene} {tag:7s}: AUROC {v.mean():.4f} ± {v.std():.4f} (SE {v.std()/np.sqrt(len(v)):.4f})")
    f1s = [d["splits"][str(s)][scene]["closed_f1"] for s in d["seeds"]]
    print(f"{scene} closed_f1: {np.mean(f1s):.4f} ± {np.std(f1s):.4f}")
print("ALL CHECKS PASSED")
