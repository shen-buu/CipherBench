"""
SM4实现指纹识别 — 全局配置
目标会议: FSE 2027 (ToSC) / ACNS 2027 / CSP 2027
"""
import os
import secrets
import hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data", "cache")
MODEL_DIR = os.path.join(ROOT, "models", "checkpoints")
RESULT_DIR = os.path.join(ROOT, "results")
for d in [DATA_DIR, MODEL_DIR, RESULT_DIR]:
    os.makedirs(d, exist_ok=True)

SEED = 42
WINDOW_SIZE = 1024
SAMPLES_PER_CONFIG = 2000  # 每个(库×模式)组合的样本数
TEST_RATIO = 0.2
VAL_RATIO = 0.1

# ── 被测密码库 ────────────────────────────────────────
# 每组 (库名, 导入方式, 是否可用)
LIBRARIES = {
    "gmssl": {
        "name": "GmSSL",
        "version_hint": "3.x (Python)",
        "description": "北京大学开发, 最广泛使用的国密Python库",
        "sm4_supported": True,
        "aes_supported": False,
    },
    "cryptography": {
        "name": "pyca/cryptography",
        "version_hint": "41.x+ (Python)",
        "description": "Python密码学标准库, SM4支持始于2.0",
        "sm4_supported": True,
        "aes_supported": True,
    },
    "manual": {
        "name": "Manual Reference",
        "version_hint": "自实现 (Python)",
        "description": "基于gmssl SM4原语的手工CBC/CTR模式实现",
        "sm4_supported": True,
        "aes_supported": False,
    },
    "openssl": {
        "name": "OpenSSL CLI",
        "version_hint": "3.x (subprocess)",
        "description": "命令行调用, 工业标准密码库",
        "sm4_supported": True,
        "aes_supported": True,
    },
    "pycryptodome": {
        "name": "PyCryptodome",
        "version_hint": "3.x (Python)",
        "description": "广泛使用的第三方Python密码库",
        "sm4_supported": False,  # PyCryptodome 不支持 SM4
        "aes_supported": True,
    },
}

# ── 被测算法与模式 ────────────────────────────────────
SM4_MODES = ["cbc", "ctr", "gcm"]
AES_MODES = ["cbc", "ctr", "gcm"]  # 对照组

# ── 分类任务定义 ─────────────────────────────────────
# 任务1: SM4-CBC × 5库 → 5分类
# 任务2: SM4-CTR × 5库 → 5分类
# 任务3: SM4-GCM × 5库 → 5分类
# 任务4: SM4全模式 × 5库 → 15分类 (跨模式)
# 任务5: AES-256-CBC × 3库 → 3分类 (对照组)
# 任务6: 跨算法泛化 (SM4-trained → AES test)

# ── 模型参数 (复用已验证架构) ───────────────────────
BATCH_SIZE = 64
EPOCHS = 100
LR = 1e-3
WEIGHT_DECAY = 1e-4
EARLY_STOP_PATIENCE = 15

CNN_CHANNELS = [64, 128, 256, 256]
CNN_KERNEL = 3
CNN_POOL = 2
FC_DIMS = [256, 128]
DROPOUT1 = 0.5
DROPOUT2 = 0.3
