"""
Financial Model Validator
=========================

Automated integrity checks for financial projection models.

Inspired by real transaction advisory work: before trusting any projection
model in a valuation or due diligence context, a set of consistency checks
should pass. This module automates the most common ones.

Input format: a pandas DataFrame where rows are line items (index) and
columns are periods (e.g. 2026E, 2027E, ...). See sample_model.py for
the expected line item names, or map your model's labels via `aliases`.

Usage:
    python model_validator.py path/to/model.xlsx
"""

import sys
from dataclasses import dataclass, field

import pandas as pd

TOLERANCE = 0.01  # absolute tolerance for tie-out checks (in model currency units)


@dataclass
class Finding:
    severity: str      # "ERROR" | "WARNING" | "INFO"
    check: str         # short name of the check
    period: str        # period where the issue was found ("-" if model-wide)
    message: str

    def __str__(self):
        icon = {"ERROR": "✗", "WARNING": "!", "INFO": "i"}[self.severity]
        return f"[{icon} {self.severity:<7}] {self.check:<28} {self.period:<8} {self.message}"


@dataclass
class ValidationReport:
    findings: list = field(default_factory=list)

    def add(self, severity, check, period, message):
        self.findings.append(Finding(severity, check, str(period), message))

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "WARNING"]

    def print_summary(self):
        print()
        print("=" * 90)
        print("FINANCIAL MODEL VALIDATION REPORT")
        print("=" * 90)
        if not self.findings:
            print("All checks passed. No issues found.")
        for f in self.findings:
            print(f)
        print("-" * 90)
        print(f"Result: {len(self.errors)} error(s), {len(self.warnings)} warning(s), "
              f"{len(self.findings) - len(self.errors) - len(self.warnings)} info")
        if self.errors:
            print("Model integrity: FAILED — errors must be resolved before relying on outputs.")
        elif self.warnings:
            print("Model integrity: PASSED WITH WARNINGS — review flagged items.")
        else:
            print("Model integrity: PASSED")
        print("=" * 90)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(df, item):
    """Return a line item as a Series, or None if absent from the model."""
    if item in df.index:
        return df.loc[item]
    return None


def _close(a, b, tol=TOLERANCE):
    return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# Checks — each takes the model DataFrame and a ValidationReport
# ---------------------------------------------------------------------------

def check_required_lines(df, report):
    """Flag structurally required line items that are missing entirely."""
    required = [
        "Revenue", "COGS", "EBITDA", "D&A", "EBIT", "Taxes", "Net Income",
        "Capex", "Total Assets", "Total Liabilities", "Equity",
        "Operating Cash Flow", "Closing Cash",
    ]
    for item in required:
        if item not in df.index:
            report.add("WARNING", "missing_line_item", "-",
                       f"'{item}' not found in model — related checks will be skipped.")


def check_ebitda_bridge(df, report):
    """EBITDA - D&A must equal EBIT in every period (the classic 'check line')."""
    ebitda, da, ebit = _get(df, "EBITDA"), _get(df, "D&A"), _get(df, "EBIT")
    if ebitda is None or da is None or ebit is None:
        return
    for period in df.columns:
        # Sign-convention agnostic: D&A may be stored as positive or negative.
        expected = ebitda[period] - abs(da[period])
        if not _close(expected, ebit[period]):
            diff = ebit[period] - expected
            report.add("ERROR", "ebitda_bridge", period,
                       f"EBITDA - D&A = {expected:,.0f} but EBIT = {ebit[period]:,.0f} "
                       f"(check line ≠ 0, diff {diff:+,.0f}).")


def check_balance_sheet_ties(df, report):
    """Assets must equal Liabilities + Equity in every period."""
    assets = _get(df, "Total Assets")
    liab = _get(df, "Total Liabilities")
    equity = _get(df, "Equity")
    if assets is None or liab is None or equity is None:
        return
    for period in df.columns:
        rhs = liab[period] + equity[period]
        if not _close(assets[period], rhs):
            report.add("ERROR", "balance_sheet_tie", period,
                       f"Assets {assets[period]:,.0f} ≠ Liabilities + Equity {rhs:,.0f} "
                       f"(diff {assets[period] - rhs:+,.0f}).")


def check_depreciation(df, report):
    """Zero depreciation with positive capex or asset base is a modeling red flag."""
    da, capex = _get(df, "D&A"), _get(df, "Capex")
    if da is None:
        return
    for period in df.columns:
        if da[period] == 0:
            has_capex = capex is not None and abs(capex[period]) > 0
            severity = "ERROR" if has_capex else "WARNING"
            extra = " despite positive capex" if has_capex else ""
            report.add(severity, "zero_depreciation", period,
                       f"D&A is zero{extra} — missing assumption or hardcoded cell.")


