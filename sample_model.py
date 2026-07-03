"""
Generates a demo 5-year projection model (sample_model.xlsx) with
deliberately seeded errors, so the validator has something to catch:

  1. EBITDA bridge broken in 2028E (check line ≠ 0)
  2. Balance sheet doesn't tie in 2029E
  3. D&A hardcoded to zero in 2030E despite positive capex
  4. Taxes zeroed out in 2027E with positive pre-tax income
  5. Cash roll-forward broken between 2028E and 2029E

Run:  python sample_model.py  →  python model_validator.py sample_model.xlsx
"""

import pandas as pd

periods = ["2026E", "2027E", "2028E", "2029E", "2030E"]

# A simple, internally consistent base model...
revenue = [1000, 1150, 1323, 1521, 1749]
cogs = [-550, -633, -728, -836, -962]
opex = [-250, -287, -331, -380, -437]
ebitda = [r + c + o for r, c, o in zip(revenue, cogs, opex)]
da = [-40, -46, -53, -61, 0]                      # error 3: D&A zero in 2030E
ebit = [e + d for e, d in zip(ebitda, da)]
ebit[2] += 25                                      # error 1: bridge broken in 2028E
interest = [-15, -15, -15, -15, -15]
ebt = [e + i for e, i in zip(ebit, interest)]
taxes = [round(-0.34 * x) if x > 0 else 0 for x in ebt]
taxes[1] = 0                                       # error 2 (tax): zero taxes in 2027E
net_income = [e + t for e, t in zip(ebt, taxes)]

capex = [-60, -69, -79, -91, -105]
ocf = [n - d for n, d in zip(net_income, da)]      # simplified: NI + D&A add-back
fcf = [o + c for o, c in zip(ocf, capex)]

opening_cash = [100]
closing_cash = []
for f in fcf:
    closing_cash.append(opening_cash[-1] + f)
    opening_cash.append(closing_cash[-1])
opening_cash = opening_cash[:5]
opening_cash[3] += 30                              # error 5: broken cash roll-forward

assets = [900, 980, 1070, 1170, 1280]
equity = [500, 560, 630, 710, 800]
liabilities = [a - e for a, e in zip(assets, equity)]
liabilities[3] += 50                               # error 4: BS doesn't tie in 2029E

model = pd.DataFrame(
    {
        "Revenue": revenue,
        "COGS": cogs,
        "Opex": opex,
        "EBITDA": ebitda,
        "D&A": da,
        "EBIT": ebit,
        "Interest Expense": interest,
        "Taxes": taxes,
        "Net Income": net_income,
        "Capex": capex,
        "Operating Cash Flow": ocf,
        "Opening Cash": opening_cash,
        "Closing Cash": closing_cash,
        "Total Assets": assets,
        "Total Liabilities": liabilities,
        "Equity": equity,
    },
    index=periods,
).T  # transpose: rows = line items, columns = periods

if __name__ == "__main__":
    model.to_excel("sample_model.xlsx")
    print("sample_model.xlsx generated (5 seeded errors inside).")
    print("Now run: python model_validator.py sample_model.xlsx")
