"""Collect research reports authored by one analyst from the Naver research API.

The public list API carries no author field, so authorship is decided from the
PDF itself: the analyst's name (or e-mail id) must appear on the first pages,
either in the text layer or, where the broker sets the byline as outlines
(IBK Securities), in an OCR of page 1 (tools/ocr.swift, macOS Vision).

Stages (all cached under data/raw, safe to re-run):
  1. list   : month-by-month listing per category, kept only for target brokers
  2. check  : detail -> attachUrl -> PDF (local crawler copy first) -> name match
  3. export : data/raw/hits.json  (one row per authored report)

Scans backward in time and stops once STOP_AFTER consecutive months older than
FLOOR_SOFT contain no authored report.

Read-only with respect to the crawler project: its DB is opened mode=ro and its
PDFs are only read.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import fitz  # PyMuPDF
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
LISTING = RAW / "listing"
PDFS = RAW / "pdf"
CHECKED = RAW / "checked.jsonl"
HITS = RAW / "hits.json"

API = "https://stock.naver.com/api/stockSecurity/researches/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Referer": "https://stock.naver.com/research",
}
CRAWLER_DB = Path("/Volumes/Snow_Home/#Para/3_Resources/kor_report/reports.db")
CATEGORY_KO = {"invest": "투자정보", "market": "시황정보", "economy": "경제분석",
               "industry": "산업분석", "company": "기업분석", "debenture": "채권분석"}

AUTHOR = "권순호"
AUTHOR_RX = re.compile(r"권순호|snowkonn|soonho\.kwon", re.I)   # matched on whitespace-stripped text
ROUTINE_RX = re.compile(r"IBKS Daily|Morning Brief|Start with IBKS", re.I)  # dailies: never listed, not checked
OCR_BIN = RAW / "bin" / "ocr"          # swiftc -O tools/ocr.swift -o data/raw/bin/ocr
CHECK_VERSION = 3                      # 3 = text layer + full first-page OCR
BROKERS = ("IBK투자증권", "대신증권")
STOP_AFTER = 9            # consecutive empty months
FLOOR_SOFT = "2023-01"    # never stop before scanning back to here
FLOOR_HARD = "2015-01"
DELAY = 0.6
PAGES_FOR_AUTHOR = 2

session = requests.Session()
session.headers.update(HEADERS)


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def get(url: str, *, binary: bool = False, tries: int = 4) -> Any:
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                time.sleep(DELAY)
                return r.content if binary else r.json()
            if r.status_code in (429, 500, 502, 503):
                time.sleep(5 * (attempt + 1))
                continue
            log(f"  HTTP {r.status_code} {url}")
            return None
        except (requests.RequestException, ValueError) as exc:
            log(f"  retry {attempt + 1}: {exc}")
            time.sleep(3 * (attempt + 1))
    return None


def month_bounds(ym: str) -> tuple[str, str]:
    y, m = map(int, ym.split("-"))
    first = dt.date(y, m, 1)
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    last = min(nxt - dt.timedelta(days=1), dt.date.today())
    return first.isoformat(), last.isoformat()


def prev_month(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"


def list_month(category: str, ym: str) -> list[dict]:
    """All target-broker items of one category in one month (cached unless current month)."""
    cache = LISTING / f"{category}_{ym}.json"
    current = ym == f"{dt.date.today():%Y-%m}"
    if cache.exists() and not current:
        return json.loads(cache.read_text())
    start, end = month_bounds(ym)
    out, index, seen = [], 0, set()
    while True:
        data = get(f"{API}/{category}?index={index}&size=50&startDate={start}&endDate={end}")
        if not data or not isinstance(data.get("items"), list):
            raise RuntimeError(f"listing failed: {category} {ym} index={index}")
        fresh = 0
        for it in data["items"]:
            nid = str(it.get("nid"))
            if nid in seen:
                continue
            seen.add(nid)
            fresh += 1
            if (it.get("brokerName") or "") in BROKERS:
                out.append({
                    "category": category, "nid": nid, "date": it.get("writeDate"),
                    "title": (it.get("title") or "").strip(),
                    "broker": it.get("brokerName"),
                    "summary_html": it.get("content") or "",
                })
        if not data.get("hasNext") or not fresh:
            break
        index += 1
    cache.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def load_checked() -> dict[str, dict]:
    done = {}
    if CHECKED.exists():
        for line in CHECKED.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done[f"{row['category']}/{row['nid']}"] = row
    return done


def local_pdf(item: dict) -> Path | None:
    """PDF already saved by the crawler (matched on title+date+broker, not nid alone)."""
    if not CRAWLER_DB.exists():
        return None
    con = sqlite3.connect(f"file:{quote(str(CRAWLER_DB))}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select pdf_path from reports where nid=? and date=? and broker=? and title=?",
            (item["nid"], item["date"], item["broker"], item["title"])).fetchone()
    finally:
        con.close()
    if row and row[0]:
        p = Path(row[0])
        if p.is_file() and p.stat().st_size > 1000:
            return p
    return None


def ocr_byline(doc) -> str:
    """Recognised text of page 1 (empty if the helper is missing).

    The whole page, not just the header: co-author bylines sit lower on IBK covers.
    """
    if not OCR_BIN.exists() or not doc.page_count:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        doc[0].get_pixmap(dpi=200).save(tmp.name)
        try:
            return subprocess.run([str(OCR_BIN), tmp.name], capture_output=True, text=True,
                                  timeout=60).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""


def squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text)


def author_evidence(pdf_bytes: bytes) -> tuple[bool, str, int]:
    """(name found on first pages, the line that carries it, page count)."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return False, "unreadable pdf", 0
    n = doc.page_count
    for pno in range(min(PAGES_FOR_AUTHOR, n)):
        text = doc[pno].get_text()
        if AUTHOR_RX.search(squeeze(text)):
            line = next((ln for ln in text.splitlines() if AUTHOR_RX.search(squeeze(ln))), "")
            return True, f"p{pno + 1}: {line.strip()[:120]}", n
    seen = ocr_byline(doc)
    if AUTHOR_RX.search(squeeze(seen)):
        part = next((x for x in seen.split(" | ") if AUTHOR_RX.search(squeeze(x))), "")
        return True, f"p1 ocr: {part[:120]}", n
    return False, "", n


