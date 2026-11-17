"""Build the static site (Korean at /, English at /en/) plus the agent index files.

Inputs : data/profile.json, data/publications.json, data/study.json, data/stoploss.json, data/vol.json, src/
Outputs: docs/  (index.html, en/index.html, stoploss/, en/stoploss/, publications.json, llms.txt,
                 llms-full.txt, robots.txt, sitemap.xml, assets/)
No third-party packages.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import shutil
from html import escape as e, unescape
from itertools import groupby
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
P = json.loads((ROOT / "data" / "profile.json").read_text())
PUBS = json.loads((ROOT / "data" / "publications.json").read_text())
PUBS.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
STUDY = json.loads((ROOT / "data" / "study.json").read_text())   # notes kept as PDFs in docs/study
TOOL = json.loads((ROOT / "data" / "stoploss.json").read_text())  # copy of the stop-loss calculator
VOL = json.loads((ROOT / "data" / "vol.json").read_text())        # written by tools/update_vol.py
BASE = P["base_url"].rstrip("/")
TODAY = dt.date.today()
FONT_API = "https://fonts.googleapis.com/css2?family={family}&display=swap&text={text}"


def house(pub: dict) -> dict:
    return P["houses"][pub["house"]]


def title(pub: dict, lang: str) -> str:
    return pub["title_ko"] if lang == "ko" else (pub.get("title_en") or pub["title_ko"])


def tenure(lang: str) -> list[tuple[str, str, str]]:
    """(period, house) lines computed from the report dates themselves."""
    ui, out = P[lang]["ui"], []
    by_house = {}
    for pub in PUBS:
        by_house.setdefault(pub["house"], []).append(pub["date"])
    latest = max(by_house, key=lambda h: max(by_house[h]))
    for h, dates in sorted(by_house.items(), key=lambda kv: max(kv[1]), reverse=True):
        first, last = min(dates)[:7].replace("-", "."), max(dates)[:7].replace("-", ".")
        end = ui["to_present"] if h == latest else last
        n = f"{len(dates)}{ui['reports']}" if lang == "ko" else f"{len(dates)} {ui['reports']}"
        out.append((f"{first} – {end}", P["houses"][h][lang], n))
    return out


def tape(lang: str) -> str:
    ui = P[lang]["ui"]
    start = dt.date(int(min(p["date"] for p in PUBS)[:4]), 1, 1)
    end = dt.date(TODAY.year + 1, 1, 1)
    span = (end - start).days
    pos = lambda d: 100 * (d - start).days / span
    max_pages = 60
    ticks = []
    for i, pub in enumerate(sorted(PUBS, key=lambda r: r["date"])):
        d = dt.date.fromisoformat(pub["date"])
        pages = min(pub.get("pages") or 8, max_pages)
        height = 18 + 82 * math.sqrt(pages / max_pages)
        cls = f"tick {house(pub)['key']}" + (" contrib" if pub["role"] != "author" else "")
        label = f"{pub['date']}  {title(pub, lang)}"
        ticks.append(
            f'<a class="{cls}" href="#{pub["id"]}" style="left:{pos(d):.2f}%;height:{height:.0f}%;--i:{i}" '
            f'data-label="{e(label)}" aria-label="{e(label)}"></a>')
    years = "".join(
        f'<span style="left:{pos(dt.date(y, 1, 1)):.2f}%">{y}</span>'
        for y in range(start.year, TODAY.year + 1))
    keys = "".join(f'<span class="key {h["key"]}">{e(h[lang])}</span>'
                   for h in P["houses"].values() if any(p["house"] == h["ko"] for p in PUBS))
    if any(p["role"] != "author" for p in PUBS):
        keys += f'<span class="key hollow">{e(ui["key_contrib"])}</span>'
    return f"""
    <div class="tape-block">
      <div class="tape">{''.join(ticks)}</div>
      <div class="tape-years" aria-hidden="true">{years}</div>
      <div class="tape-caption"><span class="now">{e(ui['tape_rest'])}</span><span class="keys">{keys}</span></div>
    </div>"""


def ledger(lang: str) -> str:
    ui, out = P[lang]["ui"], []
    prefix = "" if lang == "ko" else "../"
    for year, group in groupby(PUBS, key=lambda r: r["date"][:4]):
        group = list(group)
        n = f"{len(group)}{ui['reports']}" if lang == "ko" else f"{len(group)} {ui['reports']}"
        rows = []
        for pub in group:
            h = house(pub)
            text = " ".join([pub["title_ko"], pub.get("title_en") or "",
                             pub.get("summary_ko", "") if lang == "ko" else ""]).lower()
            orig = (f'<p class="orig" lang="ko">{e(pub["title_ko"])}</p>'
                    if lang == "en" and pub.get("title_en") else "")
            meta = [f'<span class="house {h["key"]}">{e(h[lang])}</span>']
            meta += [f'<span>{e(P["topics"][t][lang])}</span>' for t in pub.get("topics", [])]
            if pub.get("pages"):
                meta.append(f'<span>{ui["pages"].replace("{n}", str(pub["pages"]))}</span>')
            if pub["role"] != "author":
                meta.append(f'<span>{e(ui["contrib"])}</span>')
            if pub.get("code_url"):
                meta.append(f'<a href="{e(pub["code_url"])}" rel="noopener">{ui["code"]}</a>')
            if pub.get("file"):
                meta.append(f'<a href="{prefix}{e(pub["file"])}">{ui["pdf"]}</a>')
            if pub.get("text_file"):
                meta.append(f'<a href="{prefix}{e(pub["text_file"])}">{ui["text"]}</a>')
            summary = ""
            if pub.get("summary_ko"):
                summary = (f'<details><summary>{e(ui["summary"])}</summary>'
                           f'<p lang="ko">{e(pub["summary_ko"])}</p></details>')
            rows.append(f"""
          <li id="{pub['id']}" data-house="{h['key']}" data-topics="{' '.join(pub.get('topics', []))}" data-text="{e(text)}">
            <time datetime="{pub['date']}">{pub['date'][5:7]}.{pub['date'][8:]}</time>
            <div>
              <p class="title"><a href="{e(pub['naver_url'])}" rel="noopener">{e(title(pub, lang))}</a></p>{orig}
              <p class="meta">{''.join(meta)}</p>{summary}
            </div>
          </li>""")
        out.append(f"""
        <div class="year">
          <h3>{year} <small>{n}</small></h3>
          <ul class="ledger">{''.join(rows)}
          </ul>
        </div>""")
    return "".join(out)


def controls(lang: str) -> str:
    ui = P[lang]["ui"]
    chip = lambda v, label, on=False: (
        f'<button type="button" data-value="{v}" aria-pressed="{str(on).lower()}">{e(label)}</button>')
    houses = [h for h in P["houses"].values() if any(p["house"] == h["ko"] for p in PUBS)]
    used = [t for t in P["topics"] if any(t in p.get("topics", []) for p in PUBS)]
    house_chips = chip("all", ui["all"], True) + "".join(chip(h["key"], h[lang]) for h in houses)
    topic_chips = chip("all", ui["all"], True) + "".join(chip(t, P["topics"][t][lang]) for t in used)
    topics = f'<div class="chips" data-key="topic" role="group">{topic_chips}</div>' if used else ""
    return f"""
        <div class="controls">
          <div class="chips" data-key="house" role="group">{house_chips}</div>
          <input type="search" id="q" placeholder="{e(ui['search'])}" aria-label="{e(ui['search'])}">
        </div>
        <div class="controls">
          {topics}
          <p class="count" data-tpl="{e(ui['count'])}" aria-live="polite">{ui['count'].replace('{n}', str(len(PUBS)))}</p>
        </div>"""


def study_section(lang: str) -> str:
    t, notes = STUDY[lang], STUDY["notes"]
    for note in notes:
        if not (SITE / note["file"]).is_file():
            raise SystemExit(f"study note missing: docs/{note['file']}")
    rows = "".join(
        f'<li><a href="/{e(n["file"])}">{e(n["label"][lang])}</a>'
        f'<span>{e(n[lang])} {e(t["pages"].replace("{n}", str(n["pages"])))}</span></li>' for n in notes)
    return f"""<section id="study">
    <h2>{e(t['h'])}<small>{e(t['count'].replace('{n}', str(len(notes))))}</small></h2>
    <div>
      <p>{e(t['note'])}</p>
      <ul class="rows">{rows}</ul>
    </div>
  </section>"""


def agent_rows(lang: str) -> str:
    rows = [
        ("/llms.txt", "전체 목록", "The full list"),
        ("/llms-full.txt", "목록과 요약", "The list with summaries"),
        ("/publications.json", "리포트별 데이터", "One record per report"),
        ("/reports/", "리포트 PDF와 텍스트", "Report PDFs and their text"),
    ]
    def name(path: str) -> str:                      # a folder has no index page to link to
        return f"<code>{path}</code>" if path.endswith("/") else f'<a href="{path}"><code>{path}</code></a>'
    return "".join(f'<li>{name(path)}<span>{e(ko if lang == "ko" else en)}</span></li>' for path, ko, en in rows)


def jsonld() -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "ProfilePage",
        "mainEntity": {
            "@type": "Person", "name": P["name"]["en"], "alternateName": P["name"]["ko"],
            "jobTitle": "Quant analyst", "url": BASE + "/", "sameAs": [P["github"]],
            "worksFor": {"@type": "Organization", "name": "Daishin Securities"},
            "knowsAbout": ["Korean equities", "investor flows", "factor investing", "quantitative research"],
        },
        "hasPart": [{
            "@type": "Report", "name": pub["title_ko"], "alternateName": pub.get("title_en") or None,
            "datePublished": pub["date"], "inLanguage": "ko", "url": pub["naver_url"],
            "publisher": {"@type": "Organization", "name": house(pub)["en"]},
            "author": {"@type": "Person", "name": P["name"]["en"]},
        } for pub in PUBS],
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def visible_text(markup: str) -> str:
    return unescape(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", markup, flags=re.S))


def font_links(doc: str) -> str:
    """Google Fonts stylesheets cut down to the characters this page shows.

    The full Korean families come as ~20 files per weight (about 3 MB for this page);
    a text= subset is one small file per weight. Characters outside the subset fall back to
    the system Korean font, so a later edit can never leave a blank glyph.
    """
    ascii_ = {chr(c) for c in range(32, 127)}
    body = {c for c in visible_text(doc) if not c.isspace()} | ascii_
    heads = " ".join(visible_text(m) for m in re.findall(
        r"<(?:h1|h2|h3)\b.*?</(?:h1|h2|h3)>|<p class=\"lede\">.*?</p>", doc, flags=re.S))
    display = {c for c in heads if not c.isspace()} | ascii_ | set("0123456789")
    pack = lambda chars: quote("".join(sorted(chars)))
    return "\n".join(
        f'<link rel="stylesheet" href="{e(FONT_API.format(family=fam, text=pack(chars)))}">'
        for fam, chars in (("Hahmlet:wght@300;400;600", display), ("IBM+Plex+Sans+KR:wght@400;500", body)))


def _page(lang: str) -> str:
    t, ui = P[lang], P[lang]["ui"]
    other = "en" if lang == "ko" else "ko"
    prefix = "" if lang == "ko" else "../"
    here, there = (("/", "/en/") if lang == "ko" else ("/en/", "/"))
    name, alt = P["name"][lang], P["name"][other]
    lang_switch = (f'<span aria-current="page">한국어</span><a href="{there}" lang="en" hreflang="en">English</a>'
                   if lang == "ko" else
                   f'<a href="{there}" lang="ko" hreflang="ko">한국어</a><span aria-current="page">English</span>')
    posts = "".join(f'<li><span class="when">{e(when)}</span><span><strong>{e(h)}</strong> {e(n)}</span></li>'
                    for when, h, n in tenure(lang))
    repos = "".join(f'<li><a href="{e(r["url"])}" rel="noopener">{e(r["name"])}</a><span>{e(r[lang])}</span></li>'
                    for r in P["repos"])
    updated = f"{TODAY:%Y.%m.%d}" if lang == "ko" else f"{TODAY:%-d %B %Y}"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(t['title'])}</title>
<meta name="description" content="{e(t['description'])}">
<link rel="canonical" href="{BASE}{here}">
<link rel="alternate" hreflang="ko" href="{BASE}/">
<link rel="alternate" hreflang="en" href="{BASE}/en/">
<link rel="alternate" type="application/json" href="{BASE}/publications.json" title="Publications">
<link rel="alternate" type="text/plain" href="{BASE}/llms.txt" title="llms.txt">
<meta property="og:type" content="profile">
<meta property="og:title" content="{e(t['title'])}">
<meta property="og:description" content="{e(t['description'])}">
<meta property="og:url" content="{BASE}{here}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
@@FONTS@@
<link rel="stylesheet" href="{prefix}assets/style.css">
<script type="application/ld+json">{jsonld()}</script>
</head>
<body>
<header class="masthead">
  <div class="wrap">
    <p class="series">{e(P['series'])}</p>
    <nav class="lang" aria-label="Language">{lang_switch}</nav>
  </div>
</header>

<div class="hero">
  <div class="wrap">
    <h1>{e(name)} <span class="alt" lang="{other}">{e(alt)}</span></h1>
    <p class="lede">{e(t['lede'])}</p>
    <p class="role">{e(t['role'])}</p>
    <p class="contact"><a href="mailto:{P['email']}">{P['email']}</a><a href="{P['github']}" rel="me noopener">github.com/SnowKonn</a></p>
    <ul class="posts">{posts}</ul>
    {tape(lang)}
  </div>
</div>

<main class="wrap">
  <section id="publications">
    <h2>{e(t['pubs_h'])}<small>{ui['count'].replace('{n}', str(len(PUBS)))}</small></h2>
    <div>
      <p>{e(t['pubs_note'])}</p>{controls(lang)}
      {ledger(lang)}
      <p class="empty" hidden>{e(ui['empty'])}</p>
    </div>
  </section>

  {study_section(lang)}

  <section id="repositories">
    <h2>{e(t['tools_h'])}</h2>
    <div><ul class="rows">{repos}</ul></div>
  </section>

  <section id="agents">
    <h2>{e(t['agents_h'])}</h2>
    <div>
      <p>{e(t['agents_note'])}</p>
      <ul class="rows">{agent_rows(lang)}</ul>
    </div>
  </section>
</main>

<footer>
  <div class="wrap">
    <p>{e(t['disclaimer'])}</p>
    <p>{e(ui['updated'])} {updated}</p>
  </div>
</footer>
<script src="{prefix}assets/site.js" defer></script>
</body>
</html>
"""