def check_capex_coherence(df, report):
    """Capex should exist for a growing business; flag zero or missing capex."""
    capex, revenue = _get(df, "Capex"), _get(df, "Revenue")
    if capex is None:
        report.add("WARNING", "capex_missing", "-",
                   "No capex line found — projections may overstate free cash flow.")
        return
    for period in df.columns:
        if capex[period] == 0 and revenue is not None and revenue[period] > 0:
            report.add("WARNING", "zero_capex", period,
                       "Capex is zero with positive revenue — verify assumption.")


def check_taxes(df, report):
    """Effective tax rate should be plausible; zero tax on positive EBT is a flag."""
    taxes, ebit = _get(df, "Taxes"), _get(df, "EBIT")
    interest = _get(df, "Interest Expense")
    if taxes is None or ebit is None:
        return
    for period in df.columns:
        # Sign-agnostic: interest expense may be stored as positive or negative.
        ebt = ebit[period] - (abs(interest[period]) if interest is not None else 0)
        if ebt <= 0:
            continue
        rate = abs(taxes[period]) / ebt
        if taxes[period] == 0:
            report.add("ERROR", "zero_taxes", period,
                       f"Taxes are zero with positive pre-tax income ({ebt:,.0f}) — "
                       f"missing tax assumption.")
        elif rate > 0.50:
            report.add("WARNING", "tax_rate_high", period,
                       f"Effective tax rate {rate:.0%} looks implausibly high.")
        elif rate < 0.10:
            report.add("WARNING", "tax_rate_low", period,
                       f"Effective tax rate {rate:.0%} — confirm tax benefit/NOL rationale.")


def check_cash_flow_continuity(df, report):
    """Closing cash of one period must equal opening cash of the next."""
    closing = _get(df, "Closing Cash")
    opening = _get(df, "Opening Cash")
    if closing is None or opening is None:
        return
    periods = list(df.columns)
    for prev, curr in zip(periods, periods[1:]):
        if not _close(closing[prev], opening[curr]):
            report.add("ERROR", "cash_continuity", curr,
                       f"Opening cash {opening[curr]:,.0f} ≠ prior closing cash "
                       f"{closing[prev]:,.0f} (broken cash roll-forward).")


def check_growth_sanity(df, report):
    """Flag extreme or erratic revenue growth that usually signals a typo."""
    revenue = _get(df, "Revenue")
    if revenue is None:
        return
    periods = list(df.columns)
    for prev, curr in zip(periods, periods[1:]):
        if revenue[prev] <= 0:
            continue
        g = revenue[curr] / revenue[prev] - 1
        if abs(g) > 1.0:
            report.add("WARNING", "revenue_growth_outlier", curr,
                       f"Revenue growth of {g:+.0%} vs prior period — verify driver or typo.")


def check_margin_consistency(df, report):
    """EBITDA margin drifting more than 15 p.p. between periods deserves scrutiny."""
    revenue, ebitda = _get(df, "Revenue"), _get(df, "EBITDA")
    if revenue is None or ebitda is None:
        return
    periods = list(df.columns)
    margins = {p: (ebitda[p] / revenue[p] if revenue[p] else None) for p in periods}
    for prev, curr in zip(periods, periods[1:]):
        if margins[prev] is None or margins[curr] is None:
            continue
        drift = margins[curr] - margins[prev]
        if abs(drift) > 0.15:
            report.add("WARNING", "margin_drift", curr,
                       f"EBITDA margin moved {drift:+.1%} in one period "
                       f"({margins[prev]:.1%} → {margins[curr]:.1%}) — verify drivers.")


ALL_CHECKS = [
    check_required_lines,
    check_ebitda_bridge,
    check_balance_sheet_ties,
    check_depreciation,
    check_capex_coherence,
    check_taxes,
    check_cash_flow_continuity,
    check_growth_sanity,
    check_margin_consistency,
]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def validate(df, aliases=None):
    """Run all checks against a model DataFrame and return a ValidationReport.

    aliases: optional dict mapping your model's labels to the canonical names,
             e.g. {"Receita Líquida": "Revenue", "Impostos": "Taxes"}.
    """
    if aliases:
        df = df.rename(index=aliases)
    report = ValidationReport()
    for check in ALL_CHECKS:
        check(df, report)
    return report


def load_model(path):
    """Load a model from Excel/CSV: first column = line items, others = periods."""
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path, index_col=0, sep=None, engine="python")
    else:
        df = pd.read_excel(path, index_col=0)
    df.index = df.index.astype(str).str.strip()
    return df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python model_validator.py path/to/model.xlsx")
        print("Tip: run sample_model.py first to generate a demo model with seeded errors.")
        sys.exit(1)
    model = load_model(sys.argv[1])
    print(f"Loaded model: {sys.argv[1]} — {len(model.index)} line items, "
          f"{len(model.columns)} periods ({', '.join(map(str, model.columns))})")
    validate(model).print_summary()
