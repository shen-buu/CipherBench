#!/usr/bin/env python3
"""libmagic 5.46 vs an 11-OID metadata baseline on 18 containers (intact/oid_zero/head48/trunc50). Output: results/tools_baseline_formal.json."""
import os, sys, json, subprocess, glob
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
OID_PREFIX = bytes.fromhex("06096086480165030403")   # 2.16.840.1.101.3 前缀（PQ OID 共用）

# 11 个算法 OID 的 DER 编码（06 len content）；ML-KEM-512 与 768/1024 分别为 4.4.1/4.4.2/4.4.3
def oid_der(arcs):
    b = [arcs[0] * 40 + arcs[1]]
    for a in arcs[2:]:
        enc = [a % 128]; a //= 128
        while a:
            enc.append(a % 128 | 0x80); a //= 128
        b += reversed(enc)
    body = bytes(b)
    return bytes([0x06, len(body)]) + body

OIDS = {
    "mldsa44": oid_der([2, 16, 840, 1, 101, 3, 4, 3, 17]),
    "mldsa65": oid_der([2, 16, 840, 1, 101, 3, 4, 3, 18]),
    "mldsa87": oid_der([2, 16, 840, 1, 101, 3, 4, 3, 19]),
    "mlkem512": oid_der([2, 16, 840, 1, 101, 3, 4, 4, 1]),
    "mlkem768": oid_der([2, 16, 840, 1, 101, 3, 4, 4, 2]),
    "mlkem1024": oid_der([2, 16, 840, 1, 101, 3, 4, 4, 3]),
    "slhdsa128s": oid_der([2, 16, 840, 1, 101, 3, 4, 3, 26]),
    "slhdsa256s": oid_der([2, 16, 840, 1, 101, 3, 4, 3, 30]),
    "rsa": oid_der([1, 2, 840, 113549, 1, 1, 1]),
    "ec": oid_der([1, 2, 840, 10045, 2, 1]),
    "ed25519": oid_der([1, 3, 101, 112]),
}
# 容器类型头标记
CERT_MARK = bytes.fromhex("a0030201")     # TBS version [0] EXPLICIT + INTEGER 2
PKCS8_MARK = bytes.fromhex("020100")      # version INTEGER 0（PKCS#8 头）
PKCS1_MARK = bytes.fromhex("02010002820101")   # PKCS#1：version 0 + 257B 模数 INTEGER
SEC1_MARK = bytes.fromhex("02010104")          # SEC1：version 1 + privateKey OCTET
EC_P256_OID = bytes.fromhex("2a8648ce3d030107")  # prime256v1 曲线 OID

ALG_TO_CLASS = {
    "mldsa44": ("mldsa44_pkcs8", "mldsa44_cert"), "mldsa65": ("mldsa65_pkcs8", "mldsa65_cert"),
    "mldsa87": ("mldsa87_pkcs8", "mldsa87_cert"), "mlkem512": ("mlkem512_pkcs8", None),
    "mlkem768": ("mlkem768_pkcs8", None), "mlkem1024": ("mlkem1024_pkcs8", None),
    "slhdsa128s": ("slhdsa128s_pkcs8", "slhdsa128s_cert"), "slhdsa256s": ("slhdsa256s_pkcs8", None),
    "rsa": ("rsa2048_pkcs8", "rsa2048_cert"), "ec": ("ecdsap256_pkcs8", "ecdsap256_cert"),
    "ed25519": ("ed25519_pkcs8", "ed25519_cert"),
}
CLASSES = sorted([c for t in ALG_TO_CLASS.values() for c in t if c])
assert len(CLASSES) == 18

LIB_MAP = {
    "DER Encoded Key Pair, 2048 bits": "rsa2048_pkcs8",
    "Certificate, Version=3": "__cert_family__",
    "data": "__abstain__",
}


def load_objects():
    meta = json.load(open(os.path.join(BASE, "data", "meta.json")))
    objs = {}
    for name, v in meta.items():
        if isinstance(v, dict) and v.get("type") in ("pkcs8", "cert"):
            d = os.path.join(BASE, "data", name)
            objs[name] = [open(f, "rb").read() for f in sorted(glob.glob(os.path.join(d, "*.der")))]
    return objs


def transform(data, cond):
    if cond == "intact":
        return data
    if cond == "oid_zero":
        b = bytearray(data)
        i = 0
        while True:
            j = bytes(b).find(OID_PREFIX, i)
            if j < 0:
                break
            b[j:j + len(OID_PREFIX)] = b"\x00" * len(OID_PREFIX)
            i = j + 1
        return bytes(b)
    if cond == "head48":
        return b"\x00" * 48 + data[48:]
    if cond == "trunc50":
        h = len(data) // 2
        return b"\x00" * h + data[h:]
    raise ValueError(cond)


