"""Rough volatility estimates for the stop-loss calculator.

Input : data/vol_universe.json  (asset classes; one Yahoo Finance ticker each)
Output: data/vol.json           (annualized standard deviation of daily log returns)

Method: daily closes from Yahoo Finance through the yfinance package, log returns, sample
standard deviation over the last 252 and the last 756 observations, annualized with the number of
observations per year measured from the dates (about 252 for exchange-traded assets, 365 for
assets quoted every day). These are historical values measured from data, not forecasts.
Needs: pip install yfinance.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = {"1y": 252, "3y": 756}


def vol(closes: list[float], n: int, per_year: float) -> float | None:
    if len(closes) < n + 1:
        return None
    r = [math.log(b / a) for a, b in zip(closes[-n - 1:-1], closes[-n:]) if a > 0 and b > 0]
    if len(r) < 0.9 * n:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1) * per_year)


def main() -> None:
    universe = json.loads((ROOT / "data" / "vol_universe.json").read_text())
    out, failed = [], []
    for a in universe:
        try:
            h = yf.Ticker(a["ticker"]).history(period="5y", interval="1d", auto_adjust=True)
            c = h["Close"].dropna()
            closes = [float(x) for x in c.tolist()]
            last = c.index[-1].date().isoformat()
            per_year = (len(c) - 1) / ((c.index[-1] - c.index[0]).days / 365.25)
        except Exception as err:                       # one failed ticker must not stop the rest
            failed.append(f"{a['ticker']}: {type(err).__name__}")
            continue
        row = {k: a[k] for k in ("id", "ticker", "group", "ko", "en")}
        row.update({f"vol_{w}": (round(v, 4) if (v := vol(closes, n, per_year)) else None) for w, n in WINDOWS.items()})
        row.update(last=last, n=len(closes), per_year=round(per_year, 1))
        if row["vol_1y"] is None:
            failed.append(f"{a['ticker']}: too few observations ({len(closes)})")
            continue
        out.append(row)
    if len(out) < len(universe) // 2:
        raise SystemExit(f"too many tickers failed, data/vol.json left unchanged: {failed}")
    doc = {"generated": dt.date.today().isoformat(), "source": "Yahoo Finance via yfinance",
           "method": "sample standard deviation of daily log returns over the last 252 and 756 observations, annualized with the observations per year measured from the dates",
           "assets": out}
    (ROOT / "data" / "vol.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    print(f"data/vol.json: {len(out)} assets" + (f"; failed: {failed}" if failed else ""))
    for r in out:
        print(f"  {r['id']:8s} {r['ticker']:10s} 1y {r['vol_1y']*100:5.1f}%  3y {(r['vol_3y'] or float('nan'))*100:5.1f}%  last {r['last']}  n={r['n']}")


if __name__ == "__main__":
    main()
