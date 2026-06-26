<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# yes

Yes — here is a concrete R-first template for the figure pack, with structure aimed at publication-quality output and direct clinical interpretation for fall/ED prevention.[^1][^2][^3]

## Package stack

Use **R** with `tidygraph`, `ggraph`, `igraph`, `ggplot2`, `dplyr`, `tidyr`, `stringr`, `patchwork`, and `ggrepel`. This stack is the best fit for your use case because your attached material centers on typed nodes, multiple edge classes, cohort stratification, and small-multiple figures rather than highly interactive exploration.[^2][^3][^1]

```r
library(tidyverse)
library(tidygraph)
library(ggraph)
library(igraph)
library(ggrepel)
library(patchwork)
library(scales)
```


## Data model

Your figures need three core tables: `nodes`, `edges`, and `cohort_scores`. The node table should include gene/drug/phenotype class and tier, the edge table should include relation type and any cohort-specific importance, and the cohort table should carry rank, importance, outcome, and age band so that the same network can be reweighted for Falls or ED panels.[^3][^1][^2]

```r
nodes <- tribble(
  ~name,     ~node_class,   ~tier,        ~cluster,
  "CYP2D6",  "gene",        "Tier 1",     "Adrenergic",
  "SLCO1B1", "gene",        "Tier 1",     "Lipid",
  "CYP3A4",  "gene",        "Tier 1",     "Lipid",
  "ABCB1",   "gene",        "Tier 1",     "Lipid",
  "HMGCR",   "gene",        "Tier 2",     "Lipid",
  "ADD1",    "gene",        "Undefined",  "Diuretic",
  "NEDD4L",  "gene",        "Undefined",  "Diuretic",
  "PRKCA",   "gene",        "Undefined",  "Diuretic",
  "YEATS4",  "gene",        "Undefined",  "Diuretic",
  "CETP",    "gene",        "Undefined",  "Lipid",
  "LPA",     "gene",        "Undefined",  "Lipid",
  "ADRA2C",  "gene",        "Undefined",  "Adrenergic",
  "GRK4",    "gene",        "Undefined",  "Adrenergic",
  "GRK5",    "gene",        "Undefined",  "Adrenergic",
  "PTGFR",   "gene",        "Undefined",  "Ophthalmic",
  "CES1",    "gene",        "Undefined",  "Antiplatelet",
  "FUROSEMIDE",          "drug", "Drug", "Diuretic",
  "HYDROCHLOROTHIAZIDE", "drug", "Drug", "Diuretic",
  "SIMVASTATIN",         "drug", "Drug", "Lipid",
  "CARVEDILOL",          "drug", "Drug", "Adrenergic",
  "ATENOLOL",            "drug", "Drug", "Adrenergic",
  "LATANOPROST",         "drug", "Drug", "Ophthalmic",
  "CLOPIDOGREL",         "drug", "Drug", "Antiplatelet"
)

edges <- tribble(
  ~from, ~to, ~relation, ~outcome, ~age_band, ~importance, ~rank,
  "ADD1", "FUROSEMIDE", "featureimportancedruggene", "Falls", "65-74", 0.1769, 1,
  "NEDD4L", "HYDROCHLOROTHIAZIDE", "featureimportancedruggene", "ED", "75-84", 0.1095, 3,
  "PRKCA", "HYDROCHLOROTHIAZIDE", "featureimportancedruggene", "ED", "75-84", 0.1095, 3,
  "YEATS4", "HYDROCHLOROTHIAZIDE", "featureimportancedruggene", "ED", "75-84", 0.1095, 3,
  "CETP", "SIMVASTATIN", "featureimportancedruggene", "Falls", "65-74", 0.1396, 3,
  "LPA", "SIMVASTATIN", "featureimportancedruggene", "Falls", "65-74", 0.1396, 3,
  "ADRA2C", "CARVEDILOL", "featureimportancedruggene", "ED", "65-74", 0.3941, 1,
  "GRK4", "CARVEDILOL", "featureimportancedruggene", "ED", "65-74", 0.3941, 1,
  "GRK5", "CARVEDILOL", "featureimportancedruggene", "ED", "65-74", 0.3941, 1,
  "ADRA2C", "ATENOLOL", "featureimportancedruggene", "ED", "75-84", 0.0050, 12,
  "GRK4", "ATENOLOL", "featureimportancedruggene", "ED", "75-84", 0.0050, 12,
  "GRK5", "ATENOLOL", "featureimportancedruggene", "ED", "75-84", 0.0050, 12,
  "PTGFR", "LATANOPROST", "featureimportancedruggene", "ED", "75-84", 0.0105, 11,
  "CES1", "CLOPIDOGREL", "featureimportancedruggene", "ED", "65-74", 0.0078, 21,
  "ADRA2C", "CYP2D6", "cometabolizes", NA, NA, NA, NA,
  "GRK4", "CYP2D6", "cometabolizes", NA, NA, NA, NA,
  "GRK5", "CYP2D6", "cometabolizes", NA, NA, NA, NA,
  "CETP", "SLCO1B1", "cometabolizes", NA, NA, NA, NA,
  "LPA", "SLCO1B1", "cometabolizes", NA, NA, NA, NA,
  "CETP", "CYP3A4", "cometabolizes", NA, NA, NA, NA,
  "LPA", "CYP3A4", "cometabolizes", NA, NA, NA, NA
)
```

