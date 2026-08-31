"""
数据生成器 — 50类数据的加密/压缩/编码生成管线
"""
import os
import io
import gzip
import bz2
import lzma
import zlib
import struct
import hashlib
import base64
import random
import secrets
from pathlib import Path
import numpy as np

from config import *
from data.corpus import get_corpus

# ── 密码库导入 ────────────────────────────────────────
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding as asym_padding
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.backends import default_backend
from gmssl.sm4 import CryptSM4, SM4_ENCRYPT, SM4_DECRYPT
# 注：SM2 生成使用 pysmx（snowland-smx），
# 且 gmssl.sm2 的导入隐式依赖 pycryptodomex，移除后环境依赖更少

import zstandard as zstd
import brotli

random.seed(SEED)
np.random.seed(SEED)

# ══════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════

def _derive_key(password: bytes, salt: bytes, length: int = 32) -> bytes:
    """PBKDF2密钥派生"""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=length, salt=salt,
                     iterations=PBKDF2_ITERATIONS, backend=default_backend())
    return kdf.derive(password)


def _random_salt() -> bytes:
    return secrets.token_bytes(KEY_DERIVATION_SALT_LEN)


def _random_iv(block_size: int = 16) -> bytes:
    return secrets.token_bytes(block_size)


def _pad(data: bytes, block_size: int = 16) -> bytes:
    """PKCS7填充"""
    padder = sym_padding.PKCS7(block_size * 8).padder()
    return padder.update(data) + padder.finalize()


# ══════════════════════════════════════════════════════
# 明文类生成器
# ══════════════════════════════════════════════════════

def gen_english_text(corpus_pool: list) -> bytes:
    src = random.choice(corpus_pool)
    try:
        return src.decode('ascii').encode('ascii')
    except:
        return b"Sample English text for network payload analysis. " * 20


def gen_chinese_text() -> bytes:
    texts = [
        "第{}号记录：系统运行状态正常。数据处理模块已完成初始化，等待上级指令下发。"
        "网络连接状态良好，防火墙规则已加载。日志记录器启动完成，开始监控所有接口流量。"
        "安全策略已生效，入侵检测引擎进入在线模式。内存使用率正常，CPU负载稳定。"
        "磁盘剩余空间充足。系统管理员已登录，执行了例行检查命令，操作结果为成功。",
    ]
    return random.choice(texts).format(random.randint(1, 99999)).encode('utf-8')


def gen_python_code(corpus_pool: list) -> bytes:
    py_srcs = [p for p in corpus_pool if b'import ' in p[:200] or b'def ' in p[:200]]
    if py_srcs:
        return random.choice(py_srcs)
    return b"import sys\nimport os\n\ndef process_data(input_file, output_file):\n    pass\n"


def gen_c_cpp_code(corpus_pool: list) -> bytes:
    c_srcs = [p for p in corpus_pool if b'#include' in p[:200]]
    if c_srcs:
        return random.choice(c_srcs)
    return b"#include <stdio.h>\n#include <stdlib.h>\n\nint main(int argc, char **argv) {\n    return 0;\n}\n"


def gen_json_data(corpus_pool: list) -> bytes:
    json_srcs = [p for p in corpus_pool if b'{' in p[:100] and b'"' in p[:100]]
    if json_srcs:
        return random.choice(json_srcs)
    import json
    return json.dumps({"id": random.randint(1, 1000), "status": "ok"}).encode()


def gen_xml_html(corpus_pool: list) -> bytes:
    xml_srcs = [p for p in corpus_pool if b'<' in p[:100] and b'>' in p[:100]]
    if xml_srcs:
        return random.choice(xml_srcs)
    return b"<html><body><p>Sample content</p></body></html>"


# ══════════════════════════════════════════════════════
# 编码类生成器
# ══════════════════════════════════════════════════════

def gen_base64(pool: list) -> bytes:
    raw = random.choice(pool)[:768]
    return base64.b64encode(raw)[:WINDOW_SIZE]


def gen_hex_base16(pool: list) -> bytes:
    raw = random.choice(pool)[:512]
    return raw.hex().encode('ascii')[:WINDOW_SIZE]


def gen_base32(pool: list) -> bytes:
    raw = random.choice(pool)[:512]
    return base64.b32encode(raw)[:WINDOW_SIZE]


def gen_url_encode(pool: list) -> bytes:
    raw = random.choice(pool)[:256]
    from urllib.parse import quote
    return quote(raw.decode('latin-1', errors='replace'), safe='').encode()[:WINDOW_SIZE]


