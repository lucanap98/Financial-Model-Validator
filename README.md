# Financial Model Validator

Automated integrity checks for financial projection models.

Before trusting any projection model in a valuation or due diligence context, a set of consistency checks should pass — the balance sheet must tie, the EBITDA bridge must close, cash must roll forward, tax and depreciation assumptions must exist. In practice, these checks are done by eye, cell by cell. This tool automates them.

Built from real transaction advisory experience: every check in this repo corresponds to an issue I've actually found reviewing projection models — non-zero EBITDA check lines, zero depreciation with active capex plans, missing tax assumptions.

## What it checks

| Check | Severity | What it catches |
|---|---|---|
| `ebitda_bridge` | ERROR | EBITDA − D&A ≠ EBIT (the classic non-zero "check line") |
| `balance_sheet_tie` | ERROR | Assets ≠ Liabilities + Equity in any period |
| `cash_continuity` | ERROR | Opening cash ≠ prior period's closing cash (broken roll-forward) |
| `zero_taxes` | ERROR | Zero tax with positive pre-tax income (missing assumption) |
| `zero_depreciation` | ERROR/WARN | D&A = 0 — error if capex is positive, warning otherwise |
| `capex_missing` / `zero_capex` | WARNING | No capex line, or zero capex with growing revenue (overstated FCF) |
| `tax_rate_high` / `tax_rate_low` | WARNING | Effective tax rate outside plausible bounds |
| `revenue_growth_outlier` | WARNING | >100% period-over-period swings (usually a typo or broken driver) |
| `margin_drift` | WARNING | EBITDA margin moving >15 p.p. in a single period |
| `missing_line_item` | WARNING | Structurally required lines absent from the model |

Checks are **sign-convention agnostic** — D&A and interest expense can be stored as positive or negative.

## Quick demo

```bash
pip install pandas openpyxl
python sample_model.py            # generates a 5-year model with 5 seeded errors
python model_validator.py sample_model.xlsx
```

Output:

```
FINANCIAL MODEL VALIDATION REPORT
==========================================================================================
[✗ ERROR  ] ebitda_bridge                2028E    EBITDA - D&A = 211 but EBIT = 236 (check line ≠ 0, diff +25).
[✗ ERROR  ] balance_sheet_tie            2029E    Assets 1,170 ≠ Liabilities + Equity 1,220 (diff -50).
[✗ ERROR  ] zero_depreciation            2030E    D&A is zero despite positive capex — missing assumption or hardcoded cell.
[✗ ERROR  ] zero_taxes                   2027E    Taxes are zero with positive pre-tax income (169) — missing tax assumption.
[✗ ERROR  ] cash_continuity              2029E    Opening cash 472 ≠ prior closing cash 442 (broken cash roll-forward).
------------------------------------------------------------------------------------------
Result: 5 error(s), 0 warning(s), 0 info
Model integrity: FAILED — errors must be resolved before relying on outputs.
```

All 5 seeded errors caught, each in the correct period.

## Using it on your own model

Input format: Excel or CSV where the **first column contains line item names** and the remaining columns are periods (`2026E`, `2027E`, ...).

```bash
python model_validator.py my_model.xlsx
```

If your model uses different labels (e.g. in Portuguese), map them via `aliases`:

```python
from model_validator import load_model, validate

df = load_model("modelo.xlsx")
report = validate(df, aliases={
    "Receita Líquida": "Revenue",
    "Impostos": "Taxes",
    "Depreciação e Amortização": "D&A",
})
report.print_summary()
```

## Design notes

- **Findings, not exceptions.** A broken model shouldn't crash the validator — every issue becomes a `Finding` with severity, check name, period and message, collected in a `ValidationReport`. The report distinguishes ERROR (model can't be relied on) from WARNING (needs professional judgment).
- **Checks are independent functions** registered in `ALL_CHECKS`. Adding a new check = writing one function. Missing line items degrade gracefully: the related check is skipped and flagged, rather than failing the run.
- **Tolerance-based tie-outs.** Rounding in real models means exact equality is the wrong test; ties use an absolute tolerance (`TOLERANCE`).

## Roadmap

- [ ] Working capital coherence (DSO/DIO/DPO implied by balance sheet vs. revenue/COGS)
- [ ] D&A vs. gross PP&E reasonableness (implied useful life)
- [ ] Excel report export with findings highlighted per cell
- [ ] Configurable thresholds via YAML

## About

Built by [Luca Rivitti](https://www.linkedin.com/) — Valuation & Transaction Advisory @ Grant Thornton Brasil. Part of a series translating transaction advisory workflows into Python. See also: [`financial-statement-analyzer`](https://github.com/lucanap98/financial-statement-analyzer).
