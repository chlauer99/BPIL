#!/usr/bin/env python3
"""
make_figures.py -- regenerates Figures 1-3 of

    "BPIL: A Compact Intermediate Representation for LLM-Based
     Business Process Modeling" (Process Science)

exactly as they appear in the manuscript.

--------------------------------------------------------------------------
FIGURES
--------------------------------------------------------------------------
Figure 1  (fig_footprint.pdf)
    Grouped log-scale bars: min / median / mean / max of the per-model
    token and character counts of the 105 evaluation models, full
    tool-emitted BPMN 2.0 XML vs BPIL, with the per-statistic reduction
    annotated.  The summary statistics are the corpus measurement
    reported in Sec. "Representational economy (RQ1)"; they were
    obtained by tokenizing the stored model pairs with the
    gpt-oss-120b tokenizer.  Re-deriving them requires the model corpus
    and that tokenizer (both in the data release); the constants below
    are the measured values and are kept here so that the figure is
    reproducible from this package alone.

Figure 2  (fig_validity.pdf)
    Slope chart: validity (share of the 105 items with tool-processable
    output) of each model across the three generation conditions
    XML zero-shot -> BPIL zero-shot -> BPIL fine-tuned, computed from
    the score exports via compute_stats.load().  Dashed line = the
    gpt-oss-120b XML baseline (.705).  gpt-oss-120b has no fine-tuned
    point.  The two Qwen3 zero-shot BPIL points are the operationally
    confounded cells (different inference stack); see the caption and
    Sec. "Inference infrastructure".

Figure 3  (fig_shift.pdf)
    Paired per-item quality change (fine-tuned minus zero-shot BPIL) on
    the jointly valid items of Qwen2.5-14B (n = 48) and Falcon-H1-7B
    (n = 25): one jittered dot per item and dimension, thick bar =
    median paired change, annotated with the unadjusted two-sided
    Wilcoxon p (Holm-adjusted values are in the paper text).

--------------------------------------------------------------------------
DETERMINISM AND STYLE
--------------------------------------------------------------------------
* The only randomness is the jitter in Fig. 3; its RNG is seeded (11),
  so output PDFs are visually identical across runs.
* Fonts: STIX (matplotlib built-in) with Type-42 embedding, so no
  system fonts are required.
* Colors: Okabe-Ito palette (color-blind safe).

Usage:
    python scripts/make_figures.py [--data-dir data] [--out-dir figures]

Runtime: < 15 s.  Dependencies: see requirements.txt.
"""
from __future__ import annotations
import argparse
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# reuse the loader + validity definition of the statistics script so the
# two scripts can never disagree about what the data mean
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_stats import load, valid, DIMS  # noqa: E402

plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix",
    "font.size": 9, "axes.linewidth": 0.6, "pdf.fonttype": 42,
})

#: Okabe-Ito palette, one fixed color per model (order = legend order)
MODEL_COLORS = {
    "gpt-oss-120b": "#56B4E9", "Qwen2.5-14B": "#D55E00",
    "Falcon-H1-7B": "#009E73", "Qwen3-14B": "#CC79A7",
    "Qwen3-30B-A3B": "#E69F00", "Llama-3.1-8B": "#0072B2",
    "gpt-oss-20b": "#000000",
}

# ------------------------------------------------------- Figure 1 constants
#: corpus footprint summary statistics (measured once from the 105 model
#: pairs with the gpt-oss-120b tokenizer; see module docstring)
FOOT_STATS = ["min", "median", "mean", "max"]
TOK_XML, TOK_BPIL = [3173, 7538, 8670, 42480], [718, 1629, 2104, 17389]
CHR_XML, CHR_BPIL = [2889, 7254, 8386, 42196], [434, 1367, 1820, 17105]


def fig_footprint(out: Path) -> None:
    """Figure 1: corpus footprint, XML vs BPIL (log-scale grouped bars)."""
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.55))
    panels = [(axes[0], TOK_XML, TOK_BPIL, "Tokens"),
              (axes[1], CHR_XML, CHR_BPIL, "Characters")]
    for ax, xml_v, bpil_v, title in panels:
        x, w = np.arange(4), 0.38
        ax.bar(x - w / 2, xml_v, w, color="#9dbcd4", edgecolor="#33506b",
               lw=.6, label="BPMN 2.0 XML")
        ax.bar(x + w / 2, bpil_v, w, color="#f0b27a", edgecolor="#8c4a12",
               lw=.6, label="BPIL")
        ax.set_yscale("log")
        ax.set_xticks(x, FOOT_STATS)
        ax.set_title(title, fontsize=9, pad=4)
        ax.set_axisbelow(True)
        ax.grid(axis="y", which="major", lw=.4, color="#dddddd")
        for xi, (a, b) in enumerate(zip(xml_v, bpil_v)):
            ax.annotate(f"{a:,}", (xi - w / 2, a), textcoords="offset points",
                        xytext=(0, 2.5), ha="center", fontsize=6.6,
                        color="#33506b")
            ax.annotate(f"{b:,}\n\u2212{100 * (1 - b / a):.1f}\u2009%",
                        (xi + w / 2, b), textcoords="offset points",
                        xytext=(0, 2.5), ha="center", fontsize=6.6,
                        color="#8c4a12", linespacing=1.05)
        ax.set_ylim(300, 260000)
    axes[0].set_ylabel("count (log scale)")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left",
                   handlelength=1.4)
    fig.tight_layout(w_pad=1.6)
    fig.savefig(out / "fig_footprint.pdf")
    plt.close(fig)


