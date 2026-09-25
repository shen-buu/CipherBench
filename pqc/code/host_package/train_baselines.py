#!/usr/bin/env python3
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""Frozen baseline training v2.2: P1/P2 1024B windows (uniform random fill), RF/HGB/CNN/BiLSTM, 5-fold CV x 5 seeds (E8), checkpointed per-seed JSONs."""
import os, sys, json, time, argparse, glob
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WINDOW = 1024
SEEDS = [42, 123, 2024, 7, 99]


def group_tag(groups_str):
    """断点名组维度：默认混合组无后缀；子组加 _g_* 后缀（防止静默跳过）"""
    if groups_str == "primitives,pkcs8,cert":
        return ""
    m = {"primitives": "prim", "pkcs8": "pk8", "cert": "crt"}
    return "_g_" + "+".join(m.get(p, p) for p in groups_str.split(","))


def load_dataset(data_dir, groups=("primitives", "pkcs8", "cert")):
    """加载正式数据集：返回 {class_name: [bytes,...]} 与 meta"""
    meta = json.load(open(os.path.join(data_dir, "meta.json")))
    objs = {}
    for name, v in meta.items():
        if not isinstance(v, dict) or v.get("type") not in groups:
            continue
        d = os.path.join(data_dir, name)
        files = sorted(glob.glob(os.path.join(d, "*.bin")) +
                       glob.glob(os.path.join(d, "*.der")))
        objs[name] = [open(f, "rb").read() for f in files]
        if v.get("n") and len(files) != v["n"]:
            raise ValueError(f"{name}: 文件数 {len(files)} ≠ meta.n {v['n']}")
        if any(len(o) == 0 for o in objs[name]):
            raise ValueError(f"{name}: 存在 0 字节文件")
    return objs, meta


def make_window(data, scene, rng):
    """P1/P2 窗口构造（短对象随机填充，禁零填充）"""
    if scene == "len":
        return None
    if len(data) >= WINDOW:
        off = int(rng.integers(0, len(data) - WINDOW + 1)) if scene == "p1" else 0
        w = data[off: off + WINDOW]
    else:
        if scene == "p1":
            # 探针协议：短对象放在窗口内随机位置（避免位置锚定泄漏）
            n = len(data)
            off = int(rng.integers(0, WINDOW - n + 1))
            w = rng.bytes(WINDOW)
            w = bytearray(w)
            w[off: off + n] = data
            w = bytes(w)
        else:
            # P2 头部协议：对象锚定在位置 0 + 随机填充
            w = data + rng.bytes(WINDOW - len(data))
    return w


def featurize(w, mode):
    if mode == "raw":
        return np.frombuffer(w, dtype=np.uint8).astype(np.float32) / 255.0
    if mode == "stats":
        from statistical import extract_full_features
        return extract_full_features(w)
    raise ValueError(mode)


def fit_eval(X, y, clf_factory, seed):
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import f1_score, confusion_matrix
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    yt, yp = [], []
    for tr, te in skf.split(X, y):
        clf = clf_factory()   # 每折新建：防止 torch 模型跨折状态泄漏
        clf.fit(X[tr], y[tr])
        yt.extend(y[te]); yp.extend(clf.predict(X[te]))
    yt, yp = np.array(yt), np.array(yp)
    return (float(f1_score(yt, yp, average="macro")),
            f1_score(yt, yp, average=None).tolist(),
            confusion_matrix(yt, yp).tolist())


def build_data(objs, scene, seed, feat_mode):
    names = list(objs)
    rng = np.random.default_rng(seed)
    X, y = [], []
    for cid, name in enumerate(names):
        for d in objs[name]:
            if scene == "len":
                X.append([float(len(d))])
            else:
                w = make_window(d, scene, rng)
                X.append(featurize(w, feat_mode))
            y.append(cid)
    return names, np.array(X, dtype=np.float32), np.array(y)


def make_clf(arch, seed, n_classes, device, epochs=15):
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    if arch == "rf":
        return RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=seed)
    if arch == "hgb":
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                              max_leaf_nodes=31, random_state=seed)
    if arch in ("cnn", "bilstm"):
        import torch
        import torch.nn as nn

        class CNN(nn.Module):
            def __init__(self):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Conv1d(1, 64, 7, padding=3), nn.ReLU(), nn.MaxPool1d(4),
                    nn.Conv1d(64, 128, 5, padding=2), nn.ReLU(), nn.MaxPool1d(4),
                    nn.Conv1d(128, 256, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool1d(1),
                    nn.Flatten(), nn.Dropout(0.3), nn.Linear(256, n_classes))
            def forward(self, x):
                return self.net(x)

        class BiLSTM(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(input_size=1, hidden_size=64, num_layers=2,
                                    batch_first=True, bidirectional=True)
                self.fc = nn.Sequential(nn.Dropout(0.3), nn.Linear(128, n_classes))
            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :])

        class TorchWrap:
            def __init__(self, arch):
                torch.manual_seed(seed)   # E5/E8：种子必须作用于 torch 全局 RNG
                self.arch = arch
                self.device = device
                self.n_classes = n_classes
                self.model = (CNN() if arch == "cnn" else BiLSTM()).to(device)
                self.opt = torch.optim.Adam(self.model.parameters(), lr=1e-3)
                self.lossf = nn.CrossEntropyLoss()
                self.epochs = epochs      # 默认 15（冻结协议）；30 = 预算敏感性消融

            def _t(self, X):
                t = torch.tensor(X, dtype=torch.float32)
                return (t[:, None, :] if self.arch == "cnn" else t[:, :, None]).to(self.device)

            def fit(self, X, y):
                self.model.train()
                Xt = self._t(X)
                yt = torch.tensor(y, dtype=torch.long).to(self.device)
                for _ in range(self.epochs):
                    perm = torch.randperm(len(Xt))
                    for i in range(0, len(Xt), 128):
                        idx = perm[i: i + 128]
                        self.opt.zero_grad()
                        loss = self.lossf(self.model(Xt[idx]), yt[idx])
                        loss.backward()
                        self.opt.step()

            def predict(self, X):
                self.model.eval()
                outs = []
                with torch.no_grad():
                    for i in range(0, len(X), 256):     # 分块推理：避免整测试集
                        outs.append(self.model(self._t(X[i: i + 256])).argmax(1).cpu())
                return torch.cat(outs).numpy()          # 数值与整批等价（无 BN/状态跨块）

        return TorchWrap(arch)
    raise ValueError(f"未知架构：{arch}（可选 rf|hgb|cnn|bilstm）")


_G = {}   # 并行 worker 通过 fork 继承：{args, objs, res_dir}


def _set_gpu_flags():
    """TF32 + cuDNN autotune：小模型训练约 1.3–2×；数值影响 < 种子噪声。
    进程级标志，每个 worker 需自行设置。无 torch 环境时静默跳过。"""
    try:
        import torch
        torch.set_num_threads(2)                    # 避免多 worker CPU 过订阅
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        return True
    except Exception:
        return False


def run_one(job):
    """job = (arch, scene, seed)。已完成则秒跳（断点续跑），结果写独立 JSON。"""
    arch, scene, seed = job
    a = _G["args"]
    res_dir = _G["res_dir"]
    _set_gpu_flags()
    tag = "nn" if scene == "len" else arch
    suffix = "_smoke" if a.smoke else ""
    if getattr(a, "tag", None):
        suffix += f"_{a.tag}"
    gtag = group_tag(a.groups)
    out_f = os.path.join(res_dir, f"{tag}_{scene}_seed{seed}{gtag}{suffix}.json")
    if os.path.exists(out_f):
        # skip only if the checkpoint parses and has the required fields (audit #43)
        try:
            _prev = json.load(open(out_f))
            assert isinstance(_prev.get("macro_f1"), float) and "per_class_f1" in _prev
            print(f"[skip] {tag}/{scene}/{seed}", flush=True)
            return None
        except Exception:
            print(f"[re-run] {tag}/{scene}/{seed}: existing {out_f} invalid, rerunning", flush=True)
    t0 = time.time()
    feat_mode = "stats" if arch in ("rf", "hgb") else "raw"
    names, X, y = build_data(_G["objs"], scene, seed, feat_mode)
    if scene == "len":
        from sklearn.neighbors import KNeighborsClassifier
        factory = lambda: KNeighborsClassifier(n_neighbors=1)
    else:
        factory = lambda: make_clf(arch, seed, len(names), a.device, a.epochs)
    mac, pcls, cm = fit_eval(X, y, factory, seed)
    env = {"torch": "n/a", "device": "cpu", "gpu_flags": _G.get("gpu_flags", False),
           "parallel": a.parallel, "epochs": a.epochs,
           "tag": getattr(a, "tag", None)}
    try:
        import torch
        env["torch"] = torch.__version__
        if torch.cuda.is_available():
            env["device"] = torch.cuda.get_device_name(0)
            env["cuda"] = torch.version.cuda
    except Exception:
        pass
    if not (0.0 <= mac <= 1.0) or not all(0.0 <= x <= 1.0 for x in pcls):
        raise ValueError(f"invalid F1 range: mac={mac}")
    # arch field matches the frozen format; model field marks 1nn; atomic write (audit #42/#43).
    payload = {"arch": arch, "model": "1nn" if scene == "len" else arch,
               "scene": scene, "seed": seed,
               "macro_f1": mac, "per_class_f1": dict(zip(names, pcls)),
               "confusion": cm, "sec": round(time.time() - t0, 1),
               "n_classes": len(names), "env": env}
    tmp_f = out_f + ".tmp"
    with open(tmp_f, "w", encoding="utf-8") as _fj:
        json.dump(payload, _fj)
    os.replace(tmp_f, out_f)
    print(f"[{arch}/{scene}/seed{seed}] macro-F1={mac:.4f} ({time.time()-t0:.0f}s, "
          f"{env['device']})", flush=True)
    return {"arch": arch, "scene": scene, "seed": seed, "macro_f1": mac}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--arch", default="rf", help="rf|hgb|cnn|bilstm|all")
    ap.add_argument("--scene", default="p1", help="p1|p2|len|all")
    ap.add_argument("--groups", default="primitives,pkcs8,cert")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--smoke", action="store_true", help="每类 20 样本冒烟")
    ap.add_argument("--parallel", type=int, default=1,
                    help="单 GPU 多进程并发 worker 数（小模型延迟型负载，2-4 倍墙钟提速）")
    ap.add_argument("--epochs", type=int, default=15,
                    help="训练轮数（冻结协议 15；30 仅用于预算敏感性消融）")
    ap.add_argument("--tag", default="", help="结果文件名后缀（如 e30），用于消融变体")
    a = ap.parse_args()

    # realpath keeps mkdir and file writes on the same path (audit #20).
    res_dir = os.path.realpath(os.path.abspath(os.path.join(a.data, "..", "results")))
    os.makedirs(res_dir, exist_ok=True)
    objs, meta = load_dataset(a.data, groups=set(a.groups.split(",")))
    if a.smoke:
        objs = {k: v[:20] for k, v in objs.items()}
    print(f"数据：{len(objs)} 类，共 {sum(len(v) for v in objs.values())} 对象", flush=True)

    archs = ["rf", "hgb", "cnn", "bilstm"] if a.arch == "all" else [a.arch]
    scenes = ["p1", "p2", "len"] if a.scene == "all" else [a.scene]
    jobs = []
    for arch in archs:
        for scene in scenes:
            if scene == "len" and arch not in ("rf", "hgb"):
                print(f"[skip] {arch}/len（长度信道为架构无关 1-NN，只跑一次）", flush=True)
                continue
            for seed in SEEDS:
                jobs.append((arch, scene, seed))

    _G["args"] = a
    _G["objs"] = objs
    _G["res_dir"] = res_dir
    _G["gpu_flags"] = _set_gpu_flags()

    if a.parallel > 1:
        import multiprocessing as mp
        try:
            ctx = mp.get_context("fork")
        except ValueError:
            print("[warn] 无 fork 上下文，退回串行", flush=True)
            a.parallel = 1
        if a.parallel > 1:
            print(f"并行 worker × {a.parallel}，任务 {len(jobs)} 个", flush=True)
            with ctx.Pool(a.parallel) as pool:
                pool.map(run_one, jobs)
    if a.parallel <= 1:
        for j in jobs:
            run_one(j)
    print("完成 → results/", flush=True)


if __name__ == "__main__":
    main()
