# CipherBench-PQC Audit Log (63 cases, shipped with the release)

> Numbering: #1–#18 development-phase cases (reconstructed numbering, see note in the Chinese
> master `audit_log.md`); #19–#26 keep the original numbering used in the internal records
> (RESUME.md, host_verification.md, QA_交付报告.md). Each entry: finding → ruling → fix → evidence.

## #1 Window RNG shared across seeds → spuriously tight seed SDs (norm E8 was born here)
- Finding: reported ±SD across seeds was systematically too small.
- Ruling: all seeds drew windows from one shared RNG sequence, so seeds were not independent replicates.
- Fix: **E8 — per-seed independent window RNG**; all ± values report seed SD.
- Evidence: paper §4.2/§4.5; §6 box "Anatomy of a frozen number", first case.

## #2 Naive length-identity gap of 3×10⁻⁴ between theory and measurement
- Finding: measured nn_len = 0.926176 vs. the naive identity 0.9265; initially suspected as a bug.
- Ruling: the entire gap comes from the 784 B near-collision (rsa2048_cert: 3/300 at 784 B, 297 at 785 B).
- Fix: exact decomposition written into §5.3 and host_verification.md.
- Evidence: 0.926176 = (29×1 + 0.5 + 0 + 0 + 0.995025 + 0.994975)/34.

## #3 Zero-padding backdoor (Bug#3) — fill fraction as a length proxy
- Finding: with a tiled layout and zero-filled final blocks, the 16-byte length difference between the
  768 B and 784 B classes leaks through the fill ratio, macro-F1 = **0.988 ± 0.002**.
- Ruling: zero fill makes padding bytes distinguishable from data, turning fill fraction into a length channel.
- Fix: P1/P2 use uniform random fill; **zero-padding is forbidden**; the number is quoted in §3.2.
- Evidence: host_verification.md §三·补2; paper §3.2.

## #4 Tie-breaking dependence of the exact-level macro-F1
- Finding: per-class F1 inside the 768 B/784 B collision sites depends on the 1-NN tie-breaking
  convention, interval [0.9262, 0.9409]; the 50-draw β estimate sat 2.8 SE above its expectation,
  and sample numbers such as 1.018/1.468 had no reconstructible semantics.
- Ruling: β(G) formally defined as E_T[macro-F1(ĉ_T)] with per-object independent uniform
  tie-breaking; exact expectations: 3×0.33352 = 1.0006 (768 B site), 0.6647+0.7977 = 1.4624
  (784 B site); E[β] = 0.9254; convention-wise maximum = 0.9409.
- Fix: §5.3 rewritten with the definition and reader-checkable arithmetic; footnote reworded.
- Evidence: 复核报告 §十一; §5.3; §6 box, third case.

## #5 Length-atom accounting 34 → 49 → 46
- Finding: G=46 contradicted the "34 classes → 49 class-specific lengths"口径.
- Ruling: the 768 B three-way tie merges 3 atoms and the 784 B near-collision merges 2: 49−3 = 46.
- Fix: full ledger in §5.3 (8 multi-support classes contribute 4+6+3+2+2+2+2+2 = 23 atoms +
  26 single-atom classes + 2 collision sites).
- Evidence: host_verification.md §二·补; §5.3.

## #6 Drift ledger — four frozen iterations of the B4 cross-spec leg: 0.557 → 0.502 → 0.482 → 0.494
- Finding: four consecutive frozen runs of identical code returned 0.557 → 0.502 → 0.482 → 0.494
  with no code change; the then-reported SD was spuriously tight (it missed which implementation
  pairing each run drew).
- Ruling: pure inter-implementation sampling noise; variance bridge = inter-implementation variance
  (which pairings are drawn) vs. inter-seed variance (how windows are drawn).
- Fix: B4 legs report **between-realization SD** (0.494 ± 0.020, 10 realizations); §6 box, second case.
- Evidence: §6 box; Table 4a.

## #7 Fill-fraction rival hypothesis for the ECDSA 0.2508 excursion (three exclusions)
- Finding: ECDSA (69–72 B) at 0.2508 needed the "short object + fill ⇒ fill fraction = length proxy"
  explanation ruled out.
- Exclusion 1: the shorter Ed25519 (64 B) sits with the uniform classes at F1 = 0.0713;
- Exclusion 2: length↔F1 correlation r = −0.186, no gradient, single spike;
- Exclusion 3 (by construction): P1 fill is uniform random bytes, statistically indistinguishable
  from uniform content.
- Fix: Ed25519 control sentence in §5.2; attribution confirmed as DER-tag content structure.
- Evidence: host_verification.md §三·补2; §5.2.

## #8 The double 0.494 coincidence (PQClean window leg vs. cross-spec leg; historical — dissolved at 10 realizations on 2026-09-19, see #27)
- Finding: two independent experiments both average exactly 0.494; misreadable as one dataset.
- Ruling: coincidence; per-realization vectors differ (0.4678–0.5433, 10 real. vs. 0.4806–0.5089,
  5 real.) and the experiments are disjoint by construction.
- Fix: Coincidence note after Table 4a.
- Evidence: Table 4a note; b4_pqclean_leg.json.

## #9 Wild-set RSA false positive kept as a method negative control
- Finding: a name-based CT search surfaced vpn.dilithiumnetworks.com, but the certificate is
  sha1WithRSA with no PQ OID — a naming artifact.
- Ruling: not a PQ certificate; its S1 false-positive probability (<0.10) is specificity evidence.
- Fix: retained and labeled "Retained as method-negative control" (Table 3).
- Evidence: wild/meta.jsonl; Table 3.

## #10 sntrup761 ciphertext 1039 B ≠ expected 1122 B
- Finding: the OpenSSH handshake dump showed 1039 B where the KEM specification suggested 1122 B.
- Ruling: the expectation used the wrong field口径 (encapsulation vs. share field); 1039 B measured is authoritative.
- Fix: wild records annotated with the measured value; no "correction".
- Evidence: wild/REPORT.md; ssh-src dump script.

## #11 OpenSSH DEBUG_KEXECDH output truncated at MSGBUFSIZ (1024)
- Finding: patched OpenSSH debug output was cut at 1024 B, losing handshake digests/ciphertexts.
- Ruling: debug3 channel MSGBUFSIZ limit.
- Fix: dump_digest switched to debug3 chunked output (CPPFLAGS -DDEBUG_KEXECDH); collection rerun.
- Evidence: ssh-src/kex.c patch; wild/REPORT.md.

## #12 Wild single-certificate S1 trajectory — 22/22 reproduction gates
- Finding: wild predictions had to be proven to come from the frozen pipeline, not an ad-hoc configuration.
- Fix: exp_wild_s1.py enforces 22 condition×seed macro-F1 reproduction gates against
  s1_*_seed*.json, digit-exact; 22/22 passed.
- Evidence: results/wild_s1_trajectory.json + wild_s1_实验记录.md; §5.8.

## #13 NIST battery boundary and range wording (24 cells, three displayed 0.95s, cusum range)
- Finding: 24-vs-25 bold-cell dispute; two displayed 0.95s in the ML-DSA-87 column with unclear
  semantics; §5.1 cusum range "0.88–0.95" used an unbolded cell as endpoint.
- Ruling: strictly-below-0.95 cells = exactly 24; the three displayed 0.95 cells are 0.9500
  (285/300) and 0.9533 (286/300) ×2, none strictly below; bold ML-DSA cusum cells are
  {0.93, 0.88, 0.93} → range 0.88–0.93.
- Fix: Table 2 note and §5.1 rewritten.
- Evidence: results/table3_nist_formal.json; 复核报告 §十二.

## #14 Three inconsistent z values for G=5 (18/17/8) and §6 using the β ceiling as a measurement
- Finding: §5.3 "z = 467/616/500/70/18", Fig. 1 "z=17", §6 "(z = 18)"; §6 quoted β = 0.1466 as
  if it were the measured leak.
- Ruling: the z ladder is computed from measured nn-F1; (0.046148−0.016563)/0.001693 = 17.48 → 17;
  the measured G=5 leak is 0.0461.
- Fix: all three spots unified to z = 17; §6 changed to 0.0461; Table 5 C_len row 0.1466 → 0.0461.
- Evidence: results/s2s3_formal.json; 复核报告 §九.

## #15 B-grid retention precision chain (30.1%/62.1% not reconstructible from displayed values)
- Finding: (B2−B1)/(B5−B1) computed from 3-decimal displays does not give 30.1%/62.1%.
- Ruling: numerator/denominator use unrounded means (0.0208/0.0691 and 0.0901/0.1451).
- Fix: unrounded note added in §5.7.
- Evidence: §5.7; Table 4 note.

## #16 Stale Table 4/5 values (30.7%/0.161/0.244)
- Finding: tables still carried 3-seed-era values contradicting the frozen 5-seed grid.
- Fix: replaced with the frozen 5-seed values (B0–B5 grid).
- Evidence: results/align_order.json (n_seeds=5); 复核报告 N1.

