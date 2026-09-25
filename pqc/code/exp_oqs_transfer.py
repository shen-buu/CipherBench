#!/usr/bin/env python3
"""
跨实现迁移测试集 + 冻结管线评测（§5 新小节）
====================================================
- 测试集：原生 OpenSSL 3.5（default provider，非 oqs-provider）生成
  6 类 PKCS#8（ML-DSA-44/65/87、ML-KEM-512/768/1024）+ 3 类自签 X.509（ML-DSA-44/65/87），
  每类 100 个，仅作测试（不进训练）。
- 管线：冻结容器管线的同配置重训（训练集 = data/ 18 类 liboqs/oqs-provider 容器，300/类）：
  S0 P1/P2（170 维统计特征 RF300）+ S1 intact（1024B 头部窗口 raw-byte RF300）。
  5 seeds（E14，per-seed 独立窗口 E8）。
- 对比：同分布 liboqs 测试对象（240/60 划分的 60 侧）逐类 F1 vs 原生 OpenSSL 对象逐类 F1。
- 输出：results/oqs_transfer_formal.json（含 env：openssl 版本、provider、liboqs 训练侧版本）。
用法：python3 exp_oqs_transfer.py --gen    （生成测试集 data_oqs_native/）
      python3 exp_oqs_transfer.py --eval   （训练+评测，输出 JSON）
"""
import os, sys, glob, json, time, argparse, subprocess
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
DATA = os.path.join(BASE, "data")
TESTDIR = os.path.join(BASE, "data_oqs_native")
RES = os.path.join(BASE, "results")
sys.path.insert(0, os.path.join(BASE, "host_package"))
from statistical import extract_full_features
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score

SEEDS = [7, 42, 99, 123, 2024]
PQC_PKCS8 = ["mldsa44_pkcs8", "mldsa65_pkcs8", "mldsa87_pkcs8",
             "mlkem512_pkcs8", "mlkem768_pkcs8", "mlkem1024_pkcs8"]
PQC_CERT = ["mldsa44_cert", "mldsa65_cert", "mldsa87_cert"]
ALG = {"mldsa44_pkcs8": "mldsa44", "mldsa65_pkcs8": "mldsa65", "mldsa87_pkcs8": "mldsa87",
       "mlkem512_pkcs8": "mlkem512", "mlkem768_pkcs8": "mlkem768", "mlkem1024_pkcs8": "mlkem1024",
       "mldsa44_cert": "mldsa44", "mldsa65_cert": "mldsa65", "mldsa87_cert": "mldsa87"}


def gen_testset():
    """原生 OpenSSL 3.5 生成 9 类 × 100 对象（PKCS#8 DER + 自签 X.509 DER）。"""
    os.makedirs(TESTDIR, exist_ok=True)
    for cls in PQC_PKCS8 + PQC_CERT:
        d = os.path.join(TESTDIR, cls)
        os.makedirs(d, exist_ok=True)
        alg = ALG[cls]
        for i in range(100):
            key_pem = os.path.join(d, f"k{i}.pem")
            if cls.endswith("_cert"):
                subprocess.run(["openssl", "genpkey", "-algorithm", alg, "-out", key_pem],
                               check=True, capture_output=True)
                subprocess.run(["openssl", "req", "-new", "-x509", "-key", key_pem,
                                "-subj", f"/CN=formal{i:05d}", "-days", "365",
                                "-outform", "DER", "-out", os.path.join(d, f"c{i}.der")],
                               check=True, capture_output=True)
                os.remove(key_pem)
            else:
                subprocess.run(["openssl", "genpkey", "-algorithm", alg,
                                "-outform", "DER", "-out", os.path.join(d, f"k{i}.der")],
                               check=True, capture_output=True)
        sizes = [os.path.getsize(f) for f in glob.glob(os.path.join(d, "*.der"))]
        print(f"[gen] {cls}: {len(sizes)} objects, size range {min(sizes)}–{max(sizes)} B", flush=True)


def load_objs(dirpath, names):
    out = {}
    for n in names:
        d = os.path.join(dirpath, n)
        out[n] = [open(f, "rb").read() for f in sorted(glob.glob(os.path.join(d, "*.der")))]
    return out