This template directly reflects the mapped drug–gene pairs, cluster structure, and co-metabolism bridges described in your attached reports.[^1][^2][^3]

## Main network

Use one intervention-weighted bipartite-style network as the anchor figure. Genes and drugs should stay visually distinct, Undefined genes should be emphasized because they resolve the sparse periphery, and edge width should encode feature importance so readers can immediately spot FUROSEMIDE, CARVEDILOL, and SIMVASTATIN-centered risk structure.[^2][^3][^1]

```r
node_palette <- c(
  "Tier 1" = "#c0392b",
  "Tier 2" = "#f39c12",
  "Undefined" = "#8e44ad",
  "Drug" = "#5dade2"
)

graph_all <- tbl_graph(
  nodes = nodes,
  edges = edges %>% filter(relation %in% c("featureimportancedruggene", "cometabolizes")),
  directed = FALSE
) %>%
  activate(nodes) %>%
  mutate(
    degree = centrality_degree(),
    label_flag = tier %in% c("Tier 1", "Undefined") | name %in% c("FUROSEMIDE", "CARVEDILOL", "SIMVASTATIN")
  )

p_main <- ggraph(graph_all, layout = "fr") +
  geom_edge_link(
    aes(
      width = if_else(relation == "featureimportancedruggene", coalesce(importance, 0.02), 0.03),
      alpha = relation,
      color = relation
    ),
    show.legend = TRUE
  ) +
  geom_node_point(
    aes(size = degree, color = tier, shape = node_class)
  ) +
  geom_node_text(
    aes(label = if_else(label_flag, name, "")),
    repel = TRUE,
    size = 3
  ) +
  scale_color_manual(values = c(node_palette, "cometabolizes" = "#2e86c1", "featureimportancedruggene" = "#7f8c8d")) +
  scale_edge_color_manual(values = c(
    "featureimportancedruggene" = "#7f8c8d",
    "cometabolizes" = "#2e86c1"
  )) +
  scale_edge_width(range = c(0.4, 2.2)) +
  scale_shape_manual(values = c("gene" = 16, "drug" = 23, "phenotype" = 15)) +
  guides(edge_width = "none") +
  theme_graph(base_family = "sans") +
  labs(title = "PGx intervention network", subtitle = "Undefined genes integrated into actionable drug-centered clusters")
```

This figure is where you show that isolated or dangling nodes become clinically interpretable once mapped back to high-importance medications and Tier 1 metabolic cores.[^1][^2]

