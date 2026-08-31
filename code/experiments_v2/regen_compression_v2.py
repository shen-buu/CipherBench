#!/usr/bin/env python3
"""压缩类（14-21）缓存生成工具。

- 删除 train/val/test 中 14-21 全部 pkl 后按生产路径重新生成；
- 与生产路径一致：CachedCipherDataset.__getitem__（含 170 维特征）。
"""
import sys, os, glob, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from data.dataset import CachedCipherDataset

COMP = list(range(14, 22))


def clear(cache_dir):
    n = 0
    for cid in COMP:
        for p in glob.glob(os.path.join(cache_dir, f"{cid}_*.pkl")):
            os.unlink(p)
            n += 1
    return n


def regen(split):
    ds = CachedCipherDataset(split=split, dual_view=True)
    failed = {}
    ok = 0
    for idx, (cid, sid) in enumerate(ds.index):
        if cid not in COMP:
            continue
        try:
            ds[idx]
            ok += 1
        except Exception as e:
            failed.setdefault(CLASS_NAMES[cid], []).append(f"{sid}:{str(e)[:60]}")
        if (ok + len(failed)) % 1000 == 0:
            print(f"  [{split}] progress={ok} failed_classes={list(failed.keys())}", flush=True)
    print(f"[{split}] ok={ok} failed={failed}", flush=True)
    return ok, failed


if __name__ == "__main__":
    report = {}
    for split in ['train', 'val', 'test']:
        cache_dir = os.path.join(DATA_DIR, f"cache_{split}")
        removed = clear(cache_dir)
        print(f"[{split}] removed {removed} pkls", flush=True)
        ok, failed = regen(split)
        report[split] = {'removed': removed, 'ok': ok, 'failed': failed}
    out = os.path.join(RESULT_DIR, 'regen_compression_v2.json')
    os.makedirs(RESULT_DIR, exist_ok=True)
    with open(out, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print("saved:", out, flush=True)
    print("ALL DONE", flush=True)
