"""
训练脚本 — 完整训练管线
"""
import os
import json
import time
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             classification_report, confusion_matrix)
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

from config import *
from data.dataset import CipherDataset, CachedCipherDataset
from models.cnn import SingleChannelCNN, MultiChannelCNN, count_parameters
from models.sota_baselines import ByteTransformer, BiLSTMAttention
from features.statistical import extract_full_features


def set_seed(seed=SEED):
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    # Fix "Too many open files" on data-heavy workloads
    try:
        torch.multiprocessing.set_sharing_strategy('file_system')
    except RuntimeError:
        pass


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
    macro_p = precision_score(all_labels, all_preds, average='macro', zero_division=0)
    macro_r = recall_score(all_labels, all_preds, average='macro', zero_division=0)
    macro_f1 = f1_score(all_labels, all_preds, average='macro', zero_division=0)

    return total_loss / total, acc, macro_p, macro_r, macro_f1, all_preds, all_labels


def train_cnn(model, train_loader, val_loader, model_name, epochs=EPOCHS,
              patience=EARLY_STOP_PATIENCE, save=True):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = model.to(device)
    print(f"设备: {device}, 参数量: {count_parameters(model):,}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=LR_REDUCE_FACTOR,
        patience=LR_REDUCE_PATIENCE
    )

    history = {'train_loss': [], 'train_acc': [], 'val_loss': [],
               'val_acc': [], 'val_macro_p': [], 'val_macro_r': [], 'val_macro_f1': []}
    best_val_loss = float('inf')
    best_state = None
    patience_counter = 0

    for epoch in range(1, epochs + 1):
        start = time.time()
        train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc, mp, mr, mf1, _, _ = validate(model, val_loader, criterion, device)

        scheduler.step(val_loss)

        history['train_loss'].append(train_loss)
        history['train_acc'].append(train_acc)
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_acc)
        history['val_macro_p'].append(mp)
        history['val_macro_r'].append(mr)
        history['val_macro_f1'].append(mf1)

        elapsed = time.time() - start
        print(f"Epoch {epoch:3d}/{epochs} | "
              f"T Loss: {train_loss:.4f} | T Acc: {train_acc:.4f} | "
              f"V Loss: {val_loss:.4f} | V Acc: {val_acc:.4f} | "
              f"F1: {mf1:.4f} | Time: {elapsed:.1f}s")

        # Early stopping
        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"Early stopping at epoch {epoch}")
                break

    # 恢复最佳模型
    if best_state is not None:
        model.load_state_dict(best_state)

    # 保存模型和训练历史
    if save:
        save_path = os.path.join(MODEL_DIR, f"{model_name}.pt")
        torch.save({'state_dict': best_state, 'history': history}, save_path)
        print(f"模型已保存: {save_path}")

    return model, history


def train_gbt(train_loader, val_loader):
    """训练梯度提升树基线 (仅用170维统计特征)

    优先使用 XGBoost, 若不可用则回退到 sklearn HistGradientBoostingClassifier
    """
    if HAS_XGBOOST:
        print("训练 XGBoost 基线...")
    else:
        print("训练 HistGradientBoostingClassifier 基线 (sklearn)...")

    # 收集特征
    X_train, y_train = [], []
    for batch in tqdm(train_loader, desc='Collect train features'):
        X_train.append(batch['features'].numpy())
        y_train.append(batch['label'].numpy())
    X_train = np.vstack(X_train)
    y_train = np.hstack(y_train)

    X_val, y_val = [], []
    for batch in tqdm(val_loader, desc='Collect val features'):
        X_val.append(batch['features'].numpy())
        y_val.append(batch['label'].numpy())
    X_val = np.vstack(X_val)
    y_val = np.hstack(y_val)

    # 训练
    if HAS_XGBOOST:
        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=8, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            random_state=SEED, n_jobs=-1, verbosity=0
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    else:
        model = HistGradientBoostingClassifier(**GBT_PARAMS)
        model.fit(X_train, y_train)

    # 评估（验证集）
    preds = model.predict(X_val)
    acc = accuracy_score(y_val, preds)
    mp = precision_score(y_val, preds, average='macro', zero_division=0)
    mr = recall_score(y_val, preds, average='macro', zero_division=0)
    mf1 = f1_score(y_val, preds, average='macro', zero_division=0)

    tag = "XGBoost" if HAS_XGBOOST else "HistGradientBoosting"
    print(f"{tag} | Val Acc: {acc:.4f} | F1: {mf1:.4f}")

    # 返回 (model, 指标字典) 元组
    return model, {'val_acc': acc, 'val_macro_p': mp, 'val_macro_r': mr, 'val_macro_f1': mf1}