def libmagic_predict(data, tmp):
    with open(tmp, "wb") as f:
        f.write(data)
    r = subprocess.run(["file", "-b", tmp], capture_output=True, text=True)
    if r.returncode != 0:                       # file(1) 失败不得静默映射为弃权
        raise RuntimeError(f"file(1) failed rc={r.returncode}: {r.stderr[:200]}")
    out = r.stdout.strip()
    return LIB_MAP.get(out, "__abstain__"), out


def oid_predict(data):
    b = bytes(data)
    if PKCS1_MARK in b[:24]:
        return "rsa2048_pkcs8"
    if SEC1_MARK in b[:16] and EC_P256_OID in b:
        return "ecdsap256_pkcs8"
    is_cert = CERT_MARK in b[:64] or b[4:6] == bytes.fromhex("3082")
    alg = None
    for a, oid in OIDS.items():
        if oid in b:
            alg = a
            break
    if alg is None:
        return "__abstain__"
    pk, cr = ALG_TO_CLASS[alg]
    if cr is None:
        return pk
    return cr if is_cert else pk


def evaluate(preds, ytrue, classes):
    n = len(classes)
    per = {}
    for i, c in enumerate(classes):
        tp = sum(1 for p, t in zip(preds, ytrue) if p == c and t == c)
        fp = sum(1 for p, t in zip(preds, ytrue) if p == c and t != c)
        fn = sum(1 for p, t in zip(preds, ytrue) if p != c and t == c)
        per[c] = {"tp": tp, "fp": fp, "fn": fn}
    f1s = []
    for c in classes:
        d = per[c]
        f1s.append(2 * d["tp"] / (2 * d["tp"] + d["fp"] + d["fn"]) if d["tp"] else 0.0)
    macro = float(np.mean(f1s))
    fam_ok = 0
    for p, t in zip(preds, ytrue):
        tf = "cert" if t.endswith("_cert") else "pkcs8"
        if p == "__cert_family__" and tf == "cert":
            fam_ok += 1
        elif p not in ("__abstain__", "__cert_family__") and p.endswith("_pkcs8") == (tf == "pkcs8"):
            fam_ok += 1
    return macro, fam_ok / len(ytrue), per


def main():
    objs = load_objects()
    tmp = os.path.join(BASE, "results", ".file_tmp")
    out = {"protocol": "tools_baseline v1",
           "env": {"file_version": subprocess.run(["file", "--version"], capture_output=True, text=True).stdout.splitlines()[0],
                   "magic_db": "system default", "oid_baseline": "11 algorithm OIDs + container-type/format head markers"},
           "classes": CLASSES, "conditions": {}}
    for cond in ["intact", "oid_zero", "head48", "trunc50"]:
        print(f"== {cond} ==", flush=True)
        cc = {"libmagic": {"preds": {}, "raw": {}}, "oid": {"preds": {}}}
        preds_m = []; preds_o = []; y = []
        for cid, c in enumerate(CLASSES):
            for d in objs[c]:
                dd = transform(d, cond)
                p_m, raw = libmagic_predict(dd, tmp)
                p_o = oid_predict(dd)
                preds_m.append(p_m); preds_o.append(p_o); y.append(c)
                cc["libmagic"]["raw"].setdefault(raw, 0)
                cc["libmagic"]["raw"][raw] += 1
        if cond == "intact":
            n_rsa = sum(1 for p, t in zip(preds_m, y) if t == "rsa2048_pkcs8" and p == "rsa2048_pkcs8")
            assert n_rsa == 300, f"libmagic sentinel failed: {n_rsa}/300 RSA recognized"
        for tag, ps in [("libmagic", preds_m), ("oid", preds_o)]:
            macro, fam, per = evaluate(ps, y, CLASSES)
            cc[tag]["macro_f1"] = macro
            cc[tag]["family_correct"] = fam
            cc[tag]["per_class_f1"] = {c: (2 * per[c]["tp"] / (2 * per[c]["tp"] + per[c]["fp"] + per[c]["fn"]) if per[c]["tp"] else 0.0) for c in CLASSES}
            print(f"  {tag}: macro={macro:.4f} family={fam:.4f}", flush=True)
        out["conditions"][cond] = cc
    if os.path.exists(tmp):
        os.remove(tmp)
    json.dump(out, open(os.path.join(BASE, "results", "tools_baseline_formal.json"), "w"), indent=1)
    print("→ results/tools_baseline_formal.json")


if __name__ == "__main__":
    main()