## Cohort facets

For Falls vs ED and 65–74 vs 75–84, build a reweighted network for each stratum. This is the clearest way to show that FUROSEMIDE dominates Falls 65–74 while CARVEDILOL dominates ED 65–74, with HYDROCHLOROTHIAZIDE rising in ED 75–84 and SIMVASTATIN appearing as a recurrent lipid anchor in fall cohorts.[^3][^1]

```r
make_cohort_plot <- function(outcome_sel, age_sel) {
  e_sub <- edges %>%
    filter(
      relation == "featureimportancedruggene",
      outcome == outcome_sel,
      age_band == age_sel
    )

  keep_nodes <- union(e_sub$from, e_sub$to)

  g_sub <- tbl_graph(
    nodes = nodes %>% filter(name %in% keep_nodes),
    edges = e_sub,
    directed = FALSE
  ) %>%
    activate(nodes) %>%
    mutate(
      degree = centrality_degree(),
      label_flag = TRUE
    )

  ggraph(g_sub, layout = "stress") +
    geom_edge_link(aes(width = importance), color = "#7f8c8d", alpha = 0.7) +
    geom_node_point(aes(size = degree, color = tier, shape = node_class)) +
    geom_node_text(aes(label = name), repel = TRUE, size = 3) +
    scale_color_manual(values = node_palette) +
    scale_shape_manual(values = c("gene" = 16, "drug" = 23, "phenotype" = 15)) +
    scale_edge_width(range = c(0.6, 3)) +
    theme_graph() +
    labs(title = paste(outcome_sel, age_sel))
}

p_fall_6574 <- make_cohort_plot("Falls", "65-74")
p_ed_6574   <- make_cohort_plot("ED", "65-74")
p_ed_7584   <- make_cohort_plot("ED", "75-84")
```

You can then assemble these with `patchwork`, and later add Falls 75–84 once the corresponding extracted edge table is ready from your source files.[^3][^1]

```r
(p_fall_6574 | p_ed_6574) / p_ed_7584
```


## Ego networks

The therapeutic cluster panels should be the most clinically readable figures because they convert the full topology into reviewable medication modules. Use one panel each for the adrenergic, diuretic, and lipid/statin clusters, with the drug fixed at center and nearby Tier 1 bridges pulled inward.[^1][^3]

```r
make_cluster_plot <- function(cluster_sel) {
  nodes_sub <- nodes %>% filter(cluster == cluster_sel | name %in% c("CYP2D6", "SLCO1B1", "CYP3A4", "ABCB1"))
  edges_sub <- edges %>%
    filter(from %in% nodes_sub$name, to %in% nodes_sub$name)

  g_sub <- tbl_graph(nodes = nodes_sub, edges = edges_sub, directed = FALSE)

  ggraph(g_sub, layout = "kk") +
    geom_edge_link(aes(color = relation, width = if_else(is.na(importance), 0.04, importance)), alpha = 0.8) +
    geom_node_point(aes(color = tier, shape = node_class), size = 6) +
    geom_node_text(aes(label = name), repel = TRUE, size = 3.2) +
    scale_color_manual(values = c(node_palette, "featureimportancedruggene" = "#7f8c8d", "cometabolizes" = "#2e86c1")) +
    scale_edge_color_manual(values = c("featureimportancedruggene" = "#7f8c8d", "cometabolizes" = "#2e86c1")) +
    theme_graph() +
    labs(title = paste(cluster_sel, "cluster"))
}

p_adrenergic <- make_cluster_plot("Adrenergic")
p_diuretic   <- make_cluster_plot("Diuretic")
p_lipid      <- make_cluster_plot("Lipid")

p_adrenergic | p_diuretic | p_lipid
```

These panels directly support intervention logic: beta-blocker review for the adrenergic module, diuretic review for the fall-linked hypertension cluster, and statin-pathway review for the lipid cluster.[^1]

