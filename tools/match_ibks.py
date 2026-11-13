"""For IBK-board rows authored by the analyst: read each view page (full title,
attachment file name, download link) and match it to the Naver listing by
attachment file name. Output: data/raw/ibks_mine.json
"""
import json, re, subprocess, time
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
BASE = "https://www.ibks.com"

rows = {}
for line in (RAW / "ibks_strategy.jsonl").read_text().splitlines():
    r = json.loads(line); rows[(r["seq"], r["gubun"])] = r
mine = sorted((r for r in rows.values() if "권순호" in r["author"]), key=lambda r: r["date"])

naver = {}
for line in (RAW / "checked.jsonl").read_text().splitlines():
    if line.strip():
        r = json.loads(line)
        if r.get("attach_name"):
            naver.setdefault(r["attach_name"], r)
            if r.get("hit"):
                naver[r["attach_name"]] = r

out = []
for r in mine:
    url = f"{BASE}/investment/research/strategy_view.do?seq={r['seq']}&gubun={r['gubun']}&popup=null"
    body = subprocess.run(["curl", "-s", "--max-time", "30", "-A", UA, "-e", BASE + "/investment/research/strategy_list.do", url],
                          capture_output=True).stdout.decode("euc-kr", errors="replace")
    m = re.search(r'href="(/company/common/download\.jsp\?filepath=[^"]+?filename=([^"&]+)[^"]*)"', body)
    t = re.search(r'<(?:h\d|th|td|p|div)[^>]*class="[^"]*(?:tit|subject|title)[^"]*"[^>]*>(.*?)</', body, re.S)
    fname = m.group(2) if m else ""
    n = naver.get(fname)
    out.append({**r, "view_url": url, "file": fname, "download": BASE + unescape(m.group(1)) if m else "",
                "title_full": re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", t.group(1)))).strip() if t else "",
                "naver": f"{n['category']}/{n['nid']}" if n else "", "naver_hit": bool(n and n.get("hit")),
                "naver_title": n["title"] if n else ""})
    time.sleep(0.4)
(RAW / "ibks_mine.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
for o in out:
    flag = "OK " if o["naver_hit"] else ("NOHIT" if o["naver"] else "NOT_ON_NAVER")
    print(o["date"], flag, o["file"], "|", (o["naver_title"] or o["title_full"] or o["title"])[:60])
hit_files = {r.get("attach_name") for r in naver.values() if r.get("hit") and r["broker"].startswith("IBK")}
print("--- Naver IBK hits not authored by 권순호 on the IBK board (co-authored):")
by_file = {}
for (seq, g), r in rows.items():
    pass
for f in sorted(hit_files - {o["file"] for o in out}):
    r = naver[f]; print(" ", r["date"], f, "|", r["title"][:60], "|", r.get("evidence", "")[:50])