def fig_validity(M: dict, out: Path) -> None:
    """Figure 2: grouped bars, valid outputs / 105 per model x condition.

    Layout matches the manuscript figure: three bars per model
    (XML zero-shot, BPIL zero-shot, BPIL after LoRA SFT) with the
    absolute count printed on each bar, an "n/a" marker for the missing
    gpt-oss-120b fine-tuned cell, and a dashed reference line at the
    gpt-oss-120b XML baseline.
    """
    order = ["gpt-oss-120b", "gpt-oss-20b", "Qwen3-30B-A3B", "Qwen2.5-14B",
             "Qwen3-14B", "Llama-3.1-8B", "Falcon-H1-7B"]
    xlabels = ["gpt-oss-\n120b", "gpt-oss-\n20b", "Qwen3-\n30B-A3B",
               "Qwen2.5-\n14B", "Qwen3-\n14B", "Llama-\n3.1-8B",
               "Falcon-\nH1-7B"]
    counts = {m: [int(valid(M, "XML", m).sum()),
                  int(valid(M, "BPIL0", m).sum()),
                  int(valid(M, "SFT", m).sum()) if ("SFT", "syn", m) in M
                  else None] for m in order}
    baseline = counts["gpt-oss-120b"][0] / 105

    colors = ["#0072B2", "#E69F00", "#009E73"]          # Okabe-Ito
    labels = ["XML (zero-shot)", "BPIL (zero-shot)", "BPIL (LoRA SFT)"]

    fig, ax = plt.subplots(figsize=(6.3, 3.0))
    x, w = np.arange(len(order)), 0.26
    for k in range(3):
        xs = [xi + (k - 1) * w for xi in x]
        hs = [(counts[m][k] or 0) / 105 for m in order]
        ax.bar(xs, hs, w, color=colors[k], label=labels[k])
        for xi, m in zip(xs, order):
            c = counts[m][k]
            if c is None:
                ax.text(xi, .012, "n/a", ha="center", va="bottom",
                        fontsize=5.8, color="#888", rotation=90)
            else:
                ax.text(xi, c / 105 + .012, str(c), ha="center",
                        va="bottom", fontsize=6.6)
    ax.axhline(baseline, color="#555", ls=(0, (4, 3)), lw=.9)
    ax.text(1.5, baseline + .022,
            f"gpt-oss-120b XML baseline ({baseline:.3f})",
            fontsize=7.0, color="#555", ha="center")
    ax.set_xticks(x, xlabels, fontsize=7.6)
    ax.set_ylabel("valid outputs / 105")
    ax.set_ylim(0, 1.0)
    ax.set_axisbelow(True)
    ax.grid(axis="y", lw=.4, color="#e2e2e2")
    ax.legend(frameon=False, fontsize=7.6, ncol=3, loc="upper center",
              bbox_to_anchor=(.5, 1.14), handlelength=1.3,
              columnspacing=1.4)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "fig_validity.pdf")
    plt.close(fig)


def fig_shift(M: dict, out: Path) -> None:
    """Figure 3: paired quality change on jointly valid items."""
    from scipy import stats as sps
    rng = np.random.default_rng(11)          # jitter only; fixed seed
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.9), sharey=True)
    for ax, m in zip(axes, ["Qwen2.5-14B", "Falcon-H1-7B"]):
        j = valid(M, "BPIL0", m) & valid(M, "SFT", m)
        ax.axhline(0, color="#888", lw=.8, ls=(0, (4, 3)))
        for i, d in enumerate(DIMS):
            y = (M[("SFT", d, m)][j] - M[("BPIL0", d, m)][j]).to_numpy(float)
            ax.scatter(i + rng.uniform(-.14, .14, len(y)), y, s=9,
                       color="#7f8fa4", alpha=.55, lw=0)
            med = float(np.median(y))
            ax.plot([i - .24, i + .24], [med, med],
                    color="#D55E00" if med < 0 else "#009E73", lw=2.4)
            p = float(sps.wilcoxon(y).pvalue)
            p_txt = "p<.001" if p < .001 else f"p={p:.3f}"
            lab = f"$\\Delta_{{med}}$ = {med:+.3f}\n{p_txt}"
            y_lab = .315 if med >= 0 else -.245
            ax.text(i, y_lab, lab, ha="center", va="bottom",
                    fontsize=6.4, color="#444", linespacing=1.1)
        ax.set_xticks(range(3), ["syntactic", "pragmatic", "semantic"])
        ax.set_title(f"{m} (n = {int(j.sum())} paired items)",
                     fontsize=9, pad=4)
        ax.set_ylim(-.30, .45)
        for s in ["top", "right"]:
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("paired score change\n(fine-tuned $-$ zero-shot BPIL)")
    fig.tight_layout(w_pad=1.4)
    fig.savefig(out / "fig_shift.pdf")
    plt.close(fig)


def main(data_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    M = load(data_dir)
    fig_footprint(out_dir)
    fig_validity(M, out_dir)
    fig_shift(M, out_dir)
    print(f"[make_figures] wrote fig_footprint / fig_validity / fig_shift "
          f"to {out_dir}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--out-dir", type=Path, default=Path("figures"))
    a = ap.parse_args()
    main(a.data_dir, a.out_dir)
