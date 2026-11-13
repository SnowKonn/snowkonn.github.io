"""Second pass over IBK non-hits: OCR the whole first page at 200 dpi and record
whose byline it carries, so OCR misses of the author's name can be told apart
from reports by other analysts. Output: data/raw/recheck.jsonl
Usage: recheck_ibk.py <from YYYY-MM> <to YYYY-MM>
"""
import json, re, subprocess, sys, tempfile, time
from pathlib import Path
import fitz, requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
lo, hi = sys.argv[1], sys.argv[2]
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://stock.naver.com/research"}
ME = re.compile(r"권순호|snowkonn|soonho", re.I)
rows = {}
for line in (RAW / "checked.jsonl").read_text().splitlines():
    if line.strip():
        r = json.loads(line); rows[f"{r['category']}/{r['nid']}"] = r
todo = [r for r in rows.values() if r["broker"].startswith("IBK") and not r.get("hit")
        and r.get("pages") and lo <= r["date"][:7] <= hi and r.get("pdf_url")]
with (RAW / "recheck.jsonl").open("a") as out:
    for r in sorted(todo, key=lambda r: r["date"], reverse=True):
        try:
            blob = requests.get(r["pdf_url"], headers=H, timeout=30).content
            doc = fitz.open(stream=blob, filetype="pdf")
            with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                doc[0].get_pixmap(dpi=200).save(tmp.name)
                seen = subprocess.run([str(RAW / "bin" / "ocr"), tmp.name], capture_output=True, text=True, timeout=90).stdout
        except Exception as exc:
            seen = f"ERROR {exc}"
        flat = re.sub(r"\s+", "", seen)
        emails = sorted(set(re.findall(r"[A-Za-z0-9_.]+@ibks\.com", flat)))
        byline = [x.strip()[:60] for x in seen.split(" | ") if re.search(r"@ibks|^(Quant|Strategy|Economist|Macro|ETF|자산배분)", x.strip())][:3]
        mine = bool(ME.search(flat))
        where = [x.strip()[:80] for x in seen.split(" | ") if ME.search(re.sub(r"\s+", "", x))][:3]
        out.write(json.dumps({"key": f"{r['category']}/{r['nid']}", "date": r["date"], "title": r["title"],
                              "mine": mine, "emails": emails, "byline": byline, "where": where}, ensure_ascii=False) + "\n")
        if mine:
            (RAW / "pdf" / f"{r['category']}_{r['nid']}.pdf").write_bytes(blob)
            with (RAW / "checked.jsonl").open("a") as sink:
                sink.write(json.dumps({**r, "v": 3, "hit": True, "evidence": "p1 full ocr: " + " / ".join(where)},
                                      ensure_ascii=False) + "\n")
        out.flush(); time.sleep(0.4)
print("recheck done", lo, hi, len(todo))
