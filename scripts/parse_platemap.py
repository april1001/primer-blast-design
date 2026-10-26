"""Parse a Dharmacon / Horizon siRNA plate map into a primer-design job list.

Usage:
    python parse_platemap.py <platemap.xls|xlsx|csv> <jobs.csv>

One row per gene (the plate map has one row per siRNA duplex). Control wells are
mapped to their target gene where one exists; non-targeting controls are skipped.
Output columns:
    gene, gene_id, well, candidate_nm, n_candidate_nm, gene_accession, needs_mane_lookup, note
gene_accession is pre-filled only when exactly one NM_ accession is listed;
otherwise it is left empty and needs_mane_lookup is True.
"""

import sys

import pandas as pd

# Dharmacon control wells -> (gene symbol, NCBI Gene ID). Verify IDs on NCBI Gene.
CONTROL_TARGETS = {
    "cyclophilin": ("PPIB", 5479),
    "gapd": ("GAPDH", 2597),
}


def read_table(path):
    if path.lower().endswith(".csv"):
        raw = pd.read_csv(path, header=None)
    else:
        try:
            raw = pd.read_excel(path, header=None)
        except ImportError:
            sys.exit("Reading .xls needs xlrd: pip install xlrd")
    # Find the header row that holds the column names
    for i, row in raw.iterrows():
        values = [str(v).strip().lower() for v in row.values]
        if "gene symbol" in values and "gene accession" in values:
            table = raw.iloc[i + 1:].copy()
            table.columns = [str(v).strip() for v in row.values]
            return table.dropna(how="all")
    sys.exit("Could not find a header row with 'Gene Symbol' and 'Gene Accession'.")


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python parse_platemap.py <platemap> <jobs.csv>")
    table = read_table(sys.argv[1])

    jobs = []
    seen = set()
    for _, row in table.iterrows():
        symbol = str(row.get("Gene Symbol", "")).strip()
        if not symbol or symbol.lower() == "nan" or symbol in seen:
            continue
        seen.add(symbol)
        well = row.get("Well")
        gene_id = row.get("GENE ID")
        accessions = [] if pd.isna(row.get("Gene Accession")) else \
            [a.strip() for a in str(row["Gene Accession"]).split(",") if a.strip()]
        nm = [a for a in accessions if a.startswith("NM_")]
        note = ""

        if "control" in symbol.lower():
            target = next((v for k, v in CONTROL_TARGETS.items() if k in symbol.lower()), None)
            if target is None:
                print(f"Skipped control well {well}: {symbol}")
                continue
            note = f"control well '{symbol}' mapped to target gene"
            symbol, gene_id = target
            nm = []

        jobs.append({
            "gene": symbol,
            "gene_id": int(gene_id) if pd.notna(gene_id) else None,
            "well": well,
            "candidate_nm": ",".join(nm),
            "n_candidate_nm": len(nm),
            "gene_accession": nm[0] if len(nm) == 1 else "",
            "needs_mane_lookup": len(nm) != 1,
            "note": note,
        })

    out = pd.DataFrame(jobs)
    out.to_csv(sys.argv[2], index=False)
    print(f"Wrote {sys.argv[2]}: {len(out)} genes, "
          f"{int(out['needs_mane_lookup'].sum())} need a MANE Select lookup")


if __name__ == "__main__":
    main()
