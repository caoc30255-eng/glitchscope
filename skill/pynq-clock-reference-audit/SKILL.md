---
name: pynq-clock-reference-audit
description: Diagnose PYNQ clock inconsistencies across device references, software versions, clock trees, requests/readbacks and metadata. Use a platform-neutral rational clock-tree model or the tested Zynq-7000 raw adapter before changing clocks or RTL. New hardware needs a reviewed profile; outputs describe reference-clock and configuration derivations; configuration changes are a separate authorized task.
---

# PYNQ clock reference audit

Identify whether a displayed clock rate is a register-derived estimate using the wrong reference frequency. Preserve working hardware while investigating.

## Choose the device path

Read [generalization.md](references/generalization.md) for a new platform or a mismatch beyond the Zynq raw adapter. Use scripts/inspect_platform.py for software-only discovery and scripts/diagnose_clock_tree.py for normalized device/clock-tree facts. Do not assume that the tested Zynq MMIO map applies to other devices.

## Procedure

1. Separate API requests, API readbacks and rates derived from register configuration using a documented board reference. Attach the reference source and derivation chain to each conclusion; treat HWH/device-tree values as declarations.
2. Establish the board's **PS_CLK** reference from its schematic/manual. Do not substitute a PL oscillator, another board's PS clock or an assumed 33/50MHz constant. Record source and uncertainty.
3. Inspect installed PYNQ version and the live clock instance's reference value. PYNQ 2.7's Zynq default is 50MHz, but installed code may differ. Follow [workflow.md](references/workflow.md) if environment or clock-source interpretation is unclear.
4. Use an existing trusted snapshot, or explicitly authorized read-only collection with `scripts/collect_clock.py`. No Overlay download, setter, reset, SLCR unlock or test START is required. The collector refuses non-armv7l hosts before importing PYNQ.
5. Analyze the frozen snapshot offline with `scripts/audit_clock.py`, supplying the reference frequency and its source. Reject unstable samples, missing/invalid divisors, unsupported PLL states and inconsistent metadata. For qualified PLL bypass, obtain BOOT_MODE[4]; lock status is not a substitute for that strap.
6. Compare the resulting rate to the clock constraint in the **same implementation**. A failed hypothetical 150MHz STA does not establish that a board reporting150 actually runs150. Bind each frequency conclusion to its reference source and each STA result to the exact implementation and constraints.
7. Report the conclusion, formula, source artifacts and remaining unknowns. Do not silently rewrite old evidence or promote an untested firmware candidate.

## Preserve configuration

Do not automatically patch PYNQ or replace a numeric API setting. Correcting only a reference constant, or only a requested frequency, can change hardware divisors. An authorized calibration/configuration change is a separate task and must preserve the intended hardware frequency and account for all callers.

For GLITCHSCOPE the requested resolution was documentation only: keep the accepted environment and nominal150 setting, document approximately100MHz derived from the board reference and registers. This is a case-specific choice, not a universal recommendation.

## Evidence and reuse

- [README.md](README.md): commands, input/output and validation scope required by the competition package.
- [case_study.md](references/case_study.md): actual Navigator7020 incident, failed assumptions, read-only board outcome and limits.
- [workflow.md](references/workflow.md): PLL/divider decoding, environment troubleshooting and official references.
- `examples/navigator_snapshot.json`: user-provided board snapshot excerpt; not an invented synthetic measurement.

The original and hardened collectors have now run read-only on the current Navigator7020/PYNQ2.7 target; both register snapshots agree and BOOT_MODE was collected. The generic decoder was rerun offline against the new snapshot. Subsequent AX7010/PYNQ2.4 collection is recorded below; conclusions retain their reference-source and configuration derivation.


PYNQ2.4 exposes classmethod clock implementation ancestry; 2.7 exposes a cached instance. Use the collector resolver, retaining raw API type/style. v0.1.1 was collected on the current7020; the v0.1.2 compatibility revision has25 offline tests and awaits target2.4 collection. Do not count an unsupported-implementation failure as a cross-board pass.


## Subsequent cross-board evidence

v0.1.2 collection succeeded on the operator-identified AX7010/PYNQ2.4, including legacy classmethod reference extraction and matching raw snapshots. See examples/ax7010_pynq24_snapshot_excerpt.json and references/provenance.json. The DT declaration33333000Hz differs from configured33333333Hz by about10ppm; the strict offline auditor retains REFERENCE_EVIDENCE_CONFLICT. Retain the strict comparison and reference-source provenance independently of a PASS label. Earlier pending notes describe the prior revision.
