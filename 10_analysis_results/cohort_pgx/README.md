# Cohort PGx Network Topology

## Research questions this visual answers

- **Which pharmacogenes and drugs matter for this cohort and age band?** The network is built from **top drug names drawn from SHAP/FFA Consensus Filter feature importance**. We seed the graph with model-ranked drugs and their resolved CPIC genes, so the graph reflects what is driving the cohort.
- **How do genes, drugs, and phenotypes connect in the literature?** PharmGKB VIP reports and extracted relationships show gene–drug metabolism, drug–drug interactions, and gene–phenotype (e.g. adverse event) links, so we can see clinical context for the important features.
- **Where are the main clinical risks and guideline-backed genes?** Tier (PharmGKB/CPIC) and filter views highlight the most clinically actionable genes and interactions, reducing noise and aligning with evidence-based PGx.

**Feature importance drives this visual.** Top drug names come from the current SHAP/FFA Consensus Filter outputs; those drugs are resolved to CPIC pharmacogenes and used as seed nodes/edges in the NetworkX model so we understand what is driving our target cohorts.

### How features are filtered and used downstream

- **Top-N selection:** `fetch_vip_reports.py` reads ranked drug features from `10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/bin_models/{bin}/` and takes the **top-N consensus drug names** that the model uses.
- **Seeded graph edges:** Those top drugs are resolved to CPIC pharmacogenes and written as `*_seed_drug_features.csv` and `*_seed_drug_gene_edges.csv`. `build_network_topology.py` ingests the seed edge CSV and adds direct `feature_importance_drug_gene` NetworkX edges weighted by combined SHAP/FFA importance.
- **Network scope:** The multi-layer network (genes, seed drugs, literature drugs, phenotypes, interactions) is anchored to model-relevant drugs, then enriched with PharmGKB VIP text relationships.

---

## Overview

The **Cohort PGx** feature combines:
- **SHAP/FFA Consensus Filter feature importance** - Identifies top N drug features for a cohort/age band/density bin
- **PharmGKB VIP reports** - Fetches comprehensive clinical annotations, guidelines, and drug interactions
- **pytextrank** - Extracts key phrases and entities from VIP summary text
- **AWS Comprehend** (optional) - Medical entity recognition and key phrase extraction
- **NetworkX + Plotly** - Builds interactive multi-layer network topology with filtering

## Key Features

### Rich Data Layers

1. **Genes** - Color-coded by PharmGKB tier (Tier 1/2/3), sized by number of connections
   - Tier 1 (Red): Most clinically important pharmacogenes
   - Tier 2 (Orange): Well-established pharmacogenes
   - Tier 3 (Yellow): Emerging evidence pharmacogenes
   - Includes CPIC guideline status and AMP tier annotations

2. **Drugs** - Medications affected by gene variants
   - Direct gene-drug "metabolizes" relationships
   - Drug-drug interactions (inhibition, induction, combination effects)
   - Weighted by mention frequency in clinical text

3. **Phenotypes** - Adverse events and clinical outcomes
   - Extracted from VIP summaries (e.g., "Bleeding Risk", "QT Prolongation")
   - Gene-phenotype "affects_risk" relationships

4. **Drug-Drug Interactions** - Pharmacokinetic/pharmacodynamic interactions
   - Inhibition, induction, enhancement, combination effects
   - Evidence snippets from clinical text

### Interactive Filtering

Dropdown menu controls to toggle network views:
- **Show All**: Complete network (all layers visible)
- **Genes Only**: Just gene nodes and gene-gene connections
- **Genes + Drugs**: Gene-drug metabolism relationships
- **Genes + Phenotypes**: Gene-adverse event associations
- **Drug-Drug Interactions**: Pharmacokinetic interactions between drugs
- **Tier 1 Only**: Focus on most clinically important genes

### Weighted Edges

Edge thickness represents evidence strength:
- Mention frequency in VIP text (drugs/phenotypes)
- Evidence text length (drug-drug interactions)
- Normalized to 0-1 scale

