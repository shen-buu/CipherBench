#!/usr/bin/env python3
"""
探针实验 — per-class NIST SP 800-22 随机性实测（向量化电池，9 项检验）
====================================================================
类内对象长度一致 → 全部样本堆叠成 (S, n) 位矩阵做向量化检验：
frequency / block_frequency / runs / longest_run_of_ones / approximate_entropy /
serial_p1 / serial_p2 / cusum_fwd / cusum_rev。
输出每类每检验通过率（α=0.01）、均值 p 值、偏离度得分。

运行：python3 nist_battery.py（需要 numpy）
"""
import os, sys, json, math, time
import numpy as np
from scipy.special import gammaincc
from scipy.stats import norm

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
RESULT_DIR = os.path.join(ROOT, "results")
os.makedirs(RESULT_DIR, exist_ok=True)


def to_bits_stack(objects) -> np.ndarray:
    """对象字节列表 → (S, n) 位矩阵（类内定长）"""
    n = len(objects[0]) * 8
    arr = np.frombuffer(b"".join(bytes(o) for o in objects), dtype=np.uint8)
    return np.unpackbits(arr).reshape(len(objects), n).astype(np.int32)


def p_frequency(bits):  # (S,n) -> p 向量
    n = bits.shape[1]
    s = np.abs((2 * bits - 1).sum(axis=1))
    return np.vectorize(math.erfc)(s / math.sqrt(n) / math.sqrt(2))


def p_block_frequency(bits, M=128):
    S, n = bits.shape
    N = n // M
    blk = bits[:, : N * M].reshape(S, N, M)
    pi = blk.mean(axis=2)
    chi2 = 4.0 * M * ((pi - 0.5) ** 2).sum(axis=1)
    return gammaincc(N / 2.0, chi2 / 2.0)


def p_runs(bits):
    S, n = bits.shape
    pi = bits.mean(axis=1)
    v = 1 + (bits[:, 1:] != bits[:, :-1]).sum(axis=1)
    denom = 2.0 * np.sqrt(2.0 * n) * pi * (1 - pi)
    p = np.vectorize(math.erfc)(np.abs(v - 2.0 * n * pi * (1 - pi)) / np.where(denom > 0, denom, 1e-12))
    p = np.where(np.abs(pi - 0.5) < 2.0 / np.sqrt(n), p, 0.0)
    return p