def gen_quoted_printable(pool: list) -> bytes:
    import quopri
    raw = random.choice(pool)[:512]
    buf = io.BytesIO()
    quopri.encode(io.BytesIO(raw), buf, quotetabs=False)
    return buf.getvalue()[:WINDOW_SIZE]


# ══════════════════════════════════════════════════════
# 哈希类生成器
# ══════════════════════════════════════════════════════

def gen_md5(pool: list) -> bytes:
    raw = random.choice(pool)
    return hashlib.md5(raw).hexdigest().encode()[:WINDOW_SIZE]


def gen_sha1(pool: list) -> bytes:
    raw = random.choice(pool)
    return hashlib.sha1(raw).hexdigest().encode()[:WINDOW_SIZE]


def gen_sha256(pool: list) -> bytes:
    raw = random.choice(pool)
    return hashlib.sha256(raw).hexdigest().encode()[:WINDOW_SIZE]


# ══════════════════════════════════════════════════════
# 压缩类生成器
# ══════════════════════════════════════════════════════

def _compress_common(pool: list, compress_fn, header_len: int = 0) -> tuple:
    """通用压缩生成，返回 (raw_bytes, headless_flag_for_training)"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    compressed = compress_fn(raw)
    if len(compressed) < MIN_PAYLOAD + header_len:
        compressed = compress_fn(raw * 4)

    # 去头训练：以概率 p 剥离文件头
    headless = random.random() < HEADLESS_PROB
    if headless and header_len > 0 and len(compressed) > header_len + MIN_PAYLOAD:
        compressed = compressed[header_len:]
    return compressed


def gen_gzip(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9, mtime=0) as f:
        f.write(raw)
    compressed = buf.getvalue()
    headless = random.random() < HEADLESS_PROB
    if headless and len(compressed) > 12:
        compressed = compressed[10:]  # strip gzip header
    return compressed


def gen_zip(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    # ZIP raw deflate
    compressor = zlib.compressobj(level=9, wbits=-15, memLevel=9)
    compressed = compressor.compress(raw) + compressor.flush()
    headless = random.random() < HEADLESS_PROB
    if not headless:
        compressed = b'PK\x03\x04' + b'\x00' * 22 + compressed
    return compressed


def gen_7z_lzma2(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    filters = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME}]
    compressed = lzma.compress(raw, format=lzma.FORMAT_RAW, filters=filters)
    headless = random.random() < HEADLESS_PROB
    if not headless:
        compressed = b"7z\xbc\xaf'\x1c" + b'\x00' * 27 + compressed
    return compressed


def gen_bzip2(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    # compresslevel 为仅位置参数，须位置传参
    compressor = bz2.BZ2Compressor(9)
    compressed = compressor.compress(raw)
    try:
        compressed += compressor.flush()
    except:
        pass
    headless = random.random() < HEADLESS_PROB
    if headless and len(compressed) > 4:
        compressed = compressed[4:]  # strip BZh header
    return compressed


def gen_xz_lzma(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    filters = [{"id": lzma.FILTER_LZMA2, "preset": 9}]
    compressed = lzma.compress(raw, format=lzma.FORMAT_RAW, filters=filters)
    return compressed


def gen_zstd(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    cctx = zstd.ZstdCompressor(level=19)
    compressed = cctx.compress(raw)
    headless = random.random() < HEADLESS_PROB
    if headless and len(compressed) > 5:
        compressed = compressed[4:]  # strip zstd magic
    return compressed


def gen_lz4(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    # 使用 lz4 块格式（store_size=False，无 frame 魔数），
    # 保证跨环境生成格式一致；依赖缺失时显式报错。
    import lz4.block
    return lz4.block.compress(raw, store_size=False)


def gen_brotli(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    compressed = brotli.compress(raw, quality=11)
    return compressed


# ══════════════════════════════════════════════════════
# 对称加密生成器
# ══════════════════════════════════════════════════════

def _sym_encrypt_aes(pool: list, key_size: int, mode_str: str) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    salt = _random_salt()
    key = _derive_key(secrets.token_bytes(32), salt, key_size)
    iv = _random_iv(16)

    if mode_str == 'cbc':
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    elif mode_str == 'gcm':
        iv = _random_iv(12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    elif mode_str == 'ctr':
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
    else:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())

    encryptor = cipher.encryptor()
    if mode_str == 'gcm':
        ct = encryptor.update(raw) + encryptor.finalize()
        ct += encryptor.tag
    else:
        padded = _pad(raw, 16)
        ct = encryptor.update(padded) + encryptor.finalize()
    return ct


def gen_aes128_cbc(pool): return _sym_encrypt_aes(pool, 16, 'cbc')
def gen_aes128_gcm(pool): return _sym_encrypt_aes(pool, 16, 'gcm')
def gen_aes128_ctr(pool): return _sym_encrypt_aes(pool, 16, 'ctr')
def gen_aes192_cbc(pool): return _sym_encrypt_aes(pool, 24, 'cbc')
def gen_aes192_gcm(pool): return _sym_encrypt_aes(pool, 24, 'gcm')
def gen_aes256_cbc(pool): return _sym_encrypt_aes(pool, 32, 'cbc')
def gen_aes256_gcm(pool): return _sym_encrypt_aes(pool, 32, 'gcm')
def gen_aes256_ctr(pool): return _sym_encrypt_aes(pool, 32, 'ctr')


def _openssl_cli_encrypt(plaintext: bytes, key: bytes, iv: bytes, cipher_name: str,
                         block_pad: bool = True) -> bytes:
    """通过 openssl CLI 加密（用于 camellia/aria 等 cryptography 未实现的算法）。

    block_pad=True 时交给 openssl 做 PKCS#7 填充（与其它 CBC 类长度一致）。
    """
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f_in:
        f_in.write(plaintext)
        in_path = f_in.name
    out_path = in_path + '.enc'
    cmd = ["openssl", "enc", f"-{cipher_name}", "-e",
           "-K", key.hex(), "-iv", iv.hex(),
           "-in", in_path, "-out", out_path, "-nosalt"]
    if not block_pad:
        cmd.append("-nopad")
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        with open(out_path, 'rb') as f:
            return f.read()
    finally:
        for p in (in_path, out_path):
            if os.path.exists(p):
                os.unlink(p)


def gen_camellia256_cbc(pool: list) -> bytes:
    """真实 Camellia-256-CBC（openssl CLI）。"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 32)
    iv = _random_iv(16)
    return _openssl_cli_encrypt(raw, key, iv, 'camellia-256-cbc')


