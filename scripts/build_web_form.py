#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""온라인 응시본 생성기. items/ + forms/MANIFEST.yml -> forms/form-A.web.html

생성물이므로 손으로 고치지 않는다. 정답·해설·오답 진단은 읽지도 쓰지도 않는다.

응시본은 **파일 하나로, 네트워크 없이** 동작해야 한다 — 사내망에서 외부 폰트·CDN이 막혀도
응시가 멈추면 안 된다. 외부 URL이 들어가면 생성이 실패한다(check_leaks).
"""
import re, io, json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT  = ROOT / "forms" / "form-A.web.html"

# ---------- 파싱 ----------
def read(p): return (ROOT / p).read_text(encoding="utf-8")

def parse(path):
    t = path.read_text(encoding="utf-8")
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', t, re.S)
    fm = {}
    for line in m.group(1).split('\n'):
        km = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if km: fm[km.group(1)] = km.group(2).strip()
    return fm, m.group(2)

def section(body, name):
    m = re.search(rf'^## {name}\n(.*?)(?=^## |\Z)', body, re.S | re.M)
    return m.group(1).strip() if m else ""

# ---------- 아주 작은 마크다운 -> HTML ----------
def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def inline(s):
    s = esc(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'「([^」]+)」', r'<em class="doc">「\1」</em>', s)
    return s

def blocks(s):
    """문단 / 인용 블록만 지원한다. 문항 본문에 그 이상은 쓰지 않는다."""
    out, buf, quote = [], [], []
    def flush_p():
        if buf:
            out.append("<p>%s</p>" % inline(" ".join(buf))); buf.clear()
    def flush_q():
        if quote:
            out.append('<blockquote>%s</blockquote>' % inline(" ".join(quote))); quote.clear()
    for raw in s.split("\n"):
        line = raw.rstrip()
        if line.startswith("> "):
            flush_p(); quote.append(line[2:])
        elif not line.strip():
            flush_p(); flush_q()
        else:
            flush_q(); buf.append(line.strip())
    flush_p(); flush_q()
    return "".join(out)

def item_context(situation, stem):
    """문항 고유 자료. 블록 문항은 '(STEM-00N 참조)' 표지를 떼고 남는 것이 고유 자료다.

    블록 문항이라도 상황 절에 검증 대상 AI 출력문 같은 고유 자료가 붙는다.
    이걸 버리면 답할 수 없는 문항이 된다.
    """
    if stem == "null":
        return situation
    return re.sub(r'^\(STEM-\d{3}\s*참조\)\s*', '', situation).strip()

def options_of(body):
    return re.findall(r'^\d\.\s*(.+)$', section(body, '선택지'), re.M)

# ---------- 자료 수집 ----------
def collect():
    stems = {}
    for p in sorted(ROOT.glob("items/stems/STEM-*.md")):
        fm, body = parse(p)
        stems[fm['id']] = {"label": fm.get('label', '').strip('"'),
                           "html": blocks(section(body, '지문'))}

    order = re.findall(r'^  - \{seq: (\d+),\s+id: (MC-[A-Z]{3}-\d{3}), stem: (\S+),',
                       read("forms/MANIFEST.yml"), re.M)

    mc = []
    for seq, iid, stem in order:
        path = list(ROOT.glob(f"items/mc/*/{iid}.md"))[0]
        fm, body = parse(path)
        opts = options_of(body)
        assert len(opts) == 4, iid
        mc.append({
            "seq": int(seq), "id": iid,
            "stem": None if stem == "null" else stem,
            "solo": blocks(item_context(section(body, '상황'), stem)),
            "q": blocks(section(body, '질문')),
            "options": [inline(o) for o in opts],
            "worst": fm.get('form') == '최선차선',
        })

    # 자기보고. '→ ____' 이 붙은 선택지를 고르면 한 줄 서술칸을 연다.
    sr_src = read("selfreport/checkitems.md")
    sr = []
    for m in re.finditer(r'^## (SR-\d+)\n\n\*\*(.+?)\*\*(.*?)(?=^##|\Z)', sr_src, re.S | re.M):
        sid, q, rest = m.group(1), m.group(2), m.group(3)
        raw = re.findall(r'^- \[ \] (.+)$', rest, re.M)
        opts = [re.sub(r'\s*→.*$', '', o).strip() for o in raw]
        free = next((o for o, r in zip(opts, raw) if '→' in r), None)
        sr.append({"id": sid, "q": inline(q), "options": opts, "free": free})
    assert len(sr) == 3, sr

    # 주관식
    fr = []
    for fid, seq in [("FR-01", 21), ("FR-02", 22)]:
        fm, body = parse(ROOT / f"items/fr/{fid}.md")
        fr.append({
            "id": fid, "seq": seq,
            "guide": blocks(section(body, '지시')),
            "q": blocks(section(body, '문항')),
            "persona": fm.get('persona_selectable') == 'true',
            "min": int(fm.get('answer_min_chars', 400)),
        })

    personas = []
    for p in sorted(ROOT.glob("personas/*.md")):
        fm, body = parse(p)
        personas.append({"key": fm['key'], "label": fm['label'],
                         "html": blocks(body.split("## 페르소나", 1)[1].strip())})
    ORDER = ["HR", "SALES", "MFG", "FIN", "DEV", "STAFF"]
    personas.sort(key=lambda x: ORDER.index(x['key']))

    return {"form": "A", "stems": stems, "mc": mc, "sr": sr, "fr": fr, "personas": personas}

# ---------- 누출·외부 의존 검사 ----------
def check_data(data):
    """생성 데이터 단계의 누출 검사. 문제 목록을 돌려준다."""
    blob = json.dumps(data, ensure_ascii=False)
    return [f"생성 데이터에 '{kw}' 누출" for kw in ("정답", "해설", "distractor", "answer", "오답")
            if kw in blob]

def check_leaks(html):
    """완성된 응시본 검사. 문제 목록을 돌려준다(빈 목록이면 통과)."""
    problems = [f"응시본에 '{kw}' 누출" for kw in ("정답", "해설", "distractor_dx", "오답 진단")
                if kw in html]
    # 네트워크 없이 동작해야 한다: 외부 리소스를 불러오는 src/href 금지
    for m in re.finditer(r'''(?:src|href)\s*=\s*["']?\s*(https?:)?//''', html, re.I):
        problems.append(f"응시본에 외부 리소스 참조: {html[m.start():m.start()+60]!r}")
    for bad in ("fonts.googleapis", "fonts.gstatic", "@import"):
        if bad in html:
            problems.append(f"응시본에 외부 의존 '{bad}'")
    for need, why in (("<!DOCTYPE html>", "DOCTYPE"), ('<html lang="ko">', "lang"),
                      ('name="viewport"', "viewport")):
        if need not in html:
            problems.append(f"응시본에 {why} 선언 없음")
    return problems

# ---------- 템플릿 ----------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AX Literacy 진단 폼 A</title>
<style>
:root{
  --ground:#f7f8fa; --surface:#ffffff; --surface-2:#f0f2f6;
  --ink:#1a1d23; --ink-soft:#4f5764; --ink-faint:#666e7a;
  --line:#e2e5eb; --line-strong:#cbd1da;
  --accent:#2f5d8c; --accent-soft:#eaf1f8; --accent-ink:#22456a; --on-accent:#ffffff;
  --warn:#9a5716; --warn-soft:#fbf1e6; --ok:#2a6549;
  --barh:54px;
  --sans:system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#14171c; --surface:#1c2027; --surface-2:#232830;
  --ink:#e8eaed; --ink-soft:#b0b8c3; --ink-faint:#949ca8;
  --line:#2c323b; --line-strong:#3b434e;
  --accent:#7faad4; --accent-soft:#1f2a36; --accent-ink:#a8c8e6; --on-accent:#0f1620;
  --warn:#e0a060; --warn-soft:#2a2118; --ok:#6bbd95;
}}
:root[data-theme="dark"]{
  --ground:#14171c; --surface:#1c2027; --surface-2:#232830;
  --ink:#e8eaed; --ink-soft:#b0b8c3; --ink-faint:#949ca8;
  --line:#2c323b; --line-strong:#3b434e;
  --accent:#7faad4; --accent-soft:#1f2a36; --accent-ink:#a8c8e6; --on-accent:#0f1620;
  --warn:#e0a060; --warn-soft:#2a2118; --ok:#6bbd95;
}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
     font-size:15px;line-height:1.7;-webkit-text-size-adjust:100%;word-break:keep-all;overflow-wrap:anywhere}
.wrap{max-width:720px;margin:0 auto;padding-inline:16px;padding-block:0 96px}
h1,h2,h3{text-wrap:balance;margin:0}
code{font-family:var(--mono);font-size:.9em;background:var(--surface-2);
     padding:1px 5px;border-radius:3px}
.doc{font-style:normal;font-weight:500}
blockquote{margin:12px 0;padding:12px 16px;background:var(--surface-2);
  border-left:3px solid var(--line-strong);border-radius:0 6px 6px 0;color:var(--ink)}
button{font:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}

/* ---- 상단 바 ---- */
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:40;background:var(--surface);
  border-bottom:1px solid var(--line);height:var(--barh);display:flex;align-items:center}
.bar .wrap{padding-block:0;display:flex;align-items:center;gap:14px;width:100%}
.bar-sec{font-weight:600;font-size:13px;letter-spacing:.02em;white-space:nowrap}
.bar-prog{font-family:var(--mono);font-size:12px;color:var(--ink-soft);
  font-variant-numeric:tabular-nums;white-space:nowrap}
.bar-time{margin-left:auto;text-align:right;font-family:var(--mono);
  font-variant-numeric:tabular-nums;white-space:nowrap}
.bar-time b{font-weight:500;font-size:14px}
.bar-time span{display:block;font-size:11px;color:var(--ink-faint);line-height:1.3}
.bar-time.over b{color:var(--warn)}
.meter{position:absolute;left:0;bottom:-1px;height:2px;background:var(--accent);
  transition:width .9s linear;width:0}
.meter.over{background:var(--warn)}
@media(max-width:420px){.bar-prog{display:none}}
.toast{position:sticky;top:calc(var(--barh) + 8px);z-index:35;margin-top:10px;display:flex;gap:10px;
  align-items:flex-start;background:var(--warn-soft);border:1px solid var(--line-strong);
  border-left:3px solid var(--warn);border-radius:0 8px 8px 0;padding:10px 12px;font-size:13.5px}
.toast button{margin-left:auto;background:none;border:0;color:var(--ink-soft);padding:0 4px;font-size:18px;line-height:1}

/* ---- 공통 ---- */
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-faint);font-weight:600;font-family:var(--mono);margin:0}
.lede{color:var(--ink-soft)}
.rule{height:1px;background:var(--line);border:0;margin:28px 0}
.btn{appearance:none;border:1px solid var(--accent);background:var(--accent);color:var(--on-accent);
  padding:11px 22px;border-radius:7px;font-weight:600;font-size:15px;min-height:44px}
.btn:hover{filter:brightness(1.08)}
.btn.ghost{background:transparent;color:var(--accent-ink);border-color:var(--line-strong)}
.btn.danger{background:transparent;color:var(--warn);border-color:var(--line-strong)}
.nav{display:flex;gap:10px;flex-wrap:wrap;margin-top:32px}
.note{background:var(--accent-soft);border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;font-size:13.5px;color:var(--ink)}
.note.warn{background:var(--warn-soft)}
.note p{margin:0}.note p+p{margin-top:6px}

/* ---- 인트로 ---- */
.hero{padding-block:44px 8px}
.hero h1{font-size:30px;font-weight:600;letter-spacing:-.02em;line-height:1.3}
.hero .sub{color:var(--ink-soft);margin-top:10px;font-size:16px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;
  background:var(--surface);margin:26px 0 0}
.fact{padding:14px 16px;border-right:1px solid var(--line)}
.fact:last-child{border-right:0}
.fact dt{font-size:11px;color:var(--ink-faint);letter-spacing:.08em;font-weight:600}
.fact dd{margin:3px 0 0;font-family:var(--mono);font-size:17px;font-variant-numeric:tabular-nums}
.rules{margin:22px 0 0;border-top:1px solid var(--line)}
.rules div{padding:13px 0;border-bottom:1px solid var(--line);display:grid;
  grid-template-columns:130px 1fr;gap:16px;align-items:start;font-size:14px}
.rules dt{font-weight:600}.rules dd{margin:0}
@media(max-width:520px){.rules div{grid-template-columns:1fr;gap:4px}.fact{border-right:0;border-bottom:1px solid var(--line)}
  .hero h1{font-size:25px}.btn{flex:1 1 auto}}
.idfield{margin-top:24px}
.idfield label{display:block;font-weight:600;font-size:14px;margin-bottom:6px}
input[type=text],textarea{width:100%;font-family:inherit;font-size:16px;color:var(--ink);
  background:var(--surface);border:1px solid var(--line-strong);border-radius:7px;
  padding:10px 12px;line-height:1.7}
textarea{resize:vertical;min-height:260px}
textarea.small{min-height:110px;font-size:14px}
input[type=text]:focus,textarea:focus{border-color:var(--accent);outline:none;
  box-shadow:0 0 0 3px var(--accent-soft)}
.resume{margin-top:22px}

/* ---- 문항 ---- */
.sec-head{padding-block:30px 6px}
.sec-head h2{font-size:21px;font-weight:600;letter-spacing:-.01em}
.sec-head p{color:var(--ink-soft);margin:6px 0 0;font-size:14px}
.block{margin-top:26px}
.stem{position:sticky;top:calc(var(--barh) + env(safe-area-inset-top,0px));z-index:20;
  background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:0 9px 9px 0;padding:14px 16px 12px;margin-bottom:4px;
  box-shadow:0 6px 14px -12px rgba(0,0,0,.4)}
.stem-top{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
.stem-top .eyebrow{color:var(--accent-ink)}
.stem-toggle{margin-left:auto;background:none;border:0;color:var(--ink-soft);
  font-size:12px;padding:6px 8px;border-radius:4px}
.stem-body{max-height:46vh;overflow:auto;font-size:14.5px}
.stem-body p{margin:0 0 8px}
.stem.collapsed .stem-body{display:none}
/* 좁은 화면에서는 지문이 선택지를 가리므로 고정하지 않는다 */
@media(max-width:520px){.stem{position:static}}
.item{padding:22px 0;border-bottom:1px solid var(--line);scroll-margin-top:calc(var(--barh) + 16px)}
.item:last-child{border-bottom:0}
.item.flash{animation:flash 1.6s ease-out}
@keyframes flash{from{background:var(--warn-soft)}to{background:transparent}}
.q{display:flex;gap:12px;align-items:baseline}
.q-num{font-family:var(--mono);font-weight:500;color:var(--accent-ink);
  font-size:15px;flex:none;min-width:26px}
.q-body p{margin:0 0 8px}.q-body p:last-child{margin-bottom:0}
fieldset{border:0;margin:0;padding:0;min-width:0}
.opts{margin:14px 0 0;padding:0;display:flex;flex-direction:column;gap:7px}
.opt{display:flex;gap:11px;align-items:flex-start;padding:10px 13px;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid transparent;border-radius:0 7px 7px 0;
  cursor:pointer;font-size:14.5px;transition:background .12s,border-color .12s}
.opt:hover{background:var(--surface-2)}
.opt input{margin:5px 0 0;accent-color:var(--accent);flex:none;width:16px;height:16px}
.opt .n{font-family:var(--mono);color:var(--ink-faint);flex:none}
.opt.on,.opt:has(input:checked){background:var(--accent-soft);border-color:var(--line-strong);border-left-color:var(--accent)}
.opts.worst .opt.on,.opts.worst .opt:has(input:checked){background:var(--warn-soft);border-left-color:var(--warn)}
.opt:has(input:focus-visible){outline:2px solid var(--accent);outline-offset:1px}
.pick{margin-top:14px}
.pick-label{font-size:12px;font-weight:600;letter-spacing:.04em;color:var(--ink-soft);
  margin-bottom:6px;display:flex;align-items:center;gap:7px}
.pick-label .dot{width:7px;height:7px;border-radius:50%;background:var(--accent)}
.pick-label.worst .dot{background:var(--warn)}
.dup{color:var(--warn);font-size:12.5px;margin-top:7px}

/* ---- 주관식 ---- */
.fr{margin-top:26px;padding-bottom:6px}
.fr-guide{background:var(--surface);border:1px solid var(--line);border-radius:9px;
  padding:15px 17px;font-size:14.5px}
.fr-guide p{margin:0 0 9px}.fr-guide p:last-child{margin-bottom:0}
.fr-q{margin-top:18px;font-size:14.5px}
.fr-q p{margin:0 0 10px}
.personas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:16px 0}
.pcard{display:flex;gap:9px;align-items:center;padding:11px 13px;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid transparent;border-radius:0 7px 7px 0;
  cursor:pointer;font-size:14px}
.pcard.on,.pcard:has(input:checked){background:var(--accent-soft);border-left-color:var(--accent)}
.pcard .k{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint)}
.ptext{margin:6px 0 18px}
.field-label{display:block;font-weight:600;font-size:14px;margin:14px 0 6px}
.field-label span{font-weight:400;color:var(--ink-soft)}
.counter{font-family:var(--mono);font-size:12px;color:var(--ink-faint);
  text-align:right;margin:6px 0 0;font-variant-numeric:tabular-nums}
.counter.ok{color:var(--ok)}

/* ---- 제출 검토 ---- */
.review{margin-top:28px;border:1px solid var(--line-strong);border-radius:10px;background:var(--surface);padding:18px}
.review h3{font-size:17px}
.review ul{margin:10px 0 0;padding-left:20px;font-size:14px}
.review li{margin:6px 0}
.review .inline{display:inline-flex;flex-wrap:wrap;gap:4px 10px;vertical-align:top}
.linkbtn{background:none;border:0;padding:0;color:var(--accent-ink);text-decoration:underline;font-size:inherit}

/* ---- 완료 ---- */
.done-head{padding-block:40px 4px}
.code{font-family:var(--mono);font-size:22px;letter-spacing:.12em;font-weight:500}
.sumgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:0;
  border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface);margin:20px 0 0}
.out{width:100%;min-height:160px;font-family:var(--mono);font-size:11.5px;line-height:1.55;
  white-space:pre;overflow:auto}
.steps{counter-reset:s;margin:18px 0 0;padding:0;list-style:none}
.steps li{counter-increment:s;padding:14px 0 14px 38px;border-bottom:1px solid var(--line);
  position:relative;font-size:14.5px}
.steps li::before{content:counter(s);position:absolute;left:0;top:14px;width:24px;height:24px;
  border-radius:50%;background:var(--accent-soft);color:var(--accent-ink);font-family:var(--mono);
  font-size:12px;display:grid;place-items:center;font-weight:600}
.steps .nav{margin-top:10px}
.msg{font-size:13px;margin:8px 0 0;color:var(--ink-soft)}
.survey{margin:18px 0 0;padding:16px 16px 6px;border:1px solid var(--line);border-radius:8px;background:var(--surface)}
.survey h2{font-size:17px;font-weight:600}
.survey fieldset{border:0;margin:16px 0 0;padding:0;min-width:0}
.survey legend{font-weight:600;font-size:14px;padding:0;margin-bottom:8px}
.sv-nums{display:flex;flex-wrap:wrap;gap:6px}
.sv-nums label,.sv-scale label{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border:1px solid var(--line);
  border-radius:6px;background:var(--surface);font-family:var(--mono);font-size:13px;cursor:pointer}
.sv-scale label{font-family:inherit}
.sv-nums label.on,.sv-nums label:has(input:checked),.sv-scale label.on,.sv-scale label:has(input:checked){background:var(--accent-soft);border-color:var(--accent)}
.sv-nums input,.sv-scale input{accent-color:var(--accent);margin:0}
.sv-scale{display:flex;flex-wrap:wrap;gap:6px}
details summary{cursor:pointer;color:var(--ink-soft);font-size:13px;margin-top:22px}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>

<header class="bar" id="bar" hidden>
  <div class="wrap">
    <span class="bar-sec" id="barSec">0부</span>
    <span class="bar-prog" id="barProg"></span>
    <span class="bar-time" id="barTime"><b id="tSec">0:00</b><span id="tTotal">전체 0:00</span></span>
  </div>
  <div class="meter" id="meter"></div>
</header>

<main class="wrap">
<div class="toast" id="toast" role="status" hidden><span id="toastMsg"></span><button type="button" id="toastX" aria-label="안내 닫기">×</button></div>

<!-- 인트로 -->
<section id="s-intro">
  <div class="hero">
    <p class="eyebrow">폼 A</p>
    <h1>AX Literacy 진단</h1>
    <p class="sub">툴 지식을 묻지 않습니다. 실제 업무 상황에서 <strong>어떻게 판단하는지</strong>를 봅니다.</p>
  </div>

  <div class="note warn resume" id="resumeBox" hidden>
    <p><strong>이 PC에 작성 중인 응답이 있습니다.</strong> <span id="resumeInfo"></span></p>
    <div class="nav" style="margin-top:12px">
      <button class="btn" type="button" id="resumeYes">이어서 하기</button>
      <button class="btn danger" type="button" id="resumeNo">지우고 새로 시작</button>
    </div>
  </div>

  <dl class="facts">
    <div class="fact"><dt>소요 시간</dt><dd>35분</dd></div>
    <div class="fact"><dt>객관식</dt><dd>20문항</dd></div>
    <div class="fact"><dt>주관식</dt><dd>2문항</dd></div>
    <div class="fact"><dt>총점</dt><dd>100점</dd></div>
  </dl>

  <div class="note" style="margin-top:20px">
    <p>이 진단의 결과는 <strong>교육 설계에만 사용되며, 인사 평가·승진·배치 자료로 사용되지 않습니다.</strong></p>
    <p>응답은 인터넷으로 전송되지 않습니다. 마지막 화면에서 <strong>응답 파일을 저장해 담당자에게 보내면</strong> 끝납니다.</p>
    <p>작성 중인 내용은 이 브라우저에 자동 저장되므로, 창을 닫거나 새로고침해도 이어서 할 수 있습니다.</p>
  </div>

  <h3 style="margin-top:30px;font-size:16px">이 진단이 쓰는 우선순위 규칙</h3>
  <p class="lede" style="font-size:14px;margin:6px 0 0">일부 문항은 "가장 먼저 할 일"을 묻습니다.
    <strong>모든 선택지가 옳을 수 있고, 그중 우선순위를 봅니다.</strong></p>
  <dl class="rules">
    <div><dt>검증 우선순위</dt><dd>의사결정에 직접 쓰이는가 × 원자료로 재현 가능한가. 비슷하면 <strong>"없다고 한 것"을 먼저</strong> 본다 — 확인하지 않으면 드러나지 않기 때문이다</dd></div>
    <div><dt>위임 경계 기준</dt><dd>작업량이 아니라 책임이 귀속되는 판단인가 × 되돌릴 수 있는가</dd></div>
    <div><dt>흐름 개선 우선순위</dt><dd>단계를 덧붙이는 것보다 <strong>없앨 수 있는 단계</strong>가 먼저</dd></div>
  </dl>

  <h3 style="margin-top:28px;font-size:16px">주관식 준비 사항</h3>
  <ul style="font-size:14px;color:var(--ink-soft);padding-left:20px;margin:8px 0 0">
    <li><strong>21번</strong>은 지난 한 달 안에 실제로 수행한 반복 업무 1개로 답합니다. 답안에 <strong>업무 이름 / 시스템 이름 / 데이터 항목 이름</strong>이 들어가야 합니다.</li>
    <li><strong>22번</strong>은 직무 페르소나 6개 중 하나를 골라 답합니다.</li>
    <li><strong>AI를 사용해 작성해도 됩니다.</strong> 사용했다면 답안 아래 「사용한 프롬프트」 칸에 붙여넣으십시오. 채점 자료로 함께 씁니다.</li>
  </ul>

  <div class="idfield">
    <label for="pid">식별 코드 <span style="font-weight:400;color:var(--ink-soft)">(선택) — 무기명입니다. 재진단 때 대조하려면 <strong>본인만 아는 규칙</strong>으로 만드십시오 (예: 좋아하는 색 + 태어난 달)</span></label>
    <input type="text" id="pid" placeholder="예: navy07" autocomplete="off" maxlength="40">
  </div>

  <div class="nav"><button class="btn" type="button" id="go">진단 시작</button></div>
</section>

<!-- 0부 -->
<section id="s-sr" hidden>
  <div class="sec-head">
    <p class="eyebrow">0부 · 권장 2분</p>
    <h2>자기보고 3문항</h2>
    <p>이 3문항은 <strong>점수에 반영되지 않습니다.</strong> 결과 해석의 정확도를 높이는 데만 씁니다. 사실대로 답해 주십시오.</p>
  </div>
  <div id="srList"></div>
  <div class="nav"><button class="btn" type="button" data-next="mc">1부로</button></div>
</section>

<!-- 1부 -->
<section id="s-mc" hidden>
  <div class="sec-head">
    <p class="eyebrow">1부 · 권장 20분</p>
    <h2>객관식 20문항</h2>
    <p>__WORST_SEQS__번은 <strong>가장 적절한 것</strong>과 <strong>가장 부적절한 것</strong>을 각각 고릅니다. 나머지는 가장 적절한 것 하나를 고릅니다.</p>
  </div>
  <div id="mcList"></div>
  <div class="nav">
    <button class="btn ghost" type="button" data-next="sr">0부로</button>
    <button class="btn" type="button" data-next="fr">2부로</button>
  </div>
</section>

<!-- 2부 -->
<section id="s-fr" hidden>
  <div class="sec-head">
    <p class="eyebrow">2부 · 권장 13분</p>
    <h2>주관식 2문항</h2>
    <p><strong>네 개의 번호에 모두 답해 주십시오.</strong> 분량보다 네 항목의 균형이 중요합니다.</p>
  </div>
  <div id="frList"></div>
  <div class="nav">
    <button class="btn ghost" type="button" data-next="mc">1부로</button>
    <button class="btn" type="button" id="submit">제출 전 확인</button>
  </div>
  <div class="review" id="review" hidden tabindex="-1">
    <h3 id="reviewTitle">제출 전 확인</h3>
    <div id="reviewBody"></div>
    <div class="nav" style="margin-top:16px">
      <button class="btn" type="button" id="confirm">제출하고 응답 파일 만들기</button>
      <button class="btn ghost" type="button" id="reviewClose">계속 작성</button>
    </div>
  </div>
</section>

<!-- 완료 -->
<section id="s-done" hidden>
  <div class="done-head">
    <p class="eyebrow">아직 끝나지 않았습니다</p>
    <h1 style="font-size:26px;font-weight:600">응답 파일을 담당자에게 보내야 완료됩니다</h1>
    <p class="lede" style="margin-top:8px">응답은 인터넷으로 전송되지 않았습니다. 아래 순서대로 진행해 주십시오.</p>
  </div>
  <div class="note" style="margin-top:14px">
    <p>응답 코드 <span class="code" id="ridShow"></span></p>
    <p style="font-size:13px;color:var(--ink-soft)">담당자에게 파일을 보낼 때 이 코드를 함께 적어 주십시오.</p>
  </div>
  <div id="warnBox"></div>
  <section class="survey" aria-labelledby="svTitle">
    <h2 id="svTitle">파일을 저장하기 전에 — 문항을 고치는 데 쓰는 질문 3개</h2>
    <p class="msg">선택입니다. <strong>점수와 무관</strong>하고, 답하면 응답 파일에 함께 담깁니다. 답한 뒤에 파일을 저장해 주십시오.</p>
    <fieldset><legend>1. 답을 고르기 어려울 만큼 헷갈렸던 문항이 있었습니까? (여러 개 선택)</legend>
      <div class="sv-nums" id="svNums"></div>
      <label class="field-label" for="svWhy">왜 헷갈렸는지 <span>(선택) — 한두 문장</span></label>
      <input type="text" id="svWhy">
    </fieldset>
    <fieldset><legend>2. 문항의 상황이 내 업무에서 실제로 있을 법했습니까?</legend>
      <div class="sv-scale" id="svReal"></div>
    </fieldset>
    <fieldset><legend>3. 22번 페르소나 6개 중 내 직무에 맞는 것이 있었습니까?</legend>
      <div class="sv-scale" id="svFit"></div>
      <label class="field-label" for="svRole">내 직무 <span>(맞는 것이 없었다면) — 예: 웹 퍼블리싱</span></label>
      <input type="text" id="svRole">
    </fieldset>
  </section>
  <ol class="steps">
    <li><strong>응답 파일 저장</strong>
      <div class="nav"><button class="btn" type="button" id="dl">응답 파일 저장</button>
        <button class="btn ghost" type="button" id="copy">내용 복사</button></div>
      <p class="msg" id="copyMsg" aria-live="polite"></p></li>
    <li><strong>담당자에게 전송</strong> — 안내받은 경로(메일·메신저)로 파일을 첨부하거나 복사한 내용을 붙여넣습니다.</li>
    <li><strong>이 PC에서 지우기</strong> — 전송을 마쳤다면 이 브라우저에 남은 작성 기록을 지웁니다. 공용 PC라면 꼭 눌러 주십시오.
      <div class="nav"><button class="btn danger" type="button" id="wipe">이 PC에서 응답 지우기</button></div>
      <p class="msg" id="wipeMsg" aria-live="polite"></p></li>
  </ol>
  <dl class="sumgrid" id="sumgrid"></dl>
  <div class="nav"><button class="btn ghost" type="button" id="backEdit">돌아가서 수정</button></div>
  <details>
    <summary>응답 내용 보기</summary>
    <textarea class="out" id="out" readonly aria-label="응답 데이터"></textarea>
  </details>
</section>

</main>

<script>
const DATA = __DATA__;
const BUDGET = {sr:120, mc:1200, fr:780};
const SECNAME = {sr:"0부 자기보고", mc:"1부 객관식", fr:"2부 주관식", done:"제출"};
const $ = s => document.querySelector(s);
const el = (t,c,h) => {const n=document.createElement(t); if(c)n.className=c; if(h!==undefined)n.innerHTML=h; return n;};
const mmss = s => Math.floor(s/60)+":"+String(Math.floor(s%60)).padStart(2,"0");

function newState(){
  return {pid:"", rid:"", cur:"intro", startedAt:null, secStart:null, submittedAt:null,
    spent:{intro:0,sr:0,mc:0,fr:0,done:0}, sr:{}, mc:{}, fr:{}, events:[], resumes:0, warned:{},
    survey:{ambiguous:[], why:"", realism:null, persona_fit:null, role:""}};
}
let state = newState();
let restoring = false, confirmStartOver = false;

function makeRid(){
  const A="ABCDEFGHJKLMNPQRSTUVWXYZ23456789", b=new Uint8Array(6);
  (window.crypto||{}).getRandomValues ? crypto.getRandomValues(b) : b.forEach((_,i)=>b[i]=Math.random()*256);
  return Array.from(b,x=>A[x%A.length]).join("");
}

/* ---------- 초안 저장 (브라우저 내부 전용) ---------- */
const KEY="axst-formA-draft";
function save(){try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){}}
function readDraft(){try{const r=localStorage.getItem(KEY); if(!r)return null; const d=JSON.parse(r);
  return d&&d.startedAt ? d : null}catch(e){return null}}
function wipeDraft(){try{localStorage.removeItem(KEY)}catch(e){}}

/* ---------- 렌더 ---------- */
function renderSR(){
  const box=$("#srList");
  DATA.sr.forEach((s,i)=>{
    const it=el("div","item"); it.id="item-"+s.id;
    const fs=el("fieldset");
    fs.appendChild(el("legend","q",'<span class="q-num">SR'+(i+1)+'</span><span class="q-body">'+s.q+'</span>'));
    const box2=el("div","opts");
    let inp=null;
    s.options.forEach((o,j)=>{
      const lab=el("label","opt");
      lab.innerHTML='<input type="radio" name="'+s.id+'" id="'+s.id+'-'+j+'"><span>'+o+'</span>';
      lab.querySelector("input").onchange=()=>{
        state.sr[s.id]=Object.assign({}, state.sr[s.id], {choice:o});
        if(inp){inp.hidden=(o!==s.free);}
        if(!restoring){updateBar(); save();}
      };
      box2.appendChild(lab);
    });
    fs.appendChild(box2); it.appendChild(fs);
    if(s.free){
      inp=el("input"); inp.type="text"; inp.placeholder="무엇인지 한 줄로";
      inp.setAttribute("aria-label", "SR"+(i+1)+" — 무엇인지 한 줄로");
      inp.style.marginTop="9px"; inp.id=s.id+"-free"; inp.hidden=true;
      inp.oninput=()=>{state.sr[s.id]=Object.assign({}, state.sr[s.id], {text:inp.value}); save()};
      it.appendChild(inp);
    }
    box.appendChild(it);
  });
}

function makeOpts(m,kind,onPick){
  const fs=el("fieldset");
  const label = m.worst ? (kind==="worst"?"가장 부적절한 것":"가장 적절한 것") : "가장 적절한 것";
  fs.appendChild(el("legend","sr-only",m.seq+"번 "+label));
  const box=el("div","opts"+(kind==="worst"?" worst":""));
  m.options.forEach((o,j)=>{
    const lab=el("label","opt");
    lab.innerHTML='<input type="radio" name="q'+m.seq+'-'+kind+'" id="q'+m.seq+'-'+kind+'-'+j+'"><span class="n" aria-hidden="true">'+(j+1)+'</span><span>'+o+'</span>';
    lab.querySelector("input").onchange=()=>onPick(j+1);
    box.appendChild(lab);
  });
  fs.appendChild(box);
  return fs;
}

function renderMC(){
  const box=$("#mcList"); let curStem=null, host=box;
  DATA.mc.forEach(m=>{
    if(m.stem && m.stem!==curStem){
      curStem=m.stem;
      const st=DATA.stems[m.stem];
      const blk=el("section","block");
      const card=el("div","stem");
      const top=el("div","stem-top",'<span class="eyebrow">상황 · '+st.label+'</span>');
      const tg=el("button","stem-toggle","지문 접기"); tg.type="button";
      tg.setAttribute("aria-expanded","true");
      tg.onclick=()=>{const c=card.classList.toggle("collapsed");
        tg.textContent=c?"지문 펼치기":"지문 접기"; tg.setAttribute("aria-expanded", String(!c))};
      top.appendChild(tg); card.appendChild(top);
      card.appendChild(el("div","stem-body",st.html));
      blk.appendChild(card); box.appendChild(blk); host=blk;
    } else if(!m.stem){ host=box; curStem=null; }

    const it=el("div","item"); it.id="item-"+m.seq;
    it.appendChild(el("div","q",'<span class="q-num">'+m.seq+'.</span><div class="q-body">'+(m.solo||"")+m.q+'</div>'));
    const rec=(kind,v)=>{
      state.mc[m.seq]=Object.assign({}, state.mc[m.seq]); state.mc[m.seq][kind]=v;
      if(restoring) return;
      state.events.push({seq:m.seq,kind:kind,pick:v,t:Math.round(secElapsed())});
      updateBar(); save(); checkDup();
    };
    const best=makeOpts(m,"best",v=>rec("best",v));
    if(m.worst){
      const bw=el("div","pick"); bw.appendChild(el("div","pick-label",'<span class="dot"></span>가장 적절한 것')); bw.appendChild(best);
      const ww=el("div","pick"); ww.appendChild(el("div","pick-label worst",'<span class="dot"></span>가장 부적절한 것'));
      ww.appendChild(makeOpts(m,"worst",v=>rec("worst",v)));
      it.appendChild(bw); it.appendChild(ww);
      const dup=el("p","dup","가장 적절한 것과 가장 부적절한 것은 서로 달라야 합니다.");
      dup.dataset.seq=m.seq; dup.hidden=true; dup.setAttribute("role","alert"); it.appendChild(dup);
    } else { it.appendChild(best); }
    host.appendChild(it);
  });
}
function checkDup(){
  document.querySelectorAll(".dup").forEach(d=>{
    const a=state.mc[d.dataset.seq]||{};
    d.hidden=!(a.best&&a.worst&&a.best===a.worst);
  });
}

function charCount(s){return (s||"").replace(/\s/g,"").length}

function renderFR(){
  const box=$("#frList");
  DATA.fr.forEach(f=>{
    const w=el("div","fr"); w.id="item-"+f.id;
    w.appendChild(el("div","q",'<span class="q-num">'+f.seq+'.</span><div class="q-body"></div>'));
    w.appendChild(el("div","fr-guide",f.guide));
    if(f.persona){
      const grid=el("div","personas"); grid.setAttribute("role","radiogroup"); grid.setAttribute("aria-label",f.seq+"번 페르소나 선택");
      DATA.personas.forEach(p=>{
        const c=el("label","pcard");
        c.innerHTML='<input type="radio" name="persona" value="'+p.key+'"><span class="k">'+p.key+'</span><span>'+p.label+'</span>';
        c.querySelector("input").onchange=()=>{
          state.fr[f.id]=Object.assign({}, state.fr[f.id], {persona:p.key});
          $("#ptext").innerHTML='<div class="stem" style="position:static"><div class="stem-top"><span class="eyebrow">페르소나 · '+p.label+'</span></div><div class="stem-body" style="max-height:none">'+p.html+'</div></div>';
          if(!restoring){updateBar(); save();}
        };
        grid.appendChild(c);
      });
      w.appendChild(grid);
      w.appendChild(el("div","ptext")).id="ptext";
    }
    w.appendChild(el("div","fr-q",f.q));
    const lab=el("label","field-label","답안"); lab.htmlFor="ta-"+f.id; w.appendChild(lab);
    const ta=el("textarea"); ta.id="ta-"+f.id;
    ta.placeholder="①부터 ④까지 번호를 붙여 답해 주십시오.";
    const cnt=el("p","counter","0자 / 권장 "+f.min+"자 이상"); cnt.setAttribute("aria-live","off");
    ta.oninput=()=>{
      state.fr[f.id]=Object.assign({}, state.fr[f.id], {text:ta.value});
      const n=charCount(ta.value);
      cnt.textContent=n+"자 / 권장 "+f.min+"자 이상";
      cnt.classList.toggle("ok", n>=f.min);
      if(!restoring){updateBar(); save();}
    };
    w.appendChild(ta); w.appendChild(cnt);
    const plab=el("label","field-label",'사용한 프롬프트 <span>(선택) — AI를 썼다면 입력한 지시문을 그대로 붙여넣으십시오. 글자 수에는 포함되지 않습니다.</span>');
    plab.htmlFor="pr-"+f.id; w.appendChild(plab);
    const pr=el("textarea","small"); pr.id="pr-"+f.id;
    pr.oninput=()=>{state.fr[f.id]=Object.assign({}, state.fr[f.id], {ai_prompt:pr.value}); if(!restoring)save();};
    w.appendChild(pr);
    box.appendChild(w);
  });
}

/* ---------- 응시 후 설문 (점수 미반영, 제출 뒤·파일 저장 전) ---------- */
const REALISM=["1 전혀 없다","2","3 보통","4","5 매우 있을 법하다"], FIT=["있었다","비슷한 것만 있었다","없었다"];
function refreshOut(){ if(state.submittedAt) $("#out").value=JSON.stringify(buildResponse(),null,2); }
function svSet(k,v){ state.survey=Object.assign(newState().survey, state.survey); state.survey[k]=v; if(!restoring){save(); refreshOut();} }
function renderSurvey(){
  const nums=$("#svNums");
  DATA.mc.map(m=>m.seq).concat(DATA.fr.map(f=>f.seq)).forEach(q=>{
    const lab=el("label","",'<input type="checkbox" id="sv-q'+q+'" value="'+q+'">'+q);
    lab.querySelector("input").onchange=e=>{
      const cur=new Set((state.survey||{}).ambiguous||[]);
      e.target.checked?cur.add(q):cur.delete(q);
      svSet("ambiguous",[...cur].sort((a,b)=>a-b));
    };
    nums.appendChild(lab);
  });
  const radios=(box,name,opts,key,val)=>opts.forEach((o,i)=>{
    const lab=el("label","",'<input type="radio" name="'+name+'" id="'+name+'-'+i+'">'+o);
    lab.querySelector("input").onchange=()=>svSet(key,val(o,i));
    $(box).appendChild(lab);
  });
  radios("#svReal","svReal",REALISM,"realism",(o,i)=>i+1);
  radios("#svFit","svFit",FIT,"persona_fit",o=>o);
  $("#svWhy").oninput=e=>svSet("why",e.target.value);
  $("#svRole").oninput=e=>svSet("role",e.target.value);
}

/* 저장된 state를 화면 입력에 되살린다. change/input 이벤트를 흘려 표시를 맞추되 기록은 남기지 않는다. */
function applyState(){
  restoring=true;
  const fire=(n,type)=>n.dispatchEvent(new Event(type,{bubbles:true}));
  DATA.sr.forEach(s=>{
    const v=state.sr[s.id]||{};
    const j=s.options.indexOf(v.choice);
    if(j>=0){const r=$("#"+s.id+"-"+j); r.checked=true; fire(r,"change");}
    const t=$("#"+s.id+"-free"); if(t&&v.text) t.value=v.text;
  });
  DATA.mc.forEach(m=>{
    const a=state.mc[m.seq]||{};
    ["best","worst"].forEach(k=>{ if(a[k]){const r=$("#q"+m.seq+"-"+k+"-"+(a[k]-1)); if(r){r.checked=true; fire(r,"change");}} });
  });
  DATA.fr.forEach(f=>{
    const v=state.fr[f.id]||{};
    if(f.persona&&v.persona){const r=document.querySelector('input[name="persona"][value="'+v.persona+'"]'); if(r){r.checked=true; fire(r,"change");}}
    const ta=$("#ta-"+f.id); ta.value=v.text||""; fire(ta,"input");
    const pr=$("#pr-"+f.id); pr.value=v.ai_prompt||"";
  });
  const sv=Object.assign(newState().survey, state.survey);
  document.querySelectorAll('#svNums input').forEach(i=>{i.checked=sv.ambiguous.includes(+i.value); fire(i,"change");});
  if(sv.realism){const r=$("#svReal-"+(sv.realism-1)); r.checked=true; fire(r,"change");}
  const fi=FIT.indexOf(sv.persona_fit); if(fi>=0){const r=$("#svFit-"+fi); r.checked=true; fire(r,"change");}
  $("#svWhy").value=sv.why; $("#svRole").value=sv.role;
  state.survey=sv;
  $("#pid").value=state.pid||"";
  restoring=false; checkDup();
}

/* ---------- 구간·타이머 ---------- */
function secElapsed(){return state.secStart?(Date.now()-state.secStart)/1000:0}
function goto(name, focusId){
  if(state.cur&&state.secStart!==null) state.spent[state.cur]=(state.spent[state.cur]||0)+secElapsed();
  ["intro","sr","mc","fr","done"].forEach(k=>{const n=$("#s-"+k); if(n)n.hidden=(k!==name)});
  $("#review").hidden=true;
  state.cur=name; state.secStart=Date.now();
  $("#bar").hidden=(name==="intro");
  $("#toast").hidden=true;
  updateBar(); save();
  if(focusId){const t=$("#item-"+focusId); if(t){t.scrollIntoView({block:"start"}); t.classList.remove("flash"); void t.offsetWidth; t.classList.add("flash");}}
  else window.scrollTo({top:0,behavior:"instant"});
}
function mcDone(m){const a=state.mc[m.seq]||{}; return a.best&&(!m.worst||a.worst)}
function updateBar(){
  const k=state.cur; if(k==="intro") return;
  $("#barSec").textContent = SECNAME[k];
  let prog="";
  if(k==="mc"){prog=DATA.mc.filter(mcDone).length+" / "+DATA.mc.length+" 완료";}
  if(k==="sr"){prog=DATA.sr.filter(s=>(state.sr[s.id]||{}).choice).length+" / "+DATA.sr.length+" 완료";}
  if(k==="fr"){prog=DATA.fr.filter(f=>(state.fr[f.id]||{}).text).length+" / "+DATA.fr.length+" 작성";}
  $("#barProg").textContent=prog;
  const b=BUDGET[k], e=secElapsed();
  if(b){const over=e>b;
    $("#tSec").textContent=mmss(e)+" / "+mmss(b);
    $("#barTime").classList.toggle("over",over);
    const mt=$("#meter"); mt.style.width=Math.min(100,e/b*100)+"%"; mt.classList.toggle("over",over);
    if(over && !state.warned[k]){ state.warned[k]=true; save();
      toast(SECNAME[k]+" 권장 시간("+Math.round(b/60)+"분)이 지났습니다. 시간이 지나도 계속 응답할 수 있지만, 다음 구간으로 넘어가는 것을 권합니다."); }
  } else {$("#tSec").textContent=""; $("#meter").style.width="0";}
  const tot=["sr","mc","fr"].reduce((a,c)=>a+(state.spent[c]||0),0)+(BUDGET[k]?e:0);
  $("#tTotal").textContent="전체 "+mmss(tot);
}
function toast(msg){$("#toastMsg").textContent=msg; $("#toast").hidden=false;}
setInterval(()=>{if(state.cur!=="intro"&&state.cur!=="done")updateBar()},1000);

/* ---------- 제출 ---------- */
function missing(){
  const out=[];
  DATA.sr.forEach((s,i)=>{ if(!(state.sr[s.id]||{}).choice) out.push({sec:"sr",id:s.id,label:"자기보고 SR"+(i+1)}); });
  DATA.mc.forEach(m=>{ if(!mcDone(m)) out.push({sec:"mc",id:m.seq,label:"객관식 "+m.seq+"번"+(m.worst&&(state.mc[m.seq]||{}).best?" (가장 부적절한 것)":"")}); });
  DATA.fr.forEach(f=>{const v=state.fr[f.id]||{};
    if(f.persona&&!v.persona) out.push({sec:"fr",id:f.id,label:f.seq+"번 페르소나 선택"});
    if(!v.text) out.push({sec:"fr",id:f.id,label:f.seq+"번 주관식 답안"});
    else if(charCount(v.text)<f.min) out.push({sec:"fr",id:f.id,label:f.seq+"번 답안이 권장 분량("+f.min+"자)보다 짧음",soft:true});
  });
  return out;
}
function openReview(){
  const miss=missing(), hard=miss.filter(x=>!x.soft);
  const body=$("#reviewBody"); body.innerHTML="";
  $("#reviewTitle").textContent = hard.length ? "아직 답하지 않은 항목이 "+hard.length+"개 있습니다" : "모든 문항에 답했습니다";
  if(miss.length){
    const ul=el("ul");
    const link=(x,text)=>{const b=el("button","linkbtn",text); b.type="button"; b.onclick=()=>goto(x.sec,x.id); return b;};
    const group=(title,xs,short)=>{ if(!xs.length) return;
      const li=el("li"); li.appendChild(el("span","",title+" ")); const box=el("span","inline");
      xs.forEach(x=>box.appendChild(link(x,short(x)))); li.appendChild(box); ul.appendChild(li); };
    group("자기보고", miss.filter(x=>x.sec==="sr"), x=>x.label.replace("자기보고 ",""));
    group("객관식", miss.filter(x=>x.sec==="mc"), x=>x.label.replace("객관식 ",""));
    miss.filter(x=>x.sec==="fr").forEach(x=>{const li=el("li"); li.appendChild(link(x,x.label)); ul.appendChild(li);});
    body.appendChild(ul);
    body.appendChild(el("p","msg","항목을 누르면 그 문항으로 이동합니다. 빠진 채로 제출할 수도 있지만, 빠진 문항은 점수를 받지 못합니다."));
  } else body.appendChild(el("p","msg","제출하면 응답 파일을 만드는 화면으로 넘어갑니다. 그 뒤에도 돌아와서 고칠 수 있습니다."));
  $("#confirm").textContent = hard.length ? "빠진 채로 제출" : "제출하고 응답 파일 만들기";
  $("#review").hidden=false; $("#review").focus(); $("#review").scrollIntoView({block:"start"});
}
function buildResponse(){
  const spent=Object.assign({},state.spent);
  const round=o=>Object.fromEntries(["sr","mc","fr"].map(k=>[k,Math.round(o[k]||0)]));
  const miss=DATA.mc.filter(m=>!mcDone(m)).map(m=>m.seq);
  const r=round(spent);
  return {form:"A", schema:"axst-response-1", respondent:state.pid||"(미기재)", rid:state.rid,
    startedAt:new Date(state.startedAt).toISOString(), submittedAt:new Date(state.submittedAt).toISOString(),
    durations_sec:Object.assign(r,{total:r.sr+r.mc+r.fr}), resumes:state.resumes,
    selfreport:state.sr, mc:state.mc, unanswered_mc:miss,
    free_response:Object.fromEntries(DATA.fr.map(f=>{const v=state.fr[f.id]||{};
      return [f.id,{persona:v.persona||null,text:v.text||"",chars:charCount(v.text),ai_prompt:v.ai_prompt||""}]})),
    survey:Object.assign(newState().survey, state.survey),
    events:state.events};
}
function finish(){
  if(!state.rid) state.rid=makeRid();
  if(!state.startedAt) state.startedAt=Date.now();
  if(state.secStart!==null) state.spent[state.cur]=(state.spent[state.cur]||0)+secElapsed();
  state.secStart=null; state.submittedAt=state.submittedAt||Date.now();
  goto("done");
  const r=buildResponse();
  $("#out").value=JSON.stringify(r,null,2);
  $("#ridShow").textContent=state.rid;
  const g=$("#sumgrid"); g.innerHTML="";
  [["전체 소요",mmss(r.durations_sec.total)],["0부",mmss(r.durations_sec.sr)],
   ["1부",mmss(r.durations_sec.mc)],["2부",mmss(r.durations_sec.fr)],
   ["객관식 응답",(DATA.mc.length-r.unanswered_mc.length)+" / "+DATA.mc.length]]
    .forEach(([k,v])=>{const d=el("div","fact"); d.innerHTML="<dt>"+k+"</dt><dd>"+v+"</dd>"; g.appendChild(d)});
  const w=$("#warnBox"); w.innerHTML="";
  const hard=missing().filter(x=>!x.soft);
  if(hard.length){
    const cnt=s=>hard.filter(x=>x.sec===s).length, parts=[];
    if(cnt("sr")) parts.push("자기보고 "+cnt("sr")+"문항");
    if(cnt("mc")) parts.push("객관식 "+cnt("mc")+"문항");
    hard.filter(x=>x.sec==="fr").forEach(x=>parts.push(x.label));
    const n=el("div","note warn","빠진 항목이 있습니다 — "+parts.join(" · ")+". 「돌아가서 수정」으로 채운 뒤 파일을 다시 저장할 수 있습니다.");
    n.style.marginTop="14px"; w.appendChild(n);}
  $("#copyMsg").textContent=""; $("#wipeMsg").textContent="";
}
function fileName(){
  const d=new Date(state.submittedAt), p=n=>String(n).padStart(2,"0");
  const stamp=d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+"-"+p(d.getHours())+p(d.getMinutes());
  const who=(state.pid||"").replace(/[^0-9A-Za-z가-힣_-]/g,"").slice(0,24);
  return "axst-"+(who?who+"-":"")+state.rid+"-"+stamp+".json";
}

/* ---------- 부팅 ---------- */
renderSR(); renderMC(); renderFR(); renderSurvey();
/* :has() 미지원 브라우저용 선택 표시 */
document.addEventListener("change",e=>{const i=e.target;
  if(i.type==="checkbox"){const l=i.closest("label"); if(l)l.classList.toggle("on",i.checked); return;}
  if(i.type!=="radio")return;
  document.querySelectorAll('input[name="'+i.name+'"]').forEach(x=>{const l=x.closest("label"); if(l)l.classList.toggle("on",x.checked)});});
document.querySelectorAll("[data-next]").forEach(b=>b.onclick=()=>goto(b.dataset.next));
$("#toastX").onclick=()=>{$("#toast").hidden=true};
$("#go").onclick=()=>{
  if(readDraft() && !confirmStartOver) {$("#resumeBox").hidden=false; $("#resumeBox").scrollIntoView({block:"center"}); return;}
  const pid=$("#pid").value.trim();
  wipeDraft(); state=newState(); applyState();
  state.pid=pid; $("#pid").value=pid; state.rid=makeRid(); state.startedAt=Date.now(); goto("sr");
};
$("#submit").onclick=openReview;
$("#reviewClose").onclick=()=>{$("#review").hidden=true};
$("#confirm").onclick=finish;
$("#backEdit").onclick=()=>{state.submittedAt=null; goto("fr")};
$("#pid").oninput=()=>{ if(state.startedAt){state.pid=$("#pid").value.trim(); save();} };

(function boot(){
  const d=readDraft(); if(!d) return;
  const answered=Object.keys(d.mc||{}).length, when=new Date(d.startedAt);
  $("#resumeInfo").textContent="("+when.toLocaleString("ko-KR",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})+" 시작 · 객관식 "+answered+"문항 응답)";
  $("#resumeBox").hidden=false;
  $("#resumeYes").onclick=()=>{
    state=Object.assign(newState(), d);
    state.spent=Object.assign(newState().spent, d.spent);
    if(!state.rid) state.rid=makeRid();
    state.resumes=(state.resumes||0)+1;
    applyState(); $("#resumeBox").hidden=true;
    const to = state.submittedAt ? "done" : (["sr","mc","fr"].includes(state.cur)?state.cur:"sr");
    state.cur=null; state.secStart=null;
    if(to==="done") finish(); else goto(to);
  };
  $("#resumeNo").onclick=()=>{ wipeDraft(); confirmStartOver=true; $("#resumeBox").hidden=true; };
})();

$("#copy").onclick=async()=>{
  const t=$("#out").value;
  try{await navigator.clipboard.writeText(t); $("#copyMsg").textContent="복사했습니다. 담당자에게 붙여넣어 보내 주십시오.";}
  catch(e){const det=$("#out").closest("details"); det.open=true; $("#out").focus(); $("#out").select();
    $("#copyMsg").textContent="자동 복사가 막혔습니다. 펼쳐진 상자가 전체 선택됐으니 Ctrl/Cmd+C 로 복사하십시오.";}
};
/* 파일 저장: 웹에서는 downloads 권한, 로컬 파일로 열었을 때는 링크 방식 */
let DL=null;
(async()=>{
  try{ DL = window.claude && window.claude.use ? await window.claude.use("downloads") : null; }
  catch(e){ DL=null; }
})();
$("#dl").onclick=async()=>{
  const name=fileName(), txt=$("#out").value;
  if(DL){
    try{ await DL.save({filename:name, data:txt});
         $("#copyMsg").textContent="저장했습니다: "+name; }
    catch(e){ const c=e&&e.code;
      $("#copyMsg").textContent = c==="declined" ? "저장을 취소했습니다."
        : c==="rate_limited" ? "잠시 후 다시 눌러 주십시오."
        : "저장할 수 없습니다. 「내용 복사」를 쓰십시오."; }
    return;
  }
  try{
    const b=new Blob([txt],{type:"application/json"});
    const a=document.createElement("a"); a.href=URL.createObjectURL(b);
    a.download=name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(a.href), 4000);
    $("#copyMsg").textContent="다운로드 폴더에 저장했습니다: "+name+" — 저장되지 않았다면 「내용 복사」를 쓰십시오.";
  }catch(e){ $("#copyMsg").textContent="저장할 수 없습니다. 「내용 복사」를 쓰십시오."; }
};
$("#wipe").onclick=()=>{
  wipeDraft();
  $("#wipeMsg").textContent="이 브라우저에서 지웠습니다. 이 창을 닫으면 응답이 남지 않습니다. (창을 닫기 전이라면 파일 저장은 아직 할 수 있습니다)";
  $("#backEdit").hidden=true;
  save = function(){};
};
</script>
</body>
</html>
"""

def render(data):
    worst = [str(m['seq']) for m in data['mc'] if m['worst']]
    return (TEMPLATE
            .replace("__WORST_SEQS__", "·".join(worst))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"))))

def build():
    data = collect()
    problems = check_data(data)
    html = render(data)
    problems += check_leaks(html)
    return data, html, problems

def main():
    data, html, problems = build()
    if problems:
        sys.exit("FAIL: " + "\n      ".join(problems))
    OUT.write_text(html, encoding="utf-8")
    print(f"생성: {OUT.relative_to(ROOT)}  ({len(html):,}자)")
    print(f"  객관식 {len(data['mc'])} / 공통지문 {len(data['stems'])} / 자기보고 {len(data['sr'])} / "
          f"주관식 {len(data['fr'])} / 페르소나 {len(data['personas'])}")

if __name__ == "__main__":
    main()
