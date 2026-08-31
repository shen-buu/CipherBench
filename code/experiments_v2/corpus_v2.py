#!/usr/bin/env python3
"""语料级划分评估：10 个分区（corpus_split_seed=1..10），MC seed42。
缓存目录：DATA_DIR/cache_corpus_split_{k}/{train,val,test}（自动生成）。
结果：results2/v2/corpus_split_{k}.json
"""
import os, sys, json, argparse, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import accuracy_score, f1_score
from config import *
from data.dataset_corpus_split import CorpusSplitCachedCipherDataset
from models.cnn import MultiChannelCNN
from train import set_seed, train_cnn, get_predictions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--k', type=int, required=True, help='corpus_split_seed (1..10)')
    ap.add_argument('--epochs', type=int, default=EPOCHS)
    args = ap.parse_args()
    k = args.k

    set_seed(42)
    print(f"===== corpus split {k} =====", flush=True)
    train_ds = CorpusSplitCachedCipherDataset('train', dual_view=True, split_seed=k)
    val_ds = CorpusSplitCachedCipherDataset('val', dual_view=True, split_seed=k)
    test_ds = CorpusSplitCachedCipherDataset('test', dual_view=True, split_seed=k)
    train_ds.preload_all(); val_ds.preload_all(); test_ds.preload_all()
    tl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
    vl = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)
    el = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2)

    model = MultiChannelCNN(num_classes=NUM_CLASSES)
    model, hist = train_cnn(model, tl, vl, f'corpus_{k}',
                            epochs=args.epochs, patience=EARLY_STOP_PATIENCE, save=False)
    preds, labels, _ = get_predictions(model, el, 'cnn')
    result = {
        'model': 'multichannel', 'seed': 42, 'corpus_split_seed': k,
        'test_acc': float(accuracy_score(labels, preds)),
        'test_macro_f1': float(f1_score(labels, preds, average='macro', zero_division=0)),
        'best_epoch': int(np.argmin(hist['val_loss'])) + 1,
        'best_val_acc': float(max(hist['val_acc'])),
    }
    out = f'results2/v2/corpus_split_{k}.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(result, f, indent=2, default=float)
    print(f"corpus split {k} done: acc={result['test_acc']*100:.2f}% -> {out}", flush=True)


if __name__ == "__main__":
    main()
