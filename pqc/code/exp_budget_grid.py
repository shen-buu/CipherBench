#!/usr/bin/env python3
"""Epoch budget grid 15/30/60 via train_baselines.py (checkpointed). --verify replays against frozen results (CNN <=0.026, BiLSTM exact)."""
import os, sys, json, glob, time, argparse, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
SEEDS = [7, 42, 99, 123, 2024]


def run_group(arch, scene, epochs, groups="primitives,pkcs8,cert"):
    """train_baselines 内部循环 5 seeds（断点制）。groups=primitives → prim 组 60ep 补跑。"""
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tag = "" if epochs == 15 else f"e{epochs}"   # 无下划线：train_baselines 内部加 "_"（历史 __e60 双下划线事故，audit #42）
    cmd = [sys.executable, os.path.join(BASE, "host_package", "train_baselines.py"),
           "--data", os.path.join(BASE, "data"), "--arch", arch, "--scene", scene,
           "--epochs", str(epochs), "--tag", tag, "--device", dev,
           "--groups", groups]
    subprocess.run(cmd, check=True, cwd=os.path.join(BASE, "host_package"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--arch", type=str, default=None)   # None = both
    ap.add_argument("--scene", type=str, default=None)  # None = both
    ap.add_argument("--groups", type=str, default="primitives,pkcs8,cert")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    if a.verify:
        import json as _j
        if a.groups == "primitives":
            # H1 修复（audit #43）：删除前落盘 .bak，重跑失败时 finally 恢复，冻结结果不丢。
            # prim-60ep 同机复现验证：备份 2 个现值，删除后重跑（断点制只补缺），
            # 比对同机重跑界（CNN ≤0.026，沿用既有复现界口径）。
            import shutil as _sh
            if not torch.cuda.is_available():   # M2 修复：verify 必须在冻结 GPU 环境执行
                print("[verify] requires the frozen CUDA env (torch 2.9.1+cu128 / V100); abort", flush=True)
                sys.exit(2)
            files = ["cnn_p1_seed7_g_prim_e60.json", "cnn_p2_seed99_g_prim_e60.json"]
            before, baks = {}, {}
            try:
                for f in files:
                    p = os.path.join(BASE, "results", f)
                    assert os.path.exists(p), f"missing {f}"
                    before[f] = _j.load(open(p))["macro_f1"]
                    _sh.copy(p, p + ".bak")
                    baks[f] = p + ".bak"
                    os.remove(p)
                run_group("cnn", "p1", 60, "primitives")
                run_group("cnn", "p2", 60, "primitives")
                ok = True
                for f in files:
                    got = _j.load(open(os.path.join(BASE, "results", f)))["macro_f1"]
                    d = abs(before[f] - got)
                    verdict = "OK" if d <= 0.026 else "VIOLATED"
                    if d > 0.026:
                        ok = False
                    print(f"[verify prim60] {f}: before {before[f]:.4f} vs rerun {got:.4f} -> |Δ|={d:.4f} (bound 0.026) {verdict}", flush=True)
                sys.exit(0 if ok else 1)
            except BaseException:
                for f, bak in baks.items():
                    if os.path.exists(bak):
                        _sh.move(bak, os.path.join(BASE, "results", f))
                        print(f"[verify prim60] restored {f} from .bak", flush=True)
                raise
        # 参照快照（冻结值）
        snap = {"cnn_p1_seed7.json": os.path.join(BASE, "results", "cnn_p1_seed7.json"),
                "bilstm_p2_seed99.json": os.path.join(BASE, "results", "bilstm_p2_seed99.json")}
        import shutil as _sh
        if not torch.cuda.is_available():   # M2 修复：冻结环境内验证（BiLSTM 1e-9 为同环境 exact 界）
            print("[verify] requires the frozen CUDA env; abort", flush=True)
            sys.exit(2)
        for f in snap:
            p = os.path.join(BASE, "results", f)
            if os.path.exists(p):
                os.remove(p)
        run_group("cnn", "p1", 15)
        run_group("bilstm", "p2", 15)
        ok = True
        for f, sref in snap.items():
            ref = _j.load(open(os.path.join(BASE, sref)))["macro_f1"]
            got = _j.load(open(os.path.join(BASE, "results", f)))["macro_f1"]
            d = abs(ref - got)
            lim = 0.026 if f.startswith("cnn") else 1e-9
            verdict = "OK" if d <= lim else "VIOLATED"
            if d > lim:
                ok = False
                # M1 修复：超界时从冻结快照恢复参考副本，避免验证动作污染 results/
                _sh.copy(os.path.join(BASE, sref), os.path.join(BASE, "results", f))
                print(f"[verify] restored {f} from rental_snapshot", flush=True)
            print(f"[verify] {f}: frozen {ref:.4f} vs rerun {got:.4f} -> |Δ|={d:.4f} (bound {lim}) {verdict}", flush=True)
        sys.exit(0 if ok else 1)
    archs = [a.arch] if a.arch else ["cnn", "bilstm"]
    scenes = [a.scene] if a.scene else ["p1", "p2"]
    for arch in archs:
        for scene in scenes:
            run_group(arch, scene, a.epochs, a.groups)


if __name__ == "__main__":
    main()