def get_predictions(model, loader, model_type='cnn'):
    """获取模型在数据加载器上的预测"""
    if model_type == 'cnn':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model = model.to(device)
        model.eval()
        all_preds, all_labels, all_probs = [], [], []
        with torch.no_grad():
            for batch in tqdm(loader, desc='Predict'):
                x = batch['raw'].to(device)
                y = batch['label']
                logits = model(x)
                probs = torch.softmax(logits, dim=1)
                all_preds.extend(logits.argmax(1).cpu().numpy())
                all_labels.extend(y.numpy())
                all_probs.extend(probs.cpu().numpy())
    else:  # xgboost
        X = []
        all_labels = []
        for batch in tqdm(loader, desc='Predict XGB'):
            X.append(batch['features'].numpy())
            all_labels.append(batch['label'].numpy())
        X = np.vstack(X)
        all_labels = np.hstack(all_labels)
        all_preds = model.predict(X)
        all_probs = model.predict_proba(X)

    return np.array(all_preds), np.array(all_labels), np.array(all_probs)


def create_model(model_type: str, num_classes: int = NUM_CLASSES):
    """Model factory."""
    if model_type == 'cnn_baseline':
        return SingleChannelCNN(num_classes=num_classes)
    elif model_type == 'multichannel':
        return MultiChannelCNN(num_classes=num_classes)
    elif model_type == 'transformer':
        return ByteTransformer(num_classes=num_classes)
    elif model_type == 'bilstm':
        return BiLSTMAttention(num_classes=num_classes)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def train_all_baselines():
    """Train all baseline models."""
    set_seed()

    print("=" * 60)
    print("Building datasets...")
    print("=" * 60)
    train_ds = CachedCipherDataset(split='train', dual_view=True)
    val_ds = CachedCipherDataset(split='val', dual_view=True)
    test_ds = CachedCipherDataset(split='test', dual_view=True)

    print("Preloading train split...")
    train_ds.preload_all()
    print("Preloading val split...")
    val_ds.preload_all()
    print("Preloading test split...")
    test_ds.preload_all()

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)

    all_results = {}

    def eval_test(model, loader, mtype='cnn'):
        preds, labels, _ = get_predictions(model, loader, mtype)
        return {
            'test_acc': float(accuracy_score(labels, preds)),
            'test_macro_p': float(precision_score(labels, preds, average='macro', zero_division=0)),
            'test_macro_r': float(recall_score(labels, preds, average='macro', zero_division=0)),
            'test_macro_f1': float(f1_score(labels, preds, average='macro', zero_division=0)),
        }

    # GBT
    print("\n" + "=" * 60)
    print("Training GBT baseline")
    print("=" * 60)
    gbt_model, gbt_results = train_gbt(train_loader, val_loader)
    all_results['GBT (170-dim)'] = dict(gbt_results)
    all_results['GBT (170-dim)'].update(eval_test(gbt_model, test_loader, 'xgboost'))

    # 1D-CNN
    print("\n" + "=" * 60)
    print("Training 1D-CNN baseline")
    print("=" * 60)
    cnn_baseline = create_model('cnn_baseline')
    cnn_baseline, cnn_hist = train_cnn(cnn_baseline, train_loader, val_loader, "cnn_baseline")
    all_results['1D-CNN'] = {'val_acc': cnn_hist['val_acc'][-1],
                              'val_macro_f1': cnn_hist['val_macro_f1'][-1]}
    all_results['1D-CNN'].update(eval_test(cnn_baseline, test_loader, 'cnn'))

    # Multi-Channel CNN
    print("\n" + "=" * 60)
    print("Training Multi-Channel CNN")
    print("=" * 60)
    full_model = create_model('multichannel')
    full_model, full_hist = train_cnn(full_model, train_loader, val_loader, "multichannel_full")
    all_results['Multi-Channel CNN'] = {'val_acc': full_hist['val_acc'][-1],
                                         'val_macro_f1': full_hist['val_macro_f1'][-1]}
    all_results['Multi-Channel CNN'].update(eval_test(full_model, test_loader, 'cnn'))

    # Byte Transformer
    print("\n" + "=" * 60)
    print("Training Byte Transformer")
    print("=" * 60)
    transformer = create_model('transformer')
    transformer, trans_hist = train_cnn(transformer, train_loader, val_loader, "transformer")
    all_results['Byte Transformer'] = {'val_acc': trans_hist['val_acc'][-1],
                                        'val_macro_f1': trans_hist['val_macro_f1'][-1]}
    all_results['Byte Transformer'].update(eval_test(transformer, test_loader, 'cnn'))

    # BiLSTM-Attention
    print("\n" + "=" * 60)
    print("Training BiLSTM-Attention")
    print("=" * 60)
    bilstm = create_model('bilstm')
    bilstm, bilstm_hist = train_cnn(bilstm, train_loader, val_loader, "bilstm_attention")
    all_results['BiLSTM-Attention'] = {'val_acc': bilstm_hist['val_acc'][-1],
                                        'val_macro_f1': bilstm_hist['val_macro_f1'][-1]}
    all_results['BiLSTM-Attention'].update(eval_test(bilstm, test_loader, 'cnn'))

    # Summary：同时报告验证集与测试集指标
    print("\n" + "=" * 60)
    print("Training complete! Summary:")
    print("=" * 60)
    for name, res in all_results.items():
        print(f"  {name:25s} | Val Acc: {res['val_acc']:.4f} | "
              f"Test Acc: {res['test_acc']:.4f} | Test F1: {res['test_macro_f1']:.4f}")

    import json
    with open(os.path.join(RESULT_DIR, "all_baselines_summary.json"), 'w') as f:
        json.dump(all_results, f, indent=2, default=float)

    return all_results


