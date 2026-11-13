"""List every report on the IBK Securities research board (전략/시황) with its
author column, and keep the rows whose author field names the analyst.

The board is a plain server-rendered table (EUC-KR), paged by POST.
Output: data/raw/ibks_strategy.jsonl (all rows), printed summary of matches.
Usage: collect_ibks.py [first_page] [last_page]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "ibks_strategy.jsonl"
URL = "https://www.ibks.com/investment/research/strategy_list.do?popup=null"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126 Safari/537.36",
           "Referer": "https://www.ibks.com/investment/research/strategy_list.do"}
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
VIEW = re.compile(r"strategyView\('(\d+)',\s*'([^']*)'\)")


def text(cell: str) -> str:
    cell = re.sub(r"<!--.*?-->", "", cell, flags=re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", cell))).strip()


def fetch(page: int) -> tuple[list[dict], int]:
    # curl, not requests: the site's TLS setup is refused by Python's OpenSSL.
    out = subprocess.run(
        ["curl", "-s", "--max-time", "30", "-A", HEADERS["User-Agent"], "-e", HEADERS["Referer"],
         "--data", f"search_key=TITLE&search_value=&start_reg_date=&end_reg_date=&current_page={page}", URL],
        capture_output=True, check=True).stdout
    body = out.decode("euc-kr", errors="replace")
    rows = []
    for tr in ROW.findall(body):
        m = VIEW.search(tr)
        cells = CELL.findall(tr)
        if not m or len(cells) < 7:
            continue
        rows.append({"no": text(cells[0]), "gubun": m.group(2), "seq": m.group(1), "title": text(cells[2]),
                     "author": text(cells[3]), "date": text(cells[5]), "views": text(cells[6])})
    last = max((int(n) for n in re.findall(r"goPage\((\d+)\)", body)), default=page)
    return rows, last


def main() -> None:
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    rows, last = fetch(first)
    last = int(sys.argv[2]) if len(sys.argv) > 2 else last
    with OUT.open("a") as sink:
        page = first
        while True:
            for row in rows:
                sink.write(json.dumps({**row, "page": page}, ensure_ascii=False) + "\n")
            sink.flush()
            if page % 50 == 0 or page == first:
                print(f"page {page}/{last} rows={len(rows)} oldest={rows[-1]['date'] if rows else '-'}", flush=True)
            if page >= last or not rows:
                break
            page += 1
            time.sleep(0.4)
            for attempt in range(4):
                try:
                    rows, _ = fetch(page)
                    break
                except subprocess.SubprocessError as exc:
                    print(f"retry page {page}: {exc}", flush=True)
                    time.sleep(5 * (attempt + 1))
            else:
                print(f"FAILED page {page}", flush=True)
                break
    print("done", flush=True)


if __name__ == "__main__":
    main()
