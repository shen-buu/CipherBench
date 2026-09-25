# wild 单证书 S1 轨迹表（H 决策 B 口径，2025-09-17）

管线：exp_s1.py 冻结管线本体（复用 import，非复制）；**复现门 22/22 逐位一致**
（每条件×每种子〔42/123〕重跑的 macro-F1 与 s1_*_seed*.json 完全相同）→ 轨迹预测全部
来自冻结管线。wild 窗口用独立 per-seed rng（流位置 0），训练流未扰动（E8）。
对象：真证书 idenTrust_MLDSA_root_cert.der（7628B，ML-DSA-87）+ 误报 dilithiumnetworks.der
（1404B，RSA/sha1，特异性对照）。18 容器类 × 300，P2 头窗 1024B，raw 字节，RF300 × 5 折。

| 条件 | 真证书：主导投票（折数/5） | P(mldsa87_cert) 均值 | 误报 P(mldsa87_cert) |
|---|---|---|---|
| intact | mldsa87_cert（4-5/5） | 0.1753 / 0.2093 | 0.0707 / 0.0600 |
| oid_zero | mldsa87_cert（5/5） | 0.2833 / 0.2713 | 0.0360 / 0.0473 |
| oid_rand | mldsa87_cert（3/5） | 0.1300 / 0.1227 | ≤0.10 |
| head24 | 短 pkcs8 类 | 0.1087 / 0.0967 | ≤0.10 |
| head48 | 短 pkcs8 类 | 0.0313 / 0.0220 | ≤0.10 |
| trunc25/50/75 | 无关类 | 0.077 / 0.072-0.079 / 0.066 | ≤0.10 |
| slide25 | slhdsa128s_cert（5/5） | 0.0153 / 0.0107 | 0.0040 / 0.0033 |
| slide50/75 | 无关类 | 0.111 / 0.137、0.129 / 0.128 | ≤0.10 |

要点：
1. 敏感侧：intact 与 OID 抹除下识别为 mldsa87_cert（OID 冗余在部署级工件上复现，
   oid_zero 置信反升 0.18→0.28）；head/trunc/slide 沿 S1 梯度崩塌——轨迹即已验证边界；
2. 特异侧：RSA 误报全条件 P(mldsa87_cert)<0.10（max 0.097，slide75）——无假阳性式高置信；
3. 门禁：定量多样本演示仍等 wild ≥50/类 + §4 定稿；本表为 n=1 案例，非统计比较。
落盘：results/wild_s1_trajectory.json（22 门 + 逐折投票 + proba）。
