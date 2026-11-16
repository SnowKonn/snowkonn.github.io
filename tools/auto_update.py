"""Daily job: publish new sole-author Daishin reports to the site without manual steps.

Flow
  1. preflight: clean git tree on main, in sync with origin
  2. collect_reports.py for the current and previous month (Daishin only; cached rows are skipped)
  3. curate.py; stop quietly if no report is new
  4. hold a new report that names another Daishin analyst on its first pages
     (the page lists sole-author reports only) -> curation.json "drop" + "hold", needs a human look
  5. new reports without an English title / topics: `claude -p` fills them (falls back to blank,
     the page then shows the Korean title)
  6. build_site.py, verify, commit, push, wait until the live page shows the report
Failures restore the tree and send a Telegram alert through ~/.openclaw/scripts/notify-ops.sh.

Run by launchd (com.snowkonn.site-autoupdate); safe to run by hand: python tools/auto_update.py [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
CLAUDE = Path.home() / ".local" / "bin" / "claude"
NOTIFY = Path.home() / ".openclaw" / "scripts" / "notify-ops.sh"
CUR_PATH = ROOT / "data" / "curation.json"
PUBS_PATH = ROOT / "data" / "publications.json"
LIVE = "https://snowkonn.github.io"
OWN_MAIL = "soonho.kwon@daishin.com"


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def run(cmd: list[str], *, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed ({r.returncode}): {(r.stderr or r.stdout)[-600:]}")
    return r


def git(*args: str, check: bool = True) -> str:
    return run(["git", *args], check=check).stdout.strip()


def notify(title: str, body: str) -> None:
    if NOTIFY.exists():
        subprocess.run(["/bin/bash", str(NOTIFY), title, body], capture_output=True, timeout=60)


def restore_tree() -> None:
    """Drop everything this run generated (the tree was clean at the start)."""
    git("checkout", "--", "data", "docs", check=False)
    git("clean", "-fdq", "docs", check=False)


def load_pubs() -> list[dict]:
    return json.loads(PUBS_PATH.read_text(encoding="utf-8"))


def other_analysts(pdf: Path) -> list[str]:
    """Other Daishin e-mail addresses on the first two pages (a co-authored report)."""
    import fitz
    doc = fitz.open(pdf)
    text = "".join(doc[i].get_text() for i in range(min(2, doc.page_count)))
    return sorted({m for m in re.findall(r"[\w.]+@daishin\.com", text) if not m.endswith(OWN_MAIL)
                   and OWN_MAIL not in m})


def fill_english(new: list[dict], topics: dict[str, dict], examples: list[dict]) -> dict[str, dict]:
    """English title and topic keys for reports the curation file does not know yet."""
    shots = "\n".join(json.dumps({"title_ko": e["title_ko"], "title_en": e["title_en"], "topics": e["topics"]},
                                 ensure_ascii=False) for e in examples)
    legend = "\n".join(f"- {k}: {v['ko']} / {v['en']}" for k, v in topics.items())
    out: dict[str, dict] = {}
    for pub in new:
        prompt = (
            "Translate the title of a Korean securities research report into plain English and pick its topics.\n"
            "Rules: translate what the Korean says, nothing more; no marketing words; keep tickers, indices and "
            "names as they are; sentence case; no trailing period. Pick 1 to 3 topic keys from the list.\n"
            f"Topics:\n{legend}\n\nExamples (JSON lines):\n{shots}\n\n"
            f"Report: {json.dumps({'title_ko': pub['title_ko'], 'pages': pub.get('pages'), 'summary_ko': (pub.get('summary_ko') or '')[:700]}, ensure_ascii=False)}\n\n"
            'Answer with one JSON object only: {"title_en": "...", "topics": ["..."]}')
        try:
            r = subprocess.run([str(CLAUDE), "-p", prompt, "--model", "sonnet", "--tools", "",
                                "--no-session-persistence", "--output-format", "text"],
                               cwd="/tmp", capture_output=True, text=True, timeout=240)
            m = re.search(r"\{.*\}", r.stdout, re.S)
            if not m:
                raise ValueError(f"no JSON in answer: {r.stdout[:200]!r}")
            data = json.loads(m.group(0))
            keys = [k for k in data.get("topics", []) if k in topics][:3]
            title = str(data["title_en"]).strip()
            if title and keys:
                out[pub["id"]] = {"title_en": title, "topics": keys}
                log(f"  english: {pub['id']} -> {title} {keys}")
                continue
        except Exception as exc:  # noqa: BLE001 - any failure falls back to blank
            log(f"  claude -p failed for {pub['id']}: {exc}")
        log(f"  english title left blank for {pub['id']}")
    return out


def wait_live(pub_id: str, tries: int = 30) -> bool:
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"{LIVE}/?t={int(time.time())}", timeout=20) as r:
                if f'id="{pub_id}"' in r.read().decode("utf-8", "ignore"):
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(10)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="collect and build, but do not commit or push")
    ap.add_argument("--pretend-new", default="", help="test only: treat this publication id as not yet published")
    args = ap.parse_args()

    lock = open(ROOT / "data" / "raw" / ".auto_update.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another run is active, exit")
        return 0

    # 1. preflight
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        notify("소개 페이지 자동 갱신 중단", "main 브랜치가 아니어서 건너뜀")
        return 1
    if git("status", "--porcelain"):
        notify("소개 페이지 자동 갱신 중단", "작업 트리에 커밋되지 않은 변경이 있어 건너뜀")
        log("dirty tree, skip")
        return 1
    git("fetch", "-q", "origin")
    if git("rev-list", "--count", "HEAD..origin/main") != "0":
        git("pull", "--ff-only", "-q", "origin", "main")

    before = {p["id"] for p in load_pubs()} - {args.pretend_new}
    today = dt.date.today()
    prev = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    try:
        # 2-3. collect and curate
        run([PY, "tools/collect_reports.py", "--start", f"{today:%Y-%m}", "--floor", prev,
             "--brokers", "대신증권"])
        run([PY, "tools/curate.py"])
        pubs = load_pubs()
        new = [p for p in pubs if p["id"] not in before]
        log(f"publications {len(before)} -> {len(pubs)}; new: {[p['id'] for p in new]}")
        if not new:
            restore_tree()
            return 0

        # 4. hold co-authored reports
        cur = json.loads(CUR_PATH.read_text(encoding="utf-8"))
        held = []
        for p in new:
            pdf = ROOT / "docs" / p["file"]
            extra = other_analysts(pdf) if pdf.exists() else []
            if extra:
                cur.setdefault(p["id"], {}).update({"drop": True, "hold": f"other analyst on cover: {', '.join(extra)}"})
                held.append((p, extra))
        if held:
            CUR_PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            run([PY, "tools/curate.py"])
            notify("소개 페이지: 공동 집필로 보이는 새 리포트 보류",
                   "\n".join(f"{p['date']} {p['title_ko']} ({', '.join(x)})" for p, x in held)
                   + "\n게재하려면 data/curation.json에서 drop·hold를 지우고 keep:true")
            pubs = load_pubs()
            new = [p for p in pubs if p["id"] not in before]

        # 5. English titles and topics
        profile = json.loads((ROOT / "data" / "profile.json").read_text(encoding="utf-8"))
        todo = [p for p in new if not p["title_en"] or not p["topics"]]
        if todo:
            examples = [p for p in pubs if p["title_en"] and p["topics"]][:6]
            filled = fill_english(todo, profile["topics"], examples)
            if filled:
                cur = json.loads(CUR_PATH.read_text(encoding="utf-8"))
                for pid, vals in filled.items():
                    cur.setdefault(pid, {}).update(vals)
                CUR_PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                run([PY, "tools/curate.py"])

        # 6. build and verify
        run([PY, "tools/build_site.py"])
        pubs = load_pubs()
        for p in (q for q in pubs if q["id"] not in before):
            files = [ROOT / "docs" / p[k] for k in ("file", "text_file") if p.get(k)]
            if not files or any(not f.exists() or f.stat().st_size < 1000 for f in files):
                raise RuntimeError(f"missing report files for {p['id']}")
            if f'id="{p["id"]}"' not in (ROOT / "docs" / "index.html").read_text(encoding="utf-8"):
                raise RuntimeError(f"{p['id']} missing from index.html")
        if len(pubs) < len(before):
            raise RuntimeError("publication count went down")
    except Exception as exc:  # noqa: BLE001
        log(f"FAILED: {exc}")
        restore_tree()
        notify("소개 페이지 자동 갱신 실패", str(exc)[:500])
        return 1

    added = [p for p in load_pubs() if p["id"] not in before]
    if args.dry_run:
        log(f"dry run: would publish {[p['id'] for p in added]}")
        restore_tree()
        return 0

    # 7. commit, push, confirm
    git("add", "data/curation.json", "data/publications.json", "docs")
    lines = [f"- {p['date']} {p['title_ko']}" for p in added]
    blank = [p["id"] for p in added if not p["title_en"]]
    head = f"Add {len(added)} new report(s)" if added else f"Hold {len(held)} co-authored report(s)"
    msg = f"{head}\n\n" + "\n".join(lines or [f"- {p['date']} {p['title_ko']}" for p, _ in held]) + \
        ("\n\nEnglish title pending: " + ", ".join(blank) if blank else "") + "\n\nAutomated by tools/auto_update.py"
    git("commit", "-q", "-m", msg)
    try:
        git("push", "-q", "origin", "main")
    except RuntimeError as exc:
        log(f"push failed: {exc}")
        notify("소개 페이지 자동 갱신: push 실패", str(exc)[:400])
        return 1
    log(f"pushed: {[p['id'] for p in added]}")
    if added and not wait_live(added[0]["id"]):
        notify("소개 페이지: push 후 5분 내 반영 미확인", added[0]["title_ko"])
        return 1
    log("live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