def make_window(data, scene, rng):
    WIN = 1024
    if len(data) >= WIN:
        off = int(rng.integers(0, len(data) - WIN + 1)) if scene == "p1" else 0
        return data[off: off + WIN]
    if scene == "p1":
        n = len(data)
        off = int(rng.integers(0, WIN - n + 1))
        w = bytearray(rng.bytes(WIN)); w[off: off + n] = data
        return bytes(w)
    return data + rng.bytes(WIN - len(data))


def featurize(objs, scene, seed):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for cid, n in enumerate(objs):
        for d in objs[n]:
            w = make_window(d, scene, rng)
            if scene == "s1":
                X.append(np.frombuffer(w, dtype=np.uint8).astype(np.float32) / 255.0)
            else:
                X.append(extract_full_features(w))
            y.append(cid)
    return np.array(X), np.array(y)


def run_eval():
    train_names = PQC_PKCS8 + PQC_CERT + ["ecdsap256_pkcs8", "ed25519_pkcs8", "rsa2048_pkcs8",
                                          "slhdsa128s_pkcs8", "slhdsa256s_pkcs8",
                                          "ecdsap256_cert", "ed25519_cert", "rsa2048_cert",
                                          "slhdsa128s_cert"]
    assert len(train_names) == 18
    train = load_objs(DATA, train_names)
    test = load_objs(TESTDIR, PQC_PKCS8 + PQC_CERT)
    env = {"openssl": subprocess.run(["openssl", "version"], capture_output=True, text=True).stdout.strip(),
           "test_provider": "native (OpenSSL default provider)",
           "train_side": "oqs-provider build + liboqs 0.16.0, OpenSSL 3.5.3"}
    out = {"protocol": "cross-impl transfer v1", "seeds": SEEDS, "env": env, "scenes": {}}
    for scene in ["p1", "p2", "s1"]:
        print(f"== scene {scene} ==", flush=True)
        sc = {"per_seed": {}, "test_per_class": {}}
        for seed in SEEDS:
            Xtr, ytr = featurize(train, scene, seed)
            Xte, _ = featurize(test, scene, seed)
            # 同分布参照：liboqs 240/60 划分，60 侧逐类 F1
            rng = np.random.default_rng(2000 + seed)
            tr_idx, te_idx = [], []
            for c in np.unique(ytr):
                idx = np.where(ytr == c)[0]
                perm = rng.permutation(len(idx))
                tr_idx.append(idx[perm[:240]]); te_idx.append(idx[perm[240:]])
            tr_idx = np.concatenate(tr_idx); te_idx = np.concatenate(te_idx)
            clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
            clf.fit(Xtr[tr_idx], ytr[tr_idx])
            ref_pred = clf.predict(Xtr[te_idx])
            ref_y = ytr[te_idx]
            test_pred = clf.predict(Xte)
            ref_pc = {train_names[c]: f1_score(ref_y == c, ref_pred == c)
                      for c in np.unique(ref_y) if train_names[c] in PQC_PKCS8 + PQC_CERT}
            test_pc = {n: f1_score(np.ones(100), test_pred[i * 100:(i + 1) * 100] == i, zero_division=0)
                       for i, n in enumerate(PQC_PKCS8 + PQC_CERT)}
            sc["per_seed"][str(seed)] = {"ref_pc": ref_pc, "test_pc": test_pc}
            macro_ref = float(np.mean(list(ref_pc.values())))
            macro_test = float(np.mean(list(test_pc.values())))
            print(f"  seed {seed}: ref macro {macro_ref:.4f} | transfer macro {macro_test:.4f}", flush=True)
        # 汇总
        for k in ["ref", "test"]:
            agg = {}
            for n in PQC_PKCS8 + PQC_CERT:
                vals = [sc["per_seed"][str(s)][f"{k}_pc"][n] for s in SEEDS]
                agg[n] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
            sc[f"{k}_agg"] = agg
        out["scenes"][scene] = sc
    json.dump(out, open(os.path.join(RES, "oqs_transfer_formal.json"), "w"), indent=1)
    print("→ results/oqs_transfer_formal.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--eval", action="store_true")
    a = ap.parse_args()
    if a.gen:
        gen_testset()
    if a.eval:
        run_eval()