## Workflow

### 1. Extract Top Genes from Feature Importance

**Script**: `fetch_vip_reports.py`

Extracts top N drug features from SHAP/FFA Consensus Filter outputs, resolves those drugs to CPIC genes, writes the seed drug and drug-gene edge tables, and fetches VIP reports from PharmGKB API with comprehensive clinical data.

**Drug names vs gene symbols:** The script only considers **drug_name** codes from SHAP/FFA Consensus Filter artifacts. Activity type = drug → token = drug name; only those tokens are resolved to genes. ICD/CPT codes are never passed to CPIC. PharmGKB gene API expects gene symbols (e.g. CYP2D6). The script resolves drug names to genes using:
- **CPIC drug list** (`5_pgx_analysis/data/cpic_drug_list.json`): known pharmacogene symbols pass through; drug names are mapped to their CPIC genes.
- **Global drug–CPIC mapping** (optional, `5_pgx_analysis/outputs/global/drug_cpic_mapping_global.csv`): APCD drug name → CPIC drug name → genes. Built from **final (cohort) feature importances** (`cohort_feature_importance.csv`) by `build_global_drug_cpic_mapping.py` (idempotent; use `--force` to rebuild).
- **Fuzzy match** (optional): if `5_pgx_analysis.map_drugs_to_genes` is available, unresolved tokens are fuzzy-matched to CPIC drugs. Only resolved gene symbols are sent to PharmGKB.

**Input**:
- `10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/bin_models/{bin}/consensus_features.json`
- `10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/bin_models/{bin}/combined_importance.csv`
- `5_pgx_analysis/data/cpic_drug_list.json` (for drug→gene resolution)
- `5_pgx_analysis/outputs/global/drug_cpic_mapping_global.csv` (optional, for better drug-name coverage)

**Idempotent**: If `{cohort}_{age_band}_vip_reports.json` already exists, fetch is skipped unless `--force` is used.

**Output**:
- `{cohort}_{age_band}_vip_reports.json` - VIP reports including:
  - `vipSummary` metadata when PharmGKB provides it. In the API schema this is optional; when present it is a dictionary with numeric `id` and string `html`, which are normalized as `vip_summary_id`, `vip_summary_html`, `vip_summary_text`, `vip_summary_present`, and `vip_summary_schema_valid`.
  - ClinPGx VIP page text fallback in `vip_text` when `vipSummary` is absent or too sparse.
  - `vipCitation` when PharmGKB provides it.
  - CPIC/AMP status
  - Tier classification
  - Genomic coordinates
- `{cohort}_{age_band}_seed_drug_features.csv` - ranked seed drug features with combined SHAP/FFA importance.
- `{cohort}_{age_band}_seed_drug_gene_edges.csv` - resolved seed drug→gene edges used to initialize NetworkX graph edges.

**Usage**:
```bash
python fetch_vip_reports.py \
  --cohort opioid_ed \
  --age-band 25-44 \
  --top-n 50 \
  --project-root /path/to/repo \
  --output-dir outputs/reports
```

### 2. Build Multi-Layer Network Topology

**Script**: `build_network_topology.py`

Processes VIP reports to extract entities, relationships, interactions, and build comprehensive network topology.

**Entity Extraction**:
- **Genes**: From VIP metadata (symbol, name, tier, CPIC/AMP status)
- **Drugs**: Pattern matching + Comprehend entities
- **Phenotypes**: Adverse event extraction from clinical text
  - Pattern matching: "risk of X", "adverse events: X", "X toxicity"
  - Common adverse events: bleeding, QT prolongation, myopathy, etc.

**Relationship Discovery**:
- **Seed Drug → Gene**: Direct model-seeded CPIC relationship weighted by combined SHAP/FFA importance
- **Gene → Drug**: Metabolizes/interacts (weighted by mention frequency)
- **Gene → Phenotype**: Affects risk (weighted by mention frequency)
- **Gene ↔ Gene**: Co-metabolizes (shared drug targets)
- **Drug ↔ Drug**: Interactions (inhibition, induction, enhancement)

