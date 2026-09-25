#!/bin/bash
# C2 校准/灵敏度梯子 + 真实数据正控制（租机端，断点续跑：已存在文件自动跳过）
# 用法：nohup bash run_ladder.sh > ladder_all.log 2>&1 &
set -u
PY=python3
SCRIPT=/root/pqc/train_baselines.py
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

for L in 0.0 0.0625 0.125 0.25 0.5 1.0; do
  cd /root/pqc_ladder/L$L || { echo "MISSING L$L"; exit 1; }
  echo "=== L$L cnn ==="
  $PY -u $SCRIPT --data ./data --arch cnn --scene p1 --device cuda --parallel 2 >> ladder.log 2>&1 || echo "L$L cnn RETRY-NEXT-ROUND"
  echo "=== L$L bilstm ==="
  $PY -u $SCRIPT --data ./data --arch bilstm --scene p1 --device cuda --parallel 2 >> ladder.log 2>&1 || echo "L$L bilstm RETRY-NEXT-ROUND"
done

# 真实数据正控制：cert 组 P2（对照 RF 锚点 0.8488）
cd /root/pqc
echo "=== ctrl cnn cert-p2 ==="
$PY -u $SCRIPT --data ./data --arch cnn --scene p2 --groups cert --device cuda --parallel 2 >> ladder_ctrl.log 2>&1 || echo "ctrl cnn RETRY-NEXT-ROUND"
echo "=== ctrl bilstm cert-p2 ==="
$PY -u $SCRIPT --data ./data --arch bilstm --scene p2 --groups cert --device cuda --parallel 2 >> ladder_ctrl.log 2>&1 || echo "ctrl bilstm RETRY-NEXT-ROUND"

touch /root/pqc_ladder/all.done
echo ALL-DONE