def p_longest_run(bits):
    S, n = bits.shape
    if n < 6272:
        M, probs = 8, np.array([0.2148, 0.3672, 0.2305, 0.1875])
    else:
        M, probs = 128, np.array([0.1174, 0.2430, 0.2493, 0.1752, 0.1027, 0.1124])
    N = n // M
    y = np.concatenate([np.zeros((S, N, 1), np.int32),
                        bits[:, : N * M].reshape(S, N, M),
                        np.zeros((S, N, 1), np.int32)], axis=2)
    d = np.diff(y, axis=2).reshape(-1)          # (S*N*W,): +1 起点, -1 终点
    W = M + 1
    flat_s = np.where(d == 1)[0]
    flat_e = np.where(d == -1)[0]
    j1 = flat_s % W
    j2 = flat_e % W
    s_s = (flat_s // W) // N
    i_s = (flat_s // W) % N
    lens = j2 - j1                              # 按行内交替顺序配对
    mx = np.zeros((S, N), dtype=np.int32)
    np.maximum.at(mx, (s_s, i_s), lens)
    v = np.zeros((S, len(probs)), dtype=np.float64)
    for k in range(len(probs)):
        if M == 8:
            sel = (mx <= 1) if k == 0 else (mx == 2) if k == 1 else (mx == 3) if k == 2 else (mx >= 4)
        else:
            sel = (mx <= 4) if k == 0 else (mx >= 9) if k == 5 else (mx == k + 4)
        v[:, k] = sel.sum(axis=1)
    chi2 = ((v - N * probs) ** 2 / (N * probs)).sum(axis=1)
    return gammaincc(len(probs) / 2.0, chi2 / 2.0)


def p_approx_entropy(bits, m=5):
    """NIST 2.12：循环扩展 n 个重叠窗口，pi = counts/n"""
    S, n = bits.shape
    def phi(mm):
        ext = np.concatenate([bits, bits[:, : mm - 1]], axis=1)   # 循环扩展
        idx = np.zeros((S, n), dtype=np.int64)
        for j in range(mm):
            idx = (idx << 1) | ext[:, j: j + n]
        out = np.zeros(S)
        for s in range(S):
            counts = np.bincount(idx[s], minlength=2 ** mm).astype(np.float64)
            pi = counts / n
            out[s] = np.sum(pi[pi > 0] * np.log(pi[pi > 0]))
        return out
    ap_m = phi(m)
    ap_m1 = phi(m + 1)
    chi2 = 2.0 * n * (math.log(2) - (ap_m - ap_m1))
    return gammaincc(2 ** (m - 1), chi2 / 2.0)


def p_serial(bits, m=5):
    """NIST 2.11：循环扩展 n 个重叠窗口，psi = (2^m/n)·Σc² − n"""
    S, n = bits.shape
    def psi(mm):
        if mm == 0:
            return np.full(S, float(n))
        ext = np.concatenate([bits, bits[:, : mm - 1]], axis=1)
        idx = np.zeros((S, n), dtype=np.int64)
        for j in range(mm):
            idx = (idx << 1) | ext[:, j: j + n]
        out = np.zeros(S)
        for s in range(S):
            counts = np.bincount(idx[s], minlength=2 ** mm).astype(np.float64)
            out[s] = np.sum(counts ** 2) * (2 ** mm) / n - n
        return out
    p0 = psi(m); p1 = psi(m - 1); p2 = psi(m - 2)
    d1 = p0 - p1
    d2 = p0 - 2.0 * p1 + p2
    return (gammaincc(2 ** (m - 2), d1 / 2.0), gammaincc(2 ** (m - 3), d2 / 2.0))


def p_cusum(bits, reverse=False):
    S, n = bits.shape
    b = bits[:, ::-1] if reverse else bits
    cum = np.cumsum(2 * b - 1, axis=1)
    z = np.max(np.abs(cum), axis=1) / math.sqrt(n)
    out = np.zeros(S)
    for s in range(S):
        zs = z[s]
        if zs < 1e-9:
            out[s] = 1.0
            continue
        # NIST sts C 语义：int() 向零截断（不能用 floor！）
        k1 = int((-n / zs + 1) / 4); k2 = int((n / zs - 1) / 4)
        ks = np.arange(k1, k2 + 1)
        sum1 = float(np.sum(norm.cdf((4 * ks + 1) * zs) - norm.cdf((4 * ks - 1) * zs)))
        k3 = int((-n / zs - 3) / 4); k4 = int((n / zs - 1) / 4)
        ks = np.arange(k3, k4 + 1)
        sum2 = float(np.sum(norm.cdf((4 * ks + 3) * zs) - norm.cdf((4 * ks + 1) * zs)))
        out[s] = 1.0 - sum1 + sum2
    return out


TESTS = [
    ("frequency", p_frequency),
    ("block_frequency", p_block_frequency),
    ("runs", p_runs),
    ("longest_run", p_longest_run),
    ("approx_entropy", p_approx_entropy),
    ("serial_p1", lambda b: p_serial(b)[0]),
    ("serial_p2", lambda b: p_serial(b)[1]),
    ("cusum_fwd", p_cusum),
    ("cusum_rev", lambda b: p_cusum(b, reverse=True)),
]


def main():
    meta = json.load(open(os.path.join(DATA_DIR, "meta.json")))
    out = {}
    t0 = time.time()
    for name in meta:
        z = np.load(os.path.join(DATA_DIR, f"{name}.npz"), allow_pickle=True)
        objs = [bytes(o) for o in z["objects"]]
        lens = {len(o) for o in objs}
        rec = {}
        if len(lens) == 1:
            bits = to_bits_stack(objs)
            for t, fn in TESTS:
                ps = np.asarray(fn(bits), dtype=np.float64)
                rec[t] = {
                    "pass_rate": float(np.mean(ps >= 0.01)),
                    "mean_p": float(np.mean(ps)),
                    "median_p": float(np.median(ps)),
                }
        else:
            # 类内变长（如 ECDSA DER 69-72B）：逐样本 (1,n) 计算
            ps_all = {t: [] for t, _ in TESTS}
            for o in objs:
                arr = np.unpackbits(np.frombuffer(o, dtype=np.uint8)).astype(np.int32).reshape(1, -1)
                for t, fn in TESTS:
                    ps_all[t].append(float(np.asarray(fn(arr))[0]))
            for t, _ in TESTS:
                ps = np.array(ps_all[t])
                rec[t] = {
                    "pass_rate": float(np.mean(ps >= 0.01)),
                    "mean_p": float(np.mean(ps)),
                    "median_p": float(np.median(ps)),
                }
            print(f"[{name}] 变长类（{len(lens)} 种长度），逐样本计算", flush=True)
        rec["deviation_score"] = float(np.mean([rec[t]["mean_p"] < 0.01 for t, _ in TESTS]))
        out[name] = rec
        print(f"[{name}] dev={rec['deviation_score']:.2f} freq={rec['frequency']['pass_rate']:.2f} "
              f"runs={rec['runs']['pass_rate']:.2f} serial_p1={rec['serial_p1']['pass_rate']:.2f} "
              f"cusum={rec['cusum_fwd']['pass_rate']:.2f} ({time.time()-t0:.0f}s)", flush=True)
    with open(os.path.join(RESULT_DIR, "nist_battery.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"完成，总耗时 {time.time()-t0:.0f}s → results/nist_battery.json")


if __name__ == "__main__":
    main()
