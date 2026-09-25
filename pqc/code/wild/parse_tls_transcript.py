#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""轨道C：解析 openssl s_client -msg 转录，抠 X25519MLKEM768(4588) 的 key_share。
-msg 输出形如：">>> TLS 1.3, Handshake [length ..], ClientHello" 后接 16 字节/行的 hex 块。
结构（TLS 1.3）：ClientHello: type(1) len(3) ver(2) random(32) sid(1+n) ciphers(2+n)
comp(1+n) ext_len(2) extensions[type(2) len(2) data]。key_share=51；entry: group(2) len(2) ke。
X25519MLKEM768 客户端 key_share = X25519 pub(32) || ML-KEM-768 pubkey(1184)；
服务器 key_share = X25519 pub(32) || ML-KEM-768 ciphertext(1088)。IANA 4588（已查表）。
"""
import re, sys, hashlib, json, datetime

TRAN = os.path.join(BASE, "wild", "raw", "tls_endpoint", "pq_cf_transcript.txt")
OUTDIR = os.path.join(BASE, "wild", "raw", "tls_endpoint") + os.sep
GROUP = 4588


def parse_msgs(path):
    lines = open(path, errors="ignore").read().splitlines()
    msgs, cur, buf = [], None, bytearray()
    for ln in lines:
        if ln.startswith(">>> TLS") or ln.startswith("<<< TLS"):
            if cur in ("ClientHello", "ServerHello") and buf:
                msgs.append((cur, bytes(buf)))
            m = re.search(r"(ClientHello|ServerHello)", ln)
            cur = m.group(1) if m else None
            buf = bytearray()
        elif re.match(r"^\s+([0-9a-f]{2}[ \t]+)+[0-9a-f]{2}\s*$", ln):
            hx = re.sub(r"\s", "", ln)
            try:
                buf += bytes.fromhex(hx)
            except ValueError:
                pass
    if cur in ("ClientHello", "ServerHello") and buf:
        msgs.append((cur, bytes(buf)))
    return msgs


def find_keyshare(data, label):
    """返回 [(group, key_bytes)]，按 ClientHello/ServerHello 结构解析"""
    out = []
    i = 0
    if label == "ClientHello":
        i = 1 + 3 + 2 + 32
        n = data[i]; i += 1 + n
        n = int.from_bytes(data[i:i+2], "big"); i += 2 + n
        n = data[i]; i += 1 + n
        ext_len = int.from_bytes(data[i:i+2], "big"); i += 2
        end = i + ext_len
    else:
        i = 1 + 3 + 2 + 32
        n = data[i]; i += 1 + n            # legacy session id
        i += 2                             # cipher suite（2 字节值，非长度）
        i += 1                             # compression method
        ext_len = int.from_bytes(data[i:i+2], "big"); i += 2
        end = i + ext_len
    while i + 4 <= end:
        et = int.from_bytes(data[i:i+2], "big")
        el = int.from_bytes(data[i+2:i+4], "big")
        i += 4
        if et == 51:                       # key_share
            j = i
            if label == "ClientHello":
                j += 2                     # client_shares 向量长度
                while j + 4 <= i + el:
                    g = int.from_bytes(data[j:j+2], "big")
                    kl = int.from_bytes(data[j+2:j+4], "big")
                    j += 4
                    if g == GROUP:
                        out.append((g, data[j:j+kl]))
                    j += kl
            else:                          # ServerHello：单 KeyShareEntry
                g = int.from_bytes(data[j:j+2], "big")
                kl = int.from_bytes(data[j+2:j+4], "big")
                if g == GROUP:
                    out.append((g, data[j+4:j+4+kl]))
        i += el
    return out


def main():
    msgs = parse_msgs(TRAN)
    print(f"消息记录 {len(msgs)} 条")
    results = {}
    for label, raw in msgs:
        ks = find_keyshare(raw, label)
        for g, kb in ks:
            print(f"{label}: group={g} key_len={len(kb)}")
            results[label] = kb
    # 校验长度：客户端 1216（32+1184）、服务器 1120（32+1088）
    assert len(results.get("ClientHello", b"")) == 1216, "客户端 key_share 长度异常"
    assert len(results.get("ServerHello", b"")) == 1120, "服务器 key_share 长度异常"
    blob = results["ClientHello"][32:] + results["ServerHello"][32:]   # ML-KEM pub || ciphertext
    open(OUTDIR + "pq_cf_x25519mlkem768.bin", "wb").write(blob)
    rec = {"id": "pq_cf_1", "source": {"type": "tls_endpoint", "ref": "pq.cloudflareresearch.com:443"},
           "fetched_at": datetime.datetime.now().isoformat(),
           "sha256": hashlib.sha256(blob).hexdigest(), "byte_len": len(blob),
           "oid_detected": "n/a (TLS key_share, group 4588 per IANA registry)",
           "class_label": "X25519MLKEM768", "verify_status": "verified_by_protocol_negotiation",
           "layout": "ML-KEM-768 pubkey(1184) || ML-KEM-768 ciphertext(1088)"}
    with open(os.path.join(BASE, "wild", "meta.jsonl"), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"落盘 {OUTDIR}pq_cf_x25519mlkem768.bin ({len(blob)}B) + meta.jsonl")


if __name__ == "__main__":
    main()