def gen_chacha20(pool: list) -> bytes:
    """真实 ChaCha20-Poly1305（ct || 16字节认证标签）。"""
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 32)
    nonce = _random_iv(12)
    return ChaCha20Poly1305(key).encrypt(nonce, raw, None)


def gen_rc4(pool: list) -> bytes:
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 16)
    cipher = Cipher(algorithms.ARC4(key), mode=None, backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(raw)


def gen_3des(pool: list) -> bytes:
    """真实 3DES-EDE3-CBC（24字节密钥，8字节块 PKCS#7）。"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 24)
    iv = _random_iv(8)
    cipher = Cipher(algorithms.TripleDES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(_pad(raw, 8)) + encryptor.finalize()


def gen_blowfish(pool: list) -> bytes:
    """真实 Blowfish-CBC（8字节块 PKCS#7）。"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 32)
    iv = _random_iv(8)
    cipher = Cipher(algorithms.Blowfish(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(_pad(raw, 8)) + encryptor.finalize()


def gen_twofish(pool: list) -> bytes:
    """真实 Twofish-CBC（PyPI twofish 纯 Python 实现，手工 CBC + PKCS#7）。"""
    from twofish import Twofish
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 32)
    iv = _random_iv(16)
    t = Twofish(key)
    padded = _pad(raw, 16)
    ct = b''
    prev = iv
    for i in range(0, len(padded), 16):
        block = bytes(a ^ b for a, b in zip(padded[i:i+16], prev))
        ct_block = t.encrypt(block)
        ct += ct_block
        prev = ct_block
    return ct


def _sm4_encrypt_block(sm4: CryptSM4, block: bytes) -> bytes:
    """单块SM4加密（无填充）。

    实现说明：
    gmssl 的 CryptSM4.crypt_ecb 默认 padding_mode=PKCS7，会对已对齐的
    16 字节块再垫一整块，不适合直接做 CBC 链接的底层原语；
    这里用 one_round 做无填充单块加密（SM4 的单轮压缩函数可视为
    固定轮密钥下的单块加密），与 pyca/cryptography 的 SM4-CBC 输出逐字节一致。
    """
    return bytes(sm4.one_round(sm4.sk, list(block)))


def gen_sm4_cbc(pool: list) -> bytes:
    """SM4-CBC 国密对称加密"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = secrets.token_bytes(16)  # SM4 uses 128-bit key
    iv = _random_iv(16)
    sm4 = CryptSM4()
    sm4.set_key(key, SM4_ENCRYPT)
    padded = _pad(raw, 16)
    # Manual CBC（使用无填充的单块加密 _sm4_encrypt_block）
    ct = b''
    prev = iv
    for i in range(0, len(padded), 16):
        block = bytes(a ^ b for a, b in zip(padded[i:i+16], prev))
        ct_block = _sm4_encrypt_block(sm4, block)
        ct += ct_block
        prev = ct_block
    return ct


def gen_sm4_ctr(pool: list) -> bytes:
    """SM4-CTR 国密对称加密"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = secrets.token_bytes(16)
    nonce = int.from_bytes(secrets.token_bytes(8), 'big')
    sm4 = CryptSM4()
    sm4.set_key(key, SM4_ENCRYPT)
    ct = b''
    for i in range(0, len(raw), 16):
        counter = (nonce + i // 16).to_bytes(16, 'big')
        keystream = _sm4_encrypt_block(sm4, counter)  # 同样使用无填充单块加密
        ct += bytes(a ^ b for a, b in zip(raw[i:i+16], keystream[:len(raw)-i]))
    return ct


def gen_aria256_cbc(pool: list) -> bytes:
    """真实 ARIA-256-CBC（openssl CLI）。"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 32)
    iv = _random_iv(16)
    return _openssl_cli_encrypt(raw, key, iv, 'aria-256-cbc')


def gen_seed_cbc(pool: list) -> bytes:
    """SEED-CBC (Korean standard)"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    key = _derive_key(secrets.token_bytes(32), _random_salt(), 16)
    iv = _random_iv(16)
    cipher = Cipher(algorithms.SEED(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(_pad(raw, 16)) + encryptor.finalize()


# ══════════════════════════════════════════════════════
# 非对称加密生成器
# ══════════════════════════════════════════════════════

# RSA密钥缓存
_rsa_key_cache = {}

def _get_or_create_rsa_key(key_size: int):
    if key_size not in _rsa_key_cache:
        _rsa_key_cache[key_size] = rsa.generate_private_key(
            public_exponent=65537, key_size=key_size, backend=default_backend()
        )
    return _rsa_key_cache[key_size]


def _rsa_encrypt(pool: list, key_size: int) -> bytes:
    """RSA OAEP加密, 自动限制明文长度"""
    # OAEP with SHA-256: overhead = 2*hash_len + 2 = 66 bytes
    max_pt = key_size // 8 - 66
    raw = random.choice(pool)
    raw = raw[:max_pt]
    if len(raw) < 1:
        raw = b'\x00' * max_pt
    key = _get_or_create_rsa_key(key_size)
    return key.public_key().encrypt(raw, asym_padding.OAEP(
        mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None
    ))


def gen_rsa_1024(pool: list) -> bytes:
    return _rsa_encrypt(pool, 1024)


def gen_rsa_2048(pool: list) -> bytes:
    return _rsa_encrypt(pool, 2048)


def gen_rsa_4096(pool: list) -> bytes:
    return _rsa_encrypt(pool, 4096)


def gen_gpg_mixed(pool: list) -> bytes:
    """GPG混合加密模拟: RSA-wrapped session key + AES-256-CBC ciphertext"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    session_key = secrets.token_bytes(32)
    iv = _random_iv(16)
    cipher = Cipher(algorithms.AES(session_key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ct = encryptor.update(_pad(raw, 16)) + encryptor.finalize()
    # Prepend RSA-wrapped session key
    rsa_key = _get_or_create_rsa_key(2048)
    wrapped_key = rsa_key.public_key().encrypt(session_key, asym_padding.OAEP(
        mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None
    ))
    return wrapped_key + iv + ct


def gen_ecc_secp256r1(pool: list) -> bytes:
    """ECC密文: ECDH-derived key + AES-GCM"""
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    priv = ec.generate_private_key(ec.SECP256R1(), default_backend())
    pub = priv.public_key()
    pub_bytes = pub.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    # Use ephemeral key for encryption
    ephemeral = ec.generate_private_key(ec.SECP256R1(), default_backend())
    shared = ephemeral.exchange(ec.ECDH(), pub)
    key = hashlib.sha256(shared).digest()
    iv = _random_iv(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ct = encryptor.update(raw) + encryptor.finalize() + encryptor.tag
    return pub_bytes + ct


def gen_sm2_enc(pool: list) -> bytes:
    """SM2加密 国密非对称加密（pysmx/snowland-smx 实现）。

    实现说明：
    - SM2 使用 pysmx（snowland-smx）库，C1C3C2 输出格式；
      经官方向量验证：pysmx 的 kG 复现 GM/T 0003-2012 附录 A 官方 C1，
      密文可被手写标准解密公式还原。
    - 每样本生成新密钥对（与论文"fresh key per sample"一致）。
    依赖：pip install snowland-smx（模块名 pysmx）。
    """
    from pysmx.SM2 import generate_keypair, Encrypt
    raw = random.choice(pool)
    if len(raw) < MIN_PAYLOAD:
        raw = raw * (MIN_PAYLOAD // len(raw) + 1)
    pub, _priv = generate_keypair(len_param=64)
    ct = Encrypt(raw, pub.hex(), len_para=64, mode='C1C3C2', Hexstr=0)
    return ct


# ══════════════════════════════════════════════════════
# 真随机/对照生成器
# ══════════════════════════════════════════════════════

def gen_dev_urandom() -> bytes:
    with open('/dev/urandom', 'rb') as f:
        return f.read(WINDOW_SIZE)


def gen_python_secrets() -> bytes:
    return secrets.token_bytes(WINDOW_SIZE)


def gen_aes_ecb_zero() -> bytes:
    """AES-256-ECB of all-zero plaintext (fresh random key per sample).

    实现说明：
    每样本使用 secrets.token_bytes(32) 新密钥（与论文"每次加密使用
    新密钥"一致）。明文全零使类内保留 64 个相同 16 字节块的周期结构，
    这是该对照类"极端结构规律"设计的含义所在。
    """
    key = secrets.token_bytes(32)
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    plaintext = b'\x00' * WINDOW_SIZE
    return encryptor.update(plaintext) + encryptor.finalize()


def gen_all_zeros() -> bytes:
    return b'\x00' * WINDOW_SIZE


# ══════════════════════════════════════════════════════
# 生成器注册表
# ══════════════════════════════════════════════════════

GENERATORS = {
    # 明文文本
    "english_text":        gen_english_text,
    "chinese_text":        gen_chinese_text,
    "python_code":         gen_python_code,
    "c_cpp_code":          gen_c_cpp_code,
    "json_data":           gen_json_data,
    "xml_html":            gen_xml_html,
    # 编码
    "base64":              gen_base64,
    "hex_base16":          gen_hex_base16,
    "base32":              gen_base32,
    "url_encode":          gen_url_encode,
    "quoted_printable":    gen_quoted_printable,
    # 哈希
    "md5_hex":             gen_md5,
    "sha1_hex":            gen_sha1,
    "sha256_hex":          gen_sha256,
    # 压缩
    "gzip_deflate_l9":     gen_gzip,
    "zip_deflate_l9":      gen_zip,
    "7z_lzma2_l9":        gen_7z_lzma2,
    "bzip2_l9":           gen_bzip2,
    "xz_lzma_l9":         gen_xz_lzma,
    "zstd_l19":           gen_zstd,
    "lz4_fast":           gen_lz4,
    "brotli_l11":         gen_brotli,
    # 对称加密
    "aes128_cbc":          gen_aes128_cbc,
    "aes128_gcm":          gen_aes128_gcm,
    "aes128_ctr":          gen_aes128_ctr,
    "aes192_cbc":          gen_aes192_cbc,
    "aes192_gcm":          gen_aes192_gcm,
    "aes256_cbc":          gen_aes256_cbc,
    "aes256_gcm":          gen_aes256_gcm,
    "aes256_ctr":          gen_aes256_ctr,
    "camellia256_cbc":     gen_camellia256_cbc,
    "chacha20_poly1305":   gen_chacha20,
    "rc4":                 gen_rc4,
    "3des_ede3_cbc":       gen_3des,
    "blowfish_cbc":        gen_blowfish,
    "twofish_cbc":         gen_twofish,
    "sm4_cbc":             gen_sm4_cbc,
    "sm4_ctr":             gen_sm4_ctr,
    "aria256_cbc":         gen_aria256_cbc,
    "seed_cbc":            gen_seed_cbc,
    # 非对称加密
    "rsa_1024":            gen_rsa_1024,
    "rsa_2048":            gen_rsa_2048,
    "rsa_4096":            gen_rsa_4096,
    "gpg_mixed":           gen_gpg_mixed,
    "ecc_secp256r1":       gen_ecc_secp256r1,
    "sm2_enc":             gen_sm2_enc,
    # 真随机/对照
    "dev_urandom":         gen_dev_urandom,
    "python_secrets":      gen_python_secrets,
    "aes_ecb_zero_plaintext": gen_aes_ecb_zero,
    "all_zeros":           gen_all_zeros,
}