**Network Analysis**:
- Node degree centrality (number of connections)
- Graph density and clustering
- Hub identification (genes with most connections)
- Tier distribution (Tier 1/2/3 breakdown)

**Output**:
- `network_topology.html` - Interactive Plotly visualization with filters
- `network_topology.png` - Static GitHub-friendly preview for README/notebook embedding
- `network_nodes.csv` - Node data (id, type, label, degree, tier, CPIC status)
- `network_edges.csv` - Edge data (source, target, relation, weight, mentions, evidence)
- `drug_interactions.csv` - Drug-drug interactions (drug1, drug2, type, evidence)
- `key_phrases.json` - Extracted key phrases per gene
- `network_stats.json` - Network statistics (nodes, edges, density, tier counts)
- `gene_metadata.json` - Gene tier and CPIC information

**Usage**:
```bash
python build_network_topology.py \
  --reports outputs/reports/opioid_ed_25_44_vip_reports.json \
  --output-dir outputs/networks/opioid_ed/25_44

# Skip upload to dashboard S3 (local-only)
python build_network_topology.py \
  --reports outputs/reports/opioid_ed_25_44_vip_reports.json \
  --output-dir outputs/networks/opioid_ed/25_44 \
  --no-upload

# Skip AWS Comprehend (use pytextrank only)
python build_network_topology.py \
  --reports outputs/reports/opioid_ed_25_44_vip_reports.json \
  --output-dir outputs/networks/opioid_ed/25_44 \
  --no-comprehend

# Validate AWS Comprehend output (writes summaries + full dumps by default)
python build_network_topology.py \
  --reports outputs/reports/opioid_ed_25_44_vip_reports.json \
  --output-dir outputs/networks/opioid_ed/25_44 \
  --comprehend-audit-dir outputs/networks/opioid_ed/25_44/comprehend_audit

# Summary-only (no full dumps)
python build_network_topology.py \
  --reports outputs/reports/opioid_ed_25_44_vip_reports.json \
  --output-dir outputs/networks/opioid_ed/25_44 \
  --comprehend-audit-dir outputs/networks/opioid_ed/25_44/comprehend_audit \
  --comprehend-summary-only
```

## Installation

### Required Dependencies

```bash
# Core NLP + network analysis
pip install spacy pytextrank networkx plotly beautifulsoup4

# Download spaCy model
python -m spacy download en_core_web_sm

# AWS Comprehend (optional)
pip install boto3
```

### AWS Comprehend Setup (Optional)

If using AWS Comprehend for enhanced medical entity recognition:

1. **Install boto3**: `pip install boto3`
2. **Configure AWS credentials**: `aws configure` or set environment variables
3. **Verify access**:
   ```python
   import boto3
   client = boto3.client("comprehend", region_name="us-east-1")
   print(client.detect_entities(Text="Test", LanguageCode="en"))
   ```

**Note**: AWS Comprehend is optional. pytextrank provides entity extraction without AWS dependencies.

## Notebook Integration

Run from **notebook 4** ([4_dashboard_visuals.ipynb](../../4_dashboard_visuals.ipynb)):

1. **Fetch VIP reports**: Parallel fetch for all cohort/age_band combinations (max 2 workers for API rate limiting)
2. **Build networks**: Parallel network building (max 4 workers); each build **uploads to dashboard S3** automatically, consistent with other review visualizations.
3. **View outputs**: Interactive visualization previews

Notebook 5 (Step 6: Sync Dashboard Frontend) syncs `visualizations/cohort_pgx/` to S3 when you deploy, same as other dashboard visuals.

## Dashboard Integration

### Build and upload

Upload to the dashboard S3 bucket happens **inside** `build_network_topology.py` after writing outputs. No separate upload step is required.

