"""
统计特征提取 — 170维混合特征向量
"""
import numpy as np
from config import WINDOW_SIZE

# ══════════════════════════════════════════════════════
# 基础统计特征 (15维)
# ══════════════════════════════════════════════════════

def shannon_entropy(data: bytes) -> float:
    """香农熵"""
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = counts / len(data)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def monte_carlo_pi(data: bytes) -> float:
    """蒙特卡洛π值估计"""
    if len(data) < 2:
        return 0.0
    arr = np.frombuffer(data, dtype=np.uint8)
    n = len(arr) // 2
    if n == 0:
        return 0.0
    x = arr[:2*n:2].astype(np.float64) / 255.0
    y = arr[1:2*n:2].astype(np.float64) / 255.0
    inside = np.sum(x**2 + y**2 <= 1.0)
    return float(4.0 * inside / n)


def chi_square_stat(data: bytes) -> float:
    """卡方统计量 (均匀分布为期望)"""
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    expected = len(data) / 256.0
    if expected == 0:
        return 0.0
    return float(np.sum((counts - expected)**2 / expected))


def autocorrelation(data: bytes, lag: int) -> float:
    """Lag-k自相关"""
    arr = np.frombuffer(data, dtype=np.uint8).astype(np.float64)
    n = len(arr)
    if n <= lag:
        return 0.0
    mean = np.mean(arr)
    centered = arr - mean
    denom = float(np.dot(centered, centered))
    if denom == 0:
        return 0.0
    num = float(np.dot(centered[:-lag], centered[lag:]))
    return num / denom


def byte_stats(data: bytes) -> np.ndarray:
    """字节值统计: mean, var, q25, q50, q75, iqr, unique_ratio"""
    arr = np.frombuffer(data, dtype=np.uint8).astype(np.float64)
    n = len(arr)
    mean = np.mean(arr)
    var = np.var(arr)
    q25, q50, q75 = np.percentile(arr, [25, 50, 75])
    iqr = q75 - q25
    unique = len(set(np.frombuffer(data, dtype=np.uint8))) / 256.0
    return np.array([mean, var, q25, q50, q75, iqr, unique])


def extract_statistical_features(data: bytes, payload_only: bool = True) -> np.ndarray:
    """
    提取15维基础统计特征
    payload_only=True: 仅基于有效载荷(rstrip零填充后)计算
    """
    if payload_only:
        effective = data.rstrip(b'\x00')
        if len(effective) == 0:
            effective = data
    else:
        effective = data

    feats = []
    # 1. 香农熵
    feats.append(shannon_entropy(effective))
    # 2. 蒙特卡洛π估计
    feats.append(monte_carlo_pi(effective))
    # 3. 卡方统计量
    feats.append(chi_square_stat(effective))
    # 4-8. Lag-k 自相关 (k=1,2,4,8,16)
    for lag in [1, 2, 4, 8, 16]:
        feats.append(autocorrelation(effective, lag))
    # 9-15. 字节值分布统计 (7维)
    feats.extend(byte_stats(effective).tolist())

    return np.array(feats, dtype=np.float32)


# ══════════════════════════════════════════════════════
# N-Gram频率特征 (128维)
# ══════════════════════════════════════════════════════

def extract_ngram_features(data: bytes) -> np.ndarray:
    """
    提取N-Gram频率特征
    1-Gram (256维 → PCA降至64维)
    2-Gram (选用前64维高频组合)
    """
    arr = np.frombuffer(data, dtype=np.uint8)

    # 1-Gram: 字节频率分布 (256维, 保留全部)
    gram1 = np.bincount(arr, minlength=256).astype(np.float32)
    gram1 = gram1 / max(len(arr), 1)

    # 简单降维: 将256维按16个区间聚合 → 16维
    gram1_reduced = gram1.reshape(16, 16).sum(axis=1)

    # 2-Gram: 字节对频率 (选最重要的)
    if len(arr) >= 2:
        pairs = (arr[:-1].astype(np.int32) * 256 + arr[1:].astype(np.int32))
        pair_counts = np.bincount(pairs, minlength=65536)
        # 保留Top-48高频pair
        top_indices = np.argsort(pair_counts)[-48:]
        gram2 = pair_counts[top_indices].astype(np.float32) / max(len(arr) - 1, 1)
    else:
        gram2 = np.zeros(48, dtype=np.float32)

    # 2-Gram额外: 16个区间转移矩阵 → 64维展平
    if len(arr) >= 2:
        trans = np.zeros((16, 16), dtype=np.float32)
        for i in range(len(arr) - 1):
            row = arr[i] // 16
            col = arr[i+1] // 16
            trans[row, col] += 1
        trans = trans.flatten()
        trans = trans / max(trans.sum(), 1)
    else:
        trans = np.zeros(256, dtype=np.float32)

    # 组合: 16(gram1_agg) + 48(gram2_top) + 64(trans_partial) = 128
    feats = np.concatenate([gram1_reduced, gram2, trans[:64]])
    return feats.astype(np.float32)


