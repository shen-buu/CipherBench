"""
全局配置 — 面向碎片化载荷的分层混合流量识别
"""
import os
import hashlib

# ── 路径 ──────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data", "cache")
MODEL_DIR = os.path.join(ROOT, "models", "checkpoints")
RESULT_DIR = os.path.join(ROOT, "results")
for d in [DATA_DIR, MODEL_DIR, RESULT_DIR]:
    os.makedirs(d, exist_ok=True)

# ── 随机种子 ──────────────────────────────────────────
SEED = 42

# ── 数据参数 ──────────────────────────────────────────
WINDOW_SIZE = 1024          # 固定输入窗口(字节)
SAMPLES_PER_CLASS = 1000    # 每类样本数
TEST_RATIO = 0.15
VAL_RATIO = 0.15
HEADLESS_PROB = 0.5         # 去头训练概率
MIN_PAYLOAD = 32            # 最短有效载荷(字节)

# ── 密码学参数 ────────────────────────────────────────
PBKDF2_ITERATIONS = 10000
KEY_DERIVATION_SALT_LEN = 16
IV_LEN = 16                 # AES block size

# ── 50类完整分类体系 ──────────────────────────────────
CLASS_NAMES = {
    # ─── 明文文本 (6) ───
    0:  "english_text",
    1:  "chinese_text",
    2:  "python_code",
    3:  "c_cpp_code",
    4:  "json_data",
    5:  "xml_html",

    # ─── 编码 (5) ───
    6:  "base64",
    7:  "hex_base16",
    8:  "base32",
    9:  "url_encode",
    10: "quoted_printable",

    # ─── 哈希 (3) ───
    11: "md5_hex",
    12: "sha1_hex",
    13: "sha256_hex",

    # ─── 压缩 (8) ───
    14: "gzip_deflate_l9",
    15: "zip_deflate_l9",
    16: "7z_lzma2_l9",
    17: "bzip2_l9",
    18: "xz_lzma_l9",
    19: "zstd_l19",
    20: "lz4_fast",
    21: "brotli_l11",

    # ─── 对称加密 (18) ───
    22: "aes128_cbc",
    23: "aes128_gcm",
    24: "aes128_ctr",
    25: "aes192_cbc",
    26: "aes192_gcm",
    27: "aes256_cbc",
    28: "aes256_gcm",
    29: "aes256_ctr",
    30: "camellia256_cbc",
    31: "chacha20_poly1305",
    32: "rc4",
    33: "3des_ede3_cbc",
    34: "blowfish_cbc",
    35: "twofish_cbc",
    36: "sm4_cbc",
    37: "sm4_ctr",
    38: "aria256_cbc",
    39: "seed_cbc",

    # ─── 非对称加密 (6) ───
    40: "rsa_1024",
    41: "rsa_2048",
    42: "rsa_4096",
    43: "gpg_mixed",
    44: "ecc_secp256r1",
    45: "sm2_enc",

    # ─── 真随机/对照 (4) ───
    46: "dev_urandom",
    47: "python_secrets",
    48: "aes_ecb_zero_plaintext",
    49: "all_zeros",
}

CLASS_IDS = {v: k for k, v in CLASS_NAMES.items()}
NUM_CLASSES = len(CLASS_NAMES)

# 六大类别分组
CATEGORY_GROUPS = {
    "明文文本":    list(range(0, 6)),    # english_text → xml_html
    "编码":        list(range(6, 11)),   # base64 → quoted_printable
    "哈希":        list(range(11, 14)),  # md5_hex → sha256_hex
    "压缩":        list(range(14, 22)),  # gzip → brotli
    "对称加密":    list(range(22, 40)),  # aes128_cbc → seed_cbc
    "非对称加密":  list(range(40, 46)),  # rsa_1024 → sm2_enc
    "真随机/对照": list(range(46, 50)),  # dev_urandom → all_zeros
}

# ── 文件头魔数签名库 ──────────────────────────────────
MAGIC_SIGNATURES = {
    b'\x1f\x8b':                       "gzip_deflate_l9",
    b'PK\x03\x04':                     "zip_deflate_l9",
    b"7z\xbc\xaf'\x1c":                "7z_lzma2_l9",
    b'BZh':                            "bzip2_l9",
    b'\xfd7zXZ\x00':                   "xz_lzma_l9",
    b'\x28\xb5\x2f\xfd':               "zstd_l19",
    # 注：lz4 类数据为 block 格式（无 frame 魔数，见 gen_lz4），
    # 此条目仅作格式参考，不会在实际数据中命中
    b'\x04\x22\x4d\x18':               "lz4_fast",
    b'\xce\xb2\xcf\x81':               "brotli_l11",
    b'\x89PNG\r\n\x1a\n':              None,  # 不在50类中，但可识别
    b'\xff\xd8\xff':                   None,
    b'%PDF':                           None,
    b'\x7fELF':                        None,
    b'GIF89a':                         None,
    b'GIF87a':                         None,
    b'II*\x00':                        None,  # TIFF
}

# ── 模型超参数 ────────────────────────────────────────
# 统计层 梯度提升树 (sklearn HistGradientBoostingClassifier)
# 注意: 若 xgboost 可用, 优先使用 xgboost; 否则使用 sklearn 实现
GBT_PARAMS = {
    'max_iter': 300,
    'max_depth': 8,
    'learning_rate': 0.05,
    'max_leaf_nodes': 31,
    'random_state': SEED,
    'verbose': 0,
}

# 深度学习训练
BATCH_SIZE = 64         # 小batch适应2GB内存
NUM_WORKERS = 2         # DataLoader 工作进程数
# ⚠️ 重要：缓存型数据集每 epoch 打开数万个小文件，若系统软限制 ulimit -n 为
# 1024 且多进程并行训练，DataLoader worker 会静默崩溃导致训练卡死。
# 运行前请执行: ulimit -n 1048576（容器环境下提升文件句柄上限）
EPOCHS = 100
LR = 1e-3
WEIGHT_DECAY = 1e-4
EARLY_STOP_PATIENCE = 15
LR_REDUCE_PATIENCE = 5
LR_REDUCE_FACTOR = 0.5
DROPOUT1 = 0.5
DROPOUT2 = 0.3

# CNN 架构参数
CNN_CHANNELS = [64, 128, 256, 256]  # 每层conv filters
CNN_KERNEL = 3
CNN_POOL = 2
FC_DIMS = [256, 128]
