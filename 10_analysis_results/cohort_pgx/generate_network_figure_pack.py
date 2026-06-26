#!/usr/bin/env python3
"""
Generate publication-oriented Cohort PGx network visuals.

This script implements the figure strategy described in:
- 10_analysis_results/network_analysis.md
- 10_analysis_results/README_pgx_network_visuals.md

It reads the structured NetworkX exports produced by build_network_topology.py
and creates a figure pack with:
- intervention-weighted global network
- cohort small multiples
- therapeutic cluster ego networks
- time-to-event/prevention context
- intervention-priority heatmap
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COHORT_LABELS = {
    "falls": "Falls",
    "ed": "ED",
}

AGE_BAND_ORDER = ["65-74", "75-84"]

TIER_COLORS = {
    "Tier 1": "#C0392B",
    "Tier 2": "#F39C12",
    "Tier 3": "#D4AC0D",
    "Unknown": "#8E44AD",
    "Undefined": "#8E44AD",
    "Drug": "#5DADE2",
    "Phenotype": "#95A5A6",
}

NODE_SYMBOLS = {
    "gene": "circle",
    "drug": "diamond",
    "phenotype": "square",
}

RELATION_COLORS = {
    "feature_importance_drug_gene": "#7F8C8D",
    "co_metabolizes": "#2E86C1",
    "metabolizes": "#BDC3C7",
    "affects_risk": "#D81B60",
}

CLUSTER_RULES = {
    "Adrenergic / beta-blocker": {
        "drugs": {"CARVEDILOL", "ATENOLOL"},
        "genes": {"ADRA2C", "ADRB1", "ADRB2", "CYP2D6", "GRK4", "GRK5"},
    },
    "Diuretic / hypertension": {
        "drugs": {"FUROSEMIDE", "HYDROCHLOROTHIAZIDE"},
        "genes": {"ADD1", "NEDD4L", "PRKCA", "YEATS4"},
    },
    "Lipid / statin": {
        "drugs": {"SIMVASTATIN"},
        "genes": {"ABCB1", "CETP", "CYP3A4", "CYP3A5", "HMGCR", "LPA", "SLCO1B1"},
    },
    "GI / antiplatelet / ophthalmic": {
        "drugs": {"OMEPRAZOLE", "CLOPIDOGREL", "LATANOPROST"},
        "genes": {"CYP2C19", "CES1", "PTGFR"},
    },
}

FALLBACK_TIME_WINDOWS = [
    {
        "cohort": "falls",
        "age_band": "65-74",
        "drug": "FUROSEMIDE",
        "median_days_before_event": 25.5,
        "window_low": 21,
        "window_high": 42,
        "source": "network_analysis.md fallback",
    },
    {
        "cohort": "falls",
        "age_band": "75-84",
        "drug": "FUROSEMIDE",
        "median_days_before_event": 37.0,
        "window_low": 21,
        "window_high": 42,
        "source": "network_analysis.md fallback",
    },
]


@dataclass(frozen=True)
class FigurePaths:
    html: Path
    png: Path


def age_band_to_fname(age_band: str) -> str:
    return str(age_band).replace("-", "_")


def find_headless_browser() -> Path | None:
    candidates = [
        os.environ.get("CHROME_BIN"),
        os.environ.get("CHROMIUM_BIN"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "google-chrome",
        "chromium",
        "chromium-browser",
        "msedge",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
        resolved = shutil.which(candidate)
        if resolved:
            return Path(resolved)
    return None


def write_figure(fig: go.Figure, paths: FigurePaths, width: int = 1600, height: int = 1100) -> None:
    paths.html.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(paths.html), include_plotlyjs="cdn")
    browser = find_headless_browser()
    if not browser:
        print(f"Saved HTML only; no Chromium browser found for PNG: {paths.html}")
        return
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        "--virtual-time-budget=5000",
        f"--screenshot={paths.png.resolve()}",
        paths.html.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    if result.returncode != 0:
        print(f"PNG screenshot failed for {paths.html}: {(result.stderr or '')[-500:]}")
    elif paths.png.exists():
        print(f"Saved {paths.png}")


def load_network_tables(networks_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_frames = []
    edge_frames = []
    for edges_path in sorted(networks_root.glob("*/*/network_edges.csv")):
        cohort = edges_path.parents[1].name
        age_band = edges_path.parent.name.replace("_", "-")
        nodes_path = edges_path.with_name("network_nodes.csv")
        if not nodes_path.exists():
            continue
        nodes = pd.read_csv(nodes_path)
        edges = pd.read_csv(edges_path)
        nodes["cohort"] = nodes["cohort"].fillna(cohort) if "cohort" in nodes else cohort
        nodes["age_band"] = nodes["age_band"].fillna(age_band) if "age_band" in nodes else age_band
        edges["cohort"] = edges["cohort"].fillna(cohort) if "cohort" in edges else cohort
        edges["age_band"] = edges["age_band"].fillna(age_band) if "age_band" in edges else age_band
        nodes["network_cohort"] = cohort
        nodes["network_age_band"] = age_band
        edges["network_cohort"] = cohort
        edges["network_age_band"] = age_band
        node_frames.append(nodes)
        edge_frames.append(edges)
    if not node_frames or not edge_frames:
        raise FileNotFoundError(f"No network_nodes.csv/network_edges.csv files found under {networks_root}")
    nodes = pd.concat(node_frames, ignore_index=True)
    edges = pd.concat(edge_frames, ignore_index=True)
    return harmonize_nodes(nodes), harmonize_edges(edges)


def harmonize_nodes(nodes: pd.DataFrame) -> pd.DataFrame:
    out = nodes.copy()
    out["id"] = out["id"].astype(str)
    out["label"] = out["label"].fillna(out["id"]).astype(str)
    out["type"] = out["type"].fillna("unknown").astype(str)
    out["tier"] = out.get("tier", pd.Series(index=out.index, dtype=object)).fillna("Unknown").astype(str)
    out.loc[(out["type"] == "drug"), "tier"] = "Drug"
    out.loc[(out["type"] == "phenotype"), "tier"] = "Phenotype"
    out["seed_gene"] = out.get("seed_gene", False).fillna(False).astype(bool)
    out["seed_drug"] = out.get("seed_drug", False).fillna(False).astype(bool)
    return out


def harmonize_edges(edges: pd.DataFrame) -> pd.DataFrame:
    out = edges.copy()
    out["source"] = out["source"].astype(str)
    out["target"] = out["target"].astype(str)
    out["relation"] = out["relation"].fillna("related").astype(str)
    out["feature_importance"] = pd.to_numeric(out.get("feature_importance"), errors="coerce")
    out["rank"] = pd.to_numeric(out.get("rank"), errors="coerce")
    out["seed_edge"] = out.get("seed_edge", False).fillna(False).astype(bool)
    out["cohort"] = out["cohort"].fillna(out["network_cohort"])
    out["age_band"] = out["age_band"].fillna(out["network_age_band"])
    out["outcome"] = out["cohort"].map(COHORT_LABELS).fillna(out["cohort"])
    out["panel"] = out["outcome"].astype(str) + " " + out["age_band"].astype(str)
    return out


def aggregate_node_table(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    node_ids = pd.unique(pd.concat([edges["source"], edges["target"]], ignore_index=True))
    base = (
        nodes.sort_values(["seed_gene", "seed_drug", "degree"], ascending=[False, False, False])
        .drop_duplicates("id")
        .set_index("id")
        .reindex(node_ids)
        .reset_index()
        .rename(columns={"index": "id"})
    )
    base["label"] = base["label"].fillna(base["id"])
    base["type"] = base["type"].fillna("unknown")
    base["tier"] = base["tier"].fillna("Unknown")
    base["degree"] = base["id"].map(edges["source"].value_counts().add(edges["target"].value_counts(), fill_value=0)).fillna(0)
    return base


def node_hover(row: pd.Series) -> str:
    bits = [
        f"{row.get('id')}",
        f"type={row.get('type')}",
        f"tier={row.get('tier', 'Unknown')}",
        f"degree={row.get('degree', 0)}",
    ]
    if bool(row.get("seed_gene", False)):
        bits.append("model-seeded gene")
    if bool(row.get("seed_drug", False)):
        bits.append("model-seeded drug")
    return "<br>".join(bits)


def add_network_traces(
    fig: go.Figure,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    row: int | None = None,
    col: int | None = None,
    showlegend: bool = True,
    title_prefix: str = "",
) -> None:
    graph = nx.Graph()
    for _, node in nodes.iterrows():
        graph.add_node(node["id"])
    for _, edge in edges.iterrows():
        graph.add_edge(edge["source"], edge["target"], relation=edge["relation"])
    if graph.number_of_nodes() == 0:
        return
    pos = nx.spring_layout(graph, seed=42, k=1.2, iterations=80)

    for relation, relation_edges in edges.groupby("relation"):
        x_vals: list[float | None] = []
        y_vals: list[float | None] = []
        widths = relation_edges["feature_importance"].fillna(0.03)
        edge_width = 1.0 if widths.empty else max(0.8, min(5.0, float(widths.max()) * 10))
        for _, edge in relation_edges.iterrows():
            if edge["source"] not in pos or edge["target"] not in pos:
                continue
            x0, y0 = pos[edge["source"]]
            x1, y1 = pos[edge["target"]]
            x_vals.extend([x0, x1, None])
            y_vals.extend([y0, y1, None])
        trace = go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines",
            line=dict(color=RELATION_COLORS.get(relation, "#BBBBBB"), width=edge_width),
            opacity=0.85 if relation == "feature_importance_drug_gene" else 0.35,
            hoverinfo="skip",
            name=f"{title_prefix}{relation}",
            showlegend=showlegend,
        )
        fig.add_trace(trace, row=row, col=col)

    for (node_type, tier), group in nodes.groupby(["type", "tier"], dropna=False):
        ids = [node_id for node_id in group["id"] if node_id in pos]
        if not ids:
            continue
        group = group.set_index("id").loc[ids].reset_index()
        labels = [
            node_id if should_label_node(node_id, attrs) else ""
            for node_id, attrs in group.set_index("id").iterrows()
        ]
        sizes = [
            14 + min(float(attrs.get("degree", 1) or 1), 12) * 2.5
            + (8 if bool(attrs.get("seed_gene", False) or attrs.get("seed_drug", False)) else 0)
            for _, attrs in group.iterrows()
        ]
        trace = go.Scatter(
            x=[pos[node_id][0] for node_id in ids],
            y=[pos[node_id][1] for node_id in ids],
            mode="markers+text",
            marker=dict(
                size=sizes,
                color=TIER_COLORS.get(tier, "#8E44AD"),
                symbol=NODE_SYMBOLS.get(node_type, "circle"),
                line=dict(width=1.5, color="white"),
            ),
            text=labels,
            textposition="top center",
            textfont=dict(size=10),
            hovertext=[node_hover(attrs) for _, attrs in group.iterrows()],
            hoverinfo="text",
            name=f"{title_prefix}{tier} {node_type}",
            showlegend=showlegend,
        )
        fig.add_trace(trace, row=row, col=col)


def should_label_node(node_id: str, attrs: pd.Series) -> bool:
    highlight = {
        "FUROSEMIDE",
        "CARVEDILOL",
        "HYDROCHLOROTHIAZIDE",
        "SIMVASTATIN",
        "OMEPRAZOLE",
        "CYP2D6",
        "CYP3A4",
        "SLCO1B1",
        "ABCB1",
        "ADD1",
        "ADRA2C",
    }
    return (
        node_id in highlight
        or attrs.get("tier") in {"Tier 1", "Undefined", "Unknown"}
        or bool(attrs.get("seed_gene", False))
    )


def make_global_network(nodes: pd.DataFrame, edges: pd.DataFrame, out_dir: Path) -> None:
    graph_edges = edges[
        edges["relation"].isin(["feature_importance_drug_gene", "co_metabolizes"])
        & (edges["seed_edge"] | edges["relation"].eq("co_metabolizes"))
    ].copy()
    graph_edges = graph_edges.sort_values(["relation", "feature_importance"], ascending=[True, False]).head(180)
    graph_nodes = aggregate_node_table(nodes, graph_edges)
    fig = go.Figure()
    add_network_traces(fig, graph_nodes, graph_edges)
    fig.update_layout(
        title=(
            "PGx Intervention-Weighted Global Network"
            "<br><sup>Drug-gene seed edges use SHAP/FFA consensus importance; co-metabolizes edges show pathway bridges.</sup>"
        ),
        width=1500,
        height=1000,
        plot_bgcolor="white",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        legend=dict(orientation="v", x=1.02, y=1),
        margin=dict(l=20, r=260, t=90, b=20),
    )
    write_figure(fig, FigurePaths(out_dir / "pgx_global_intervention_network.html", out_dir / "pgx_global_intervention_network.png"))


def make_cohort_small_multiples(nodes: pd.DataFrame, edges: pd.DataFrame, out_dir: Path) -> None:
    panels = [("falls", "65-74"), ("falls", "75-84"), ("ed", "65-74"), ("ed", "75-84")]
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=[f"{COHORT_LABELS[c]} {a}" for c, a in panels],
        horizontal_spacing=0.03,
        vertical_spacing=0.08,
    )
    for idx, (cohort, age_band) in enumerate(panels):
        row = idx // 2 + 1
        col = idx % 2 + 1
        panel_edges = edges[
            edges["relation"].eq("feature_importance_drug_gene")
            & edges["cohort"].eq(cohort)
            & edges["age_band"].eq(age_band)
        ].sort_values(["rank", "feature_importance"], ascending=[True, False])
        panel_edges = panel_edges.head(45)
        panel_nodes = aggregate_node_table(nodes, panel_edges)
        add_network_traces(fig, panel_nodes, panel_edges, row=row, col=col, showlegend=(idx == 0), title_prefix=f"{cohort}-{age_band} ")
    fig.update_layout(
        title=(
            "Cohort-Specific PGx Network Small Multiples"
            "<br><sup>Same visual grammar across panels; edge width follows top model-seeded drug importance.</sup>"
        ),
        width=1600,
        height=1150,
        plot_bgcolor="white",
        margin=dict(l=20, r=240, t=105, b=20),
    )
    for axis in fig.layout:
        if str(axis).startswith("xaxis") or str(axis).startswith("yaxis"):
            fig.layout[axis].visible = False
    write_figure(fig, FigurePaths(out_dir / "pgx_cohort_small_multiples.html", out_dir / "pgx_cohort_small_multiples.png"), height=1200)


def make_cluster_ego_networks(nodes: pd.DataFrame, edges: pd.DataFrame, out_dir: Path) -> None:
    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=list(CLUSTER_RULES.keys()),
        horizontal_spacing=0.03,
        vertical_spacing=0.08,
    )
    for idx, (cluster, rule) in enumerate(CLUSTER_RULES.items()):
        row = idx // 2 + 1
        col = idx % 2 + 1
        keep_nodes = rule["drugs"] | rule["genes"]
        cluster_edges = edges[
            edges["source"].isin(keep_nodes)
            | edges["target"].isin(keep_nodes)
        ].copy()
        cluster_edges = cluster_edges[
            cluster_edges["source"].isin(keep_nodes) | cluster_edges["target"].isin(keep_nodes)
        ]
        cluster_edges = cluster_edges[
            cluster_edges["relation"].isin(["feature_importance_drug_gene", "co_metabolizes"])
        ].sort_values(["relation", "feature_importance"], ascending=[True, False]).head(60)
        cluster_nodes = aggregate_node_table(nodes, cluster_edges)
        add_network_traces(fig, cluster_nodes, cluster_edges, row=row, col=col, showlegend=(idx == 0), title_prefix=f"{cluster} ")
    fig.update_layout(
        title=(
            "Therapeutic Cluster Ego Networks"
            "<br><sup>Cluster panels highlight adrenergic, diuretic, lipid/statin, and related medication modules.</sup>"
        ),
        width=1600,
        height=1150,
        plot_bgcolor="white",
        margin=dict(l=20, r=240, t=105, b=20),
    )
    for axis in fig.layout:
        if str(axis).startswith("xaxis") or str(axis).startswith("yaxis"):
            fig.layout[axis].visible = False
    write_figure(fig, FigurePaths(out_dir / "pgx_cluster_ego_networks.html", out_dir / "pgx_cluster_ego_networks.png"), height=1200)


def intervention_priority(edges: pd.DataFrame) -> pd.DataFrame:
    seed = edges[edges["relation"].eq("feature_importance_drug_gene")].copy()
    seed = seed.dropna(subset=["feature_importance", "rank"])
    if seed.empty:
        return seed
    seed["drug"] = seed["target"]
    seed["gene"] = seed["source"]
    seed["importance_norm"] = seed.groupby(["cohort", "age_band"])["feature_importance"].transform(
        lambda s: s / s.max() if s.max() else s
    )
    seed["inv_rank_norm"] = (1 / seed["rank"]).groupby([seed["cohort"], seed["age_band"]]).transform(
        lambda s: s / s.max() if s.max() else s
    )
    tier_weight_genes = {"ADD1", "NEDD4L", "PRKCA", "YEATS4", "CETP", "LPA", "ADRA2C", "GRK4", "GRK5", "PTGFR", "CES1"}
    seed["tier_weight"] = seed["gene"].isin(tier_weight_genes).map({True: 1.2, False: 1.0})
    seed["intervention_priority"] = (
        seed["importance_norm"].fillna(0) * 0.5
        + seed["inv_rank_norm"].fillna(0) * 0.3
        + ((seed["tier_weight"] - 1.0) / 0.2).fillna(0) * 0.2
    )
    return seed


def make_priority_heatmap(edges: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    priority = intervention_priority(edges)
    if priority.empty:
        return priority
    top = (
        priority.sort_values("intervention_priority", ascending=False)
        .groupby(["cohort", "age_band"])
        .head(12)
        .copy()
    )
    top["pair"] = top["gene"] + " -> " + top["drug"]
    pivot = top.pivot_table(
        index="pair",
        columns="panel",
        values="intervention_priority",
        aggfunc="max",
        fill_value=0,
    )
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=list(pivot.index),
            colorscale="Reds",
            colorbar=dict(title="Priority"),
            hovertemplate="Pair=%{y}<br>Panel=%{x}<br>Priority=%{z:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=(
            "PGx Intervention Priority Heatmap"
            "<br><sup>Score combines normalized importance, inverse rank, and Undefined-gene emphasis.</sup>"
        ),
        width=1200,
        height=max(650, 28 * len(pivot.index)),
        margin=dict(l=260, r=40, t=100, b=80),
    )
    write_figure(fig, FigurePaths(out_dir / "pgx_intervention_priority_heatmap.html", out_dir / "pgx_intervention_priority_heatmap.png"), width=1300, height=max(800, 30 * len(pivot.index)))
    return priority


def load_time_windows(dtw_root: Path) -> pd.DataFrame:
    rows = []
    for chart_path in sorted(dtw_root.glob("*/*/chart_data.json")):
        try:
            data = json.loads(chart_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("empty"):
            continue
        cohort = data.get("cohort") or chart_path.parent.parent.name
        age_band = data.get("age_band") or chart_path.parent.name.replace("_", "-")
        for key in ("drug_timing", "timing", "trajectory_timing", "time_to_target"):
            values = data.get(key)
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict):
                        rows.append({"cohort": cohort, "age_band": age_band, **item, "source": str(chart_path)})
    if rows:
        df = pd.DataFrame(rows)
        rename = {
            "code": "drug",
            "median_days_to_target": "median_days_before_event",
            "median_days": "median_days_before_event",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if {"drug", "median_days_before_event"}.issubset(df.columns):
            df["window_low"] = df.get("window_low", 21)
            df["window_high"] = df.get("window_high", 42)
            return df[["cohort", "age_band", "drug", "median_days_before_event", "window_low", "window_high", "source"]]
    return pd.DataFrame(FALLBACK_TIME_WINDOWS)


def make_time_to_event_panel(dtw_root: Path, out_dir: Path) -> pd.DataFrame:
    time_df = load_time_windows(dtw_root)
    time_df["panel"] = time_df["cohort"].map(COHORT_LABELS).fillna(time_df["cohort"]) + " " + time_df["age_band"].astype(str)
    time_df["label"] = time_df["drug"].astype(str) + " (" + time_df["median_days_before_event"].astype(float).round(1).astype(str) + " d)"
    fig = go.Figure()
    for _, row in time_df.iterrows():
        fig.add_trace(
            go.Scatter(
                x=[row["window_low"], row["window_high"]],
                y=[row["panel"], row["panel"]],
                mode="lines",
                line=dict(color="#AED6F1", width=18),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[row["median_days_before_event"]],
                y=[row["panel"]],
                mode="markers+text",
                marker=dict(size=14, color="#1F618D"),
                text=[row["label"]],
                textposition="top center",
                hovertemplate="Panel=%{y}<br>Days before event=%{x}<extra></extra>",
                showlegend=False,
            )
        )
    fig.update_layout(
        title=(
            "Medication Lead-Time Before Event"
            "<br><sup>Uses DTW timing artifacts when available; falls values fall back to documented 3-6 week prevention window.</sup>"
        ),
        width=1100,
        height=500,
        xaxis=dict(title="Days before event", autorange="reversed"),
        yaxis=dict(title=""),
        plot_bgcolor="white",
        margin=dict(l=130, r=40, t=100, b=70),
    )
    write_figure(fig, FigurePaths(out_dir / "pgx_time_to_event_panel.html", out_dir / "pgx_time_to_event_panel.png"), width=1200, height=650)
    return time_df


def write_manifest(out_dir: Path, generated: Iterable[Path], priority: pd.DataFrame, time_df: pd.DataFrame) -> None:
    manifest = {
        "description": "Publication-oriented PGx network figure pack.",
        "source_guidance": [
            "10_analysis_results/network_analysis.md",
            "10_analysis_results/README_pgx_network_visuals.md",
        ],
        "figures": [str(path.name) for path in generated],
        "priority_rows": int(len(priority)),
        "time_window_rows": int(len(time_df)),
        "notes": [
            "PNG files are screenshots of the Plotly HTML figures for GitHub rendering.",
            "R tidygraph/ggraph implementation remains optional; this Python implementation uses the same visual grammar.",
        ],
    }
    with open(out_dir / "figure_pack_manifest.json", "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)


def generate_figure_pack(project_root: Path) -> None:
    networks_root = project_root / "10_analysis_results" / "visualizations" / "cohort_pgx" / "networks"
    dtw_root = project_root / "9_dtw_analysis" / "outputs"
    out_dir = project_root / "10_analysis_results" / "visualizations" / "cohort_pgx" / "figure_pack"
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes, edges = load_network_tables(networks_root)
    make_global_network(nodes, edges, out_dir)
    make_cohort_small_multiples(nodes, edges, out_dir)
    make_cluster_ego_networks(nodes, edges, out_dir)
    priority = make_priority_heatmap(edges, out_dir)
    time_df = make_time_to_event_panel(dtw_root, out_dir)
    priority.to_csv(out_dir / "pgx_intervention_priority_scores.csv", index=False)
    time_df.to_csv(out_dir / "pgx_time_to_event_windows.csv", index=False)
    generated = sorted(out_dir.glob("*.html")) + sorted(out_dir.glob("*.png"))
    write_manifest(out_dir, generated, priority, time_df)
    print(f"Figure pack written to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate publication-oriented PGx network visual figure pack.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd(), help="Repository root.")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    generate_figure_pack(project_root)


if __name__ == "__main__":
    main()
