---
name: "primer-blast-design"
description: Design PCR / qPCR primer pairs for one or more genes with NCBI Primer-BLAST (https://www.ncbi.nlm.nih.gov/tools/primer-blast/) by driving the web page in Chrome (Claude in Chrome), then fill the top primer pair of each gene into an Azenta oligo order form (xlsx). Use this skill whenever the user wants primers designed or ordered, asks to "run Primer-BLAST", gives gene accessions (NM_/XM_/NR_), sequences, a gene table, or an siRNA plate map (Dharmacon / Horizon) and wants primer pairs, e.g. for qPCR knockdown validation, or mentions PCR product size or primer Tm settings, even if they do not name Primer-BLAST explicitly.
compatibility: Requires the claude-in-chrome browser tools (Chrome extension connected) and Python with pandas + openpyxl (and xlrd for .xls plate maps).
---

# Primer-BLAST primer design → Azenta oligo order form

Design primer pairs on NCBI Primer-BLAST for each gene the user provides, with
user-set PCR product size and primer Tm, and write the top-ranked pair of each gene into
the Azenta oligo order form (`assets/azenta_oligo_template.xlsx`).

## Overview of the workflow

1. Parse the input into a job list (one job = one gene accession or sequence).
1b. For genes with several RefSeq mRNA candidates, pick the MANE Select transcript.
2. Show the job list + parameters to the user and get confirmation.
3. For each job: fill the Primer-BLAST form in Chrome, **ask the user before clicking "Get Primers"**, wait for results, read primer pair 1.
4. Write results to JSON, run `scripts/write_primer_table.py` to fill the order form, present the file.

Before acting, tell the user in one or two sentences what you are about to do.
Keep browser actions visible and minimal; do not run long silent bursts of tool calls.

## Step 1 — Parse the input

The template for each gene is a **Gene Accession** (RefSeq or GenBank nucleotide accession,
e.g. `NM_000546.6`, `XM_027395111.2`, `NR_xxx`), or a raw sequence.

| Input form | Example | How to handle |
|---|---|---|
| Gene Accession | `NM_000546.6` | Use directly as the PCR template. Keep the version suffix if given. |
| Raw sequence / FASTA | `>TP53_cds\nATGG...` | Use as template. Strip whitespace/numbers; only A/C/G/T/N (U → T). FASTA header = gene name. |
| Table (CSV / xlsx / pasted) | see `assets/input_template.csv` | One row per job; columns below. |
| siRNA plate map (Dharmacon / Horizon, .xls/.xlsx) | columns Plate, Well, ..., Gene Symbol, GENE ID, Gene Accession, ..., Sequence | Run `scripts/parse_platemap.py` (below). |

Table columns (case-insensitive; `gene` + `gene_accession` are required):

- `gene` — gene name, used for the Oligo Name (`<gene>_Fwd`, `<gene>_Rev`)
- `gene_accession` — nucleotide accession (or a sequence)
- `organism` — optional per-row override of the specificity-check organism
- `product_min`, `product_max` — optional per-row PCR product size (bp)
- `tm_min`, `tm_opt`, `tm_max` — optional per-row primer Tm (°C)

If a table uses different column names (e.g. "Accession", "RefSeq"), map them and tell the user the mapping.
If `gene` is missing, use the accession without version as the name.

If the user gives something that is not an accession or sequence (a numeric NCBI Gene ID
like `7157`, or a gene symbol like `TP53`), do not paste it into Primer-BLAST: a number
would be read as a GI, which is a different record. Ask the user for the Gene Accession.

### siRNA plate maps

```bash
python <skill>/scripts/parse_platemap.py <platemap.xls> /home/claude/jobs.csv
```

The script finds the header row, keeps one row per gene (a plate map has one row per siRNA
duplex), and writes `gene, gene_id, well, candidate_nm, n_candidate_nm, gene_accession,
needs_mane_lookup, note`. It handles control wells: "Cyclophilin Control" → PPIB (Gene ID 5479),
"GAPD Control" → GAPDH (Gene ID 2597); non-targeting controls are skipped. Tell the user which
control wells were mapped or skipped.

The plate map's `Sequence` column holds siRNA sequences (19 nt, with U). They are **not** PCR
templates; never use them as input. XM_ (predicted) accessions are ignored as templates.

Basic accession check: matches a pattern like `^[A-Z]{1,2}_?\d+(\.\d+)?$`. Flag anything else.

## Step 1b — Choose the transcript: MANE Select

When a gene has more than one NM_ candidate (or none, e.g. a mapped control), use the
**MANE Select** RefSeq transcript as the template:

1. Open `https://www.ncbi.nlm.nih.gov/gene/<GENE ID>` (read-only navigation, no form submission).
2. With `get_page_text`, find the transcript labelled "MANE Select" in the RefSeq section and
   record its NM_ accession (with version).
3. Set `accession_source` to `MANE Select`. If the MANE accession is not in the plate map's
   candidate list (e.g. a newer version), use the MANE one and say so in the summary.
4. If no MANE Select is shown, ask the user which transcript to use.

Genes with exactly one NM_ candidate use it directly (`accession_source: "single NM in input"`).
Accessions the user typed directly: `accession_source: "user"`.

Do the lookups one gene at a time and report progress briefly (e.g. "10/21 done").

## Step 2 — Parameters and confirmation

Global parameters (per-row table values override these):

| Primer-BLAST field | Parameter | Default |
|---|---|---|
| PCR product size — Min | `product_min` | 70 |
| PCR product size — Max | `product_max` | 200 |
| Primer melting temperatures (Tm) — Min | `tm_min` | 57.0 |
| Primer melting temperatures (Tm) — Opt | `tm_opt` | 60.0 |
| Primer melting temperatures (Tm) — Max | `tm_max` | 63.0 |
| Primer Pair Specificity Checking — Organism | `organism` | Homo sapiens |
| "Allow primer to amplify mRNA splice variants" checkbox | `splice_variants_allowed` | checked when the template is a RefSeq mRNA accession (NM_); unchecked for raw sequences |

With this box checked, products from other transcript variants of the same gene are treated as
intended targets, not as off-target products. This is the right setting for knockdown
validation, where the primers should detect the gene's transcripts broadly.

Leave every other field on the page at its default unless the user asks.

Validate before submitting:
- `product_min < product_max`, both positive integers.
- `tm_min <= tm_opt <= tm_max`.

Show the user a compact table of all jobs (gene, accession, organism, product size, Tm) and
ask for confirmation before opening any submission.

## Step 3 — Run each job in Chrome

Load the browser tools with `tool_search` (e.g. query "chrome navigate form") before first use.

For each job:

1. Open `https://www.ncbi.nlm.nih.gov/tools/primer-blast/` in a tab of the MCP tab group.
2. Locate fields **by their visible labels** with `find` / `read_page`, not by hard-coded IDs
   (NCBI can change the page). For reference, the underlying form names have historically been:
   template textarea `INPUT_SEQUENCE`; `PRIMER_PRODUCT_MIN`, `PRIMER_PRODUCT_MAX`;
   `PRIMER_MIN_TM`, `PRIMER_OPT_TM`, `PRIMER_MAX_TM`; organism text box `ORGANISM`.
   Verify against the live page.
3. Fill in:
   - "PCR Template — Enter accession, gi, or FASTA sequence": the accession, or the sequence in FASTA form (`>gene\nSEQUENCE`).
   - PCR product size Min / Max (clear existing values first).
   - Primer melting temperatures (Tm) Min / Opt / Max (clear existing values first).
   - The "Allow primer to amplify mRNA splice variants" checkbox, set per `splice_variants_allowed`
     (find it by its label text; its exact location on the page may vary).
   - Organism under "Primer Pair Specificity Checking Parameters". The box autocompletes;
     choose the matching suggestion (e.g. "Homo sapiens (taxid:9606)").
4. Read the filled values back from the page and check they match the job record.
5. **Ask the user for permission to submit** (gene, accession and parameters in one line).
   Submitting a web form always needs an explicit "yes" in chat, per job. Do not reuse an earlier yes for a later job.
6. Click "Get Primers". The page shows a "job is running" status and refreshes itself.
   Re-check with `get_page_text` every ~15–30 s. If still running after ~10 min, tell the user
   and offer to keep waiting or skip.
7. Record the results page URL in `result_url`.

### Pages that need a decision (stop and ask the user)

- **Intermediate page asking to choose target templates** or whether to submit anyway: this
  is another form submission, so explain what the page asks and get a yes before clicking.
- **"No primers found"** / **"No target templates were found"**: record `status: "no_primers"`
  with the page message. Suggest one change (widen product size or Tm range, or a different
  transcript accession) and ask whether to rerun.
- **Error / invalid accession**: record `status: "error"` with the message, tell the user, move on.

Never solve CAPTCHAs or bypass bot checks. If one appears, stop and ask the user to handle it.

## Step 4 — Read primer pair 1

Use `get_page_text` on the results page. Under "Detailed primer reports", take **Primer pair 1**
only (Primer-BLAST's top-ranked pair). It has a Forward and a Reverse row with:
Sequence (5'->3'), Template strand, Length, Start, Stop, Tm, GC%, Self complementarity,
Self 3' complementarity; then "Product length". Note any unintended products listed for this pair.

Copy numbers exactly as shown; do not recompute Tm or GC%. Absent field → `null`.

## Step 5 — Export to the Azenta order form

Write one JSON file, e.g. `/home/claude/primer_results.json`:

```json
{
  "run_date": "YYYY-MM-DD",
  "jobs": [
    {
      "gene": "TP53", "gene_accession": "NM_000546.6", "accession_source": "MANE Select",
      "splice_variants_allowed": true, "organism": "Homo sapiens",
      "product_min": 70, "product_max": 200, "tm_min": 57, "tm_opt": 60, "tm_max": 63,
      "status": "ok", "message": "", "result_url": "https://...",
      "pair": {
        "fwd_seq": "...", "fwd_len": 20, "fwd_tm": 60.03, "fwd_gc": 55.0,
        "rev_seq": "...", "rev_len": 20, "rev_tm": 59.87, "rev_gc": 50.0,
        "product_length": 150, "specificity": "none reported"
      }
    }
  ]
}
```

Then run (absolute path to this skill's folder):

```bash
python <skill>/scripts/write_primer_table.py /home/claude/primer_results.json \
    /mnt/user-data/outputs/Azenta_oligo_order.xlsx \
    --log /mnt/user-data/outputs/primer_design_log.csv
```

The script copies `assets/azenta_oligo_template.xlsx` and fills sheet
"Azenta Oligo Primer List", two rows per successful gene:

| Column | Value |
|---|---|
| Oligo # | running number 1, 2, 3, ... |
| Oligo Name | `<gene>_Fwd`, `<gene>_Rev` |
| Sequence - 5' to 3' | primer sequence |
| Length | primer length (nt) |
| GC | GC% from Primer-BLAST (e.g. 55.0) |
| Tm (°C) | Tm from Primer-BLAST |
| Scale | `25 nmole` |
| Purification | `Desalt` |

Genes with status other than `ok` are not written to the form. If the user supplies their
own (newer) Azenta template, pass it with `--template <path>`.

The design log (one row per gene: accession and its source, splice-variant setting,
parameters, status, product length, specificity, result URL) is a separate CSV so the
order form stays upload-ready.

Present the xlsx and the log with `present_files`. In chat, give a short summary: genes written to the
form, product length of each pair, any unintended products, and which genes failed and why.
Do not paste the full table into chat.

## Notes

- Write all output files in English.
- Primer-BLAST result pages expire; `result_url` is for quick re-checking soon after the run.
- Exon-junction spanning, primer position ranges and other Primer-BLAST options are set only
  when the user asks; mention them in the chat summary when used.
