"""
训练脚本 — SM4实现指纹识别
"""
import os
import json
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

from config import *
from dataset import SM4LibraryDataset, SM4LibraryModeDataset
from model import MultiChannelCNN, count_parameters


def set_seed(seed=SEED):
    torch.manual_seed(seed)
    np.random.seed(seed)


def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss, correct, total = 0, 0, 0
    for batch in tqdm(loader, desc='Train', leave=False):
        x = batch['raw'].to(device)
        y = batch['label'].to(device)
        optimizer.zero_grad()
        logits = model(x)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * x.size(0)
        correct += (logits.argmax(1) == y).sum().item()
        total += x.size(0)
    return total_loss / total, correct / total


def validate(model, loader, criterion, device):
    model.eval()
    total_loss, correct, total = 0, 0, 0
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch in tqdm(loader, desc='Val', leave=False):
            x = batch['raw'].to(device)
            y = batch['label'].to(device)
            logits = model(x)
            loss = criterion(logits, y)
            total_loss += loss.item() * x.size(0)
            preds = logits.argmax(1)
            correct += (preds == y).sum().item()
            total += x.size(0)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(y.cpu().numpy())
    acc = correct / total
    mf1 = f1_score(all_labels, all_preds, average='macro', zero_division=0)
    cm = confusion_matrix(all_labels, all_preds)
    return total_loss / total, acc, mf1, cm


def train_model(task_name, dataset_cls, num_classes, modes=None, epochs=EPOCHS):
    """训练单个任务的模型。

    实现说明：
    - num_classes 由数据集实际可用库数决定（过滤后），不按 config 的
      LIBRARIES 标志硬编码。
    - 联合任务通过 dataset_cls=SM4LibraryModeDataset + modes 传入。
    """
    print(f"\n{'='*60}")
    print(f"训练任务: {task_name} ({num_classes}类)")
    print(f"{'='*60}")

    set_seed()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"设备: {device}")

    # 数据集（可用库不足2个时 dataset 会抛 ValueError，由 main() 捕获跳过）
    train_ds = dataset_cls(task=task_name, split='train', modes=modes)
    val_ds = dataset_cls(task=task_name, split='val', modes=modes)
    test_ds = dataset_cls(task=task_name, split='test', modes=modes)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    # 模型
    model = MultiChannelCNN(num_classes=num_classes)
    model.to(device)
    n_params = count_parameters(model)
    print(f"参数量: {n_params:,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5)

    history = {'train_loss': [], 'train_acc': [], 'val_loss': [],
               'val_acc': [], 'val_f1': []}
    best_val_loss = float('inf')
    best_state = None
    patience_counter = 0

    for epoch in range(1, epochs + 1):
        start = time.time()
        train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc, val_f1, _ = validate(model, val_loader, criterion, device)
        scheduler.step(val_loss)

        history['train_loss'].append(train_loss)
        history['train_acc'].append(train_acc)
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_acc)
        history['val_f1'].append(val_f1)

        elapsed = time.time() - start
        print(f"Epoch {epoch:3d}| T:{train_acc:.4f} V:{val_acc:.4f} F1:{val_f1:.4f} | {elapsed:.0f}s")

        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= EARLY_STOP_PATIENCE:
                print(f"早停 @ epoch {epoch}")
                break

    # 恢复最佳 → 测试
    model.load_state_dict(best_state)
    _, test_acc, test_f1, test_cm = validate(model, test_loader, criterion, device)
    print(f"\n  测试集: Acc={test_acc:.4f} F1={test_f1:.4f}")
    print(f"  混淆矩阵:\n{test_cm}")

    # 保存
    save_path = os.path.join(MODEL_DIR, f"{task_name}.pt")
    torch.save({'state_dict': best_state, 'history': history,
                'test_acc': test_acc, 'test_f1': test_f1,
                'test_cm': test_cm.tolist(),
                'num_classes': num_classes}, save_path)

    return test_acc, test_f1, test_cm, history


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(RESULT_DIR, exist_ok=True)

    results = {}
    skipped = {}

    def _run_or_skip(task, dataset_cls, modes=None):
        """构建训练集以确定真实类别数；不可行任务（<2库）记录并跳过"""
        try:
            probe = dataset_cls(task=task, split='train', modes=modes)
        except ValueError as e:
            print(f"[SKIP] {task}: {e}")
            skipped[task] = str(e)
            return
        num_classes = len(probe.libs) * (len(modes) if modes else 1)
        acc, f1, cm, hist = train_model(
            task, dataset_cls, num_classes=num_classes, modes=modes)
        results[task] = {
            'accuracy': float(acc), 'f1': float(f1), 'cm': cm.tolist(),
            'libs': probe.libs, 'modes': modes or probe.modes,
            'num_classes': num_classes,
        }

    # ── SM4 单模式跨库任务 ──
    for mode in SM4_MODES:
        _run_or_skip(f"sm4_{mode}", SM4LibraryDataset)

    # ── SM4 跨模式×跨库联合任务（仅所有库都支持的模式：cbc/ctr）──
    _run_or_skip("sm4_all_cc", SM4LibraryModeDataset, modes=['cbc', 'ctr'])

    # ── AES 对照组 ──
    _run_or_skip("aes_cbc", SM4LibraryDataset)

    # ── 随机基线 ──
    for task, r in results.items():
        r['random_baseline'] = round(1.0 / r['num_classes'], 4)

    # ── 保存汇总 ──
    outpath = os.path.join(RESULT_DIR, "main_results.json")
    with open(outpath, 'w') as f:
        json.dump(results, f, indent=2, default=float)
    if skipped:
        skippath = os.path.join(RESULT_DIR, "skipped_tasks.json")
        with open(skippath, 'w') as f:
            json.dump(skipped, f, indent=2)

    print("\n" + "=" * 70)
    print("训练完成! 结果汇总:")
    print("-" * 70)
    print(f"{'任务':<20s} {'类别数':>6s} {'准确率':>8s} {'随机基线':>8s} {'提升':>8s}")
    print("-" * 70)
    for task, r in results.items():
        gain = r['accuracy'] - r['random_baseline']
        print(f"{task:<20s} {r['num_classes']:>6d} {r['accuracy']:>8.4f} "
              f"{r['random_baseline']:>8.4f} {gain:>+8.4f}")
    if skipped:
        print("-" * 70)
        for task, reason in skipped.items():
            print(f"[跳过] {task}: {reason}")
    print("=" * 70)


if __name__ == "__main__":
    main()