def page(lang: str) -> str:
    doc = _page(lang)
    return doc.replace("@@FONTS@@", font_links(doc.replace("@@FONTS@@", "")), 1)


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    return [x for v in (node.values() if isinstance(node, dict) else node) for x in _strings(v)]


def _tool_page(lang: str) -> str:
    """The stop-loss calculator: /stoploss/ (Korean) and /en/stoploss/ (English)."""
    t, ui = TOOL[lang], P[lang]["ui"]
    other = "en" if lang == "ko" else "ko"
    home, here, there = (("/", "/stoploss/", "/en/stoploss/") if lang == "ko" else ("/en/", "/en/stoploss/", "/stoploss/"))
    prefix = "../" if lang == "ko" else "../../"
    lang_switch = (f'<span aria-current="page">한국어</span><a href="{there}" lang="en" hreflang="en">English</a>'
                   if lang == "ko" else
                   f'<a href="{there}" lang="ko" hreflang="ko">한국어</a><span aria-current="page">English</span>')
    updated = f"{TODAY:%Y.%m.%d}" if lang == "ko" else f"{TODAY:%-d %B %Y}"
    items = lambda key: "".join(f"<li>{e(x)}</li>" for x in t[key])
    # text that the script writes later; listed here so that the font subset covers it
    glyphs = e(" ".join(_strings(t["js"]) + [a[lang] for a in VOL["assets"]]))
    as_json = lambda obj: json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(t['title'])}</title>
