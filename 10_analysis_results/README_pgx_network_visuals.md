# PGx Network Visuals and Prevention-Oriented Figure Plan

This document summarizes the recommended network visual strategy, the prevention framing for ED and fall outcomes, and the accompanying R template for building the figures from structured network data.[file:1][file:2][file:3]

## Overview

The most effective visual approach is a layered figure set rather than one large network because the attached material combines node tiers, drug-gene feature importance, co-metabolism structure, cohort stratification, and temporal intervention windows.[file:1][file:2][file:3] A single graph can show topology, but a figure pack is needed to support both scientific interpretation and actionable prevention logic for emergency department and fall outcomes.[file:2][file:3]

The recommended stack centers on four figure families: an intervention-weighted global network, cohort-specific small multiples, cluster-level ego networks, and a time-to-event panel.[file:2][file:3] Together, these views show which PGx-linked medication clusters matter, in which cohorts they matter most, and when an intervention window may still be open before an adverse event occurs.[file:2]

## Why these visuals fit the attached work

The attached reports describe networks in which Tier 1 genes, Tier 2 genes, drugs, and phenotypes are already visually distinguished, while some clinically relevant genes remain hidden or categorized as Undefined.[file:1][file:2][file:3] Those Undefined genes include ADD1, NEDD4L, PRKCA, YEATS4, CETP, LPA, ADRA2C, GRK4, GRK5, PTGFR, and CES1, and the reports argue that mapping them back to high-importance medications makes the network more actionable.[file:1][file:2]

The reports also distinguish two key edge meanings: feature-importance drug-gene links and co-metabolizes gene-gene links.[file:3] That distinction is important because feature-importance edges support risk prioritization, while co-metabolism edges explain pathway integration and provide the bridge from isolated peripheral nodes to the Tier 1 pharmacogenomic core.[file:1][file:2][file:3]

## Recommended figure set

### 1. Intervention-weighted global network

The global network should be a bipartite or layered network where genes and drugs are visually separated, node type and tier are encoded by color and shape, and edge width reflects feature importance.[file:2][file:3] Undefined genes should be visually emphasized because the attached reports frame them as the main resolution target for the sparse network periphery and as candidates for stronger clinical interpretation.[file:1][file:2]

Recommended encodings:

- Tier 1 genes: red circles.[file:3]
- Tier 2 genes: orange circles.[file:3]
- Undefined genes: a distinct color such as purple and, optionally, a separate outline or shape.[file:1][file:2]
- Drugs: blue diamonds.[file:3]
- Feature-importance edges: solid neutral lines with width proportional to importance.[file:2][file:3]
- Co-metabolizes edges: thicker blue links or a second edge style to show pathway structure.[file:1][file:3]

This figure is best used as the opening panel in a manuscript or slide deck because it introduces the full PGx topology while keeping the reclassified or unresolved genes visible.[file:1][file:2][file:3]

### 2. Cohort small multiples

The global graph alone cannot show how signal strength changes across Falls versus ED and across age bands.[file:2][file:3] The attached material specifically notes cohort-specific drug anchors, including FUROSEMIDE as Rank 1 in Falls 65–74 and CARVEDILOL as Rank 1 in ED 65–74, with HYDROCHLOROTHIAZIDE emerging strongly in ED 75–84.[file:2][file:3]

A 2x2 or similar small-multiple layout should therefore be used to compare the main strata side by side.[file:2][file:3] The same color and shape grammar should be used in each panel so that visual changes represent real cohort differences rather than styling differences.[file:1][file:3]

### 3. Cluster ego networks

The attached reports already organize many of the important findings into therapeutic clusters, which makes cluster ego-networks one of the most interpretable figure types.[file:2] The strongest cluster panels are the adrenergic beta-blocker cluster, the diuretic cluster, and the lipid/statin cluster because these are repeatedly tied to high-importance medications and explicit gene mappings.[file:2]

Examples described in the attached work include the ADRA2C/GRK4/GRK5 group around CARVEDILOL and ATENOLOL, the ADD1/NEDD4L/PRKCA/YEATS4 group around FUROSEMIDE and HYDROCHLOROTHIAZIDE, and the CETP/LPA/ABCB1 group around SIMVASTATIN with SLCO1B1 and CYP3A4 as pathway bridges.[file:1][file:2][file:3] These figures are ideal for the Results section because they support direct narrative interpretation and map naturally to medication review discussions.[file:2]

### 4. Time-to-event panel

The temporal analysis is a major reason the network can be used for prevention rather than only retrospective explanation.[file:2] The attached report describes a predictive window of roughly 3–6 weeks before a fall event for medications such as FUROSEMIDE, along with median timing gaps of 25.5 days in Falls 65–74 and 37 days in Falls 75–84.[file:2]

A separate time-to-event panel should therefore be shown alongside the networks.[file:2] The easiest implementation is a horizontal interval plot with medians and windows, though a Sankey-style flow from cluster to drug to event can also work if the figure remains readable.[file:2]

## Prevention framing

The visual design should not stop at topology; it should guide intervention logic.[file:2][file:3] Three prevention use cases are supported by the attached work.

First, the figures can identify medication review targets by making the highest-ranked drugs visually dominant in their relevant cohorts.[file:2][file:3] For example, FUROSEMIDE is a leading falls-related feature, CARVEDILOL is a leading ED-related feature, and HYDROCHLOROTHIAZIDE is a strong ED 75–84 signal, so those clusters should be prioritized for review in the corresponding panels.[file:2][file:3]

Second, the figures can support pathway-level interpretation by showing how Undefined genes connect into Tier 1 metabolic cores through co-metabolizes relationships.[file:1][file:2] The attached reports note that the adrenergic Undefined cluster links to CYP2D6, ADRB1, and ADRB2, and that the CETP/LPA/ABCB1 lipid cluster links to SLCO1B1 and CYP3A4 for simvastatin metabolism.[file:2]

