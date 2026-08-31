#!/usr/bin/env python3
"""审计：校准实验的再生窗口与缓存是否一致（CPU-only，不影响训练）。"""
import os, sys, json, random, hashlib, pickle, time
import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from data.generators import GENERATORS
from data.corpus import get_corpus
from models.cnn import MultiChannelCNN

print("start", flush=True)
corpus = get_corpus()
print("corpus_pool len:", len(corpus), flush=True)
print("corpus md5:", hashlib.md5(open(os.path.join(DATA_DIR, 'corpus_pool.txt'), 'rb').read()).hexdigest(), flush=True)

def regen_raw(cid, sid):
    import data.generators as gen_mod
    random.seed(SEED * 10000 + cid * 1000 + sid)
    np.random.seed(SEED * 10000 + cid * 1000 + sid)
    saved = gen_mod.HEADLESS_PROB
    gen_mod.HEADLESS_PROB = 0.0
    try:
        g = GENERATORS[CLASS_NAMES[cid]]
        sig = g.__code__.co_varnames[:g.__code__.co_argcount]
        raw = g(corpus) if 'pool' in sig or 'corpus_pool' in sig else g()
    finally:
        gen_mod.HEADLESS_PROB = saved
    return raw

# 1) raw 一致性
print("---- raw sha comparison ----", flush=True)
probe = [(0,850),(1,850),(2,850),(3,850),(4,850),(5,850),  # 6 明文类
         (6,850),(7,850),(8,850),(9,850),(10,850),(11,850),(12,850),(13,850),  # 编码5? 先按0..试试
         ]
for cid, sid in probe:
    if cid >= NUM_CLASSES:
        continue
    cache_path = os.path.join(DATA_DIR, 'cache_test', f'{cid}_{sid}.pkl')
    with open(cache_path, 'rb') as f:
        cached = pickle.load(f)
    meta = cached.get('metadata', {})
    try:
        raw = regen_raw(cid, sid)
        sha = hashlib.sha256(raw).hexdigest()
        ok = (sha == meta.get('raw_sha256'))
        print(CLASS_NAMES[cid], cid, sid, 'rawlen', len(raw), 'meta_rawlen', meta.get('raw_length'),
              'MATCH' if ok else 'MISMATCH', flush=True)
        if not ok:
            print('   head cache:', meta.get('raw_sha256')[:32], ' regen:', sha[:32], flush=True)
            print('   head bytes cache raw sample (from pkl raw tensor):', flush=True)
            rw = cached['raw']
            if rw.dim() > 1:
                rw = rw.squeeze(0)
            print('   ', rw[:16].numpy().tolist(), flush=True)
    except Exception as e:
        print(CLASS_NAMES[cid], cid, sid, 'GEN-ERR', repr(e), flush=True)

# 2) 模型评估：缓存窗口 vs 再生窗口（明文类+几个加密类）
print("---- model eval ----", flush=True)
ckpt_path = os.path.join(MODEL_DIR, 'multichannel_seed42.pt')
ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
model = MultiChannelCNN(num_classes=NUM_CLASSES)
model.load_state_dict(ckpt['state_dict'])
model.eval()
print('checkpoint loaded:', ckpt_path, flush=True)

def window_of(raw, gen_seed):
    if len(raw) < WINDOW_SIZE:
        return raw + b'\x00' * (WINDOW_SIZE - len(raw))
    rng = random.Random(gen_seed)
    start = rng.randint(0, len(raw) - WINDOW_SIZE)
    return raw[start:start + WINDOW_SIZE]

def predict(windows):
    xs = np.stack([np.frombuffer(w, dtype=np.uint8).astype(np.float32) / 255.0 for w in windows])
    x = torch.from_numpy(xs).unsqueeze(1)
    with torch.no_grad():
        logits = model(x)
    return logits.argmax(1).numpy()

cids = list(range(18))  # 明文6 + 编码5 + 哈希3 + 压缩4(GZIP/ZIP/7z/BZIP2)
report = {}
for cid in cids:
    sids = range(850, 900)
    cached_ws, regen_ws = [], []
    for sid in sids:
        cache_path = os.path.join(DATA_DIR, 'cache_test', f'{cid}_{sid}.pkl')
        with open(cache_path, 'rb') as f:
            cached = pickle.load(f)
        rw = cached['raw']
        if rw.dim() > 1:
            rw = rw.squeeze(0)
        cached_ws.append((rw.numpy() * 255).astype(np.uint8).tobytes())
        regen_ws.append(window_of(regen_raw(cid, sid), SEED * 10000 + cid * 1000 + sid))
    pc = predict(cached_ws)
    pr = predict(regen_ws)
    acc_c = float((pc == cid).mean()) * 100
    acc_r = float((pr == cid).mean()) * 100
    same = float(sum(a == b for a, b in zip(cached_ws, regen_ws))) / len(cached_ws) * 100
    print(f"{CLASS_NAMES[cid]:<18s} cached_acc={acc_c:5.1f}  regen_acc={acc_r:5.1f}  window_identical={same:5.1f}%", flush=True)

print("done", flush=True)