def check_item(item: dict) -> dict:
    row = {k: item[k] for k in ("category", "nid", "date", "title", "broker")}
    row["v"] = CHECK_VERSION
    if ROUTINE_RX.search(item["title"]):
        return {**row, "status": "ok", "hit": False, "evidence": "routine daily, not checked", "pages": None}
    detail = get(f"{API}/{item['category']}/{item['nid']}")
    if not detail:
        return {**row, "status": "detail_failed"}
    url = detail.get("attachUrl") or ""
    row.update(pdf_url=url, attach_name=detail.get("attachName") or "",
               read_count=detail.get("readCount"))
    src = local_pdf(item)
    if src:
        blob = src.read_bytes()
    elif url:
        blob = get(url, binary=True)
    else:
        return {**row, "status": "no_attachment"}
    if not blob or not blob.startswith(b"%PDF-"):
        return {**row, "status": "pdf_failed"}
    hit, evidence, pages = author_evidence(blob)
    row.update(status="ok", hit=hit, evidence=evidence, pages=pages)
    if hit:
        (PDFS / f"{item['category']}_{item['nid']}.pdf").write_bytes(blob)
    return row


def clean_summary(raw: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", raw, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(s.strip() for s in text.splitlines())).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--categories", default="invest,market")
    ap.add_argument("--start", default=f"{dt.date.today():%Y-%m}", help="newest month, YYYY-MM")
    ap.add_argument("--floor", default=None, help="force scan back to this month (disables early stop)")
    ap.add_argument("--brokers", default=",".join(BROKERS), help="check only these brokers")
    args = ap.parse_args()
    for d in (LISTING, PDFS):
        d.mkdir(parents=True, exist_ok=True)

    categories = args.categories.split(",")
    brokers = set(args.brokers.split(","))
    checked = load_checked()
    ym, empty_run = args.start, 0
    floor = args.floor or FLOOR_HARD
    with CHECKED.open("a") as sink:
        while ym >= floor:
            month_hits = 0
            for cat in categories:
                items = [it for it in list_month(cat, ym) if it["broker"] in brokers]
                for item in items:
                    key = f"{cat}/{item['nid']}"
                    old = checked.get(key, {})
                    stale = item["broker"] != "대신증권" and old.get("v") != CHECK_VERSION and not old.get("hit")
                    if old.get("status") != "ok" or stale:
                        row = check_item(item)
                        checked[key] = row
                        sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                        sink.flush()
                    month_hits += bool(checked[key].get("hit"))
                log(f"{ym} {cat:9s} candidates={len(items):3d}")
            log(f"{ym} authored={month_hits}")
            empty_run = 0 if month_hits else empty_run + 1
            if not args.floor and empty_run >= STOP_AFTER and ym < FLOOR_SOFT:
                log(f"stop: {STOP_AFTER} empty months ending {ym}")
                break
            ym = prev_month(ym)

    summaries = {}
    for f in LISTING.glob("*.json"):
        for it in json.loads(f.read_text()):
            summaries[f"{it['category']}/{it['nid']}"] = clean_summary(it["summary_html"])
    hits = [
        {**row, "category_ko": CATEGORY_KO.get(row["category"], row["category"]),
         "detail_url": f"https://stock.naver.com/research/{row['category']}/{row['nid']}",
         "summary": summaries.get(key, "")}
        for key, row in checked.items() if row.get("hit")
    ]
    hits.sort(key=lambda r: (r["date"], r["nid"]), reverse=True)
    HITS.write_text(json.dumps(hits, ensure_ascii=False, indent=1))
    failed = [r for r in checked.values() if r.get("status") != "ok"]
    log(f"done: checked={len(checked)} authored={len(hits)} failed={len(failed)} -> {HITS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