# ══════════════════════════════════════════════════════
# 编码结构特征 (27维)
# ══════════════════════════════════════════════════════

def is_valid_utf8(data: bytes) -> float:
    """UTF-8合法性校验"""
    try:
        data.decode('utf-8')
        return 1.0
    except:
        return 0.0


def extract_encoding_features(data: bytes) -> np.ndarray:
    """提取27维编码结构特征"""
    arr = np.frombuffer(data, dtype=np.uint8)
    n = len(arr)

    feats = []
    # 1. UTF-8合法性
    feats.append(is_valid_utf8(data))
    # 2. 可打印字符比例 (ASCII 32-126)
    feats.append(float(np.sum((arr >= 32) & (arr <= 126))) / n)
    # 3. 空白字符比例 (空格\\t\\n\\r)
    whitespace = {9, 10, 13, 32}
    feats.append(float(np.sum([1 for b in arr if b in whitespace])) / n)
    # 4. 控制字符比例 (0-31 except whitespace + 127)
    control = set(range(0, 32)) - whitespace | {127}
    feats.append(float(np.sum([1 for b in arr if b in control])) / n)
    # 5. 高位字节比例 (>= 0x80)
    feats.append(float(np.sum(arr >= 128)) / n)
    # 6-10. 连续高位字节游程统计
    high_run = (arr >= 128).astype(int)
    runs = []
    run_len = 0
    for v in high_run:
        if v:
            run_len += 1
        else:
            if run_len > 0:
                runs.append(run_len)
            run_len = 0
    if run_len > 0:
        runs.append(run_len)
    if runs:
        feats.extend([len(runs) / n * 256, np.mean(runs), np.max(runs), np.min(runs), np.std(runs) if len(runs) > 1 else 0])
    else:
        feats.extend([0, 0, 0, 0, 0])
    # 11-26. 字节值直方图分区统计 (16维)
    for i in range(16):
        lo, hi = i * 16, (i + 1) * 16
        feats.append(float(np.sum((arr >= lo) & (arr < hi))) / n)
    # 27. 全零字节比例
    feats.append(float(np.sum(arr == 0)) / n)

    return np.array(feats, dtype=np.float32)


# ══════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════

def extract_full_features(data: bytes, dual_view: bool = True) -> np.ndarray:
    """
    提取完整170维特征向量

    Args:
        data: 原始1024字节数据(含零填充)
        dual_view: 是否使用双视图处理
            - True: 统计特征基于rstrip后有效载荷, 编码特征基于完整数据
            - False: 所有特征基于完整数据
    Returns:
        170维特征向量
    """
    stats_feat = extract_statistical_features(data, payload_only=dual_view)
    ngram_feat = extract_ngram_features(data)
    enc_feat = extract_encoding_features(data)

    return np.concatenate([stats_feat, ngram_feat, enc_feat]).astype(np.float32)


def get_feature_dim() -> int:
    """返回特征总维度"""
    return 170


if __name__ == "__main__":
    # 快速测试
    test_data = b"Hello World! " * 80 + b'\x00' * 100
    test_data = test_data[:1024]
    feats = extract_full_features(test_data, dual_view=True)
    print(f"特征维度: {feats.shape[0]}")
    print(f"特征范围: [{feats.min():.4f}, {feats.max():.4f}]")
    entropy_input = test_data.rstrip(b'\x00')
    print(f"香农熵: {shannon_entropy(entropy_input):.4f}")