<meta name="description" content="{e(t['description'])}">
<link rel="canonical" href="{BASE}{here}">
<link rel="alternate" hreflang="ko" href="{BASE}/stoploss/">
<link rel="alternate" hreflang="en" href="{BASE}/en/stoploss/">
<meta property="og:type" content="website">
<meta property="og:title" content="{e(t['title'])}">
<meta property="og:description" content="{e(t['description'])}">
<meta property="og:url" content="{BASE}{here}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
@@FONTS@@
<link rel="stylesheet" href="{prefix}assets/style.css">
<link rel="stylesheet" href="{prefix}assets/tool.css">
</head>
<body>
<header class="masthead">
  <div class="wrap">
    <p class="series">{e(P['series'])}</p>
    <nav class="lang" aria-label="Language">{lang_switch}</nav>
  </div>
</header>

<div class="tool-head">
  <div class="wrap">
    <a class="back" href="{home}">← {e(t['back'])}</a>
    <h1>{e(t['h1'])}</h1>
    <p class="lede">{e(t['lede'])}</p>
  </div>
</div>

<main class="wrap tool">
  <section id="inputs">
    <h2>{e(t['h_in'])}</h2>
    <div>
      <p>{e(t['in_note'])}</p>
      <form>
        <div class="fields">
          <div><label for="asset">{e(t['f_asset'])}</label><select id="asset"></select></div>
          <fieldset><legend>{e(t['f_window'])}</legend><div class="radios">
            <label><input type="radio" name="win" value="1y" checked> {e(t['w1'])}</label>
            <label><input type="radio" name="win" value="3y"> {e(t['w3'])}</label></div></fieldset>
          <div><label for="sigma">{e(t['f_sigma'])}</label><input id="sigma" type="number" value="30" min="1" max="300" step="0.1" inputmode="decimal"></div>
        </div>
        <p class="hint" id="vol-note" aria-live="polite"></p>
        <div class="scroll"><table class="in" id="sc">
          <caption>{e(t['sc_caption'])}</caption>
          <thead><tr><th>{e(t['js']['col_name'])}</th><th>{e(t['js']['col_p'])}</th><th>{e(t['js']['col_r'])}</th><th></th></tr></thead>
          <tbody></tbody>
        </table></div>
        <p class="actions"><button type="button" id="add">{e(t['add'])}</button></p>
        <p class="hint" id="psum" aria-live="polite"></p>
        <div class="fields">
          <div><label for="horizon">{e(t['f_horizon'])}</label><input id="horizon" type="number" value="1" min="0.1" max="30" step="0.25" inputmode="decimal"></div>
          <div><label for="entry">{e(t['f_entry'])}</label><input id="entry" type="number" min="0" step="any" inputmode="decimal" placeholder="{e(t['f_entry_ph'])}"></div>
        </div>
        <p>{e(t['now_in_note'])}</p>
        <div class="fields">
          <div><label for="cur">{e(t['f_cur'])}</label><input id="cur" type="number" min="0" step="any" inputmode="decimal" placeholder="{e(t['f_entry_ph'])}"></div>
          <div><label for="months">{e(t['f_months'])}</label><input id="months" type="number" min="0" step="1" inputmode="decimal" placeholder="{e(t['f_entry_ph'])}"></div>
        </div>
      </form>
    </div>
  </section>

  <section id="output">
    <h2>{e(t['h_out'])}</h2>
    <div id="result" aria-live="polite"></div>
  </section>

  <section id="now">
    <h2>{e(t['h_now'])}</h2>
    <div id="now-out" aria-live="polite"></div>
  </section>

  <section id="assumptions">
    <h2>{e(t['h_assume'])}</h2>
    <div>
      <ul class="plain">{items('assume')}</ul>
      <h3>{e(t['limits_h'])}</h3>
      <ul class="plain">{items('limits')}</ul>
      <p>{e(t['source'])} <a href="/{e(TOOL['note_pdf'])}">{e(t['source_link'])}</a></p>
      <p class="note">{e(t['vol_source'].replace('{d}', VOL['generated']))}</p>
    </div>
  </section>
