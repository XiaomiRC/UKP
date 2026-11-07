# Browser-only interface

The no-install, local-processing frontend is in [browser/](browser/README.md). Use this for GitHub Pages; the earlier `web/` FastAPI prototype is not used by the static application.

# UKP SAC Investigator

A rule-based tool (no AI at run time) that automates the two investigations previously done by prompting
Claude for each SAC:

1. **SAC vs OneBill reconciliation**: SAC 360 report against the VP*.csv bills.
2. **P06 UKP deep dive**: the WD4 / 24-month P&L, Marginbase circuit and voice extracts, and the Customer2SAC mapping.

For each SAC it produces the same three Excel files as before. It also writes a **Power BI dataset** that grows with every SAC you run.

## Folder layout
```
inputs/sac_reports/   <SAC>_<NAME>_<date>.xlsx      (SAC 360 report)
inputs/bills/         VP*.csv                        (all OneBills; each SAC picks the bills its report references)
inputs/P06/           the 8 period .xlsb files       (inputs/P03 = older set)
outputs/<SAC>/        SAC_vs_OneBill_Reconciliation_<SAC>.xlsx
                      <SAC>_UKP_Deep_Dive_Analysis.xlsx   (incl. Data Sources sheet)
                      <SAC>_UKP_Tracker_Format.xlsx       (same columns as UKP tracker.xlsx)
dataset/              CSV star schema for Power BI
powerbi/              UKP_Dashboard.pbip (Power BI Project) + build_pbip.py
config/rules.yaml     editable thresholds and known shared bills
```

## Run it
Windows: double-click `run_sac.bat` and type a SAC code, or `ALL`.

Command line:
```
python run.py --sac 941BS            # one SAC (reconciliation + deep dive)
python run.py --all                  # every SAC report in inputs/sac_reports
python run.py --sac X6510 --period inputs/P03
python benchmark.py                  # accuracy vs the AI chat -> dataset/fact_benchmark.csv
python powerbi/build_pbip.py         # rebuild the Power BI project from dataset/
python -m pytest -q                  # golden tests
```
The first run parses the large .xlsb files (about 3 minutes) and caches them in `.cache/`. After that each SAC takes about 10 seconds.
To start a new period, put the new .xlsb set in `inputs/P07/` and pass `--period inputs/P07`.

## Power BI dashboard
1. Run the tool at least once so that `dataset/` exists.
2. Open `powerbi/UKP_Dashboard.pbip` in **Power BI Desktop** (Windows; enable *File → Options → Preview features →
   Power BI Project (.pbip) save option* if your version asks).
3. Go to *Transform data → Edit parameters* and set **DatasetFolder** to the full path of the `dataset` folder,
   **ending with a backslash**, for example `C:\UKP\dataset\`. Then click **Refresh**.
4. Save it as a .pbix, or publish it to the Power BI Service to share with stakeholders.

Pages: **Portfolio · Reconciliation · P&L Deep Dive · Circuit & Voice Evidence · Findings & Tracker · Accuracy & Controls**.

If the report layout fails to open (the .pbip was generated, not saved by Desktop), the semantic model still holds all
tables, relationships and measures. Delete `powerbi/UKP_Dashboard.Report/report.json`, open the model, and add
visuals using the measures listed in `powerbi/build_pbip.py` (`MEASURES`) and the page plan in `pages()`.

## The rules
| Area | Rule |
|---|---|
| Matching | SAC Billing Account ↔ bill Source account; Service number (with /0001 removed) ↔ Telephone No / Service ID |
| Shared bills | Bulk if the SAC Onebill tab says Bulk/MSfBT, if the bill is listed in `known_bulk_bills`, or if it has >50 accounts with <20% in the SAC report. Only the customer's own lines are kept |
| Bill files | Empty file, file name ≠ VP in the rows, different bill date, duplicate file, credit-only bill, multi-month rental lines, line total ≠ Total row |
| Reasons | Mobile system, bill not supplied, bill empty, contract ended (stale), £0 item, or "CHASE" (on a supplied bill but not billed) |
| P&L flags | Negative revenue with no inventory (the Dorma pattern) · cost with no revenue · revenue stopped or turned to credits · one-off entry · cost moved between BT entities · mirror entries on another SAC · elimination pair |
| Evidence | Circuit rental (product extract) vs UKP cost for the latest period; voice inventory by SAC and billing account |
| Mapping | Customer name mapped to another SAC; legal entities with no mapping; circuits with no cost; missing World Key |
| Controls | Every run records PASS/WARN/FAIL checks (totals tie, tracker sums to the P&L, WD4 = 24-month CY) in `fact_checks` |

## Accuracy against the AI chat
`benchmark.py` re-runs the 11 SACs from the chat and compares 102 figures:
- 96 are reproduced exactly.
- 4 were AI errors: the two shared-bill mistakes on TEST02, the shared-bill mistake on X0882, and the X6510 FY25 total, which quoted the Btnet-only figure.
- 2 are method differences: the app matches more service lines.
- 0 are unexplained.

The results are on the *Accuracy & Controls* page.
