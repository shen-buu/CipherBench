#!/usr/bin/env python3
"""S2 真实封装敏感性：TLS 1.3 record 密文长度（进程内 ssl.MemoryBIO 真会话）
- 默认套件序 = TLS_AES_256_GCM_SHA384（本 Python 构建不支持 set_ciphers，握手后断言实测套件）
- 每类一次真实握手，逐对象 cli.write → 解析客户端出站 record（type 23）密文长度
- 1-NN 特征：(record 数, 首 record 密文长, 次 record 密文长)；5-fold CV × 5 seeds（E14）
输出：results/tls_records_formal.json
"""
import os, ssl, json, glob, subprocess, tempfile
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
# layouts: flat (scripts beside data/) or repo (scripts under code/)
if os.path.basename(BASE) == "code" and not os.path.isdir(os.path.join(BASE, "data")):
    BASE = os.path.dirname(BASE)
SEEDS = [7, 42, 99, 123, 2024]


def make_contexts(tmpd):
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", os.path.join(tmpd, "k.pem"), "-out", os.path.join(tmpd, "c.pem"),
                    "-subj", "/CN=tls-record-probe", "-days", "1"],
                   check=True, capture_output=True)
    sc = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sc.load_cert_chain(os.path.join(tmpd, "c.pem"), os.path.join(tmpd, "k.pem"))
    cc = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cc.check_hostname = False
    cc.verify_mode = ssl.CERT_NONE
    return sc, cc


def new_session(sc, cc):
    s_in, s_out, c_in, c_out = (ssl.MemoryBIO() for _ in range(4))
    srv = sc.wrap_bio(s_in, s_out, server_side=True)
    cli = cc.wrap_bio(c_in, c_out, server_side=False)
    while True:
        try:
            cli.do_handshake(); cd = True
        except ssl.SSLWantReadError:
            cd = False
        if s_out.pending:
            c_in.write(s_out.read())
        try:
            srv.do_handshake(); sd = True
        except ssl.SSLWantReadError:
            sd = False
        if c_out.pending:
            s_in.write(c_out.read())
        if cd and sd:
            break
    while c_out.pending:
        c_out.read()
    while s_out.pending:
        s_out.read()
    return cli, srv, c_in, s_in, c_out


def record_lengths(cli, srv, s_in, c_out, obj):
    cli.write(obj)
    recs = []
    if c_out.pending:
        data = c_out.read()
        s_in.write(data)
        srv.read(65536)
        buf = bytes(data)
        i = 0
        while i + 5 <= len(buf):
            L = int.from_bytes(buf[i + 3:i + 5], "big")
            if i + 5 + L > len(buf):
                break
            if buf[i] == 23:
                recs.append(L)
            i += 5 + L
    if i != len(buf):
        raise ValueError(f"TLS record stream truncated/misaligned at {i}/{len(buf)}")
    return recs


def main():
    tmpd = tempfile.mkdtemp(prefix="tlsprobe_")
    sc, cc = make_contexts(tmpd)
    meta = json.load(open(os.path.join(BASE, "data", "meta.json")))
    feats, y = [], []
    suite = None
    for cid, (name, v) in enumerate(meta.items()):
        if not isinstance(v, dict):
            continue
        d = os.path.join(BASE, "data", name)
        files = sorted(glob.glob(os.path.join(d, "*.bin")) + glob.glob(os.path.join(d, "*.der")))
        cli, srv, c_in, s_in, c_out = new_session(sc, cc)
        if suite is None:
            suite = cli.cipher()
            assert suite[0] == "TLS_AES_256_GCM_SHA384", suite
        for f in files:
            obj = open(f, "rb").read()
            recs = record_lengths(cli, srv, s_in, c_out, obj)
            assert recs, f"no app records for {name}/{os.path.basename(f)}"
            feats.append([len(recs), recs[0], recs[1] if len(recs) > 1 else 0])  # 0=无第二 record 的冻结哨兵
            y.append(cid)
        print(f"[records] {name}: sample_recs={recs}", flush=True)

    X = np.array(feats, dtype=np.float64)
    y = np.array(y)
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import f1_score
    per_seed = {}
    for seed in SEEDS:
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
        yt, yp = [], []
        for tr, te in skf.split(X, y):
            clf = KNeighborsClassifier(n_neighbors=1)
            clf.fit(X[tr], y[tr])
            yt.extend(y[te]); yp.extend(clf.predict(X[te]))
        per_seed[str(seed)] = float(f1_score(yt, yp, average="macro"))
        print(f"seed {seed}: {per_seed[str(seed)]:.4f}", flush=True)
    vv = np.array(list(per_seed.values()))
    out = {"protocol": "tls_records v3 (in-process ssl.MemoryBIO)",
           "cipher": "TLS_AES_256_GCM_SHA384 (default preference; negotiated and asserted per session)",
           "env": {"openssl": ssl.OPENSSL_VERSION,
                   "record_policy": "max plaintext 2^14=16384; +22B/record (5 header+1 inner+16 tag)",
                   "session": "real TLS 1.3 handshake per class, per-object write"},
           "feature": "(n_records, len1, len2)", "seeds": SEEDS,
           "macro_f1": float(vv.mean()), "std": float(vv.std()), "SE": float(vv.std() / len(vv) ** 0.5),
           "per_seed": per_seed,
           "synthetic_reference": {"none": 0.9262, "rand255": 0.5766, "rand1024": 0.3173}}
    json.dump(out, open(os.path.join(BASE, "results", "tls_records_formal.json"), "w"), indent=1)
    print("→ results/tls_records_formal.json")


if __name__ == "__main__":
    main()
