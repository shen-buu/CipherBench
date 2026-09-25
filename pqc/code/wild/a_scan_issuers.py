#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""A 轨扩展：按 issuer 名批量查 crt.sh（≥2s 间隔、≤3 次重试），新证书下载 DER 后
以 NIST CSOR 注册表（运行时拉取，勿凭记忆）+ 本地 DER 解析做 OID 验证。
verified → meta.jsonl；OID 不符 → rejected 桶。全部查询响应落 raw/ct_log/query_*.json。
"""
import json, os, sys, time, hashlib, datetime, subprocess, urllib.parse, urllib.request

WILD = os.path.join(BASE, "wild")
RAW = os.path.join(WILD, "raw", "ct_log")
REJ = os.path.join(WILD, "rejected")
META = os.path.join(WILD, "meta.jsonl")

ISSUERS = [
    "IdenTrust Pilot Root TLS ML-KEM CA",
    "IdenTrust Pilot Root TLS SLH-DSA CA",
    "PQCSign Root CA",
    "mtest",
    "MTest",
    "DigiCert PQ",
    "Google Trust Services PQ",
    "Keyfactor PQ",
    "Entrust PQ",
]

CSOR = None  # 运行时从 NIST 拉取


def fetch(url, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CipherBench-PQC-wild/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if a == tries - 1:
                return None
            time.sleep(2 * (a + 1))
    return None


def get_csor():
    """NIST CSOR 算法注册（OID 表）；拉不到则回退到已核实的子集并记录 limitation"""
    global CSOR
    txt = fetch("https://csrc.nist.gov/CSRC/media/projects/computer-security-objects-register/documents/CSOR_OID_Table.txt")
    if txt:
        CSOR = txt.decode(errors="ignore")
        return True
    # 备用源：IANA SMI 网络对象下的 nistAlgorithms 分支不易拉；直接以已知三条 OID 兜底
    CSOR = ("2.16.840.1.101.3.4.3.17 ML-DSA-44\n"
            "2.16.840.1.101.3.4.3.18 ML-DSA-65\n"
            "2.16.840.1.101.3.4.3.19 ML-DSA-87\n")
    return False


def known_pq_oids():
    """返回 {oid 字符串: 算法名}；来自 CSOR 表（若拉到）"""
    out = {}
    for line in CSOR.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count(".") >= 5:
            out[parts[0]] = " ".join(parts[1:])
    return out


def main():
    full_csor = get_csor()
    oids = known_pq_oids()
    print(f"CSOR 表: {'NIST 官方' if full_csor else '兜底子集（limitation）'}，"
          f"已收录 {len(oids)} 条 OID", flush=True)
    known_ids = set()
    if os.path.exists(META):
        known_ids = {json.loads(l)["id"] for l in open(META)}
    for q in ISSUERS:
        time.sleep(2.2)
        qq = urllib.parse.quote(q)
        url = f"https://crt.sh/?q={qq}&output=json"
        data = fetch(url)
        fn = os.path.join(RAW, "query_" + q.replace(" ", "_") + ".json")
        if data is None:
            open(fn, "w").write("FETCH_FAILED")
            print(f"[{q}] 查询失败（重试 3 次）", flush=True)
            continue
        open(fn, "wb").write(data)
        try:
            rows = json.loads(data)
        except Exception:
            rows = []
        print(f"[{q}] {len(rows)} 条", flush=True)
        for row in rows:
            cid = str(row.get("id"))
            if cid in known_ids:
                continue
            time.sleep(2.2)
            der = fetch(f"https://crt.sh/?d={cid}")
            if der is None:
                print(f"  id={cid} 下载失败", flush=True)
                continue
            # DER 解析验证（cryptography 库）
            oid_str, sig_name = None, None
            try:
                import importlib.util
                from cryptography import x509
                cert = x509.load_der_x509_certificate(der)
                oid_str = cert.signature_algorithm_oid.dotted_string
                sig_name = cert.signature_algorithm_oid._name
            except Exception as e:
                oid_str = f"parse_error:{type(e).__name__}"
            if oid_str in oids:
                status, cls = "verified", oids[oid_str]
                dstdir = RAW
            else:
                status, cls = f"rejected: OID {oid_str} not in PQ registry", oid_str
                dstdir = REJ
            path = os.path.join(dstdir, f"{cid}.bin")
            open(path, "wb").write(der)
            rec = {"id": cid, "source": {"type": "ct_log", "ref": f"crt.sh id={cid} (issuer query '{q}')"},
                   "fetched_at": datetime.datetime.now().isoformat(),
                   "sha256": hashlib.sha256(der).hexdigest(), "byte_len": len(der),
                   "oid_detected": oid_str, "class_label": cls, "verify_status": status}
            with open(META, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            known_ids.add(cid)
            print(f"  id={cid} → {status}（{oid_str}）", flush=True)
    print("A 轨扩展扫描完成", flush=True)


if __name__ == "__main__":
    main()
