#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""轨道B：用户级 sshd 真实握手采集（KEM 产物，必达 ≥100 条）。
每轮：sshd -d 起一次（仅服务一个连接）→ ssh 客户端强制指定 KEX → 从 debug 日志
解析 DUMP_BEGIN/HEX/END（分块 dump，绕过 1024 截断）→ 长度校验 → 落盘。
产物 = client_kem_pub || server_kem_ct || client_x25519_pub || server_x25519_pub。
断点续跑：按已有 meta.jsonl 条数续。交替 KEX：奇数 sntrup761x25519、偶数 mlkem768x25519。
"""
import subprocess, time, re, os, sys, json, hashlib, datetime

SSHD = os.environ.get("SSHD_PATH", "")
SSH = os.environ.get("SSH_PATH", "")
CFG = os.environ.get("SSHD_CONFIG", "")
WILD = os.path.join(BASE, "wild")
RAW = os.path.join(WILD, "raw", "openssh")
META = os.path.join(WILD, "meta.jsonl")
N = 120

LENS = {
    "sntrup761x25519-sha512": {"client public key sntrup761:": 1158,
                               "server cipher text:": 1039,
                               "client public key 25519:": 32,
                               "server public key 25519:": 32},
    "mlkem768x25519-sha256": {"client public key mlkem768:": 1184,
                              "server cipher text:": 1088,
                              "client public key 25519:": 32,
                              "server public key 25519:": 32},
}
# 顺序：client_kem_pub, server_kem_ct, client_x25519, server_x25519


def run_round(i, alg):
    logf = os.path.join(WILD, f"ssh_session_{i:04d}.log")
    p = subprocess.Popen([SSHD, "-ddd", "-e", "-f", CFG],
                         stdout=open(logf, "w"), stderr=subprocess.STDOUT)
    time.sleep(1.2)
    try:
        subprocess.run([SSH, "-p", "2222", "-o", f"KexAlgorithms={alg}",
                        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                        "shen@127.0.0.1", "true"],
                       capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(0.5)
    p.wait(timeout=5)
    return logf


def parse_dumps(logf):
    """返回 {标签: bytes}"""
    dumps, cur = {}, None
    for ln in open(logf, errors="ignore"):
        m = re.match(r"debug3: DUMP_BEGIN (.+?) len=(\d+)", ln)
        if m:
            cur = {"label": m.group(1).strip(), "len": int(m.group(2)), "hex": ""}
            continue
        m = re.match(r"debug3: DUMP_HEX ([0-9a-f]+)", ln)
        if m and cur:
            cur["hex"] += m.group(1)
            continue
        m = re.match(r"debug3: DUMP_END (.+)", ln)
        if m and cur:
            raw = bytes.fromhex(cur["hex"])
            if len(raw) != cur["len"]:
                print(f"  [warn] {cur['label']} 长度 {len(raw)} ≠ {cur['len']}", flush=True)
            dumps[cur["label"]] = raw
            cur = None
    return dumps


def main():
    os.makedirs(RAW, exist_ok=True)
    ids = set()
    if os.path.exists(META):
        ids = {json.loads(l)["id"] for l in open(META)}
    for i in range(1, N + 1):
        if f"ssh_{i:04d}" in ids:
            continue
        alg = "sntrup761x25519-sha512" if i % 2 == 1 else "mlkem768x25519-sha256"
        logf = run_round(i, alg)
        d = parse_dumps(logf)
        need = LENS[alg]
        blob = b""
        ok = True
        for tag in ["client public key " + ("sntrup761:" if "sntrup" in alg else "mlkem768:"),
                    "server cipher text:", "client public key 25519:",
                    "server public key 25519:"]:
            v = d.get(tag)
            if v is None or len(v) != need[tag]:
                ok = False
                print(f"  [warn] session {i}: {tag} 缺失或长度不符", flush=True)
                break
            blob += v
        if not ok:
            continue
        path = os.path.join(RAW, f"{i:04d}.bin")
        open(path, "wb").write(blob)
        rec = {"id": f"ssh_{i:04d}", "source": {"type": "openssh", "ref": f"session {i}"},
               "fetched_at": datetime.datetime.now().isoformat(),
               "sha256": hashlib.sha256(blob).hexdigest(), "byte_len": len(blob),
               "oid_detected": "n/a (SSH KEX 产物，非 DER)",
               "class_label": alg,
               "verify_status": "verified_by_protocol_negotiation",
               "layout": "client_kem_pub || server_kem_ct || client_x25519_pub || server_x25519_pub"}
        with open(META, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if i % 10 == 0:
            print(f"进度 {i}/{N}（{alg}）", flush=True)
    print(f"完成，共 {sum(1 for _ in open(META))} 条（含 CT/TLS）", flush=True)


if __name__ == "__main__":
    main()