- **Results workflow notebooks/scripts**: Run fetch → build. Each build uploads to S3 when upload is enabled.
- **run_dashboard_visuals.py**: Runs full step-9 pipeline including Cohort PGx (fetch VIP reports, build network topology; each build uploads to S3). Use `--skip-cohort-pgx` to omit Cohort PGx; use `--no-cohort-pgx-upload` to build but not upload.

Outputs go to `10_analysis_results/visualizations/cohort_pgx/networks/{cohort}/{age_band_fname}/` locally. The builder uploads to `{S3_DASHBOARD_PREFIX}/visualizations/cohort_pgx/networks/{cohort}/{age_band}/` when upload is enabled.

**Logs (Cohort PGx):** When you run `fetch_vip_reports.py` from the command line, logs are written to **`9_dashboard_visuals/logs/cohort_pgx/fetch_vip_reports_{cohort}_{age_band_fname}.log`** (and to stderr). Use `--log-file PATH` to override. `build_network_topology.py` uses `print()` only; its output appears in the terminal or notebook cell output.

### Upload to S3 (production)

**Notebook 5** (Step 6) runs `sync_cohort_pgx_to_s3.py`, which maps EC2 dirs `25_44` to S3 keys `25-44`. Lambda expects `{S3_DASHBOARD_PREFIX}/cohort_pgx/networks/{cohort}/{age_band}/network_topology.html` (hyphen in age_band).

To re-sync without a full deploy (e.g. manual or CI), use the current visualization sync/deploy workflow for `10_analysis_results/visualizations/cohort_pgx/`.

```bash
aws s3 sync 10_analysis_results/visualizations/cohort_pgx/ s3://<dashboard-bucket>/<dashboard-prefix>/visualizations/cohort_pgx/
```

### Lambda API Endpoint

Add to `lambda_function.py`:

```python
@app.get("/visualizations/cohort-pgx")
def get_cohort_pgx_viz(cohort: str, age_band: str):
    """Get Cohort PGx network topology visualization URLs."""
    # S3 path uses hyphen (25-44); no conversion needed for URL
    base_url = f"https://{DASHBOARD_BUCKET}/{S3_PREFIX}/cohort_pgx/networks/{cohort}/{age_band}"
    
    return {
        "network_topology": f"{base_url}/network_topology.html",
        "network_nodes": f"{base_url}/network_nodes.csv",
        "network_edges": f"{base_url}/network_edges.csv",
        "drug_interactions": f"{base_url}/drug_interactions.csv",
        "gene_metadata": f"{base_url}/gene_metadata.json",
        "network_stats": f"{base_url}/network_stats.json",
        "key_phrases": f"{base_url}/key_phrases.json"
    }
```

### Frontend Tab

Add new tab to `index.html`:

```html
<div class="tab-pane fade" id="cohort-pgx-tab">
  <h3>Cohort PGx Network Topology</h3>
  <div id="cohort-pgx-container">
    <iframe id="network-iframe" style="width:100%; height:800px; border:1px solid #ddd;"></iframe>
  </div>
  <div id="network-stats" class="mt-3">
    <!-- Network statistics displayed here -->
  </div>
</div>
```

JavaScript to load network:

```javascript
async function loadCohortPgxNetwork(cohort, ageBand) {
  const response = await fetch(`/visualizations/cohort-pgx?cohort=${cohort}&age_band=${ageBand}`);
  const data = await response.json();
  
  // Load network visualization
  document.getElementById('network-iframe').src = data.network_topology;
  
  // Load and display statistics
  const statsResponse = await fetch(data.network_stats);
  const stats = await statsResponse.json();
  displayNetworkStats(stats);
}
```

## Output Structure