def train_and_evaluate(model_name, seed=SEED, corpus_split_seed=None,
                       epochs=EPOCHS, patience=EARLY_STOP_PATIENCE, output_path=None):
    """训练单个模型并在测试集上评估，返回/保存 JSON 结果。

    Args:
        model_name: cnn_baseline | multichannel | transformer | bilstm
        seed: 模型初始化 + 数据打乱的随机种子（数据生成保持 SEED=42 不变）
        corpus_split_seed: 若给定，使用源明文级划分（数据泄漏隔离实验）
        output_path: 结果 JSON 保存路径
    """
    set_seed(seed)

    print("=" * 60)
    if corpus_split_seed is not None:
        from data.dataset_corpus_split import CorpusSplitCachedCipherDataset as DS
        print(f"构建源明文级划分数据集 (split_seed={corpus_split_seed})...")
        train_ds = DS('train', dual_view=True, split_seed=corpus_split_seed)
        val_ds = DS('val', dual_view=True, split_seed=corpus_split_seed)
        test_ds = DS('test', dual_view=True, split_seed=corpus_split_seed)
    else:
        print("构建样本级划分数据集...")
        train_ds = CachedCipherDataset('train', dual_view=True)
        val_ds = CachedCipherDataset('val', dual_view=True)
        test_ds = CachedCipherDataset('test', dual_view=True)
    print("=" * 60)

    print("预加载 train split...")
    train_ds.preload_all()
    print("预加载 val split...")
    val_ds.preload_all()
    print("预加载 test split...")
    test_ds.preload_all()

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
    test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)

    model = create_model(model_name)
    model, hist = train_cnn(model, train_loader, val_loader, model_name,
                            epochs=epochs, patience=patience, save=False)

    # 测试集评估
    preds, labels, probs = get_predictions(model, test_loader, 'cnn')
    test_acc = float(accuracy_score(labels, preds))
    test_macro_p = float(precision_score(labels, preds, average='macro', zero_division=0))
    test_macro_r = float(recall_score(labels, preds, average='macro', zero_division=0))
    test_macro_f1 = float(f1_score(labels, preds, average='macro', zero_division=0))
    best_epoch = int(np.argmin(hist['val_loss'])) + 1
    best_val_acc = float(max(hist['val_acc']))
    best_val_f1 = float(max(hist['val_macro_f1']))

    result = {
        'model': model_name,
        'seed': seed,
        'corpus_split_seed': corpus_split_seed,
        'test_acc': test_acc,
        'test_macro_p': test_macro_p,
        'test_macro_r': test_macro_r,
        'test_macro_f1': test_macro_f1,
        'best_epoch': best_epoch,
        'best_val_acc': best_val_acc,
        'best_val_f1': best_val_f1,
    }

    print(f"\n[{model_name}] Test Acc: {test_acc * 100:.2f}% | "
          f"Test Macro-F1: {test_macro_f1:.4f} | Best epoch: {best_epoch}")

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(result, f, indent=2, default=float)
        print(f"结果已保存: {output_path}")

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='CipherBench Training')
    parser.add_argument('--model', type=str, default='all',
                        choices=['all', 'gbt', 'cnn_baseline', 'multichannel',
                                 'transformer', 'bilstm'],
                        help='Model to train (default: all)')
    parser.add_argument('--seed', type=int, default=SEED,
                        help='随机种子（模型初始化 + 数据打乱，数据生成保持固定）')
    parser.add_argument('--corpus_split_seed', type=int, default=None,
                        help='若给定，使用源明文级划分（R1M8 语料隔离实验）')
    parser.add_argument('--epochs', type=int, default=EPOCHS)
    parser.add_argument('--patience', type=int, default=EARLY_STOP_PATIENCE)
    parser.add_argument('--output', type=str, default=None,
                        help='结果 JSON 保存路径（单模型模式）')
    args = parser.parse_args()

    if args.model == 'all':
        train_all_baselines()
    elif args.model == 'gbt':
        set_seed(args.seed)
        if args.corpus_split_seed is not None:
            from data.dataset_corpus_split import CorpusSplitCachedCipherDataset as DS
            train_ds = DS('train', dual_view=True, split_seed=args.corpus_split_seed)
            val_ds = DS('val', dual_view=True, split_seed=args.corpus_split_seed)
            test_ds = DS('test', dual_view=True, split_seed=args.corpus_split_seed)
        else:
            train_ds = CachedCipherDataset('train', dual_view=True)
            val_ds = CachedCipherDataset('val', dual_view=True)
            test_ds = CachedCipherDataset('test', dual_view=True)
        train_ds.preload_all()
        val_ds.preload_all()
        test_ds.preload_all()
        train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=NUM_WORKERS)
        val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
        test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=NUM_WORKERS)
        model, _ = train_gbt(train_loader, val_loader)
        # 测试集评估 + 可选保存
        preds, labels, probs = get_predictions(model, test_loader, 'xgboost')
        result = {
            'model': 'gbt', 'seed': args.seed,
            'corpus_split_seed': args.corpus_split_seed,
            'test_acc': float(accuracy_score(labels, preds)),
            'test_macro_p': float(precision_score(labels, preds, average='macro', zero_division=0)),
            'test_macro_r': float(recall_score(labels, preds, average='macro', zero_division=0)),
            'test_macro_f1': float(f1_score(labels, preds, average='macro', zero_division=0)),
        }
        print(f"\n[gbt] Test Acc: {result['test_acc'] * 100:.2f}% | "
              f"Test Macro-F1: {result['test_macro_f1']:.4f}")
        if args.output:
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2, default=float)
            print(f"结果已保存: {args.output}")
    else:
        train_and_evaluate(args.model, seed=args.seed, corpus_split_seed=args.corpus_split_seed,
                           epochs=args.epochs, patience=args.patience, output_path=args.output)
