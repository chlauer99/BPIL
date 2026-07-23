#!/usr/bin/env python3
"""
compute_stats.py -- regenerates every statistic reported in the results of

    "BPIL: A Compact Intermediate Representation for LLM-Based
     Business Process Modeling" (Process Science)

from the raw evaluation score exports (Online Resource 1, `data/`).

--------------------------------------------------------------------------
INPUT DATA
--------------------------------------------------------------------------
The evaluation framework writes one CSV per (condition x quality dimension):

    data/
      XML/             zero-shot generation, BPMN 2.0 XML target
      untrained_BPIL/  zero-shot generation, BPIL target
      sft_BPIL/        BPIL target after LoRA fine-tuning
        syntactic quality.csv
        pragmatic quality.csv
        semantic quality.csv

Each CSV is semicolon-separated with decimal commas. Rows are the 105
evaluation items (first column = item id); the remaining columns are one
model each (raw run identifiers; `CANON` below maps them to the canonical
model names used in the paper). A cell holds the dimension score in [0,1]
of that model's output for that item, and is EMPTY when the output was
invalid (not tool-processable), so:

    validity(item, model, condition)
        := the item has a score in ANY of the three dimension CSVs
    conditional quality
        := mean score over the valid items of that run          (Tables 6-7)
    validity-adjusted quality
        := mean over ALL 105 items with invalid items scored 0
           == conditional mean x validity rate                  (Table 8)

--------------------------------------------------------------------------
STATISTICAL PROCEDURES (Section "Statistical analysis" of the paper)
--------------------------------------------------------------------------
* Validity contrasts .... exact two-sided McNemar test = binomial test on
                          the discordant pairs (scipy.stats.binomtest).
* Quality contrasts ..... two-sided Wilcoxon signed-rank test on the items
                          valid under BOTH compared conditions; effect
                          size = median paired difference.
* Multiplicity .......... Holm step-down within each pre-registered
                          family.  Confirmatory families contain ONLY the
                          stack-consistent contrasts:
                            - RQ2 zero-shot validity: 5 models (the two
                              Qwen3 zero-shot BPIL cells were produced on
                              a different inference stack and are
                              reported descriptively, flag "conf.");
                            - RQ3 fine-tuning validity: 4 models (same
                              Qwen3 exclusion);
                            - RQ3 vs-baseline validity: 6 models (all
                              stack-consistent);
                            - quality families as labelled in `main()`.
* Paired 95% CI ......... Wald interval on the paired difference of
                          proportions (validity vs baseline).
* Validity-adjusted ..... two-sided Wilcoxon over all 105 item scores;
                          percentile bootstrap CI of the mean difference,
                          B = 10_000 item-level resamples, fixed seed 0.
                          Two two-test Holm families: (i) fine-tuning
                          effect, (ii) versus the gpt-oss-120b XML
                          baseline.

--------------------------------------------------------------------------
OUTPUT
--------------------------------------------------------------------------
    stats.json   -- machine-readable dictionary with every reported value,
                    keyed by paper element (see MAPPING below).
    stdout       -- human-readable report; with --verify, a PASS/FAIL
                    check of 25 headline numbers against the values
                    printed in the paper (exit code 1 on any FAIL).

MAPPING (JSON key -> paper element)
    cells        -> Tables 6 and 7 (validity counts, conditional means)
    va_cells     -> Table 8 (validity-adjusted quality)
    rq2_val      -> Table 6 contrast columns + Sec. 7.2(a)
    rq2_quality  -> Sec. 7.2(b)
    rq3_val      -> Table 7 "ZS-SFT" column + Sec. 7.3(a)
    rq3_baseline -> Table 7 "vs. baseline" columns + Sec. 7.3(b)
    rq3_shift    -> Sec. 7.3(c) + Figure 3
    va_tests     -> Sec. 7.4 paired analysis

Usage:
    python scripts/compute_stats.py [--data-dir data] [--out stats.json]
                                    [--verify]

Determinism: the only stochastic step is the bootstrap; its RNG is
numpy.random.default_rng(0), so repeated runs are bit-identical.
Runtime: < 30 s on a laptop.  Dependencies: see requirements.txt.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------- constants
CONDS = {"XML": "XML", "BPIL0": "untrained_BPIL", "SFT": "sft_BPIL"}
DIMS = {"syn": "syntactic quality.csv",
        "prag": "pragmatic quality.csv",
        "sem": "semantic quality.csv"}

#: raw column-header fragment -> canonical model name (paper spelling)
CANON = {
    "gpt-oss-120b": "gpt-oss-120b", "gpt-oss-20b": "gpt-oss-20b",
    "Llama-3.1-8B": "Llama-3.1-8B", "llama-3.1-8b": "Llama-3.1-8B",
    "Qwen2.5-14B": "Qwen2.5-14B", "qwen2.5-14b": "Qwen2.5-14B",
    "Qwen3-14B": "Qwen3-14B", "qwen3:14b": "Qwen3-14B",
    "qwen3-14b": "Qwen3-14B",
    "Qwen3-30B-A3B": "Qwen3-30B-A3B", "qwen3:30b-a3b": "Qwen3-30B-A3B",
    "qwen3-30b-a3b": "Qwen3-30B-A3B",
    "Falcon-H1-7B": "Falcon-H1-7B", "falcon-h1-7b": "Falcon-H1-7B",
}

MODELS = ["gpt-oss-20b", "gpt-oss-120b", "Llama-3.1-8B", "Qwen2.5-14B",
          "Qwen3-14B", "Qwen3-30B-A3B", "Falcon-H1-7B"]
SFT_MODELS = [m for m in MODELS if m != "gpt-oss-120b"]  # 120b not tuned

#: the two zero-shot BPIL cells produced on a different inference stack
#: (ollama / q8_0 instead of vLLM / bfloat16); their ZS-involving
#: contrasts are descriptive only ("conf." in the paper's tables).
CONFOUNDED = {"Qwen3-14B", "Qwen3-30B-A3B"}
BASELINE = ("XML", "gpt-oss-120b")   # the large-model XML baseline

N_ITEMS = 105
BOOT_B, BOOT_SEED = 10_000, 0


# ------------------------------------------------------------------ loading
def load(data_dir: Path) -> dict:
    """Return {(condition, dimension, model): pd.Series of length 105}.

    Missing cells (invalid outputs) become NaN.  Raises if any expected
    file or model column is absent, or if a series is not length 105.
    """
    M = {}
    for cond, sub in CONDS.items():
        for dim, fn in DIMS.items():
            path = data_dir / sub / fn
            df = pd.read_csv(path, sep=";", decimal=",")
            df = df.set_index(df.columns[0])
            for col in df.columns:
                m = next((v for k, v in CANON.items() if k in col), None)
                if m is None:
                    continue
                s = pd.to_numeric(df[col], errors="coerce").reset_index(drop=True)
                if len(s) != N_ITEMS:
                    raise ValueError(f"{path}:{col}: {len(s)} rows, expected {N_ITEMS}")
                M[(cond, dim, m)] = s
    expected = ({("XML", d, m) for d in DIMS for m in MODELS}
                | {("BPIL0", d, m) for d in DIMS for m in MODELS}
                | {("SFT", d, m) for d in DIMS for m in SFT_MODELS})
    missing = expected - set(M)
    if missing:
        raise ValueError(f"missing series: {sorted(missing)}")
    return M


def valid(M, cond, m) -> pd.Series:
    """Boolean validity vector: item has a score in any dimension CSV."""
    return (~M[(cond, "syn", m)].isna()) | (~M[(cond, "prag", m)].isna()) \
        | (~M[(cond, "sem", m)].isna())


def va_scores(M, cond, m, dim) -> np.ndarray:
    """Validity-adjusted item scores: NaN (invalid) -> 0.0 (Sec. 7.4)."""
    return np.nan_to_num(M[(cond, dim, m)].to_numpy(float), nan=0.0)


# ------------------------------------------------------------------- tests
def mcnemar(a, b):
    """Exact two-sided McNemar: (n+ = a-only, n- = b-only, p)."""
    n_pos, n_neg = int((a & ~b).sum()), int((~a & b).sum())
    p = 1.0 if n_pos + n_neg == 0 else \
        stats.binomtest(n_pos, n_pos + n_neg, 0.5).pvalue
    return n_pos, n_neg, float(p)


def holm(pvals):
    """Holm step-down adjusted p-values (same order as input)."""
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p) - rank) * p[i]))
        adj[i] = running
    return adj


def wald_ci(a, b, n=N_ITEMS, z=1.959964):
    """Paired difference of proportions with Wald 95% CI (in shares)."""
    n_pos, n_neg = int((a & ~b).sum()), int((~a & b).sum())
    d = (n_pos - n_neg) / n
    se = np.sqrt(n_pos + n_neg - (n_pos - n_neg) ** 2 / n) / n
    return d, (d - z * se, d + z * se)


def wilcoxon_p(diff):
    """Two-sided Wilcoxon signed-rank p (ties/zeros per scipy default)."""
    return float(stats.wilcoxon(diff).pvalue)


def boot_ci_mean(diff, rng):
    """Percentile bootstrap 95% CI of the mean of `diff` (item resampling)."""
    idx = rng.integers(0, len(diff), size=(BOOT_B, len(diff)))
    means = diff[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


# ------------------------------------------------------------------- main
def main(data_dir: Path, out_path: Path, do_verify: bool) -> int:
    M = load(data_dir)
    R = {"config": {"n_items": N_ITEMS, "bootstrap_B": BOOT_B,
                    "bootstrap_seed": BOOT_SEED,
                    "confounded_zeroshot_bpil": sorted(CONFOUNDED)}}

    # ---- Tables 6/7 cells: validity + conditional means; Table 8 VA cells
    R["cells"], R["va_cells"] = {}, {}
    for cond in CONDS:
        for m in (MODELS if cond != "SFT" else SFT_MODELS):
            v = valid(M, cond, m)
            R["cells"][f"{cond}|{m}"] = {
                "valid_n": int(v.sum()),
                "validity": round(v.mean(), 4),
                **{d: (round(float(M[(cond, d, m)].mean()), 4)
                       if v.any() else None) for d in DIMS}}
            R["va_cells"][f"{cond}|{m}"] = {
                d: round(float(va_scores(M, cond, m, d).mean()), 4)
                for d in DIMS}

    # ---- RQ2: zero-shot representation effect on validity (Sec. 7.2a)
    R["rq2_val"] = {}
    conf_p = []
    for m in MODELS:
        n_pos, n_neg, p = mcnemar(valid(M, "BPIL0", m), valid(M, "XML", m))
        entry = {"n_plus": n_pos, "n_minus": n_neg, "p": round(p, 6),
                 "confirmatory": m not in CONFOUNDED}
        if m in CONFOUNDED:
            entry["note"] = "conf. (inference-stack change; descriptive)"
        R["rq2_val"][m] = entry
        if m not in CONFOUNDED:
            conf_p.append((m, p))
    for (m, _), h in zip(conf_p, holm([p for _, p in conf_p])):
        R["rq2_val"][m]["holm"] = round(float(h), 6)

    # ---- RQ2(b): conditional quality, XML vs BPIL, jointly valid >= 20
    R["rq2_quality"] = {}
    fam = []
    for m in MODELS:
        j = valid(M, "XML", m) & valid(M, "BPIL0", m)
        R["rq2_quality"][m] = {"joint_n": int(j.sum())}
        if j.sum() >= 20:
            for d in DIMS:
                diff = (M[("BPIL0", d, m)][j] - M[("XML", d, m)][j]).to_numpy(float)
                p = wilcoxon_p(diff)
                R["rq2_quality"][m][d] = {
                    "dmed": round(float(np.median(diff)), 4), "p": round(p, 6)}
                fam.append((m, d, p))
    for (m, d, _), h in zip(fam, holm([x[2] for x in fam])):
        R["rq2_quality"][m][d]["holm"] = round(float(h), 6)

    # ---- RQ3(a): fine-tuning effect on validity (4-model family)
    R["rq3_val"] = {}
    conf_p = []
    for m in SFT_MODELS:
        n_pos, n_neg, p = mcnemar(valid(M, "SFT", m), valid(M, "BPIL0", m))
        entry = {"n_plus": n_pos, "n_minus": n_neg, "p": round(p, 6),
                 "confirmatory": m not in CONFOUNDED}
        if m in CONFOUNDED:
            entry["note"] = "conf. (ZS baseline on different stack; descriptive)"
        R["rq3_val"][m] = entry
        if m not in CONFOUNDED:
            conf_p.append((m, p))
    for (m, _), h in zip(conf_p, holm([p for _, p in conf_p])):
        R["rq3_val"][m]["holm"] = round(float(h), 6)

    # ---- RQ3(b): vs the large XML baseline (6-model family, all consistent)
    base = valid(M, *BASELINE)
    R["rq3_baseline"] = {}
    ps = []
    for m in SFT_MODELS:
        n_pos, n_neg, p = mcnemar(valid(M, "SFT", m), base)
        d, ci = wald_ci(valid(M, "SFT", m), base)
        R["rq3_baseline"][m] = {
            "n_plus": n_pos, "n_minus": n_neg, "p": round(p, 6),
            "delta_pp": round(d * 100, 2),
            "ci_pp": [round(ci[0] * 100, 2), round(ci[1] * 100, 2)]}
        ps.append(p)
    for m, h in zip(SFT_MODELS, holm(ps)):
        R["rq3_baseline"][m]["holm"] = round(float(h), 6)

    # ---- RQ3(c): conditional-quality shift on jointly valid items (Fig. 3)
    R["rq3_shift"] = {}
    fam = []
    for m in ["Qwen2.5-14B", "Falcon-H1-7B"]:   # adequate paired support
        j = valid(M, "BPIL0", m) & valid(M, "SFT", m)
        R["rq3_shift"][m] = {"joint_n": int(j.sum())}
        for d in DIMS:
            diff = (M[("SFT", d, m)][j] - M[("BPIL0", d, m)][j]).to_numpy(float)
            p = wilcoxon_p(diff)
            R["rq3_shift"][m][d] = {
                "dmed": round(float(np.median(diff)), 4), "p": round(p, 6)}
            fam.append((m, d, p))
    for (m, d, _), h in zip(fam, holm([x[2] for x in fam])):
        R["rq3_shift"][m][d]["holm"] = round(float(h), 6)

    # ---- Sec. 7.4: validity-adjusted semantic quality, two 2-test families
    rng = np.random.default_rng(BOOT_SEED)
    R["va_tests"] = {"ft_effect": {}, "vs_baseline": {}}
    fams = {
        "ft_effect": [(m, va_scores(M, "SFT", m, "sem")
                       - va_scores(M, "BPIL0", m, "sem"))
                      for m in ["Qwen2.5-14B", "Falcon-H1-7B"]],
        "vs_baseline": [(m, va_scores(M, "SFT", m, "sem")
                         - va_scores(M, *BASELINE, "sem"))
                        for m in ["Qwen2.5-14B", "Falcon-H1-7B"]],
    }
    for fam_name, tests in fams.items():
        raw = []
        for m, diff in tests:
            lo, hi = boot_ci_mean(diff, rng)
            p = wilcoxon_p(diff)
            R["va_tests"][fam_name][m] = {
                "mean_diff": round(float(diff.mean()), 4),
                "ci95": [round(lo, 4), round(hi, 4)],
                "wilcoxon_p": p}
            raw.append((m, p))
        for (m, _), h in zip(raw, holm([p for _, p in raw])):
            R["va_tests"][fam_name][m]["holm"] = float(h)

    out_path.write_text(json.dumps(R, indent=1))
    print(f"[compute_stats] wrote {out_path}")

    # -------------------------------------------------------- verification
    if do_verify:
        c, vt, rb = R["cells"], R["va_tests"], R["rq3_baseline"]
        checks = [
            # Table 6/7 validity counts (per condition, valid / 105)
            ("XML gpt-oss-120b valid", c["XML|gpt-oss-120b"]["valid_n"], 74),
            ("XML Falcon valid", c["XML|Falcon-H1-7B"]["valid_n"], 12),
            ("BPIL0 gpt-oss-120b valid", c["BPIL0|gpt-oss-120b"]["valid_n"], 77),
            ("BPIL0 Qwen3-14B valid", c["BPIL0|Qwen3-14B"]["valid_n"], 0),
            ("SFT Qwen2.5 valid", c["SFT|Qwen2.5-14B"]["valid_n"], 80),
            ("SFT Falcon valid", c["SFT|Falcon-H1-7B"]["valid_n"], 80),
            ("SFT Qwen3-30B valid", c["SFT|Qwen3-30B-A3B"]["valid_n"], 45),
            # conditional means spot checks (Table 6)
            ("XML 120b sem", c["XML|gpt-oss-120b"]["sem"], .6018),
            ("BPIL0 Falcon sem", c["BPIL0|Falcon-H1-7B"]["sem"], .5884),
            # RQ2 Holm (5-model confirmatory family)
            ("RQ2 Falcon Holm", R["rq2_val"]["Falcon-H1-7B"]["holm"], .0153),
            ("RQ2 Qwen2.5 Holm", R["rq2_val"]["Qwen2.5-14B"]["holm"], .0977),
            ("RQ2 120b p", R["rq2_val"]["gpt-oss-120b"]["p"], .7428),
            # RQ3(a) Holm (4-model family)
            ("RQ3 Qwen2.5 Holm", R["rq3_val"]["Qwen2.5-14B"]["holm"], .0040),
            ("RQ3 20b p", R["rq3_val"]["gpt-oss-20b"]["p"], .5413),
            # RQ3(b) vs baseline
            ("vs-base Qwen2.5 delta", rb["Qwen2.5-14B"]["delta_pp"], 5.71),
            ("vs-base Qwen2.5 p", rb["Qwen2.5-14B"]["p"], .4296),
            ("vs-base CI low", rb["Qwen2.5-14B"]["ci_pp"][0], -6.04),
            ("vs-base CI high", rb["Qwen2.5-14B"]["ci_pp"][1], 17.47),
            # RQ3(c) shift
            ("shift Q sem dmed", R["rq3_shift"]["Qwen2.5-14B"]["sem"]["dmed"], .108),
            ("shift Q prag dmed", R["rq3_shift"]["Qwen2.5-14B"]["prag"]["dmed"], -.0750),
            ("shift F sem Holm", R["rq3_shift"]["Falcon-H1-7B"]["sem"]["holm"], .032),
            # Sec. 7.4 validity-adjusted
            ("VA FT Qwen2.5 mean", vt["ft_effect"]["Qwen2.5-14B"]["mean_diff"], .182),
            ("VA FT Falcon mean", vt["ft_effect"]["Falcon-H1-7B"]["mean_diff"], .2896),
            ("VA base Qwen2.5 Holm", vt["vs_baseline"]["Qwen2.5-14B"]["holm"], .70),
            ("VA base Falcon Holm", vt["vs_baseline"]["Falcon-H1-7B"]["holm"], .37),
            ("VA FT Qwen2.5 CI-lo", vt["ft_effect"]["Qwen2.5-14B"]["ci95"][0], .121),
            ("VA FT Qwen2.5 CI-hi", vt["ft_effect"]["Qwen2.5-14B"]["ci95"][1], .242),
            ("VA FT Falcon CI-lo", vt["ft_effect"]["Falcon-H1-7B"]["ci95"][0], .221),
            ("VA FT Falcon CI-hi", vt["ft_effect"]["Falcon-H1-7B"]["ci95"][1], .356),
        ]
        print(f"\n[verify] {len(checks)} headline numbers vs the paper "
              f"(tolerance: 2 units in the last printed digit)")
        bad = 0
        for name, got, want in checks:
            tol = 2 * 10 ** -min(_decimals(want), 4) if isinstance(want, float) else 0
            ok = (got == want) if tol == 0 else abs(got - want) <= tol + 1e-12
            print(f"  {'PASS' if ok else 'FAIL'}  {name:26s} got={got}  paper={want}")
            bad += (not ok)
        print(f"[verify] {'ALL PASS' if not bad else f'{bad} FAILURES'}")
        return 1 if bad else 0
    return 0


def _decimals(x: float) -> int:
    s = f"{x}"
    return len(s.split(".")[1]) if "." in s else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("stats.json"))
    ap.add_argument("--verify", action="store_true",
                    help="check headline numbers against the paper")
    a = ap.parse_args()
    sys.exit(main(a.data_dir, a.out, a.verify))