## #17 AES-GCM assumption wording (PRP/PRF → PRF/CTR + generator policy)
- Finding: Proposition 1 described AES-GCM as PRP/PRF without stating the plaintext/nonce policy;
  the code uses a fresh random key and 12-byte nonce per object with uniform-random plaintext.
- Fix: three spots now state PRF/CTR plus the §3.2 generator policy (uniform-random 752/768 B
  plaintext, ct‖tag output); reduction sketch retained.
- Evidence: gen_formal.py; §4.3; §3.2.

## #18 BiLSTM near-chance result closed with two controls (honest architecture result)
- Finding: BiLSTM P1/P2 = 0.0233/0.0370 below the random baseline had to be proven not an
  implementation failure.
- Control 1: constant-sequence acc = 1.0 (implementation correct); Control 2: head-signal gradient
  vanishing (λ ladder narrow-band tiers all ≤ chance).
- Fix: reported as a quantified failure mode (§5.5/§4.4), not hidden.
- Evidence: host_verification.md §四; §5.5.

## #19 BiLSTM predict() full-batch OOM (rental host)
- Finding: predict() ran the whole test set (2040×1024) in one inference; 5 concurrent workers OOM'd.
- Fix: chunked predict (256) — numerically equivalent (no BN/dropout at eval; LSTM zero-init per chunk).
- Evidence: RESUME.md #19.

## #20 Symlink-induced makedirs path mismatch (rental rerun)
- Finding: the verification directory symlinked data → the formal directory; workers failed on results paths.
- Root cause: os.makedirs("./data/../results") resolved through the kernel symlink.
- Fix: res_dir unified via os.path.realpath before makedirs.
- Evidence: RESUME.md #20; host_verification.md §四.

## #21 Last-job OOM on the CNN rerun (external contention)
- Finding: loss.backward() OOM (20 MiB requested, 14.75 MiB left).
- Fix: --parallel 2 + until-retry loop (resumable by design).
- Evidence: RESUME.md #21.

## #22 C2 calibration and the signal-density ladder (negative-result gate)
- Requirement: E3 — negative results must pass C2 calibration (≥0.60) or report a sensitivity ladder.
- Experiment: synthetic 5×300×1024 objects, 8-byte class tokens injected at probability λ.
- Result: CNN λ=0.5/1.0 = 0.893/1.000 → C2 passed; BiLSTM narrow-band tiers all ≤ chance.
- Evidence: RESUME.md #22; host_verification.md §四·补2; Fig. 6.

## #23 Budget-sensitivity ablation (30 vs. 15 epochs)
- Requirement: close the "why not train longer" question.
- Experiment: --epochs 30: CNN 0.2832/0.4590 overtakes the tree baselines; BiLSTM unmoved.
- Wording: "CNN < trees" holds only under the frozen 15-epoch protocol.
- Evidence: RESUME.md #23; §5.5 e30 paragraph.

## #24 Stale NIST summary row vs. the frozen battery (found while plotting)
- Finding: an old summary row ("serial 0.50/0.70/0.75, ECDSA freq 0.86, rest 0.97–1.00") was incomplete.
- Ruling: all 24 sub-0.95 cells concentrate in four signature classes; the other 12 primitives ≥ 0.967.
- Fix: fig4 drawn from the frozen file; §5.1 rewritten with the two-family structure.
- Evidence: figures/QA_交付报告.md #24.

## #25 RSA-OAEP-2048 wrongly placed inside Π_pse (raised by the user)
- Finding: Proposition 1 once listed RSA-OAEP ("RSA assumption") among the pseudorandom-ciphertext classes.
- Rejection (correct): RSA gives one-wayness, not indistinguishability; an OAEP ciphertext is uniform
  in Z_n, a proper subset of the byte space, so the modulus-interval truncation biases the top byte
  (measured: first byte ≥ 0x80 in 0.307 vs. 0.5 uniform, z ≈ 6.7).
- Fix: Π_pse = ML-KEM×3 + AES-GCM + uniform control; RSA-OAEP moved to the empirical bucket;
  exclusion + measurement written into §4.3(ii).
- Evidence: RESUME.md #25; §4.3.

## #26 Reversed reduction direction (raised by the user)
- Finding: the sketch derived a "π₁ vs. uniform" distinguisher directly from "π₁ vs. π₂"
  separability — the direction was wrong.
- Fix: triangle argument reordered: ① each class vs. uniform indistinguishable → ② triangle
  inequality ⇒ mutual indistinguishability (δ/2 hybrid) → ③ a classifier beyond the permutation
  band (beyond sampling error) is exactly such a separator → contradiction.
- Evidence: RESUME.md #26; §4.3 reduction sketch.

## #27 Replicate-count upgrade: S1 2→5 seeds, C_align 3→5 seeds, PQClean 5→10 realizations (internal review decision, 2026-09-19)
- Finding: replicate counts below the E14 convention (S1: 2 seeds; C_align: 3 seeds; PQClean: 5 realizations).
- Fix: all three upgraded and re-run with unchanged protocols (E8 per-seed window RNG preserved).
- Old → new (mean ± SD):

  S1 (5 seeds; old 2 seeds): intact 0.9996→0.9997; oid_zero 0.9997→0.9998; oid_rand 0.9998→0.9998;
  head48 0.8838→0.8827; trunc25/50/75 0.544/0.386/0.316→0.548/0.383/0.314;
  slide25/50/75 0.888/0.611/0.611→0.886/0.613/0.614.

  C_align (5 seeds; old 3 seeds): A2 shifted 0.8748/0.8694/0.8330→0.8748/0.8687/0.8334;
  A2_nt no-first-block 0.3765/0.2377/0.0904→0.3768/0.2372/0.0907; A1 exact 0.9262 unchanged.

  PQClean (10 realizations; old 5): whole 0.524±0.031 (SE 0.0139)→0.490±0.026 (SE 0.0081);
  window 0.494±0.010 (SE 0.0045)→0.509±0.017 (SE 0.0055); window range 0.4806–0.5089→0.4811–0.5400
  (whole range 0.4544–0.5283). Case #8's "double 0.494 coincidence" dissolved at 10 realizations;
  #8 is kept as a historical record and the paper's Coincidence note was rewritten.
- Evidence: results/s1_formal_summary.json (n=5), align_order.json (5-seed A2/A2_nt),
  b4_pqclean_leg.json (10 realizations).

## #28 Open-set v1 scoring asymmetry (caught by the null band, 2026-09-18)
- Finding: the v1 E2 permutation-null AUROC was anomalous (MSP 0.93, entropy 0.99; should be ≈0.5).
- Ruling: known objects were scored by their own fold's model while unknowns were scored by the
  5-fold average; under label permutation this asymmetry alone created an ID/OOD gap (averaging
  raises entropy, lowers max probability), contaminating the null. All v1 results were discarded.
- Fix: v2 uses a single model with an 80/20 split (known 240/60 per class, all unknowns in test),
  scoring both groups symmetrically; the null returned to the 0.5 regime. v1 JSON overwritten.
- Lesson: any average-vs-single-model scoring asymmetry must pass the null-band test first.
- Evidence: exp_open_set.py (v2); 复核报告 §二十三.

## #29 Cross-implementation transfer set (internal review decision, 2026-09-19)
- Original plan: generate the test set with oqs-provider + OpenSSL 3.5. Verified and corrected:
  the training containers were themselves generated by oqs-provider + OpenSSL 3.5.3 + liboqs 0.16.0
  (gen_formal.py), so the literal plan was same-toolchain resampling; switched to **native OpenSSL
  3.5.3 (default provider) ML-DSA/ML-KEM** for the 900-object test set (6 PKCS#8 + 3 self-signed
  X.509, 100 each, test-only). ML-KEM cannot sign, hence no ML-KEM certificates.
- First pass with a misaligned CN (19 chars vs. the training 11 chars; +16 B subject/issuer shift)
  collapsed mldsa44_cert under P2 to 0.0468 — a field-level sensitivity, not an implementation gap;
  recovered after aligning the CN format.
- Final (5 seeds, E14): S1 transfer 0.9992±0.0003 (SE 0.0001) ≈ ref 0.9993±0.0009 (SE 0.0004);
  P2 0.7494±0.0085 (SE 0.0038) vs 0.6740±0.0028 (SE 0.0012); P1 0.4589±0.0195 (SE 0.0087) vs
  0.3725±0.0183 (SE 0.0082); the only per-class drop is mldsa87_cert P2 0.3789±0.0243 (7471/7472 B
  mix shifting head-window alignment). Byte-level ASN.1 diffing: no implementation-level divergence.
- Evidence: exp_oqs_transfer.py; results/oqs_transfer_formal.json (env: OpenSSL 3.5.3 native;
  training side oqs-provider + liboqs 0.16.0).

