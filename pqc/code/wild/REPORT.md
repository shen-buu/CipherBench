# Wild Set 采集报告（进行中）

启动：2025-09-17。三轨：A=CT 日志证书（ML-DSA）、B=OpenSSH 真实握手（KEM）、C=TLS PQ 端点。
验收：B ≥100 条（必达）；A 收到多少算多少；C 30 分钟试水。

## 按类×来源计数（运行中）
（待填）

## 距 50/类 差距清单
（待填）

## 阻塞与绕过
（待填）

## 轨道 A 记录（2025-09-18 首轮）
- crt.sh 查询（限速 ≥2s，原始响应存 raw/ct_log/query_*.json）：
  IdenTrust Pilot Root TLS ML-DSA CA 1 → 仅自签根 1 件（id=29091879757，issuer_ca_id=-1，无下属叶子）；
  "ML-DSA CA" → 同上（同名根）；PQCSign / PQCSign.org / "Post-Quantum CA" → 空。
- pqcsign.org：DNS 解析失败（Could not resolve host）→ limitation，不折腾代理。
- 已入库：真根 29091879757（verified）+ 误报 37773381（rejected 桶，原因 RSA/sha1）。
- 结论：CT 日志内 ML-DSA 证书仍仅 1 件 → 稀缺性框架成立；A 轨可收工（收到多少算多少）。

## 三轨结果（2025-09-18 首日）
| 来源 | 类 | 数量 | 状态 |
|---|---|---|---|
| ct_log | mldsa87_cert | 1 | verified（CT 日志内唯一 ML-DSA 证书，无下属叶子） |
| ct_log | rsa2048_cert（误报） | 1 | rejected（RSA/sha1，入误报桶） |
| tls_endpoint | X25519MLKEM768 | 1 | verified（key_share：ML-KEM-768 pub 1184B + ct 1088B，IANA 4588） |
| openssh | sntrup761x25519-sha512 | 60 | verified_by_protocol_negotiation |
| openssh | mlkem768x25519-sha256 | 60 | verified_by_protocol_negotiation |
合计 123 条；B 轨必达项（≥100）达成 ✓。

## 距 50/类 差距
- mldsa87_cert：1/50（差 49）——CT 日志全域仅 1 件，scarcity-as-finding 框架覆盖；
- sntrup761x25519 / mlkem768x25519：各 60/50 ✓ 达标（KEM 产物，非证书类，不参与证书计数）；
- X25519MLKEM768：1 条（试水达标，30 分钟时间盒内收工）。

## 阻塞与绕过
1. gitee 匿名 git clone 弹认证 → 走 codeload.github.com 下载 V_10_0_P1 源码包 ✓；
2. 系统缺 zlib.h → 用户级编译 zlib 1.3.1（codeload 下载）并挂 CPPFLAGS/LDFLAGS ✓；
3. make install 写 /var/empty 被沙箱拒 → --with-privsep-path=/home/shen/ssh/empty ✓；
4. CFLAGS 覆盖破坏 configure 特性检测（VLA/C99 宏丢失 → USE_SNTRUP761X25519 未定义）
   → 改经 CPPFLAGS 注入 -DDEBUG_KEXECDH，特性检测保留 ✓；
5. OpenSSH 10 拆分为 sshd/sshd-session：KEX 代码在 sshd-session，dump 需补丁 dump_digest
   走 debug3 通道（privsep 子进程 stderr→/dev/null）+ 分块输出（日志 1024 截断）✓；
6. sshd -d 单次仅服务一个连接 → 逐轮重启（120 轮 × ~2.5s ≈ 6 分钟）✓；
7. sntrup761 密文长凭记忆写 1122 → 实测 dump len=1039，已改（纪律：实测为准）✓；
8. pqcsign.org DNS 解析失败 → limitation，不折腾代理。

## 命令日志（关键）
（crt.sh 查询 6 次、codeload×2、zlib/openssh 编译链、120 轮握手、TLS s_client 1 次——
  全程断点续跑，见本目录 b_harvest.py / parse_tls_transcript.py / ssh-src/ 与 meta.jsonl 时间戳）

## A 轨扩展（2025-09-18，9 个试点 CA 域名逐个查询，全部 0 条）
- IdenTrust Pilot Root TLS ML-KEM CA / SLH-DSA CA → 0
- PQCSign Root CA → 0（官网 DNS 亦不通）
- mtest / MTest / DigiCert PQ / Google Trust Services PQ / Keyfactor PQ / Entrust PQ → 0
- NIST CSOR 注册表拉取失败（csrc.nist.gov 不可达）→ 以 3 条已核实 ML-DSA OID 兜底验证，
  记 limitation；后续若补 SLH/ML-KEM 证书验证需先解决注册表可达性。
- 结论：CT 日志内 ML-DSA 证书仍仅 1 件根（无叶子、无其他试点 CA）。
  wild 证书类凑不齐 50/类 → 走 scarcity-as-finding（limitation 段落），不硬凑。