```
10_analysis_results/visualizations/cohort_pgx/
├── reports/
│   ├── opioid_ed_25_44_vip_reports.json          # Full VIP reports with clinical text
│   ├── opioid_ed_25_44_vip_reports_summary.json  # Summary statistics
│   ├── opioid_ed_25_44_seed_drug_features.csv     # Ranked top consensus drug features
│   ├── opioid_ed_25_44_seed_drug_gene_edges.csv   # Seed NetworkX drug-gene edges
│   └── ...
└── networks/
    ├── opioid_ed/
    │   ├── 25_44/
    │   │   ├── network_topology.html         # Interactive visualization with filters
    │   │   ├── network_nodes.csv             # Nodes (gene/drug/phenotype, tier, CPIC)
    │   │   ├── network_edges.csv             # Edges (source, target, relation, weight)
    │   │   ├── drug_interactions.csv         # Drug-drug interactions with evidence
    │   │   ├── gene_metadata.json            # Gene tiers and CPIC status
    │   │   ├── key_phrases.json              # Top phrases per gene
    │   │   └── network_stats.json            # Network statistics
    │   └── ...
    └── non_opioid_ed/
        └── ...
```
```

## Interpreting the Visualization

### Node Types & Colors

**Genes** (circles, sized by connections):
- **Red (Tier 1)**: Most clinically important - AMP/CPIC guidelines, strong evidence
- **Orange (Tier 2)**: Well-established pharmacogenes with clinical annotations
- **Yellow (Tier 3)**: Emerging evidence, research implications
- **Gray**: Unknown tier classification

**Drugs** (diamonds, cyan):
- Medications affected by gene variants
- Size indicates number of genes affecting the drug

**Phenotypes** (squares, mint green):
- Adverse events or clinical outcomes
- Extracted from VIP clinical summaries

### Edge Types & Colors

- **Dark green**: Seed Drug → Gene from top consensus feature importance
- **Gray**: Gene → Drug (metabolizes) - pharmacokinetic relationship
- **Pink**: Gene → Phenotype (affects_risk) - clinical outcome association
- **Blue**: Gene ↔ Gene (co_metabolizes) - shared drug targets
- **Purple**: Drug ↔ Drug (metabolic interaction)
- **Red**: Drug ↔ Drug (inhibition)
- **Green**: Drug ↔ Drug (induction)
- **Gold**: Drug ↔ Drug (combination effect)
- **Tomato**: Drug ↔ Drug (enhancement)

**Edge thickness** = evidence strength (combined SHAP/FFA importance for seed edges, mention frequency, or text detail)

### Interactive Controls

Use the **Filter View** dropdown (top-left) to explore different layers:

1. **Show All**: Complete network - see the full complexity
2. **Genes Only**: Focus on gene-gene relationships through shared pathways
3. **Genes + Drugs**: Gene-drug metabolism - which genes affect which medications
4. **Genes + Phenotypes**: Gene-adverse events - clinical risk associations
5. **Drug-Drug Interactions**: Pharmacokinetic interactions requiring monitoring
6. **Tier 1 Only**: Focus on most clinically actionable genes (CPIC guidelines)

### How to Use

**For Clinicians**:
- Check if patient's adverse event risk genes (red/orange nodes) affect their current medications
- Review drug-drug interactions for polypharmacy patients
- Identify CPIC guideline genes (✓ CPIC in hover text) requiring PGx testing

**For Researchers**:
- Identify hub genes (large nodes, many connections) - high-value PGx targets
- Compare networks across cohorts to find cohort-specific patterns
- Analyze phenotype associations for adverse event prediction

**For Pharmacists**:
- Review gene-drug relationships before dispensing high-risk medications
- Check for drug-drug interactions in complex regimens
- Determine if PGx testing would benefit the patient

## Research Applications

### 1. Cohort-Specific Pharmacogenomics

- Identify gene-drug interactions unique to each cohort
- Compare network topology across age bands
- Discover hub genes (high centrality) driving adverse events

### 2. Drug Interaction Patterns

- Visualize polypharmacy complexity
- Identify shared metabolic pathways
- Find drug combinations requiring PGx monitoring

### 3. Age-Related PGx Differences

- Compare network density across age bands
- Identify age-specific gene-drug relationships
- Guide age-appropriate PGx testing strategies

## API Details

### PharmGKB REST API v1

**Documentation**: https://www.postman.com/pharmgkb/pharmgkb-api/documentation/g9rp4zr/pharmgkb-rest-api

**Endpoints Used**:
- `GET /v1/data/gene?symbol={GENE}` - Fetch gene VIP data
- Rate limit: 0.5s delay between requests (conservative)

**VIP URLs**:
- Format: `https://www.clinpgx.org/vip/{PA_ID}/overview`
- Example: `https://www.clinpgx.org/vip/PA166170325/overview` (CYP2D6)