## #30 Table 4 cell completion (internal review decision, 2026-09-19)
- Target 8/16 → ≥12/16. New measurements: C_bytes×S1 (trunc50/slide50 damaged fragments + P1,
  rf/hgb, 5 seeds + E2 null band) and C_struct×S3 (container lengths quantized to G=16/64 + 1-NN,
  5 seeds: 1.0000 / 0.8519).
- **First-pass trunc50 design defect (zero-run marker)**: zeroing the head 50% embedded a
  length-proportional zero-run (length L/2) into the object; the 170-dim run/byte-distribution
  features read the length directly → rf/hgb ≈0.46, far above the 0.063 null band — the
  destruction method itself created a length channel. After uniform-random refill the cells fall
  back into the null band (rf from 0.0702). The zero-run marker effect is kept as a one-line note
  in §5.2.
- By-construction labeled cells: C_bytes×S2 (S2 changes only length), C_align×S2/S3 (length
  bijection derivation), C_struct×S2 (=S0), C_align×S1 (=S0), C_bytes×S3 (byte observation
  unavailable).
- Final values (5 seeds, E14): trunc50 rf 0.0663±0.0039 (SE 0.0017) / hgb 0.0659±0.0020
  (SE 0.0009), null 0.0627±0.0033 / 0.0641±0.0038 (z≤1.1); slide50 rf 0.0723±0.0033 (SE 0.0015)
  / hgb 0.0746±0.0045 (SE 0.0020), null 0.0602±0.0034 / 0.0598±0.0025 (z≤5.9, not above intact
  P1's own z=2.7). Conclusion: the impossibility layer holds under S1 damage. C_struct×S3:
  G=16 1.0000±0.0000, G=64 0.8519±0.0000.
- Coverage 8/16 → 16/16 (10 measured + 6 by-construction), no unexplained blanks.
- Evidence: results/bytes_s1_formal.json, results/struct_s3_formal.json.

## #31 Existing-tools measurement (internal review decision, 2026-09-19)
- file(1)/libmagic 5.46 (system magic db): intact class-level macro-F1 0.0555, family-level 0.4443 —
  recognizes only RSA PKCS#1 ("DER Encoded Key Pair"); certificates are "Certificate, Version=3"
  (family only, no algorithm granularity); the other 10 PKCS#8 classes (PQ/EC/Ed25519/SLH-DSA) are
  "data"; unchanged under oid_zero; 0 under head48/trunc50.
- OID+structure baseline (11 algorithm OIDs + TBS/PKCS#8/PKCS#1/SEC1 head markers; the original
  "12" was a counting error, see #50): intact 1.0000;
  oid_zero 0.5000 (ML-DSA/SLH-DSA prefix erased → 9 classes die; ML-KEM and classic OIDs sit outside
  the erased prefix and survive); head48/trunc50 0.
- First-pass OID arcs were wrong (ML-KEM-768/1024, SLH-DSA arcs from memory); corrected against the
  training objects' actual bytes (mlkem768=…4.4.2, mlkem1024=…4.4.3, slhdsa128s=…4.3.26,
  slhdsa256s=…4.3.30); rsa2048_pkcs8/ecdsap256_pkcs8 are PKCS#1/SEC1 formats (no algorithm OID) —
  format markers added.
- Evidence: results/tools_baseline_formal.json (env: file-5.46, system magic, OID table).

## #32 TLS 1.3 real-encapsulation validation (internal review decision, 2026-09-19)
- Experiment: 34-class objects sent over real TLS 1.3 sessions (AES-256-GCM, one handshake per
  class, per-object writes); client record ciphertext content lengths parsed (L+17/record:
  1 inner + 16 tag); 1-NN features (record count, first length, second length).
- Result: macro-F1 = 0.9262 ± 0.0000 (5 seeds) — exactly the synthetic "none" point; fragmentation
  affects only SLH-DSA-128f/256s (17088/29792 B → two records) and (count, remainder) stays
  class-unique → no separability loss.
- Implementation notes: this Python's ssl rejects TLS1.3 suites via set_ciphers (build cap), but the
  DEFAULT negotiation is exactly TLS_AES_256_GCM_SHA384 (asserted post-handshake); the openssl CLI
  needs -ciphersuites (not -cipher); s_client/s_server subprocess handshakes misbehave in this
  sandbox — final implementation uses in-process ssl.MemoryBIO.
- Evidence: results/tls_records_formal.json (env: OpenSSL 3.5.3, record policy, session mode).

## #33 Epoch-budget grid 15/30/60 (internal review decision, 2026-09-19; completed 2026-09-20 on rented V100)
- Design: CNN/BiLSTM × {15,30,60} × {p1,p2} × 5 seeds = 12 groups × 60 runs; the 40 per-seed
  15/30 files were already frozen in rental_snapshot/pqc/results/ (aggregates checked); 20 new
  60ep runs + reproduction-bound verification (CNN rerun ≤0.026, BiLSTM exact).
- No local GPU (torch 2.13+cpu) → user provided a rented GPU; runner exp_budget_grid.py supports
  checkpointing (--epochs 60 / --verify).
- Results (5 seeds, E14): CNN P1 0.2075±0.0083 → 0.2832±0.0066 → **0.3181±0.0045**; CNN P2
  0.3415±0.0237 → 0.4590±0.0142 → **0.4999±0.0046** (monotone; at 60ep both protocols exceed the
  tree baselines); BiLSTM P1 0.0233→0.0220→0.0223, P2 0.0370→0.0331→0.0359 (flat at the null
  band, no revival) — "CNN < tree" holds only for the frozen 15ep budget; the conclusion was
  updated accordingly.
- Reproduction bounds: CNN seed7 rerun |Δ|=0.0004 (≤0.026 ✓); BiLSTM seed99 rerun |Δ|=0.0082 —
  not exact across torch versions (2.9.1+cu128 → 2.5.1+cu124); the bound is restated as "exact
  within the frozen environment, ≤0.009 across versions" in the paper and this log.
- In the paper: Figure 7 (vector, QA 6/6), §5.5/§4.4/§1/§2 budget-grid wording, reproduction
  bound sentence.
- Evidence: results/*_e60.json (20 files, renamed to single-underscore naming).

## #34 paper.tex tail wipe and rebuild (2026-09-20, self-inflicted incident record)
- Incident: a §5.5 edit script used an md anchor ("**5.6") to locate a point in the tex; the
  search returned -1 and the slice tex[i:-1] erased everything from §5.6 to the end of the file
  (six figures, six tables and the references).
- Response: build_tail.py rebuilt the tail (§5.6–§7, seven figures, six tables incl. p-columns /
  rotated header / 4a / 5 renumbering, the box paragraph, References) from the current md and
  tables_formal.md; fixed four bug classes (\textbf string slicing, %/#/_/− escapes, table-number
  placement, section-heading emission). Recompiled: 37 pages, 0 errors, 30/30 spot checks passed
  (3 old-value absences were correct, 1 ligature artifact).
- Lesson: tex anchors must never use md syntax; assert both endpoints > 0 before any large
  replacement.

## #35 Terminology-consistency freeze round (internal review decision, 2026-09-20)
- Title variant (b) with Algorithm-Level kept: "Quantifying Algorithm-Level Observable
  Side-Channel Leakage (Representation-Level) of ...".
- Abstract: qualifier sentence inserted after the first sentence ("Herein, 'side channel' means
  representation-level functions of the stored encoding needing no secret key — not key-recovery
  channels (power, timing)."), compressed to 245 tokens (dropped "detector-calibrated,
  budget-robust", the scenario-name parenthetical, "on windows", the residual-signal tail; all
  frozen numbers and mandatory phrases kept).
- Keywords: side-channel leakage → observable leakage; representation-level identification.
- §1 second paragraph already carries the representation-level qualifier (checked, no change).
- Related Work: closing paragraph "Side-channel boundaries", citing Kocher1996 (CRYPTO'96,
  pp. 104-113, DOI 10.1007/3-540-68697-5_9) and Berzati2025 (CASCADE 2025, pp. 3-26,
  DOI 10.1007/978-3-032-01405-4_1, verified via eprint 2024/2051).
- Acceptance: every occurrence of "side channel" in the text carries a contextual qualifier or is
  the §4.1 definition itself; all 26 references cited; 37 pages, 0 compile errors.

## #36 Proposition 1 positioning wording (internal review decision, 2026-09-20)
- Contribution (3) title: "Impossibility layer with a bound" → "Impossibility layer, formalized
  and verified".
- §4.3 opening gains a folklore-positioning sentence ("its role here is not novelty but to delimit
  exactly which classes the impossibility covers — and, via the RSA-OAEP and signature exclusions,
  which it does not").
- Abstract: "a computational-indistinguishability bound (Proposition 1)" → "a formalized
  indistinguishability bound with explicit scope exclusions" (recompressed to 248 tokens).
- "methodological contribution" → "audit-discipline contribution"; the RSA-OAEP measured evidence
  and the theorem/empirical split wording kept.
- Acceptance: no "Impossibility layer with a bound" or "methodological contribution" residue;
  the contribution weight sits on the ladder+budget+three-axis experimental verification.
  38 pages, 0 compile errors.

## #37 Reference expansion 26→48 and citation anchoring (internal review decision, 2026-09-20)
- B-group 8 (lai2025getrid / liu2025rejected / shen2023encrypted / sharma2025survey /
  azab2024network / gebru2021datasheets / pineau2021improving / herley2017sok) + A-group 14
  (chen2018grayscale / wang2018cnn / mittal2021fifty / sester2021comparative /
  skracic2023bytercnn / zhu2023cnnlstm / felemban2024lightweight / sowa2024pqc /
  wickramasinghe2026mindgap / dubey2026readiness / catoni2025resumption / berman2024hint /
  zhou2025rejected / belaid2026sucre) → 48 total.
- Metadata verified against Crossref/arXiv/TCHES/ePrint/JMLR/ACM pages (DBLP blocked scraping →
  Crossref used; Semantic Scholar rate-limited, not relied on); Berzati2025 venue corrected to
  CASCADE 2025; no fabricated entries.
- No-formal-version exceptions filed (3, permitted by the rule): dubey2026readiness (arXiv-only,
  no formal version), wickramasinghe2026mindgap (arXiv + IMC 2026 to-appear note, no pages),
  berman2024hint (ePrint-only, no formal version).
- Citation anchors: §2 PQ adoption measurement (4), randomness/ML-DSA non-uniformity (3),
  side-channel boundaries (+lai/liu), encrypted-traffic classification (+3 surveys), file carving
  (+7, one summarizing sentence); §3.5 Datasheets (1); §6 methodology (herley/pineau).
  build_tail.py citation whitelist extended by 22 keys; tail rebuild idempotent.
- Adjacent fixes (data-checked): §3.5 "26 numbered cases" → 37 (the log holds #1–#37 including
  this entry; the English log gained the missing #30/#33–#36 translations and both titles now say
  37); duplicated "to our knowledge" removed (md+tex); BellareRogaway booktitle em-dash → LaTeX ---
  (missing-glyph warning eliminated); audit #35's Berzati2025 venue COSADE → CASCADE (aligned
  with the bib).
- Acceptance: bibtex 48/48 cited (0 orphans), 0 undefined citation/reference, 0 missing
  characters, 41 pages, 0 compile errors; PDF spot checks: new sentences render (e.g.,
  encrypted-traffic [30,31,32]) and references [1]–[48] all render (incl. accented entries
  Skračić/Belaïd).

## #38 Submission-package round (internal review decision, 2026-09-20)
- Four endmatter sections added (\section*, after References; the md "## End matter" block is the
  single source, parsed by build_tail.py): CRediT (Shen Jinhui: Conceptualization/Methodology/
  Software/Validation/Formal analysis/Investigation/Data curation/Writing–original draft/
  Visualization; Li Xiaofeng: Conceptualization/Supervision/Project administration/Resources/
  Writing–review & editing); Declaration of competing interest (no known competing interests);
  Data availability («REPO_URL» placeholder, MIT code / CC BY 4.0 data, DOI to be registered upon
  acceptance); Funding (no specific grant).
- Format: elsarticle preprint single column kept (C&S publishes single-column; item-by-item
  Guide-for-Authors check in submission_checklist.md); lineno installed (tlmgr install lineno)
  and \linenumbers enabled — PDF spot checks show continuous line numbers from page 1 (margin
  x≈95, 1→1062, all 43 pages); 0 compile errors, 48/48 citations unchanged.
- Highlights (highlights.txt): 5 bullets, lengths 76/76/75/81/76, all ≤85 characters, all quoting
  frozen numbers (0.9262 encryption decay, 0.883 head retention, 38-case log, etc.).
- Graphical Abstract: figures/make_ga.py → graphical_abstract.{pdf,png} (1735×860 px @300dpi,
  schematic single panel: 34 classes → 4 channels → 3 result cards (byte impossibility layer
  0.0744 / length primary channel / structure fingerprint) → release banner; blue/grey/red/orange
  semantic palette). Spec fix: the first landscape draft (2.02:1) violated the current generic
  page's "same ratio as 1328×531" rule — remade at 2.492:1 (1687×677 px ≥1328×531, 300 dpi,
  fixed-canvas export to avoid tight-bbox ratio drift); the portrait 531×1328 wording is the
  legacy journal-template figure.
- Cover letter (cover_letter.md): timeliness (IR 8547: deprecation 2030 / disallowed 2035,
  RSA/ECDSA/EdDSA), reproducibility (38-case audit log + frozen env/seed + reproduction bounds),
  scope fit (audit / forensics / migration monitoring); 5 suggested reviewers (Memon NYU /
  Frank Li UNSW / Yu Yu SJTU / An Wang BIT / Lashkari UNB), affiliations verified via
  NYU/UNSW/SJTU/pure.bit/UNB pages; emails to be filled in by the authors; no shared affiliation,
  authors must self-check for collaborations within three years.
- Build fix: conv() now escapes & → \& (the CRediT "review & editing" had caused a misplaced
  alignment tab).
- Adjacent fix (data-checked): two "head-48B 0.884" spots in §1/§2 → 0.883 and the §2
  "truncation to 25% collapses to 0.54" → 0.548 — the frozen s1_formal_summary.json holds
  head48=0.88268, trunc25=0.548 (§5.4 and Table 4 already say 0.8827/0.548); the old values were
  pre-5-seed stale roundings.
- Computation posture: no new numbers were needed this round — nothing retrained, nothing
  changed; cover letter/Highlights/GA quote frozen result files only. Note: frozen model weights
  were not saved locally (the rental host kept per-seed metric snapshots only); if a later
  "test-set resampling + frozen-model inference" revalidation is required, the weights must first
  be recovered in the frozen torch 2.9.1+cu128 environment (per the user's no-retrain constraint:
  extract from the rental host, or accept a one-time re-freeze with weights archived), with
  E-norm result files (env fields, seed records) as usual.
- GfA verification: the C&S-specific page is unreadable from this environment (ScienceDirect
  403; Wayback/archive.today unreachable; a WHU mirror is the 2014 edition) — the research
  report therefore marks every item VERIFIED / generic-Elsevier / UNKNOWN honestly, with no
  fabrication; the item-by-item list and open items live in submission_checklist.md
  (citation style: an indexed GfA snippet suggests author–year wording, mutually exclusive
  with numbered style — flagged for author confirmation; the current numbered style matches
  published C&S articles and is compliant at submission).
- Acceptance: 43 pages, 0 errors, 0 undefined; continuous line numbers; endmatter renders
  (CRediT at line numbers 1045–1048, Funding at 1060–1062, «REPO_URL» visible).

## #39 §6 padding-design subsection + Table 6 (internal review decision, 2026-09-20)
- Offline analysis exp_padding_design.py (--verify): reads only data/ and
  results/s2s3_formal.json, modifies no frozen file; no retraining, no new models.
- Protocol gate: the §5.3 frozen protocol (50 Monte-Carlo draws, symmetric randomized
  tie-breaking, seed 2025, 1-NN seeds (42,123,2024), null band 10×seed42) is first replayed on
  the ORIGINAL lengths and must match results/s2s3_formal.json bit-exactly at all five levels
  (β 0.9260/0.8824/0.7647/0.2938/0.1466 all reproduced) — old and new numbers are comparable by
  construction; any mismatch exits nonzero.
- (a) 4096-grid padding cost (ceil(L/4096)·4096): overall inflation 1.671×; per-class 1.00–85.33
  (median 2.49; worst ed25519_pkcs8 48B→4096B = 85.3×); 5 padded atoms
  {4096, 8192, 16384, 20480, 32768}.
- (b) β(G) after padding (same protocol): ladder 46/31/26/10/5 atoms → 5/5/5/4/2;
  β′ 0.1469/0.1469/0.1469/0.1176/0.0593 (exact-level = atom-count bound 5/34≈0.147); measured
  1-NN′ 0.0979/0.0979/0.0979/0.0587/0.0077 vs null′ 0.0111±0.0015/0.0111±0.0015/
  0.0111±0.0015/0.0113±0.0010/0.0088±0.0008 → z = 58.8/58.8/58.8/46.4/−1.4 (before 467/616/500/70/17):
  grid padding FLATTENS but does not eliminate the length channel; the residue is block-count
  identity.
- Uniform-max sensitivity point (32,768 B): inflation 8.263×; β′ = 1/34 = 0.0296 at every level
  (one atom = chance; measured z = −3.7) — the only design point that fully eliminates the
  length channel.
- (c) The structural channel is untouched by either padding: the content fingerprint (§5.4:
  intact 0.9997, OID erasure 0.9998/0.9998, windowed 0.55–0.85; §5.7 disorder bounds 30.1%/62.1%)
  depends only on content encoding; DER canonicalization can at best erase the OID region the
  classifier never needed. Framing: "quantitative starting point for design trade-offs", not a
  complete defense.
- In the paper: new §6 subsection "Implications for leakage-resistant format design" + Table 6
  (tables_formal.md + build_tail.py spec/renumber/label).
- Evidence: results/padding_design_formal.json (env/seed records, gate field, per-class rows,
  three ladders).
- Acceptance: --verify rerun passes (gate all True; env.no_training=True /
  frozen_files_modified=False); 44 pages, 0 errors, 0 undefined, 0 missing characters;
  the §6 subsection and Table 6 render; U+2032 primes missing from ec-lmr fonts → ASCII
  apostrophes in text.

## #40 Class-distribution mismatch sensitivity (internal review decision, 2026-09-20)
- Design: training stays balanced (300/class, frozen protocol v2.2); three test priors —
  uniform / skew80_20 (the 11 classical classes RSA/ECDSA/Ed25519/AES carry 0.80, the 22 PQ
  classes plus the urandom control share 0.20, equal within groups) / skew95_5 (0.95/0.05);
  C_len (1-NN) and C_bytes (rf, P1, 170-dim stats features), 5 seeds each (E14 [42,123,2024,7,99]);
  both aggregates reported: macro-F1 and the prior-weighted W = Σ p_c F1_c.
- Frozen-replay gate: the local rerun of the frozen protocol is compared per seed against the
  rental_snapshot frozen JSONs — C_len 5/5 exact (0.9262, |Δ|≤1e-6); C_bytes 5/5 within tolerance
  (0.2799/0.2803/0.2863/0.2826/0.2749, |Δ|≤0.002; local sklearn 1.9.0 vs rental version
  difference filed). Any mismatch exits nonzero.
- Deterministic W (frozen per-class F1s re-weighted directly, no sampling): C_len 0.9262 → 0.9455
  → 0.9516; C_bytes 0.2808 → 0.4237 → 0.4686 — under a classical-dominated prior the byte
  channel's deployment aggregate rises by half (classical per-class F1 ≈ 0.48 vs PQ-only ≈ 0.19),
  while the length channel stays at ceiling for both groups (classical ≈ 0.95; PQ-only ≈ 0.95).
- Sampled runs (5 seeds, mean±SD): C_len 80/20 macro 0.9379±0.0003 / W 0.9744±0.0006 (vs the
  exact 0.9262/0.9455 — the upward drift comes from deterministic 1-NN tie-breaking making
  tie-class F1s composition-dependent, the §5.3 mechanism re-appearing, +0.012/+0.029); C_bytes
  80/20 W 0.4586±0.0074, 95/5 W 0.5214±0.0085 (vs the exact 0.4237/0.4686 — upward bias from
  small-sample F1 estimation on the down-weighted classes, n ≈ 89–190). Both estimation effects
  are discussed explicitly in the text (user acceptance point).
- In the paper: new §5.12 subsection + Discussion paragraph "Closed-set, balanced-prior caveat";
  framing: "the deployment aggregate is W; macro-F1 is prior-blind per-class competence;
  conversions should use the released per-seed per-class F1s".
- Evidence: results/prior_skew_formal.json (env/seeds/prior definitions/gate/per-seed/
  deterministic cross-check; no training beyond frozen-protocol replay).

## #41 §5.2 slide50 self-contradiction fixed + per-class attribution (raised by the user, 2026-09-20)
- The user pointed out that §5.2's "z ≤ 5.9 — no more separated than the intact P1 value itself,
  z = 2.7" is self-contradictory (5.9 > 2.7 under the z-vs-null-SD convention). Confirmed; fixed.
- Per-class attribution experiment exp_slide50_attribution.py: exact replication of the
  exp_bytes_s1.py slide50 pipeline (damage/window/features/CV/classifier configs), frozen-macro
  gate |Δ|=0 (10/10 exactly).
- **The ECDSA-driver hypothesis is refuted by the data**: slide50 per-class F1 (5-seed means)
  is led by mldsa44_sig (rf/hgb 0.1872/0.1803), ECDSA only second (0.1055/0.0945), the rest
  ≤0.08. The 15-class macro excluding ECDSA is 0.0754±0.0031 (rf) / 0.0782±0.0047 (hgb) vs the
  16-class null centers 0.0602±0.0034/0.0598±0.0025 → z ≈ 4.5/7.4, still well above null — the
  residue is distributed signature-class structure, not an ECDSA artefact.
- The z relationship explained: slide50's F1 magnitudes (0.0723/0.0746) are comparable to the
  intact P1 value (0.0744); the larger z (5.9/3.5 vs 2.7) comes only from the tighter slide50
  null band (SD 0.0034/0.0025 vs 0.0042), not from larger separation.
- Mechanism (linked to §5.1): slide50 keeps the object's second half — for ML-DSA-44 that is the
  high-index ẑ coefficient region (rejection-sampling-shaped distribution; §5.1 documents its
  serial-test deviations), for ECDSA the s-value tail — so signature representation-level
  structure survives in attenuated form.
- Two parts of the user's suggested wording were not adopted verbatim (data-checked):
  (1) "fully attributable to the ECDSA class" does not hold (per-class evidence above);
  (2) "two orders of magnitude below any structural-channel reading" is off — byte-channel
  slide50 (0.072–0.075) is 4.2× below the weakest structural reading (trunc75 0.3139) and
  13.4× below intact (0.9997); the text uses the "comparable F1 + tighter null" framing instead.
- In the paper: the §5.2 parenthetical replaced (md+tex); a historical correction note added to
  audit #30.
- Evidence: results/slide50_perclass_attribution.json (gate/per-seed/per-class/15-class macro/
  null reference).

## #42 primitive-group 60ep budget tier (internal review decision, 2026-09-20)
- Environment: a rented V100 host (user-provided); torch 2.9.1+cu128 /
  Tesla V100-SXM2-16GB / cuda 12.8 — the same lineage as the frozen prim-group 30ep tier;
  numpy 2.2.5 + sklearn 1.9.1 installed remotely (Python 3.11.12).
- Config identical to the frozen runs: 16 primitives × 300, 1024B windows, P1/P2, the §5.5 CNN,
  batch 128, 5 seeds (E8 per-seed window RNG), the only variable being --epochs 60;
  2 protocols × 5 seeds = 10 jobs, all completed.
- Two runner defects fixed en route (no frozen-semantics change, commented in code):
  (1) train_baselines.run_one's `with open(res_path)` referenced an undefined variable left over
  from an early edit (NameError; the frozen runs never took this path) — removed, json.dump
  writes out_f directly (same semantics as the rental_snapshot frozen runs);
  (2) the historical double-underscore tag accident ("__e60") recurred — the runner now passes
  "e60" and train_baselines adds the underscore → single-underscore names.
- Same-machine reproduction check (--verify prim60): cnn_p1_seed7 |Δ|=0.0122, cnn_p2_seed99
  |Δ|=0.0160, both ≤ the 0.026 bound (CNN envelope from cudnn.benchmark/TF32 nondeterminism) ✓.
- Results (5 seeds, E14; 16-class macro ± seed SD, SE in parens):
  P1 0.0547 ± 0.0054 (SE 0.0024), z vs null band = −2.0 (below the null center);
  P2 0.1056 ± 0.0040 (SE 0.0018), z = +10.1 (lifted by ECDSA);
  non-ECDSA 15-class mean 0.0486 ± 0.0045 (P1) / 0.0478 ± 0.0042 (P2), both < chance 0.0625;
  ECDSA 0.1468 ± 0.0450 (P1) / 0.9715 ± 0.0051 (P2).
- **Honestly reported finding (per the user's acceptance rule: a finding, not a failure)**: 60ep
  surfaces the first seed-stable non-ECDSA per-class emergences — P2 rsa2048_ct 0.1233 ± 0.0182
  (SE-based z = 7.5), P1 mldsa44_sig 0.0956 ± 0.0213 (z = 3.5) — and both sit inside
  Proposition 1's EXPLICIT exclusion set (OAEP is one-way, not pseudorandom; ML-DSA is a
  signature class). The other above-chance per-class values (ed25519 / slhdsa_128f /
  mlkem1024_ct / mldsa65_sig) stay within 2×SE and do not constitute stable escapes.
- Two adjacent corrections to the 30ep sentence (data-checked): (1) the P2@30ep non-ECDSA mean
  0.036 → 0.0349 (recomputed from the frozen e30 per-class values); (2) "P1@30ep every class
  stays below chance" did not hold — mldsa44_sig 0.0782 ± 0.0355 (within 1×SE), restated
  honestly.
- In the paper: §4.4 point 2 rewritten wholesale (30ep corrections + the 60ep tier + the
  exclusion-set explanation); contribution (3) adjusted: "proving the layer is budget-robust in
  aggregate (… the only seed-stable per-class emergences … sit inside the proposition's explicit
  exclusions)" — the user's pre-authorized "report honestly and adjust contribution (3)" path
  executed.
- Evidence: results/cnn_{p1,p2}_seed{7,42,99,123,2024}_g_prim_e60.json (10 files),
  results/prim60_summary_formal.json (env assertions torch 2.9.1+cu128/V100 all pass;
  per-class mean/SD/SE; escape and stable-escape lists; verify record).

## #43 Full data-reasonableness audit + byte-level code audit (internal review decision, 2026-09-20)
- Data audit exp_data_audit.py (read-only; 215 results/*.json), four layers:
  L1 JSON hygiene all pass (parseable, no NaN/Inf, F1 within [0,1]);
  L2 structural consistency all pass (macro==mean(per_class) Δ<1e-9, SE=SD/√n, 5-seed groups
  complete);
  L3 headline cross-check 110+ claims all pass — S2 ladder, β(G) five levels (round(z) exactly
  reproduces 467/616/500/70/17), S1 eleven cells, prim P1/P2/ECDSA 0.2508/Ed25519 0.0713/
  15-class 0.0626, mixed-34 six baselines, budget grid e30/e60, prim60, C_align six values,
  open-set AUROC 0.8307/0.8064, TLS 0.9262, tools seven values, B4 five values, transfer eight
  values, and the padding/prior-skew/slide50 new frozen artifacts;
  L4 seed-outlier scan (all 5-seed groups, >3σ leave-one-out): 17 flagged items.
- Flagged-data verification (per the user's rule that flagged data must come with a verification
  script): results/verify_flags/flag_01_bilstm_p1_seed42.py +
  flag_02_group_seed_outlier.py (parameterized 4-step: integrity / internal consistency /
  seed context / statistical framing). **17/17 AUTHENTIC**: 13 identical field-by-field to the
  rental_snapshot frozen copies; the 4 s1 local-only files have macro==mean(per_class) Δ=0; every
  flagged value is seed-level variation with full-set z < 2σ (the 8.7σ etc. leave-one-out
  readings are σ-shrinkage artifacts: bilstm_p1 seed42 full-set z=1.94, 15ep 0.0352 → e30 0.0251
  → e60 0.0216 regressing to chance with budget). **No frozen value needs correction.**
- Dataset integrity: 34 classes × 300 = 10,200 objects; counts / nonzero sizes / len_unique all
  match meta, 0 issues.
- Incidental positive evidence: five rf_p1_*_g_pk8 files differ from the rental copies only in
  the `sec` field (local reruns); macro/per-class/confusion are bit-identical → new evidence of
  rf cross-environment bit-exact reproducibility.
- Two audit-script convention fixes (not data issues): the S2 ladder mapping is
  inner→rand255→rand1024; z uses round, not trunc.
- Code audit (independent static review of the 10 new/modified scripts): 1 high, 5
  medium, 9 low. Disposition: H1 (prim60 verify had no on-disk backup → .bak before delete +
  finally-restore) fixed; M1 (verify no rollback on violation → restore from snapshot) fixed;
  M2 (verify now requires CUDA or aborts) fixed; M3 (slide50 attribution 15-class macro
  methodology biased → labels-only recomputation + 15-class null band; the §5.2 sentence number
  will be back-filled from the rerun) fixed; M4 (atomic write + checkpoint validation) fixed;
  M5 (Table 6 has no generator) filed (maintained manually in tables_formal.md); L3/L4/L5/L6/L7
  fixed; L1/L2/L8/L9 filed. Verified: the new scripts write only their own new files, frozen
  protocol replays match, env assertions match. Details in 代码审计报告_20260920.md round 2.
  M3 back-fill (2026-09-24): under the labels-only methodology the 15-class macro is rf
  0.0700±0.0026 / hgb 0.0733±0.0044 vs the 15-class permutation null 0.0684±0.0043 /
  0.0676±0.0064 → z = 0.4/0.9 (at chance); the old mask-based values (0.0754/0.0782, "≈4–7 SD")
  were inflated by the two-way row removal, and the §5.2 sentence has been rewritten: "excluding
  ECDSA leaves the 15-class macro at chance … the ML-DSA-44 per-class elevation is offset by
  sub-chance classes in the aggregate". Per-class conclusions unchanged (mldsa44 0.1872/0.1803
  leads, ECDSA second 0.1055/0.0945); gates 10/10 Δ=0.

## #44 §5.5 "2×" residue and broken-parenthesis sentence rewritten (raised by the user, 2026-09-24)
- The user pointed out that §5.5 read "The budget ablation (**2× budget grid (15/30/60 epochs,
  Fig. 7): …" — the "2×" is residue from the old "2×-epoch ablation" wording (a sed leftover from
  audit #33's rewrite), and the sentence opens two parentheses that never close. Confirmed.
- Fix (md + tex head in sync):
  (1) "The budget ablation (2×\nbudget grid (15/30/60 epochs, Fig. 7):" →
      "The budget grid (15/30/60 epochs, Fig. 7):" (naming consistent with §2/§4.4/Fig. 7;
      parenthesis balance re-checked);
  (2) the same residue in the §4.2 data-protocol paragraph, "the 2×-epoch ablation uses
      --epochs 30" → "the budget-grid ablation uses --epochs 30/60".
      (2026-09-24 user follow-up: the sentence sits in §4.2, not §4.5; and per the user's
      final wording it now reads "the budget ablation sweeps --epochs {15,30,60}", with
      \{15,30,60\} in the tex so the literal braces render.)
- Whole-corpus scan: the only remaining "2×" is §5.7's "2×2 grid (rf300, 5 seeds)" — a
  legitimate experimental design (2 head conditions × 2 container groups), kept.
- Acceptance: 46 pages, 0 errors; both new sentences render, the broken string is gone.

## #45 §3.2 "10,200 in total" referent ambiguity rewritten (raised by the user, 2026-09-24)
- The user pointed out that §3.2 read "…test-only material that never enters training,\n
  10,200 in total." — the "10,200" follows the 900-object transfer-set sentence and reads as if
  it refers to the transfer set. Confirmed.
- Rewritten per the user's final wording (md + tex head):
  "Each class contributes exactly 300 objects (norm E4: class balance); the formal set totals
  34 × 300 = 10,200 objects. A 900-object cross-implementation transfer set (native OpenSSL
  3.5 ML-DSA/ML-KEM, §5.10) ships alongside as test-only material that never enters training."
- Acceptance: 46 pages, 0 errors; the new sentence renders and the ambiguous string is gone.

## #46 §5.10 "frozen … retrained unchanged" contradiction rewritten (raised by the user, 2026-09-24)
- The user pointed out that "The frozen 18-class container pipelines were retrained unchanged"
  is self-contradictory (the pipelines were retrained under the frozen configuration, not frozen
  themselves). Confirmed.
- Rewritten per the user's final wording (md tail; tex rebuilt by build_tail):
  "The 18-class container pipelines were retrained under the frozen configuration (§5.4)
  and evaluated on this set: …".
- Acceptance: 46 pages, 0 errors; the new sentence renders, the contradictory string is gone.

## #47 §5.9 closed-set baseline qualification (raised by the user, 2026-09-24)
- The user pointed out that §5.9's "P1 0.3689 → 0.3793; P2 0.5446 → 0.5474" are closed-set
  baselines of the 26-class open-set models — a different scope from §5.5's 34-class numbers —
  and suggested a clarifying qualifier. Adopted.
- Data verification (before editing): P1/P2 closed_f1 means 0.3689/0.5446 ✓
  (open_set_formal.json, 5 splits); the arrow endpoints 0.3793/0.5474 are the MSP baseline's
  20%-rejection f1_decay per-seed means (the 0.05/0.1 tiers are 0.3715/0.3737 and 0.5449/0.5453),
  provenance matched.
- In the paper (md tail; tex rebuilt by build_tail):
  (1) §5.9: "leaves the closed-set macro-F1 of the 26-class open-set models essentially intact
  (…, the 20% rejection endpoint of MSP)";
  (2) Table 4's open-set row gains "of the 26-class open-set models".
- Table-structure issue found and fixed en route: Table 4's open-set row had in fact NEVER
  been compiled (after the #34 tail rebuild, tables_formal.md lacked the row while the md mirror
  had it — the two sources had diverged). Restoring the long row overflowed the float by 261pt
  and clipped content; disposition = Table 4 converted to table* (full width) + row compression
  + finally moving the complete open-set numbers into the table note (the note sits outside the
  float, so no height limit); the float-overflow warning is gone. The note carries the full
  numbers with the 26-class qualifier, and §5.9 prose carries the qualifier plus the 20%
  endpoint provenance.
- Acceptance: 46 pages, 0 errors, 0 float-overflow warnings; qualifier and note render.

## #48 Title simplification (proposed and confirmed by the user, 2026-09-24)
- The user noted the three stacked modifiers (Algorithm-Level / Observable Side-Channel /
  Representation-Level) and proposed "Quantifying Representation-Level Leakage of Post-Quantum
  Cryptographic Objects", leaving the side-channel definition to the abstract. After analysis the
  proposal was recommended (side-channel carries a strong default meaning of key-recovery attacks,
  so the title itself invited misreading; Algorithm-Level information survives in §1/keywords/
  contribution (1); the new title matches the keyword "representation-level identification" and the
  §4.1 definition) and the user confirmed.
- In the paper: \title in paper.tex, the md first line, and the cover-letter title line; the
  abstract's defensive sentence ("Herein, 'side channel' means …") and the in-text framework name
  "observable side channels" (§4.1) stay unchanged.
- History: this reverses the #35 decision "keep Algorithm-Level in the title" (reversal proposed
  by the user themselves).
- Acceptance: 46 pages, 0 errors; the PDF title renders.

## #49 §4.4 30ep/60ep consistency verification (raised by the user, 2026-09-24)
- The user reported a contradiction: the old text claimed "every class stays below chance" at
  P1@30ep while the 60ep paragraph states ML-DSA-44 already reached 0.0782±0.0355 at P1@30ep.
- Verification: the old sentence no longer exists in the current tex/PDF (#42 already rewrote it:
  "P1@30ep overall 0.0295, with ML-DSA-44 the only class whose seed-mean exceeds the chance
  line, 0.0782±0.0355 — within one seed SE of chance"); the 60ep "below chance" claim refers
  only to the 15-class aggregate mean (0.0486/0.0478). The two statements are consistent; no
  remnant of "every class stays below chance" remains anywhere.
- The user's own paper.tex edit ("the exclusions prove necessary", previously "earn their keep")
  is kept, and the md mirror synced to the same wording.
- Acceptance: 46 pages, 0 errors; the two §4.4 sentences verified in the PDF.

## #50 OID-baseline count correction 12→11 (raised by the user, 2026-09-24)
- The user pointed out that §5.11 claims "12 algorithm OIDs" while only 11 are enumerable.
  Confirmed: exp_tools_baseline.py's OIDS dict holds exactly 11 entries — mldsa44/65/87,
  mlkem512/768/1024, slhdsa128s/256s, rsa (rsaEncryption), ec (ecPublicKey/SEC1), ed25519
  (1.3.101.112); these 11 distinct OID values cover all 18 container classes (the 7 certificate
  classes reuse the same values, disambiguated by TBS/format markers). The historical "12"
  probably counted the prime256v1 curve OID as an algorithm OID.
- Corrected: §5.11 prose (md tail → rebuilt tex), the exp_tools_baseline.py header comment
  (line 5; the in-code env string at line 153 already said 11), the frozen
  results/tools_baseline_formal.json env description (numbers untouched; metadata only), and
  correction notes on the audit #31 records (zh+en).
- Acceptance: the rebuilt PDF's §5.11 reads 11; F1 values unchanged (0.0555/0.4443/1.0000/
  0.5000/0).

## #51 Release-package preparation (before the GitHub upload, user request, 2026-09-25)
- AI-marker removal: a full scan of the upload set (py/md/json) finds zero occurrences of
  claude/deepseek/LLM/subagent or similar ("subagent" wording in the shipped logs was replaced
  by "independent review"; "length proxy" is statistical terminology and stays).
- Comment tidying: 19 script headers trimmed to 1-3 lines (protocol-critical constants and
  audit references kept); inline narrative comments in train_baselines shortened.
- Path portability: all hardcoded /home/shen and /root/pqc paths replaced with __file__-relative
  BASE; liboqs/SSH external paths moved to environment variables; nist_battery.py vendored into
  host_package/; the wild false-positive certificate and the B4 cross-library raw JSONs vendored
  into the repo (wild/raw/ct_log/, data/b4_crosslib_final/); rental_snapshot references repointed
  to results/ (the 5 mixed-34 rf_p1 frozen seeds copied into results/).
- Credential hygiene: the full scan finds no password/private-key/SSH strings (rental host names
  neutralized).
- Added: LICENSE (MIT), data/LICENSE.md (CC BY 4.0), README.md.
- Adjacent fix: the user's edited paper.tex branch had reverted the audit count to 48 (the log
  holds 50); synced to 50; rebuilt at 45 pages, 0 errors.

## #52 Workflow handover: paper.tex becomes the single source (user decision, 2026-09-25)
- The user reorganized paper.tex/supplementary.tex and completed both Zenodo DOIs
  (dataset 22950765, CC BY 4.0; code snapshot 22952070, MIT), and delegated all further
  management to the assistant.
- New workflow: paper.tex is the single source of truth; build_tail.py is deprecated
  (aborts immediately to prevent accidental runs); paper_manuscript_en.md is marked
  deprecated (archive only); verify_paper_consistency.py is the new guard (audit count /
  bibliography closure / submission-file counts; read-only).
- Handover acceptance: 42 pages, 0 errors, 0 undefined; 50 bib entries all cited, 0 orphans;
  both Zenodo records verified via API (title/creators/license/date).

## #53 Figure handover: the seven figures redrawn externally (user decision, 2026-09-25)
- The user had an external designer redraw the seven in-paper figures and copy them back into
  figures/ (fig1-7 replaced; the graphical abstract untouched).
- Handover checks: all vector with embedded fonts (fig4/fig5 contain heatmap raster blocks,
  which is normal); filenames match the tex references; textually checkable numbers match the
  frozen values (fig1 z=17/70/500/616/467; fig7 tree baselines RF 0.281/0.290, HGB 0.413/0.424,
  chance 1/34=0.029; fig2 groups and 11 cells present); curve values are vector paths and, per
  the agreement, results/ JSONs remain the only numeric source of truth (the redrawn figures are
  exempt from the figs_qa text checks).
- make_all_figs.py is deprecated with an abort guard (protects the redrawn PDFs); figs_qa.py no
  longer auto-redraws.
- Acceptance: recompiled with 0 errors; verify_paper_consistency ALL PASS.

## #54 Two key citations added (raised by the user, 2026-09-25)
- (1) PQClean citation missing: mentioned 4x in the body plus 3x in caption/table as a key
  control but absent from the bibliography — added @misc{pqclean} (Kannwischer/Rijneveld/
  Schwabe/Stebila/Wiggers + contributors, the project's canonical attribution, 2019), cited at
  the first body mention (§5.2 PQClean leg); the abstract stays citation-free (convention).
- (2) Missing closely-related work: Mallick et al., "Classifying Implementations of
  Cryptographic Primitives and Protocols that Use Post-Quantum Algorithms" (arXiv:2503.17830
  v4, 2025) — added @misc{mallick2025classifying}, with a two-sentence distinction after the
  PQClass sentence in Related Work: implementation behavior vs. representation level, detection
  accuracy vs. per-channel null-band bounds, complete protocol flows vs. carving/encryption/
  telemetry-constrained objects.
- Acceptance: 52 bib entries all cited, 0 orphans, 0 undefined; 42 pages, 0 errors; guard
  ALL PASS.

## #55 Three lineage citations added (raised by the user, 2026-09-25)
- (1) Shamir & van Someren 1999 (FC/LNCS 1648, pp. 118-124, DOI 10.1007/3-540-48390-X_9):
  a lineage sentence in the §2 carving paragraph (stored-key search → our S1 as its
  representation-level descendant).
- (2) Liberatore & Levine 2006 (CCS, pp. 255-263, DOI 10.1145/1180405.1180437 — note: the
  initially proposed DOI 1180417 was caught by Crossref as a different paper (Curtmola et al.)
  and corrected): a website-fingerprinting lineage sentence in the §2 traffic paragraph
  (packet-length statistics leak page identity; the privacy semantics of our S2 length channel
  inherit from that line).
- (3) Dyer et al. 2012 (S&P, pp. 332-346, DOI 10.1109/SP.2012.28): a sentence in the §6
  padding subsection (efficient padding defenses similarly fail to remove length information).
- All metadata Crossref-verified; zero experimental changes.
- Acceptance: 55 bib entries all cited, 0 orphans, 0 undefined; 43 pages, 0 errors; guard
  ALL PASS.

## #56 Weakened the inductive-bias claim + architecture choice explained (user, 2026-09-25)
- The user noted that §2's "first controlled evidence that ... inductive-bias-dependent" was
  over-strong: scalar BiLSTM failure on near-uniform long sequences is unsurprising, and the
  predecessor used 5 baselines including a Byte Transformer while this paper tests only
  CNN/BiLSTM — reviewers will ask about the architecture choice. Minimal path adopted
  (weaken + explain; no new experiments).
- Three edits: (1) §2 claim scoped: "…first controlled evidence, for cryptographic payloads,
  that the two depth architectures we test — a local-pattern CNN and a scalar-input BiLSTM —
  diverge at a frozen budget; … within the tested pair, not a claim over the architecture
  space." (2) §5.5 explains the choice (CNN = standard raw-byte baseline; BiLSTM =
  long-sequence recurrent control; the predecessor's Byte Transformer \cite{CipherBench} is
  outside the frozen grid — a deliberate scope decision). (3) Limitations gains: the deep
  architecture set is fixed by the frozen protocol; whether other families recover signal is
  left open.
- The stronger path (adding a Transformer tier: new GPU rental + new frozen tier) is recorded
  as a contingency for reviewer requests.
- Acceptance: 44 pages, 0 errors, 0 undefined; guard ALL PASS.

## #57 Full E1–E14 catalogue moved into the supplement (user, 2026-09-25)
- The user noted §4.5 only said the catalogue "ships with the release" (reviewers cannot see
  it) and located the frozen original (v2.4 experiment norms) in pqc_wave2.
- Cross-check: 11/14 items match current practice exactly; 4 partially matching items were
  reworded (E1 sweep → block-size grid {512,1024,4096}; E4 independence → held-out transfer
  set; E5 corpus-level holdout → transfer-set wording; E6 accuracy → macro-F1 primary plus
  group-fold; E10 short/long grouped reporting dropped), and two internal wave2 case-number
  references (#12/#13) were removed.
- Placement (user chose B): supplementary.tex gains section S-0 with the full 14-item list
  (enumerate); §4.5 now reads "The full E1–E14 catalogue appears in Supplement S-0".
- Acceptance: supplementary.pdf 3 pages, paper 44 pages, both 0 errors; S-0 renders with all
  14 items, no internal case references, and the §4.5 pointer in place.

## #58 AI-use declaration added (user-provided wording, 2026-09-25)
- Per Elsevier policy, a new section before References declares generative AI assistance:
  "Declaration of generative AI and AI-assisted technologies in the manuscript preparation
  process" (DeepSeek-V4-Pro for Chinese-to-English translation and LaTeX typesetting; the
  authors reviewed and take full responsibility). Wording as provided by the user.
- Acceptance: 44 pages, 0 errors, 0 undefined; the declaration renders.

## #59 Funding statement updated (user-provided, 2026-09-25)
- The user supplied the funding information: Academic Degrees and Graduate Education
  Development Center, MOE, grant ZT-2511417005 (project "ZhiTu WangAn: Intelligent
  Penetration Testing System Driven by Large Language Models and Knowledge Graphs for
  Cybersecurity").
- Disposition: the old no-funding Funding section was removed and the new Funding section
  placed immediately before the AI-use declaration (before References), as requested; the
  project title is set with LaTeX double quotes; submission_checklist B4 synced.
- Acceptance: 44 pages, 0 errors, 0 undefined; the grant number and project name render and
  the old no-funding sentence is gone.

## #60 Three typesetting fixes (2026-09-25, user-specified: markup/notation only, no values/content)
- Table 3 (Wild set): unbreakable long strings in narrow p{} columns overflowed and caused three
  overlaps (OID string vs. intact/OID-erased; domain vs. 1404 B; P = 0.18–0.28 vs. OID).
  Disposition: \allowbreak breakpoints inside the OIDs (2.16.840.1.101.3.4.3.19,
  1.2.840.113549.1.1.5) and the domain (vpn.dilithiumnetworks.com); column widths set to
  0.18/0.10/0.07/0.16/0.24/0.15 (sum 0.90). Acceptance: all strings present in the compiled PDF,
  pairwise text-span bbox overlap check = NONE.
- Figure 6 (λ ladder): x tick labels 0.0625 and 0.125 overlapped. Disposition: the 0.0625 tick was
  dropped (ticks now 0/0.125/0.25/0.5/1.0 plus the unlabeled wide-band offsets 1.06/1.12); new
  script figures/make_fig6.py (frozen ladder data via figs_data.get_ladder, assertions pass).
  Acceptance: PDF contains 0.125, no 0.0625, no overlaps.
- Figure 5 (length fold): the 489.6 pt figure was downscaled by width=\linewidth (390 pt) so its
  5.2 pt labels printed at ~4.3 pt. Disposition: figure resized to 390×344 pt (full text width),
  tick labels raised 4.2→7 pt; new script figures/make_fig5.py (row-normalized frozen
  nn_len_seed42.json matrix, pointwise identical). Acceptance: labels measure 6.91 pt ≥ 6 pt in
  the compiled PDF; vector output (fonttype 42). Caption unchanged and consistent with the figure.
- Table 4 (capability–leakage map):
  (a) "G=16/64" in C_struct×S3 (rounding step) collided with G = equivalence-class count in
      §5.3/Fig. 1 → renamed to "∆=16/64"; full-text search confirms G=16/64 is gone (the
      §5.3/Fig. 1 G is untouched).
  (b) C_bytes×S1 "z ≤ 1.1 / ≤ 5.9" labeled → "(trunc50 z ≤ 1.1; slide50 z ≤ 5.9)" (matches §5.8).
  (c) Cells reflowed into short semantic lines with \newline; long value chains (0.548/0.383/0.314
      etc.) got \allowbreak after each slash. Acceptance: all values/labels in place, no overlaps,
      G=16/64 cleared.
- Markup/notation only; no frozen number changed. 44 pages, 0 errors, 0 undefined.

## #61 Second external redraw of all seven figures (2026-09-26; GA untouched)
- All seven figure PDFs (fig1–fig7) replaced in place under the same filenames; the graphical
  abstract remains the make_ga.py output (60-case banner intact).
- Recompile acceptance: 43 pages (smaller figures), 0 errors, 0 undefined; Table 3/4 overlap
  checks still NONE.
- Per-figure programmatic QA against frozen anchors:
  · fig1 z annotations 17/70/500/616/467 = frozen ✓; fig7 RF 0.281 / HGB 0.290 = 0.2808/0.2903 ✓;
    fig4 ordering (four signature classes first) ✓; fig6 ticks 0/0.0625/0.125/0.25/0.5/1.0 spaced
    >= 26 pt, no overlap ✓; fig5 labels 6.5 pt x 390/388.8 ≈ 6.52 pt ≥ 6 pt ✓; fig2 "n=5 seeds"
    matches the frozen JSON (n=5) — the old figure's n=2 label was stale and is now corrected ✓.
- Open items (designer-side, awaiting the user's decision):
  (1) fig5: the leading 'a' of the two x-axis labels aes256gcm_ct_768/784 is clipped (label top
      357.5 pt > page 356.4 pt) — they render as es256gcm_ct_768/784;
  (2) fig5 has no axis titles (the previous version carried 'predicted (classes ordered by
      length)' / 'true');
  (3) all seven figures embed Type3 fonts (DejaVuSans, default fonttype 3) — Elsevier production
      is sensitive to Type3; recommend re-exporting with pdf.fonttype=42; fig6's x-axis label is
      missing the λ symbol ('signal density (class-token …)').
- Local fallbacks available: figures/make_fig5.py and make_fig6.py (frozen data, verified,
  with axis titles and λ) — adoption at the user's discretion.

## #62 Third external redraw of all seven figures (2026-09-26): all #61 items fixed, accepted
- The seven figure PDFs were replaced (08:47). All open items from #61 are cleared:
  (1) fig5's clipped leading 'a' is fixed (aes256gcm_ct_768/784 render in full, no label overflow);
  (2) fig5 axis titles restored (predicted (classes ordered by length) / true, 8 pt);
  (3) fonts upgraded Type3 -> Type0 (DejaVuSans subsets); fig6's x-axis λ restored.
- Per-figure QA against frozen anchors: fig1 z=17/70/500/616/467 ✓; fig2 n=5 seeds ✓ (matches the
  frozen JSON n=5); fig4 four-signature-class ordering ✓; fig5 labels 6.5 pt × 390/388.8 ≈ 6.52 pt
  ≥ 6 pt, axis titles in place, aes labels complete ✓; fig6 λ in place, ticks 0/0.0625/0.125/0.25/
  0.5/1.0 spaced ≥ 26 pt (no overlap), wide-band markers present ✓; fig7 RF 0.281 / HGB 0.290 /
  chance 0.029 ✓.
- Recompile: 43 pages, 0 errors, 0 undefined; Table 3/4 overlap checks NONE; guard ALL PASS.
- Note: figures/make_fig5.py, make_fig6.py and make_all_figs.py are historical scripts; the current
  seven figures are the designer's hand-managed files (do not run the scripts over them).

## #63 Historical figure-script cleanup (2026-09-26)
- Removed the obsolete figure toolchain from figures/: make_all_figs.py (retired guard version),
  make_fig5.py, make_fig6.py, figs_data.py, figs_qa.py, figstyle.py, gen_tables.py and
  __pycache__; also removed the recovery artifacts under /home/shen/tools/ (pycdc,
  make_all_figs_recovered.py).
- Kept: figures/make_ga.py (GA generator, still required by the consistency guard and the count
  chain); the seven figure PDFs and QA_交付报告.md. The seven PNG previews were re-exported from
  the final PDFs at 300 dpi so they match the shipped vectors.
- Acceptance: GA regenerates, verify_paper_consistency ALL PASS, paper recompiles with 0 errors.