</main>

<footer>
  <div class="wrap">
    <p>{e(P[lang]['disclaimer'])}</p>
    <p>{e(ui['updated'])} {updated}</p>
  </div>
</footer>
<div hidden>{glyphs}</div>
<script type="application/json" id="i18n">{as_json(t['js'])}</script>
<script type="application/json" id="vol-data">{as_json(VOL)}</script>
<script src="{prefix}assets/stoploss.js" defer></script>
</body>
</html>
"""


def tool_page(lang: str) -> str:
    doc = _tool_page(lang)
    return doc.replace("@@FONTS@@", font_links(doc.replace("@@FONTS@@", "")), 1)


def publications_json() -> str:
    return json.dumps({
        "schema": {
            "id": "stable anchor on the page, e.g. https://snowkonn.github.io/#<id>",
            "date": "publication date as listed on Naver Securities Research (YYYY-MM-DD)",
            "house": "publishing broker (Korean name); house_en is the English name",
            "category": "Naver research category key: invest | market | economy | industry",
            "title_ko": "original title", "title_en": "translation by the author of this page, not an official title",
            "role": "author = named as the report's analyst; contributor = one of several authors of a joint report",
            "pages": "PDF page count", "topics": "topic keys assigned by the author of this page",
            "summary_ko": "summary text published with the report on Naver (Korean)",
            "naver_url": "original listing (Naver Securities Research, or the broker's own board when source is ibks)",
            "pdf_url": "PDF hosted by Naver", "file_url": "PDF on this site", "text_url": "plain-text extraction of the PDF on this site",
            "code_url": "public repository with the code behind the report, if any",
            "source": "naver | ibks: where the listing was found",
        },
        "author": {"name": P["name"]["en"], "name_ko": P["name"]["ko"], "url": BASE + "/"},
        "generated": TODAY.isoformat(),
        "authorship_rule": "A report is listed only if the author is named on its first page (PDF text or OCR of the "
                           "cover) or in the author column of the broker's research board. Monthly house compilations, "
                           "weekly strategy notes and routine daily commentary are left out.",
        "count": len(PUBS),
        "publications": [{**pub, "house_en": house(pub)["en"],
                          "file_url": f"{BASE}/{pub['file']}" if pub.get("file") else "",
                          "text_url": f"{BASE}/{pub['text_file']}" if pub.get("text_file") else ""} for pub in PUBS],
    }, ensure_ascii=False, indent=1)


def llms(full: bool) -> str:
    lines = [
        f"# {P['name']['en']} ({P['name']['ko']})", "",
        f"> {P['en']['description']} Reports are written in Korean. English titles below are the author's own translations.", "",
        "## About", "", f"- {P['en']['role']}. Before that, IBK Securities.", f"- {P['en']['lede']}",
        f"- Contact: {P['email']}, {P['github']}", "",
        "## How to use this index", "",
        "- Cite a report by its title, publication date and publishing broker, and link to its Naver listing.",
        "- Only reports the author wrote alone are listed. Monthly house compilations, weekly strategy notes, "
        "daily commentary and co-authored reports are left out.",
        "- Each report is kept here as a PDF and as plain text (reports/*.txt), which is the easiest form to read.",
        "- Copyright in each report belongs to the publishing broker. The files are kept as the author's own record.",
        "- Nothing here is investment advice or an official view of the author's employer.", "",
        "## Machine-readable files", "",
        f"- [publications.json]({BASE}/publications.json): one structured record per report",
        f"- [llms-full.txt]({BASE}/llms-full.txt): this list with the Korean summary of each report",
        f"- {BASE}/reports/: one PDF and one .txt per report, named <date>-<broker>-<id>",
        f"- [Korean page]({BASE}/) and [English page]({BASE}/en/)", "",
        f"## Study notes written with AI ({len(STUDY['notes'])})", "",
        "- Derivation notes in English, written by the author together with an AI model. Not peer reviewed; "
        "the numbers in them are illustrative, not estimates for any security.",
        *[f"- [{n['title']}]({BASE}/{n['file']}): {n['authors']}, {n['date']}, v{n['version']}, {n['pages']} pages. {n['en']}"
          for n in STUDY["notes"]], "",
        f"## Publications ({len(PUBS)})", "",
    ]
    for pub in PUBS:
        en = f" / {pub['title_en']}" if pub.get("title_en") else ""
        co = ", co-authored" if pub["role"] != "author" else ""
        topics = ", ".join(P["topics"][t]["en"] for t in pub.get("topics", []))
        tail = f", {topics}" if topics else ""
        text = f" Full text: {BASE}/{pub['text_file']}" if pub.get("text_file") else ""
        lines.append(f"- [{pub['title_ko']}{en}]({pub['naver_url']}): {pub['date']}, {house(pub)['en']}{co}{tail}.{text}")
        if full and pub.get("summary_ko"):
            lines += ["", *[f"  {s}" for s in pub["summary_ko"].splitlines() if s.strip()], ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    for sub in ("assets", "en"):                     # docs/reports (curate.py) and docs/study are kept
        shutil.rmtree(SITE / sub, ignore_errors=True)
        (SITE / sub).mkdir(parents=True)
    for name in ("style.css", "site.js", "tool.css", "stoploss.js"):
        shutil.copy(ROOT / "src" / name, SITE / "assets" / name)
    for folder, lang in ((SITE / "stoploss", "ko"), (SITE / "en" / "stoploss", "en")):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.html").write_text(tool_page(lang))
    (SITE / "index.html").write_text(page("ko"))
    (SITE / "en" / "index.html").write_text(page("en"))
    (SITE / "publications.json").write_text(publications_json())
    (SITE / "llms.txt").write_text(llms(False))
    (SITE / "llms-full.txt").write_text(llms(True))
    (SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{BASE}{p}</loc><lastmod>{TODAY}</lastmod></url>\n" for p in ("/", "/en/", "/stoploss/", "/en/stoploss/"))
        + "</urlset>\n")
    (SITE / ".nojekyll").write_text("")
    print(f"built {SITE}: {len(PUBS)} publications")


if __name__ == "__main__":
    main()