### AWS Comprehend

**APIs Used**:
- `detect_entities()` - General entity recognition
- `detect_key_phrases()` - Key phrase extraction
- Text limit: 5000 bytes per request

**Entity Types**:
- `COMMERCIAL_ITEM`, `TITLE` → Drugs
- `EVENT`, `OTHER` → Phenotypes

## Performance

### Runtime Estimates

- **Fetch VIP reports**: ~1-2 minutes per cohort/age_band (API rate limited)
- **Build network**: ~2-5 minutes per cohort/age_band (depends on text volume)
- **Total for 16 combinations** (2 cohorts × 8 age bands): ~50-100 minutes

### Optimization Tips

1. **Parallel execution**: Max 2 workers for VIP fetch (API rate limits), 4 for network build
2. **Skip Comprehend**: Use `--no-comprehend` for faster processing (pytextrank only)
3. **Skip VIP pages**: Use `--no-vip-pages` to skip HTML fetching (uses API data only)
4. **Cache results**: Idempotent - skips existing outputs

## Troubleshooting

### Missing Feature Importance

**Error**: "No genes found"

**Solution**: Ensure feature importance exists:
- Notebook 3/4 scenario artifacts: `10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/bin_models/{bin}/consensus_features.json`
- Matching importance file: `10_analysis_results/visualizations/scenario/{cohort}/{age_band_fname}/bin_models/{bin}/combined_importance.csv`

### Drug Names Passed as Genes (404 from PharmGKB)

**Error**: "No results matching criteria" for tokens like AMOXICILLIN, AZITHROMYCIN (drug names, not gene symbols).

**Solution**: The script now resolves drug names to genes via CPIC. Ensure:
- `5_pgx_analysis/data/cpic_drug_list.json` exists (from CPIC / `fetch_cpic_drug_list.py` or `cpicPairs.csv`).
- Optionally run `5_pgx_analysis/build_global_drug_cpic_mapping.py` to build `outputs/global/drug_cpic_mapping_global.csv` so feature drug names (e.g. from your cohort) map to CPIC drugs and thus to genes.
- Logs will show "Resolved drug name to genes (CPIC exact|global mapping|fuzzy): …" for each resolution; unresolved tokens are skipped and not sent to PharmGKB.

### API Rate Limiting

**Error**: "429 Too Many Requests"

**Solution**: Increase `REQUEST_DELAY` in `fetch_vip_reports.py` (default 0.5s)

### AWS Comprehend Errors

**Error**: "Could not initialize AWS Comprehend"

**Solution**: 
- Use `--no-comprehend` flag (pytextrank still works)
- Check AWS credentials: `aws configure`
- Verify region: `us-east-1` recommended

### spaCy Model Missing

**Error**: "Can't find model 'en_core_web_sm'"

**Solution**: `python -m spacy download en_core_web_sm`

## References

- **PharmGKB**: https://www.pharmgkb.org
- **ClinPGx**: https://www.clinpgx.org
- **pytextrank**: https://github.com/DerwenAI/pytextrank
- **AWS Comprehend**: https://aws.amazon.com/comprehend/
- **NetworkX**: https://networkx.org/
- **Plotly**: https://plotly.com/python/

## License

See main repository LICENSE.
