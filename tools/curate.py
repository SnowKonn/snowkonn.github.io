"""data/raw/checked.jsonl (from collect_reports.py) + data/curation.json (hand edits)
-> data/publications.json, the canonical list the site is built from.

Rules
- Re-uploads of one report (same broker, same title, page count within 2) collapse
  to one entry: earliest date, latest upload's links.
- Monthly strategy compilations (joint house books: 150+ pages or a Strategy file
  name) are excluded, as are weekly strategy notes and routine market commentary
  matched by the "_exclude" patterns in curation.json (decision 2026-11-13).
- curation.json per-id overrides: title_en, topics, role, drop, keep, code_url.
- curation.json "_extra": reports found on the broker's own board but not on Naver.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CUR_PATH = ROOT / "data" / "curation.json"
CUR = json.loads(CUR_PATH.read_text()) if CUR_PATH.exists() else {}
EXCLUDE = CUR.get("_exclude", {})
JOINT_PAGES = 150          # own in-depth reports run to 100 pages; house books are 200+
JOINT_ATTACH = r"Strategy_Monthly|Daishin_Strategy"


def norm(title: str) -> str:
    return re.sub(r"[\s\W_]+", "", title).lower()


def clean_summary(raw: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", raw, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(s.strip() for s in text.splitlines())).strip()


def load_hits() -> list[dict]:
    rows: dict[str, dict] = {}
    for line in (RAW / "checked.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            key = f"{row['category']}/{row['nid']}"
            if not rows.get(key, {}).get("hit"):                # a positive check is never overwritten
                rows[key] = row
    summaries = {}
    for f in (RAW / "listing").glob("*.json"):
        for it in json.loads(f.read_text()):
            summaries[f"{it['category']}/{it['nid']}"] = clean_summary(it["summary_html"])
    return [{**row, "summary": summaries.get(key, ""),
             "detail_url": f"https://stock.naver.com/research/{row['category']}/{row['nid']}"}
            for key, row in rows.items() if row.get("hit")]


def main() -> None:
    hits = load_hits()
    merged: list[dict] = []
    for hit in sorted(hits, key=lambda r: (r["date"], int(r["nid"]))):
        twin = next((m for m in merged if m["broker"] == hit["broker"]
                     and norm(m["title"]) == norm(hit["title"])
                     and abs((m.get("pages") or 0) - (hit.get("pages") or 0)) <= 2), None)
        if twin:
            twin.update({k: hit[k] for k in ("category", "nid", "pdf_url", "detail_url", "pages", "attach_name")})
            twin["summary"] = hit["summary"] or twin["summary"]
            twin["uploads"] += 1
        else:
            merged.append({**hit, "first_date": hit["date"], "uploads": 1})

    pubs, dropped = [], []
    for m in merged:
        pid = f"r-{m['category']}-{m['nid']}"
        over = CUR.get(pid, {})
        why = "manual" if over.get("drop") else ""
        if not why and not over.get("keep"):
            if (m.get("pages") or 0) >= JOINT_PAGES or re.search(JOINT_ATTACH, m.get("attach_name", ""), re.I):
                why = "joint book"
            elif any(re.search(rx, m["title"], re.I) for rx in EXCLUDE.get("title", [])) or \
                    any(re.search(rx, m.get("attach_name", ""), re.I) for rx in EXCLUDE.get("attach", [])):
                why = "routine"
        if why:
            dropped.append((over.get("why") or why, m))
            continue
        pubs.append({
            "id": pid, "date": m["first_date"], "house": m["broker"], "category": m["category"],
            "title_ko": m["title"], "title_en": over.get("title_en", ""),
            "role": over.get("role", "author"),
            "pages": m.get("pages"), "topics": over.get("topics", []),
            "summary_ko": m.get("summary", ""), "naver_url": m["detail_url"], "pdf_url": m.get("pdf_url", ""),
            "code_url": over.get("code_url", ""), "source": "naver",
        })
    pubs += [{"code_url": "", **x} for x in CUR.get("_extra", [])]
    pubs.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    (ROOT / "data" / "publications.json").write_text(json.dumps(pubs, ensure_ascii=False, indent=1))
    (RAW / "excluded.json").write_text(json.dumps(
        [{"why": w, "date": m["first_date"], "house": m["broker"], "pages": m.get("pages"), "title": m["title"]}
         for w, m in dropped], ensure_ascii=False, indent=1))
    for why, m in dropped:
        print(f"  excluded ({why}): {m['first_date']} {m['broker']} {m.get('pages')}p {m['title'][:60]}")
    todo = [p["id"] for p in pubs if not p["title_en"] or not p["topics"]]
    print(f"hits={len(hits)} merged={len(merged)} excluded={len(dropped)} publications={len(pubs)} "
          f"missing title_en/topics={len(todo)}")


if __name__ == "__main__":
    main()
