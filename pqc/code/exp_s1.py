#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
"""S1 payload preprocessing on 18 containers (head24/48, oid_zero/rand, trunc/slide 25/50/75; 5 seeds). Output: results/s1_formal_summary.json."""
import os, sys, json, glob, time, argparse
import numpy as np

DATA = os.path.join(BASE, "data")
RES = os.path.join(BASE, "results")
os.makedirs(RES, exist_ok=True)

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, confusion_matrix

WIN = 1024
OID_PREFIX = bytes.fromhex("06096086480165030403")
CONDITIONS = ["intact", "oid_zero", "oid_rand", "head24", "head48",
              "trunc25", "trunc50", "trunc75", "slide25", "slide50", "slide75"]


def load_objects():
    meta = json.load(open(os.path.join(DATA, "meta.json")))
    objs = {}
    for name, v in meta.items():
        if isinstance(v, dict) and v.get("type") in ("pkcs8", "cert"):
            d = os.path.join(DATA, name)
            objs[name] = [open(f, "rb").read() for f in sorted(glob.glob(os.path.join(d, "*.der")))]
    return objs


def find_oid(data, start=0):
    i = data.find(OID_PREFIX, start)
    if i < 0:
        return None
    return (i, i + len(OID_PREFIX) + 1)


def make_window(data, cond, rng):
    if len(data) >= WIN:
        w = bytearray(data[:WIN])
    else:
        w = bytearray(data) + bytearray(rng.bytes(WIN - len(data)))
    if cond == "intact":
        pass
    elif cond in ("oid_zero", "oid_rand"):
        pos = find_oid(w)
        if pos:
            a, b = pos
            w[a:b] = b"\x00" * (b - a) if cond == "oid_zero" else rng.bytes(b - a)
    elif cond in ("head24", "head48"):
        w[: 24 if cond == "head24" else 48] = b"\x00" * (24 if cond == "head24" else 48)
    elif cond.startswith("trunc"):
        k = int(WIN * int(cond[5:]) / 100)
        w[:k] = b"\x00" * k
    elif cond.startswith("slide"):
        frac = int(cond[5:]) / 100.0
        off = int(len(data) * frac)
        if off + WIN <= len(data):
            w = bytearray(data[off: off + WIN])
        elif len(data) >= WIN:
            w = bytearray(data[len(data) - WIN:])
        else:
            # 短对象：无满窗可取，维持头部锚定 + 随机填充（P2 语义）
            w = bytearray(data) + bytearray(rng.bytes(WIN - len(data)))
    return bytes(w)


def run_cond(objs, cond, seed):
    names = list(objs)
    rng = np.random.default_rng(seed)
    X, y = [], []
    for cid, name in enumerate(names):
        for d in objs[name]:
            X.append(np.frombuffer(make_window(d, cond, rng), dtype=np.uint8).astype(np.float32) / 255.0)
            y.append(cid)
    X, y = np.array(X, dtype=np.float32), np.array(y)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    yt, yp = [], []
    t0 = time.time()
    for tr, te in skf.split(X, y):
        clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    yt, yp = np.array(yt), np.array(yp)
    out = {"cond": cond, "seed": seed, "macro_f1": float(f1_score(yt, yp, average="macro")),
           "per_class": {names[i]: float(f1_score(yt, yp, average=None)[i]) for i in range(len(names))},
           "confusion": confusion_matrix(yt, yp, labels=range(len(names))).tolist(),
           "sec": round(time.time() - t0, 1), "n_classes": len(names)}
    with open(os.path.join(RES, f"s1_{cond}_seed{seed}.json"), "w") as f:
        json.dump(out, f)
    print(f"[{cond}] seed={seed} macro-F1={out['macro_f1']:.4f} ({out['sec']}s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--cond", type=str, default=None)
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    objs = load_objects()
    print(f"容器类 {len(objs)}，对象总数 {sum(len(v) for v in objs.values())}", flush=True)
    if a.merge:
        recs = []
        for f in glob.glob(os.path.join(RES, "s1_*_seed*.json")):
            recs.append(json.load(open(f)))
        from collections import defaultdict
        by_cond = defaultdict(list)
        for r in recs:
            by_cond[r["cond"]].append(r["macro_f1"])
        out = {}
        for c, v in by_cond.items():
            assert all(0.0 <= x <= 1.0 for x in v), f"{c} F1 out of range"
            out[c] = {"mean": float(np.mean(v)), "std": float(np.std(v)), "n": len(v)}
        ns = {o["n"] for o in out.values()}
        assert len(ns) == 1, f"条件种子数不一致: {ns}"; n0 = ns.pop()
        assert n0 >= 5, f"S1 汇总种子数 {n0} < 5 冻结惯例"
        json.dump(out, open(os.path.join(RES, "s1_formal_summary.json"), "w"), indent=2)
        for c in CONDITIONS:
            if c in out:
                print(f"  {c:10s} {out[c]['mean']:.4f} ± {out[c]['std']:.4f}（{out[c]['n']} 种子）")
        return
    for cond in (CONDITIONS if a.cond is None else [a.cond]):
        run_cond(objs, cond, a.seed)


if __name__ == "__main__":
    main()
