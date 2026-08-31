"""
多库SM4/AES密文生成器
核心设计: 同一(明文,密钥,IV) → 不同库 → 不同密文(因实现差异)
"""
import os
import random
import secrets
import hashlib
import subprocess
import tempfile
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from config import *

# ── 密码学基础 ────────────────────────────────────────
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.backends import default_backend

random.seed(SEED)
np.random.seed(SEED)


def _check_openssl_sm4() -> bool:
    """检查OpenSSL是否支持SM4"""
    try:
        r = subprocess.run(["openssl", "enc", "-ciphers"],
                          capture_output=True, text=True, timeout=5)
        return "sm4" in r.stdout.lower()
    except:
        return False


def _check_openssl() -> bool:
    """检查OpenSSL是否可用"""
    try:
        r = subprocess.run(["openssl", "version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except:
        return False


# ── 可用性标志 ────────────────────────────────────────
HAS_OPENSSL = _check_openssl()
HAS_OPENSSL_SM4 = _check_openssl_sm4() if HAS_OPENSSL else False

# ── 明文语料 ──────────────────────────────────────────
def _get_plaintexts(n: int, size: int = 512) -> list:
    """生成n条指定长度的明文(确定性, 可复现)"""
    rng = random.Random(SEED)
    texts = []
    for i in range(n):
        rng.seed(SEED * 10000 + i)
        texts.append(bytes([rng.randint(32, 126) for _ in range(size)]))
    return texts


# ══════════════════════════════════════════════════════
# SM4 实现: GmSSL (Python)
# ══════════════════════════════════════════════════════

from gmssl.sm4 import CryptSM4, SM4_ENCRYPT


def _gmssl_encrypt_block(sm4, block: bytes) -> bytes:
    """GmSSL 无填充单块SM4加密。

    实现说明：
    CryptSM4.crypt_ecb 默认 padding_mode=PKCS7，对16字节输入会再垫一整块
    并返回32字节 = E(block) || E(0x10*16)。手工CBC把32字节整体拼接后密文
    变成 E||X||E||X...（X为常量块），产生周期伪影并被分类器利用。
    使用 one_round 单块加密，输出与 pyca/cryptography 逐字节一致。
    """
    return bytes(sm4.one_round(sm4.sk, list(block)))


def sm4_gmssl_cbc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """GmSSL SM4-CBC: 手工CBC模式(使用gmssl ECB原语, 无填充单块调用)"""
    sm4 = CryptSM4()
    sm4.set_key(key, SM4_ENCRYPT)

    # PKCS7 padding
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)

    ct = b''
    prev = iv
    for i in range(0, len(padded), 16):
        block = bytes(a ^ b for a, b in zip(padded[i:i+16], prev))
        ct_block = _gmssl_encrypt_block(sm4, block)
        ct += ct_block
        prev = ct_block
    return ct


def sm4_gmssl_ctr(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """GmSSL SM4-CTR: 手工CTR模式（无填充单块调用）"""
    sm4 = CryptSM4()
    sm4.set_key(key, SM4_ENCRYPT)
    ct = b''
    counter_base = int.from_bytes(nonce[:8], 'big')
    for i in range(0, len(plaintext), 16):
        counter = (counter_base + i // 16).to_bytes(16, 'big')
        keystream = _gmssl_encrypt_block(sm4, counter)
        chunk = plaintext[i:i+16]
        ct += bytes(a ^ b for a, b in zip(chunk, keystream[:len(chunk)]))
    return ct


# 注意：
# gmssl 不原生支持 SM4-GCM，跨库 GCM 任务仅注册真正实现 GCM 的库（cryptography）。


# ══════════════════════════════════════════════════════
# SM4 实现: cryptography (pyca)
# ══════════════════════════════════════════════════════

def sm4_cryptography_cbc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """pyca/cryptography SM4-CBC"""
    cipher = Cipher(algorithms.SM4(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = sym_padding.PKCS7(128).padder()
    return encryptor.update(padder.update(plaintext) + padder.finalize()) + encryptor.finalize()


def sm4_cryptography_ctr(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """pyca/cryptography SM4-CTR"""
    cipher = Cipher(algorithms.SM4(key), modes.CTR(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def sm4_cryptography_gcm(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """pyca/cryptography SM4-GCM (12字节nonce, 追加16字节tag)"""
    cipher = Cipher(algorithms.SM4(key), modes.GCM(nonce[:12]), backend=default_backend())
    encryptor = cipher.encryptor()
    ct = encryptor.update(plaintext) + encryptor.finalize()
    return ct + encryptor.tag  # GCM标准: 密文+认证标签


# ══════════════════════════════════════════════════════
# SM4 实现: Manual Reference (手工参考实现)
# ══════════════════════════════════════════════════════

# SM4 S-Box (来自 GM/T 0002-2012)
SBOX = [
    0xd6, 0x90, 0xe9, 0xfe, 0xcc, 0xe1, 0x3d, 0xb7, 0x16, 0xb6, 0x14, 0xc2, 0x28, 0xfb, 0x2c, 0x05,
    0x2b, 0x67, 0x9a, 0x76, 0x2a, 0xbe, 0x04, 0xc3, 0xaa, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
    0x9c, 0x42, 0x50, 0xf4, 0x91, 0xef, 0x98, 0x7a, 0x33, 0x54, 0x0b, 0x43, 0xed, 0xcf, 0xac, 0x62,
    0xe4, 0xb3, 0x1c, 0xa9, 0xc9, 0x08, 0xe8, 0x95, 0x80, 0xdf, 0x94, 0xfa, 0x75, 0x8f, 0x3f, 0xa6,
    0x47, 0x07, 0xa7, 0xfc, 0xf3, 0x73, 0x17, 0xba, 0x83, 0x59, 0x3c, 0x19, 0xe6, 0x85, 0x4f, 0xa8,
    0x68, 0x6b, 0x81, 0xb2, 0x71, 0x64, 0xda, 0x8b, 0xf8, 0xeb, 0x0f, 0x4b, 0x70, 0x56, 0x9d, 0x35,
    0x1e, 0x24, 0x0e, 0x5e, 0x63, 0x58, 0xd1, 0xa2, 0x25, 0x22, 0x7c, 0x3b, 0x01, 0x21, 0x78, 0x87,
    0xd4, 0x00, 0x46, 0x57, 0x9f, 0xd3, 0x27, 0x52, 0x4c, 0x36, 0x02, 0xe7, 0xa0, 0xc4, 0xc8, 0x9e,
    0xea, 0xbf, 0x8a, 0xd2, 0x40, 0xc7, 0x38, 0xb5, 0xa3, 0xf7, 0xf2, 0xce, 0xf9, 0x61, 0x15, 0xa1,
    0xe0, 0xae, 0x5d, 0xa4, 0x9b, 0x34, 0x1a, 0x55, 0xad, 0x93, 0x32, 0x30, 0xf5, 0x8c, 0xb1, 0xe3,
    0x1d, 0xf6, 0xe2, 0x2e, 0x82, 0x66, 0xca, 0x60, 0xc0, 0x29, 0x23, 0xab, 0x0d, 0x53, 0x4e, 0x6f,
    0xd5, 0xdb, 0x37, 0x45, 0xde, 0xfd, 0x8e, 0x2f, 0x03, 0xff, 0x6a, 0x72, 0x6d, 0x6c, 0x5b, 0x51,
    0x8d, 0x1b, 0xaf, 0x92, 0xbb, 0xdd, 0xbc, 0x7f, 0x11, 0xd9, 0x5c, 0x41, 0x1f, 0x10, 0x5a, 0xd8,
    0x0a, 0xc1, 0x31, 0x88, 0xa5, 0xcd, 0x7b, 0xbd, 0x2d, 0x74, 0xd0, 0x12, 0xb8, 0xe5, 0xb4, 0xb0,
    0x89, 0x69, 0x97, 0x4a, 0x0c, 0x96, 0x77, 0x7e, 0x65, 0xb9, 0xf1, 0x09, 0xc5, 0x6e, 0xc6, 0x84,
    0x18, 0xf0, 0x7d, 0xec, 0x3a, 0xdc, 0x4d, 0x20, 0x79, 0xee, 0x5f, 0x3e, 0xd7, 0xcb, 0x39, 0x48,
]

FK = [0xa3b1bac6, 0x56aa3350, 0x677d9197, 0xb27022dc]
CK = [
    0x00070e15, 0x1c232a31, 0x383f464d, 0x545b6269,
    0x70777e85, 0x8c939aa1, 0xa8afb6bd, 0xc4cbd2d9,
    0xe0e7eef5, 0xfc030a11, 0x181f262d, 0x343b4249,
    0x50575e65, 0x6c737a81, 0x888f969d, 0xa4abb2b9,
    0xc0c7ced5, 0xdce3eaf1, 0xf8ff060d, 0x141b2229,
    0x30373e45, 0x4c535a61, 0x686f767d, 0x848b9299,
    0xa0a7aeb5, 0xbcc3cad1, 0xd8dfe6ed, 0xf4fb0209,
    0x10171e25, 0x2c333a41, 0x484f565d, 0x646b7279,
]


def _sm4_tau(a):
    """S盒字节替换"""
    return (SBOX[(a >> 24) & 0xff] << 24) | \
           (SBOX[(a >> 16) & 0xff] << 16) | \
           (SBOX[(a >> 8) & 0xff] << 8) | \
           SBOX[a & 0xff]


def _sm4_l(b):
    """加密轮线性变换 L (rot2/10/18/24)"""
    return b ^ ((b << 2 | b >> 30) & 0xffffffff) ^ \
           ((b << 10 | b >> 22) & 0xffffffff) ^ \
           ((b << 18 | b >> 14) & 0xffffffff) ^ \
           ((b << 24 | b >> 8) & 0xffffffff)


def _sm4_l_prime(b):
    """密钥扩展线性变换 L' (rot13/23) — GM/T 0002-2012 规定"""
    return b ^ ((b << 13 | b >> 19) & 0xffffffff) ^ \
           ((b << 23 | b >> 9) & 0xffffffff)


def _sm4_round_function(x0, x1, x2, x3, rk):
    """SM4轮函数"""
    return x0 ^ _sm4_l(_sm4_tau(x1 ^ x2 ^ x3 ^ rk))


def _sm4_key_schedule(mk):
    """SM4密钥扩展。

    实现说明：
    密钥扩展按标准要求使用 L'（rot13/23）置换，
    输出与 gmssl/cryptography 的轮密钥一致。
    """
    K = [0] * 36
    for i in range(4):
        K[i] = mk[i] ^ FK[i]
    rk = [0] * 32
    for i in range(32):
        t = _sm4_tau(K[i+1] ^ K[i+2] ^ K[i+3] ^ CK[i])
        K[i+4] = K[i] ^ _sm4_l_prime(t)
        rk[i] = K[i+4]
    return rk


def _sm4_encrypt_block(block_bytes, rk):
    """SM4加密单个128-bit块"""
    X = [int.from_bytes(block_bytes[i:i+4], 'big') for i in range(0, 16, 4)]
    for i in range(32):
        X.append(_sm4_round_function(X[i], X[i+1], X[i+2], X[i+3], rk[i]))
    Y = [X[35], X[34], X[33], X[32]]
    return b''.join(y.to_bytes(4, 'big') for y in Y)


def sm4_manual_ecb_encrypt(plaintext_block: bytes, key: bytes) -> bytes:
    """手工SM4 ECB: 加密单个16字节块"""
    mk = [int.from_bytes(key[i:i+4], 'big') for i in range(0, 16, 4)]
    rk = _sm4_key_schedule(mk)
    return _sm4_encrypt_block(plaintext_block, rk)


def sm4_manual_cbc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """手工SM4-CBC"""
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)
    mk = [int.from_bytes(key[i:i+4], 'big') for i in range(0, 16, 4)]
    rk = _sm4_key_schedule(mk)
    ct = b''
    prev = iv
    for i in range(0, len(padded), 16):
        block = bytes(a ^ b for a, b in zip(padded[i:i+16], prev))
        ct_block = _sm4_encrypt_block(block, rk)
        ct += ct_block
        prev = ct_block
    return ct


def sm4_manual_ctr(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """手工SM4-CTR"""
    mk = [int.from_bytes(key[i:i+4], 'big') for i in range(0, 16, 4)]
    rk = _sm4_key_schedule(mk)
    ct = b''
    counter_base = int.from_bytes(nonce[:8], 'big')
    for i in range(0, len(plaintext), 16):
        counter = (counter_base + i // 16).to_bytes(16, 'big')
        keystream = _sm4_encrypt_block(counter, rk)
        chunk = plaintext[i:i+16]
        ct += bytes(a ^ b for a, b in zip(chunk, keystream[:len(chunk)]))
    return ct


# 注意：
# manual/gmssl 库不原生支持 SM4-GCM（openssl 亦不支持 sm4-gcm）。
# 跨库 GCM 任务仅注册真正实现 GCM 的库（cryptography）。


# ══════════════════════════════════════════════════════
# SM4 实现: OpenSSL CLI (subprocess)
# ══════════════════════════════════════════════════════

def _openssl_sm4_encrypt(plaintext: bytes, key_hex: str, iv_hex: str, mode: str) -> bytes:
    """通过OpenSSL CLI调用SM4加密"""
    if not HAS_OPENSSL_SM4:
        raise RuntimeError("OpenSSL不支持SM4")

    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f_in:
        f_in.write(plaintext)
        in_path = f_in.name

    out_path = in_path + '.enc'

    mode_map = {'cbc': 'sm4-cbc', 'ctr': 'sm4-ctr', 'gcm': 'sm4-gcm'}
    openssl_mode = mode_map.get(mode, 'sm4-cbc')

    # CBC 不加 -nopad，让 openssl 做标准 PKCS7 填充，
    # 输出长度与 cryptography/gmssl/manual 一致（512字节明文 → 528字节密文），
    # 避免密文长度差 16 字节带来的零填充比例泄漏；CTR 无填充，保持 -nopad。
    cmd = [
        "openssl", "enc", f"-{openssl_mode}", "-e",
        "-K", key_hex, "-iv", iv_hex,
        "-in", in_path, "-out", out_path,
        "-nosalt",
    ]
    if mode != "cbc":
        cmd.append("-nopad")
    subprocess.run(cmd, capture_output=True, check=True, timeout=10)

    with open(out_path, 'rb') as f:
        ct = f.read()

    os.unlink(in_path)
    if os.path.exists(out_path):
        os.unlink(out_path)

    return ct


# ══════════════════════════════════════════════════════
# AES 对照组实现 (cryptography, PyCryptodome, OpenSSL)
# ══════════════════════════════════════════════════════

def aes_crypto_cbc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = sym_padding.PKCS7(128).padder()
    return encryptor.update(padder.update(plaintext) + padder.finalize()) + encryptor.finalize()


def aes_crypto_ctr(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=default_backend())
    return cipher.encryptor().update(plaintext)


def aes_crypto_gcm(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce[:12]), backend=default_backend())
    encryptor = cipher.encryptor()
    ct = encryptor.update(plaintext) + encryptor.finalize()
    return ct + encryptor.tag


def _aes_pycryptodome_cbc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    from Crypto.Cipher import AES as AES_P
    from Crypto.Util.Padding import pad
    cipher = AES_P.new(key, AES_P.MODE_CBC, iv)
    return cipher.encrypt(pad(plaintext, 16))


def _aes_pycryptodome_ctr(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    from Crypto.Cipher import AES as AES_P
    cipher = AES_P.new(key, AES_P.MODE_CTR, nonce=nonce)
    return cipher.encrypt(plaintext)


def _aes_pycryptodome_gcm(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    from Crypto.Cipher import AES as AES_P
    cipher = AES_P.new(key, AES_P.MODE_GCM, nonce=nonce[:12])
    ct, tag = cipher.encrypt_and_digest(plaintext)
    return ct + tag


def _aes_openssl_encrypt(plaintext: bytes, key_hex: str, iv_hex: str, mode: str) -> bytes:
    if not HAS_OPENSSL:
        raise RuntimeError("OpenSSL不可用")
    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f_in:
        f_in.write(plaintext)
        in_path = f_in.name
    out_path = in_path + '.enc'
    mode_map = {'cbc': 'aes-256-cbc', 'ctr': 'aes-256-ctr', 'gcm': 'aes-256-gcm'}
    # CBC 交给 openssl 做 PKCS7 填充（长度与其它库一致），
    # CTR 保持 -nopad（流式无填充）
    cmd = ["openssl", "enc", f"-{mode_map[mode]}", "-e",
           "-K", key_hex, "-iv", iv_hex, "-in", in_path, "-out", out_path,
           "-nosalt"]
    if mode != "cbc":
        cmd.append("-nopad")
    subprocess.run(cmd, capture_output=True, check=True, timeout=10)
    with open(out_path, 'rb') as f:
        ct = f.read()
    os.unlink(in_path)
    if os.path.exists(out_path):
        os.unlink(out_path)
    return ct


# ══════════════════════════════════════════════════════
# 统一生成接口
# ══════════════════════════════════════════════════════

# SM4 生成器注册表: (lib_key, mode) → 生成函数
# 实现说明：
# 1) GCM 仅保留真正实现 GCM 的库；
# 2) openssl enc 支持 sm4-cbc/sm4-ctr（无 sm4-gcm），且 -nopad 时要求明文为
#    16 的倍数（生成器明文固定 512 字节，满足要求）。
def _openssl_sm4_cbc(plaintext, key, iv):
    return _openssl_sm4_encrypt(plaintext, key.hex(), iv.hex(), 'cbc')


def _openssl_sm4_ctr(plaintext, key, iv):
    return _openssl_sm4_encrypt(plaintext, key.hex(), iv.hex(), 'ctr')


SM4_GENERATORS = {
    # GmSSL（无GCM支持）
    ("gmssl", "cbc"): sm4_gmssl_cbc,
    ("gmssl", "ctr"): sm4_gmssl_ctr,
    # cryptography
    ("cryptography", "cbc"): sm4_cryptography_cbc,
    ("cryptography", "ctr"): sm4_cryptography_ctr,
    ("cryptography", "gcm"): sm4_cryptography_gcm,
    # Manual（无GCM支持）
    ("manual", "cbc"): sm4_manual_cbc,
    ("manual", "ctr"): sm4_manual_ctr,
    # OpenSSL CLI（无sm4-gcm）
    ("openssl", "cbc"): _openssl_sm4_cbc,
    ("openssl", "ctr"): _openssl_sm4_ctr,
}

# AES 生成器注册表（注册 openssl cbc/ctr；gcm 不注册——
# 不同 openssl 版本的 enc -aes-256-gcm 是否输出认证标签行为不一，
# 跨库 GCM 对照只用行为一致的 cryptography 实现）
def _openssl_aes_cbc(plaintext, key, iv):
    return _aes_openssl_encrypt(plaintext, key.hex(), iv.hex(), 'cbc')


def _openssl_aes_ctr(plaintext, key, iv):
    return _aes_openssl_encrypt(plaintext, key.hex(), iv.hex(), 'ctr')


AES_GENERATORS = {
    ("cryptography", "cbc"): aes_crypto_cbc,
    ("cryptography", "ctr"): aes_crypto_ctr,
    ("cryptography", "gcm"): aes_crypto_gcm,
    ("pycryptodome", "cbc"): _aes_pycryptodome_cbc,
    ("pycryptodome", "ctr"): _aes_pycryptodome_ctr,
    ("pycryptodome", "gcm"): _aes_pycryptodome_gcm,
    ("openssl", "cbc"): _openssl_aes_cbc,
    ("openssl", "ctr"): _openssl_aes_ctr,
}


def generate_sm4_samples(lib_key: str, mode: str, n: int = SAMPLES_PER_CONFIG) -> list:
    """
    为指定的库和模式生成n条SM4密文样本
    Returns: [(ciphertext, iv, key, plaintext), ...]
    所有库使用相同的(plaintext, key, iv)序列以实现可控比较
    """
    gen_func = SM4_GENERATORS.get((lib_key, mode))
    if gen_func is None:
        print(f"   ⚠ {lib_key}/{mode} 不可用, 跳过")
        return []

    plaintexts = _get_plaintexts(n, 512)
    samples = []

    # 确定性生成key和IV (复现性)
    rng = random.Random(SEED)
    for i in range(n):
        rng.seed(SEED * 10000 + i)
        key = bytes([rng.randint(0, 255) for _ in range(16)])  # SM4: 128-bit key
        iv = bytes([rng.randint(0, 255) for _ in range(16)])   # 128-bit IV
        nonce = iv  # CTR/GCM use same IV as nonce

        pt = plaintexts[i]
        try:
            if mode == "ctr":
                ct = gen_func(pt, key, nonce)
            elif mode == "gcm":
                ct = gen_func(pt, key, nonce)
            else:
                ct = gen_func(pt, key, iv)
            samples.append((ct, iv if mode != "gcm" else nonce, key, pt))
        except Exception as e:
            # 任一生成失败 → 整个 config 判为不可用，返回空表，
            # 由数据集层过滤掉该 (库, 模式) 组合。
            print(f"   ✗ {lib_key}/{mode} 生成失败 (i={i}): {e} — 该组合跳过")
            return []

    return samples


def generate_aes_samples(lib_key: str, mode: str, n: int = SAMPLES_PER_CONFIG) -> list:
    """AES对照组: 同generate_sm4_samples"""
    gen_func = AES_GENERATORS.get((lib_key, mode))
    if gen_func is None:
        return []

    plaintexts = _get_plaintexts(n, 512)
    samples = []
    rng = random.Random(SEED)
    for i in range(n):
        rng.seed(SEED * 10000 + i)
        key = bytes([rng.randint(0, 255) for _ in range(32)])  # AES-256: 256-bit key
        iv = bytes([rng.randint(0, 255) for _ in range(16)])
        nonce = iv

        pt = plaintexts[i]
        try:
            if mode == "ctr":
                ct = gen_func(pt, key, nonce)
            elif mode == "gcm":
                ct = gen_func(pt, key, nonce)
            else:
                ct = gen_func(pt, key, iv)
            samples.append((ct, iv if mode != "gcm" else nonce, key, pt))
        except Exception as e:
            # 失败时整组合跳过
            print(f"   ✗ {lib_key}/{mode} 生成失败 (i={i}): {e} — 该组合跳过")
            return []
    return samples


if __name__ == "__main__":
    # 快速测试
    print(f"OpenSSL可用: {HAS_OPENSSL}")
    print(f"OpenSSL SM4: {HAS_OPENSSL_SM4}")

    pt = b"Hello SM4 World! This is a 512-byte test message." * 10
    pt = pt[:512]
    key = secrets.token_bytes(16)
    iv = secrets.token_bytes(16)

    print(f"\nSM4-CBC 跨库对比 ({len(pt)}字节明文):")
    for lib_key in ["gmssl", "cryptography", "manual"]:
        gen = SM4_GENERATORS.get((lib_key, "cbc"))
        if gen:
            ct = gen(pt, key, iv)
            print(f"  {lib_key:15s}: {len(ct):4d} bytes | "
                  f"prefix={ct[:8].hex()} | "
                  f"entropy={sum(ct)/len(ct)/255:.3f}")