## Time-to-event panel

The temporal figure should sit beside the network figures because it translates association into prevention timing. Your attached analysis reports a 3–6 week predictive window for medications such as FUROSEMIDE before falls, with median gaps of 25.5 days in Falls 65–74 and 37 days in Falls 75–84, so the visual should make that intervention window obvious.[^1]

```r
time_df <- tribble(
  ~outcome, ~age_band, ~drug, ~median_days_before_event, ~window_low, ~window_high,
  "Falls", "65-74", "FUROSEMIDE", 25.5, 21, 42,
  "Falls", "75-84", "FUROSEMIDE", 37.0, 21, 42
)

p_time <- ggplot(time_df, aes(y = paste(outcome, age_band), x = median_days_before_event)) +
  geom_segment(aes(x = window_low, xend = window_high, yend = paste(outcome, age_band)),
               linewidth = 4, color = "#aed6f1") +
  geom_point(size = 4, color = "#1f618d") +
  geom_text(aes(label = paste0(drug, " (", median_days_before_event, " d)")),
            nudge_y = 0.2, size = 3.5) +
  scale_x_reverse() +
  labs(
    title = "Medication lead-time before fall event",
    x = "Days before event",
    y = NULL
  ) +
  theme_minimal(base_size = 12)
```

That panel gives reviewers and clinicians a reason to act before the event rather than merely describing risk after the fact.[^1]

## Prevention framing

To use the visuals for reducing ED or fall outcomes, add one derived variable: an **intervention priority score**. A simple starting version can combine normalized feature importance, inverse rank, gene tier weight, and polypharmacy context, because your reports identify drug-level importance, Tier 1 metabolic bridging, and overall PGx medication burden as the key actionable signals.[^3][^1]

A practical scoring rule could be:

```r
cohort_scores <- edges %>%
  filter(relation == "featureimportancedruggene") %>%
  mutate(
    inv_rank = 1 / rank,
    tier_weight = case_when(
      from %in% c("ADD1","NEDD4L","PRKCA","YEATS4","CETP","LPA","ADRA2C","GRK4","GRK5","PTGFR","CES1") ~ 1.2,
      TRUE ~ 1.0
    ),
    intervention_priority = rescale(importance) * 0.5 +
      rescale(inv_rank) * 0.3 +
      rescale(tier_weight) * 0.2
  )
```

You can then map `intervention_priority` to edge glow, label order, or a side heatmap so the figure answers, “Which drug-gene pairs should be reviewed first to potentially avert the outcome?” rather than just, “Which nodes are connected?”[^3][^1]

## Output workflow

A clean figure workflow is:

1. Build a harmonized node/edge table from your underlying CSVs or extracted markdown mappings.[^2][^1]
2. Generate the four figure types above with a shared palette and legend.[^2][^3][^1]
3. Export as vector PDF or SVG for the manuscript and high-resolution PNG for slides.[^3][^1]
```r
ggsave("fig-main-network.pdf", p_main, width = 12, height = 9)
ggsave("fig-time-to-event.pdf", p_time, width = 8, height = 4.5)
ggsave("fig-clusters.pdf", p_adrenergic | p_diuretic | p_lipid, width = 14, height = 5)
```

The next best step is to turn this template into your actual dataset-specific script by reading your real `networknodes.csv`, `networkedges.csv`, and time-to-event file, then applying the same plotting grammar to the full cohort set.[^2][^1]

Would you like the next pass to be a complete end-to-end R script that reads assumed CSV filenames and outputs all four figures automatically?

<div align="center">⁂</div>

[^1]: Actionable-Mapping-Report_-Resolving-Undefined-Tier-Gene-Drug-Associations-in-Fall-and-ED-Cohorts.md

[^2]: Mapping-Undefined-Nodes-in-Actionable-Network-Graphs.md

[^3]: Pharmacogenomic-Networks-of-Medication-and-Emergency-Risk.md