Third, the figures can support prevention timing by highlighting the lead-time between medication pattern emergence and the event itself.[file:2] This is especially important for falls because the attached temporal analysis suggests a period in which medication review, monitoring, deprescribing, or substitution could potentially occur before the adverse event.[file:2]

## Polypharmacy emphasis

The attached material states that pgxnumdrugs remains a persistent dominant factor across all 16 cohort strata, with maximum combined importance of 1.0.[file:2] That means the visual package should include at least one derived view or annotation that captures burden rather than only individual drug-gene edges, because total PGx medication load may be more predictive than any single relationship in isolation.[file:2]

A practical option is to compute an intervention priority score that combines normalized feature importance, inverse rank, and a burden modifier for the overall PGx drug count.[file:2] This score can then be mapped to label order, node halo, panel ordering, or a side heatmap to help clinicians identify where review effort may have the largest payoff.[file:2]

## Software recommendation

For publication-oriented work, R is the best single-language choice for this project because the figure requirements favor high-quality static network layouts, facetting, label control, and compositional multi-panel assembly.[file:1][file:2][file:3] The strongest stack is `tidygraph`, `ggraph`, `igraph`, `ggplot2`, `ggrepel`, `patchwork`, and tidyverse utilities for data wrangling.[file:1][file:2][file:3]

Python remains a good option for interactive exploration, but the attached use case is better matched to R if the immediate goal is manuscript-ready visuals and a coherent figure pack.[file:2][file:3] A hybrid workflow is also reasonable: produce final static figures in R and reserve Python for dashboard exploration if stakeholders later need hover or drill-down interaction.[file:2][file:3]

## Included R template

The accompanying R script provides a template implementation of the full figure plan using an example node table, edge table, and time-to-event table derived from the attached summaries.[file:1][file:2][file:3] The script includes functions for a global network, cohort-specific network panels, cluster ego-networks, and a time-to-event plot, along with a simple intervention-priority calculation.[file:2][file:3]

The template is designed to be replaced with the real `networknodes.csv`, `networkedges.csv`, and time-to-event source files once those are available in a structured form.[file:1][file:2] The plotting grammar should remain stable even when the full cohort set is loaded, which makes the script a good starting point for a reproducible figure pipeline.[file:2][file:3]

## Suggested implementation workflow

1. Parse or load the real node and edge tables from the network source files.[file:1][file:2]
2. Harmonize tier labels, node classes, relation types, and cohort metadata.[file:1][file:2][file:3]
3. Generate the intervention-weighted global network first.[file:2][file:3]
4. Create cohort small multiples with identical scale and legend rules.[file:2][file:3]
5. Build three to five cluster ego-networks for the main therapeutic modules.[file:2]
6. Add the time-to-event panel and, optionally, a heatmap or summary table of intervention priority.[file:2]
7. Export vector files for manuscripts and high-resolution PNG files for presentation use.[file:2][file:3]

## Implemented project workflow

The project now includes a Python/Plotly implementation of this figure plan at
`10_analysis_results/cohort_pgx/generate_network_figure_pack.py`. It reads the
real `network_nodes.csv` and `network_edges.csv` files generated by the Cohort
PGx NetworkX workflow and writes the figure pack to
`10_analysis_results/visualizations/cohort_pgx/figure_pack/`.

Generated outputs:

- `pgx_global_intervention_network.html/png` - intervention-weighted global network.
- `pgx_cohort_small_multiples.html/png` - Falls/ED by age-band small multiples.
- `pgx_cluster_ego_networks.html/png` - adrenergic, diuretic, lipid/statin, and related cluster panels.
- `pgx_intervention_priority_heatmap.html/png` - score combining normalized importance, inverse rank, and Undefined-gene emphasis.
- `pgx_pathway_context_panel.html/png` - explicit context for dynamics, kinetics, allergic-response watch-listing, underappreciated signaling, and kinetic pathways.
- `pgx_time_to_event_panel.html/png` - combined prevention timing panel using local DTW timing artifacts when available, otherwise S3 DTW summaries for Falls/ED cohort-age panels, with documented fallback rows only as a last resort.
- `pgx_time_to_event_falls_panel.html/png` and `pgx_time_to_event_ed_panel.html/png` - cohort-specific Falls and ED lead-time panels.
- `pgx_intervention_priority_scores.csv`, `pgx_pathway_context_edges.csv`, and `pgx_time_to_event_windows.csv` - tabular data behind the derived figure panels.

Notebook 4 (`4_results_review.ipynb`) can run this workflow through the Cohort
PGx NetworkX section. The static PNG outputs render in GitHub; the HTML outputs
retain interactive hover and zoom.

The R-first stack remains recommended for final manuscript polishing. Local R is
available, but `tidygraph`, `ggraph`, `ggrepel`, and `patchwork` were not
installed when this workflow was implemented. Install those packages before
running an R/ggraph version of the same figure pack.

## File descriptions

| File | Purpose |
|---|---|
| `pgx_network_figure_template.R` | R template for global network, cohort panels, cluster ego-networks, and time-to-event plot generation. |
| `cohort_pgx/generate_network_figure_pack.py` | Implemented Python/Plotly generator for the project-specific figure pack. |
| `README_pgx_network_visuals.md` | Summary of the figure strategy, prevention interpretation, and implementation guidance. |

## Closing guidance

The central design principle is to make the network clinically legible rather than merely visually dense.[file:1][file:2][file:3] The best figures are the ones that help a reader identify which medication-gene clusters matter, in which patient strata they matter most, and whether there is enough lead-time to intervene before an ED visit or fall occurs.[file:2][file:3]
