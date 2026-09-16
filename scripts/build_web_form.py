#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""온라인 응시본 생성기. items/ + forms/MANIFEST.yml -> forms/form-A.web.html

생성물이므로 손으로 고치지 않는다. 정답·해설·오답 진단은 읽지도 쓰지도 않는다.
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

# 자기보고
sr_src = read("selfreport/checkitems.md")
sr = []
for m in re.finditer(r'^## (SR-\d+)\n\n\*\*(.+?)\*\*(.*?)(?=^##|\Z)', sr_src, re.S | re.M):
    sid, q, rest = m.group(1), m.group(2), m.group(3)
    opts = re.findall(r'^- \[ \] (.+)$', rest, re.M)
    free = any('→' in o for o in opts)
    opts = [re.sub(r'\s*→.*$', '', o).strip() for o in opts]
    sr.append({"id": sid, "q": inline(q), "options": opts, "free": free})
assert len(sr) == 3, sr

# 주관식
fr = []
for n, (fid, seq) in enumerate([("FR-01", 21), ("FR-02", 22)]):
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

DATA = {"form": "A", "stems": stems, "mc": mc, "sr": sr, "fr": fr, "personas": personas}

# ---------- 정답 누출 방지 ----------
blob = json.dumps(DATA, ensure_ascii=False)
for kw in ("정답", "해설", "distractor", "answer", "오답"):
    if kw in blob:
        sys.exit(f"FAIL: 생성 데이터에 '{kw}' 누출")

# ---------- 템플릿 ----------
TEMPLATE = r"""<title>AX Literacy 진단 폼 A</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --ground:#f7f8fa; --surface:#ffffff; --surface-2:#f0f2f6;
  --ink:#1a1d23; --ink-soft:#5a626e; --ink-faint:#8b939f;
  --line:#e2e5eb; --line-strong:#cbd1da;
  --accent:#2f5d8c; --accent-soft:#eaf1f8; --accent-ink:#22456a;
  --warn:#a8621b; --warn-soft:#fbf1e6; --ok:#2e6b4f;
  --barh:54px;
  --sans:"IBM Plex Sans KR",system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#14171c; --surface:#1c2027; --surface-2:#232830;
  --ink:#e8eaed; --ink-soft:#a3abb7; --ink-faint:#79818d;
  --line:#2c323b; --line-strong:#3b434e;
  --accent:#7faad4; --accent-soft:#1f2a36; --accent-ink:#a8c8e6;
  --warn:#d9954e; --warn-soft:#2a2118; --ok:#6bbd95;
}}
:root[data-theme="dark"]{
  --ground:#14171c; --surface:#1c2027; --surface-2:#232830;
  --ink:#e8eaed; --ink-soft:#a3abb7; --ink-faint:#79818d;
  --line:#2c323b; --line-strong:#3b434e;
  --accent:#7faad4; --accent-soft:#1f2a36; --accent-ink:#a8c8e6;
  --warn:#d9954e; --warn-soft:#2a2118; --ok:#6bbd95;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
     font-size:15px;line-height:1.7;-webkit-text-size-adjust:100%}
.wrap{max-width:720px;margin:0 auto;padding-inline:16px;padding-block:0 96px}
h1,h2,h3{text-wrap:balance;margin:0}
code{font-family:var(--mono);font-size:.9em;background:var(--surface-2);
     padding:1px 5px;border-radius:3px}
.doc{font-style:normal;font-weight:500}
blockquote{margin:12px 0;padding:12px 16px;background:var(--surface-2);
  border-left:3px solid var(--line-strong);border-radius:0 6px 6px 0;color:var(--ink)}
button{font:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}

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

/* ---- 공통 ---- */
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--ink-faint);font-weight:600;font-family:var(--mono)}
.lede{color:var(--ink-soft)}
.rule{height:1px;background:var(--line);border:0;margin:28px 0}
.btn{appearance:none;border:1px solid var(--accent);background:var(--accent);color:#fff;
  padding:11px 22px;border-radius:7px;font-weight:600;font-size:15px}
.btn:hover{filter:brightness(1.08)}
.btn.ghost{background:transparent;color:var(--accent);border-color:var(--line-strong)}
.btn.wide{width:100%}
.nav{display:flex;gap:10px;flex-wrap:wrap;margin-top:32px}
.note{background:var(--accent-soft);border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;font-size:13.5px;color:var(--ink)}
.note.warn{background:var(--warn-soft)}

/* ---- 인트로 ---- */
.hero{padding-block:44px 8px}
.hero h1{font-size:30px;font-weight:600;letter-spacing:-.02em;line-height:1.3}
.hero .sub{color:var(--ink-soft);margin-top:10px;font-size:16px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;
  background:var(--surface);margin-top:26px}
.fact{padding:14px 16px;border-right:1px solid var(--line)}
.fact:last-child{border-right:0}
.fact dt{font-size:11px;color:var(--ink-faint);letter-spacing:.08em;font-weight:600}
.fact dd{margin:3px 0 0;font-family:var(--mono);font-size:17px;font-variant-numeric:tabular-nums}
.rules{margin-top:22px;border-top:1px solid var(--line)}
.rules div{padding:13px 0;border-bottom:1px solid var(--line);display:grid;
  grid-template-columns:130px 1fr;gap:16px;align-items:start;font-size:14px}
.rules dt{font-weight:600}
@media(max-width:520px){.rules div{grid-template-columns:1fr;gap:4px}.fact{border-right:0;border-bottom:1px solid var(--line)}}
.idfield{margin-top:24px}
.idfield label{display:block;font-weight:600;font-size:14px;margin-bottom:6px}
input[type=text],textarea{width:100%;font-family:inherit;font-size:15px;color:var(--ink);
  background:var(--surface);border:1px solid var(--line-strong);border-radius:7px;
  padding:10px 12px;line-height:1.7}
textarea{resize:vertical;min-height:260px}
input[type=text]:focus,textarea:focus{border-color:var(--accent);outline:none;
  box-shadow:0 0 0 3px var(--accent-soft)}

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
  font-size:12px;padding:2px 6px;border-radius:4px}
.stem-body{max-height:46vh;overflow:auto;font-size:14.5px}
.stem-body p{margin:0 0 8px}
.stem.collapsed .stem-body{display:none}
.item{padding:22px 0;border-bottom:1px solid var(--line)}
.item:last-child{border-bottom:0}
.q{display:flex;gap:12px;align-items:baseline}
.q-num{font-family:var(--mono);font-weight:500;color:var(--accent-ink);
  font-size:15px;flex:none;min-width:26px}
.q-body p{margin:0 0 8px}.q-body p:last-child{margin-bottom:0}
.opts{margin:14px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:7px}
.opt{display:flex;gap:11px;align-items:flex-start;padding:10px 13px;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid transparent;border-radius:0 7px 7px 0;
  cursor:pointer;font-size:14.5px;transition:background .12s,border-color .12s}
.opt:hover{background:var(--surface-2)}
.opt input{margin:5px 0 0;accent-color:var(--accent);flex:none}
.opt .n{font-family:var(--mono);color:var(--ink-faint);flex:none}
.opt.on{background:var(--accent-soft);border-color:var(--line-strong);border-left-color:var(--accent)}
.opt.on-worst{background:var(--warn-soft);border-left-color:var(--warn)}
.pick{margin-top:14px}
.pick-label{font-size:12px;font-weight:600;letter-spacing:.04em;color:var(--ink-soft);
  margin-bottom:6px;display:flex;align-items:center;gap:7px}
.pick-label .dot{width:7px;height:7px;border-radius:50%;background:var(--accent)}
.pick-label.worst .dot{background:var(--warn)}
.dup{color:var(--warn);font-size:12.5px;margin-top:7px;display:none}
.dup.show{display:block}

/* ---- 주관식 ---- */
.fr{margin-top:26px;padding-bottom:6px}
.fr-guide{background:var(--surface);border:1px solid var(--line);border-radius:9px;
  padding:15px 17px;font-size:14.5px}
.fr-guide p{margin:0 0 9px}.fr-guide p:last-child{margin-bottom:0}
.fr-q{margin-top:18px;font-size:14.5px}
.fr-q p{margin:0 0 10px}
.personas{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:8px;margin:16px 0}
.pcard{display:flex;gap:9px;align-items:center;padding:11px 13px;background:var(--surface);
  border:1px solid var(--line);border-left:3px solid transparent;border-radius:0 7px 7px 0;
  cursor:pointer;font-size:14px}
.pcard.on{background:var(--accent-soft);border-left-color:var(--accent)}
.pcard .k{font-family:var(--mono);font-size:11.5px;color:var(--ink-faint)}
.ptext{margin:6px 0 18px}
.counter{font-family:var(--mono);font-size:12px;color:var(--ink-faint);
  text-align:right;margin-top:6px;font-variant-numeric:tabular-nums}
.counter.ok{color:var(--ok)}

/* ---- 완료 ---- */
.done-head{padding-block:40px 4px}
.sumgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:0;
  border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface);margin-top:20px}
.out{width:100%;min-height:180px;font-family:var(--mono);font-size:11.5px;line-height:1.55;
  white-space:pre;overflow:auto}
.steps{counter-reset:s;margin:18px 0 0;padding:0;list-style:none}
.steps li{counter-increment:s;padding:11px 0 11px 34px;border-bottom:1px solid var(--line);
  position:relative;font-size:14px}
.steps li::before{content:counter(s);position:absolute;left:0;top:11px;width:22px;height:22px;
  border-radius:50%;background:var(--accent-soft);color:var(--accent-ink);font-family:var(--mono);
  font-size:12px;display:grid;place-items:center;font-weight:500}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>

<header class="bar" id="bar" hidden>
  <div class="wrap">
    <span class="bar-sec" id="barSec">0부</span>
    <span class="bar-prog" id="barProg"></span>
    <span class="bar-time" id="barTime"><b id="tSec">0:00</b><span id="tTotal">전체 0:00</span></span>
  </div>
  <div class="meter" id="meter"></div>
</header>

<main class="wrap">

<!-- 인트로 -->
<section id="s-intro">
  <div class="hero">
    <p class="eyebrow">폼 A · 진단 회차</p>
    <h1>AX Literacy 진단</h1>
    <p class="sub">툴 지식을 묻지 않습니다. 실제 업무 상황에서 <strong>어떻게 판단하는지</strong>를 봅니다.</p>
  </div>

  <dl class="facts">
    <div class="fact"><dt>소요 시간</dt><dd>35분</dd></div>
    <div class="fact"><dt>객관식</dt><dd>20문항</dd></div>
    <div class="fact"><dt>주관식</dt><dd>2문항</dd></div>
    <div class="fact"><dt>총점</dt><dd>100점</dd></div>
  </dl>

  <div class="note" style="margin-top:20px">
    이 진단의 결과는 <strong>교육 설계에만 사용되며, 인사 평가·승진·배치 자료로 사용되지 않습니다.</strong>
    응답은 이 브라우저 밖으로 전송되지 않습니다. 제출 화면에서 응답을 복사해 담당자에게 전달하십시오.
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
    <li><strong>AI를 사용해 작성해도 됩니다.</strong> 사용한 경우 프롬프트를 답안 끝에 첨부하십시오.</li>
  </ul>

  <div class="idfield">
    <label for="pid">식별 코드 <span style="font-weight:400;color:var(--ink-soft)">— 무기명입니다. 재진단 대조를 위해 <strong>본인만 아는 규칙</strong>으로 만드십시오 (예: 좋아하는 색 + 태어난 달)</span></label>
    <input type="text" id="pid" placeholder="예: navy07" autocomplete="off">
  </div>

  <div class="nav"><button class="btn" id="go">진단 시작</button></div>
</section>

<!-- 0부 -->
<section id="s-sr" hidden>
  <div class="sec-head">
    <p class="eyebrow">0부 · 권장 2분</p>
    <h2>자기보고 3문항</h2>
    <p>이 3문항은 <strong>점수에 반영되지 않습니다.</strong> 결과 해석의 정확도를 높이는 데만 씁니다. 사실대로 답해 주십시오.</p>
  </div>
  <div id="srList"></div>
  <div class="nav"><button class="btn" data-next="mc">1부로</button></div>
</section>

<!-- 1부 -->
<section id="s-mc" hidden>
  <div class="sec-head">
    <p class="eyebrow">1부 · 권장 20분</p>
    <h2>객관식 20문항</h2>
    <p>문항당 3점. 4·13·17·18번은 <strong>가장 적절한 것</strong>과 <strong>가장 부적절한 것</strong>을 각각 고릅니다.</p>
  </div>
  <div id="mcList"></div>
  <div class="nav">
    <button class="btn ghost" data-next="sr">0부로</button>
    <button class="btn" data-next="fr">2부로</button>
  </div>
</section>

<!-- 2부 -->
<section id="s-fr" hidden>
  <div class="sec-head">
    <p class="eyebrow">2부 · 권장 13분</p>
    <h2>주관식 2문항</h2>
    <p>문항당 20점. <strong>네 개의 번호에 모두 답해 주십시오.</strong> 분량보다 네 항목의 균형이 중요합니다.</p>
  </div>
  <div id="frList"></div>
  <div class="nav">
    <button class="btn ghost" data-next="mc">1부로</button>
    <button class="btn" id="submit">제출</button>
  </div>
</section>

<!-- 완료 -->
<section id="s-done" hidden>
  <div class="done-head">
    <p class="eyebrow">제출 완료</p>
    <h1 style="font-size:26px;font-weight:600">응답을 담당자에게 전달해 주십시오</h1>
    <p class="lede" style="margin-top:8px">응답은 <strong>이 브라우저 밖으로 전송되지 않았습니다.</strong> 아래 내용을 복사해 전달해야 채점됩니다.</p>
  </div>
  <dl class="sumgrid" id="sumgrid"></dl>
  <div id="warnBox"></div>
  <div class="nav" style="margin-top:22px">
    <button class="btn" id="copy">응답 복사</button>
    <button class="btn ghost" id="dl">파일로 저장</button>
    <button class="btn ghost" data-next="fr">돌아가서 수정</button>
  </div>
  <p class="lede" style="font-size:13px;margin-top:10px" id="copyMsg">응답 전달 방법을 확인하는 중…</p>
  <hr class="rule">
  <p class="eyebrow">응답 전문</p>
  <textarea class="out" id="out" readonly aria-label="응답 데이터"></textarea>
  <ol class="steps">
    <li>「응답 복사」를 누릅니다.</li>
    <li>담당자가 안내한 경로(메일·메신저)에 붙여넣어 보냅니다.</li>
    <li>담당자는 이것을 <code>pilot/responses/</code>에 저장합니다. 레포에 커밋하지 않습니다.</li>
  </ol>
</section>

</main>

<script>
const DATA = __DATA__;
const BUDGET = {sr:120, mc:1200, fr:780};
const SECNAME = {sr:"0부 자기보고", mc:"1부 객관식", fr:"2부 주관식"};
const $ = s => document.querySelector(s);
const el = (t,c,h) => {const n=document.createElement(t); if(c)n.className=c; if(h!==undefined)n.innerHTML=h; return n;};
const mmss = s => Math.floor(s/60)+":"+String(Math.floor(s%60)).padStart(2,"0");

const state = {pid:"", cur:"intro", startedAt:null, secStart:null,
  spent:{intro:0,sr:0,mc:0,fr:0}, sr:{}, mc:{}, fr:{}, events:[]};

/* ---------- 초안 저장 (브라우저 내부 전용) ---------- */
const KEY="axst-formA-draft";
function save(){try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){}}
function load(){try{const r=localStorage.getItem(KEY); if(!r)return; const d=JSON.parse(r);
  if(d&&d.startedAt){Object.assign(state,d); return true}}catch(e){} return false}

/* ---------- 렌더 ---------- */
function renderSR(){
  const box=$("#srList");
  DATA.sr.forEach((s,i)=>{
    const it=el("div","item");
    it.appendChild(el("div","q",'<span class="q-num">SR'+(i+1)+'</span><div class="q-body"><p>'+s.q+'</p></div>'));
    const ul=el("ul","opts");
    s.options.forEach((o,j)=>{
      const li=el("li","opt");
      li.innerHTML='<input type="radio" name="'+s.id+'" id="'+s.id+'-'+j+'" value="'+o+'"><span>'+o+'</span>';
      li.onclick=e=>{if(e.target.tagName!=="INPUT")li.querySelector("input").click()};
      li.querySelector("input").onchange=()=>{
        state.sr[s.id]=Object.assign({}, state.sr[s.id], {choice:o});
        ul.querySelectorAll(".opt").forEach(x=>x.classList.remove("on"));
        li.classList.add("on"); save();
      };
      ul.appendChild(li);
    });
    it.appendChild(ul);
    if(s.free){
      const inp=el("input"); inp.type="text"; inp.placeholder="있다면 무엇인지 한 줄로";
      inp.style.marginTop="9px"; inp.id=s.id+"-free";
      inp.oninput=()=>{state.sr[s.id]=Object.assign({}, state.sr[s.id], {text:inp.value}); save()};
      it.appendChild(inp);
    }
    box.appendChild(it);
  });
}

function pickGroup(seq,kind,opts,ul){
  const wrap=el("div","pick");
  wrap.appendChild(el("div","pick-label"+(kind==="worst"?" worst":""),
    '<span class="dot"></span>'+(kind==="worst"?"가장 부적절한 것":"가장 적절한 것")));
  wrap.appendChild(ul);
  return wrap;
}

function makeOpts(seq,kind,opts,onPick){
  const ul=el("ul","opts");
  opts.forEach((o,j)=>{
    const li=el("li","opt"); const id="q"+seq+"-"+kind+"-"+j;
    li.innerHTML='<input type="radio" name="q'+seq+'-'+kind+'" id="'+id+'"><span class="n">'+(j+1)+'</span><span>'+o+'</span>';
    li.onclick=e=>{if(e.target.tagName!=="INPUT")li.querySelector("input").click()};
    li.querySelector("input").onchange=()=>{
      ul.querySelectorAll(".opt").forEach(x=>x.classList.remove("on","on-worst"));
      li.classList.add(kind==="worst"?"on-worst":"on");
      onPick(j+1);
    };
    ul.appendChild(li);
  });
  return ul;
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
      tg.onclick=()=>{card.classList.toggle("collapsed");
        tg.textContent=card.classList.contains("collapsed")?"지문 펼치기":"지문 접기"};
      top.appendChild(tg); card.appendChild(top);
      card.appendChild(el("div","stem-body",st.html));
      blk.appendChild(card); box.appendChild(blk); host=blk;
    } else if(!m.stem){ host=box; curStem=null; }

    const it=el("div","item"); it.id="item-"+m.seq;
    it.appendChild(el("div","q",'<span class="q-num">'+m.seq+'.</span><div class="q-body">'+(m.solo||"")+m.q+'</div>'));
    const rec=(kind,v)=>{
      state.mc[m.seq]=Object.assign({}, state.mc[m.seq]); state.mc[m.seq][kind]=v;
      state.events.push({seq:m.seq,kind:kind,pick:v,t:Math.round(secElapsed())});
      updateBar(); save(); checkDup();
    };
    const best=makeOpts(m.seq,"best",m.options,v=>rec("best",v));
    if(m.worst){
      const worst=makeOpts(m.seq,"worst",m.options,v=>rec("worst",v));
      it.appendChild(pickGroup(m.seq,"best",m.options,best));
      it.appendChild(pickGroup(m.seq,"worst",m.options,worst));
      const dup=el("p","dup","가장 적절한 것과 가장 부적절한 것은 서로 달라야 합니다.");
      dup.dataset.seq=m.seq; it.appendChild(dup);
    } else { it.appendChild(best); }
    host.appendChild(it);
  });
}
function checkDup(){
  document.querySelectorAll(".dup").forEach(d=>{
    const a=state.mc[d.dataset.seq]||{};
    d.classList.toggle("show", a.best&&a.worst&&a.best===a.worst);
  });
}

function renderFR(){
  const box=$("#frList");
  DATA.fr.forEach(f=>{
    const w=el("div","fr");
    w.appendChild(el("div","q",'<span class="q-num">'+f.seq+'.</span><div class="q-body"></div>'));
    w.appendChild(el("div","fr-guide",f.guide));
    if(f.persona){
      const grid=el("div","personas");
      DATA.personas.forEach(p=>{
        const c=el("label","pcard");
        c.innerHTML='<input type="radio" name="persona" value="'+p.key+'"><span class="k">'+p.key+'</span><span>'+p.label+'</span>';
        c.querySelector("input").onchange=()=>{
          grid.querySelectorAll(".pcard").forEach(x=>x.classList.remove("on"));
          c.classList.add("on");
          state.fr[f.id]=Object.assign({}, state.fr[f.id], {persona:p.key});
          $("#ptext").innerHTML='<div class="stem" style="position:static"><div class="stem-top"><span class="eyebrow">페르소나 · '+p.label+'</span></div><div class="stem-body" style="max-height:none">'+p.html+'</div></div>';
          save();
        };
        grid.appendChild(c);
      });
      w.appendChild(grid);
      w.appendChild(el("div","ptext")).id="ptext";
    }
    w.appendChild(el("div","fr-q",f.q));
    const ta=el("textarea"); ta.id="ta-"+f.id;
    ta.placeholder="①부터 ④까지 번호를 붙여 답해 주십시오.";
    const cnt=el("p","counter","0자 / 권장 "+f.min+"자 이상");
    ta.oninput=()=>{
      state.fr[f.id]=Object.assign({}, state.fr[f.id], {text:ta.value});
      const n=ta.value.replace(/\s/g,"").length;
      cnt.textContent=n+"자 / 권장 "+f.min+"자 이상";
      cnt.classList.toggle("ok", n>=f.min); save();
    };
    w.appendChild(ta); w.appendChild(cnt);
    box.appendChild(w);
  });
}

/* ---------- 구간·타이머 ---------- */
function secElapsed(){return state.secStart?(Date.now()-state.secStart)/1000:0}
function goto(name){
  if(state.cur&&state.secStart!==null) state.spent[state.cur]+=secElapsed();
  ["intro","sr","mc","fr","done"].forEach(k=>{const n=$("#s-"+k); if(n)n.hidden=(k!==name)});
  state.cur=name; state.secStart=Date.now();
  $("#bar").hidden=(name==="intro");
  updateBar(); save(); window.scrollTo({top:0,behavior:"instant"});
}
function updateBar(){
  const k=state.cur; if(k==="intro") return;
  $("#barSec").textContent = k==="done" ? "제출 완료" : SECNAME[k];
  let prog="";
  if(k==="mc"){const n=DATA.mc.filter(m=>{const a=state.mc[m.seq]||{};return a.best&&(!m.worst||a.worst)}).length;
    prog=n+" / "+DATA.mc.length+" 완료";}
  if(k==="sr"){prog=Object.keys(state.sr).length+" / 3 완료";}
  if(k==="fr"){const n=DATA.fr.filter(f=>(state.fr[f.id]||{}).text).length; prog=n+" / 2 작성";}
  $("#barProg").textContent=prog;
  const b=BUDGET[k], e=secElapsed();
  if(b){const over=e>b;
    $("#tSec").textContent=mmss(e)+" / "+mmss(b);
    $("#barTime").classList.toggle("over",over);
    const mt=$("#meter"); mt.style.width=Math.min(100,e/b*100)+"%"; mt.classList.toggle("over",over);
  } else {$("#tSec").textContent=mmss(e); $("#meter").style.width="100%";}
  const tot=Object.values(state.spent).reduce((a,c)=>a+c,0)+e;
  $("#tTotal").textContent="전체 "+mmss(tot);
}
setInterval(()=>{if(state.cur!=="intro")updateBar()},1000);

/* ---------- 제출 ---------- */
function build(){
  const spent=Object.assign({},state.spent); spent[state.cur]=(spent[state.cur]||0)+secElapsed();
  const round=o=>Object.fromEntries(Object.entries(o).map(([k,v])=>[k,Math.round(v)]));
  const miss=DATA.mc.filter(m=>{const a=state.mc[m.seq]||{};return !a.best||(m.worst&&!a.worst)}).map(m=>m.seq);
  return {form:"A", schema:"axst-response-1", respondent:state.pid||"(미기재)",
    startedAt:new Date(state.startedAt).toISOString(), submittedAt:new Date().toISOString(),
    durations_sec:Object.assign(round(spent),{total:Math.round(Object.values(spent).reduce((a,c)=>a+c,0))}),
    selfreport:state.sr, mc:state.mc, unanswered_mc:miss,
    free_response:Object.fromEntries(DATA.fr.map(f=>{const v=state.fr[f.id]||{};
      return [f.id,{persona:v.persona||null,text:v.text||"",chars:(v.text||"").replace(/\s/g,"").length}]})),
    events:state.events};
}
function finish(){
  goto("done");
  const r=build();
  $("#out").value=JSON.stringify(r,null,2);
  const g=$("#sumgrid"); g.innerHTML="";
  const rows=[["전체 소요",mmss(r.durations_sec.total)],["0부",mmss(r.durations_sec.sr||0)],
    ["1부",mmss(r.durations_sec.mc||0)],["2부",mmss(r.durations_sec.fr||0)],
    ["객관식",(DATA.mc.length-r.unanswered_mc.length)+" / "+DATA.mc.length]];
  rows.forEach(([k,v])=>{const d=el("div","fact"); d.innerHTML="<dt>"+k+"</dt><dd>"+v+"</dd>"; g.appendChild(d)});
  const w=$("#warnBox"); w.innerHTML="";
  const miss=[];
  if(r.unanswered_mc.length) miss.push("객관식 미응답 "+r.unanswered_mc.join(", ")+"번");
  DATA.fr.forEach(f=>{const v=r.free_response[f.id];
    if(!v.text) miss.push(f.seq+"번 주관식 미작성");
    else if(f.persona&&!v.persona) miss.push("22번 페르소나 미선택");});
  if(miss.length) w.appendChild(el("div","note warn","제출은 됐지만 빠진 항목이 있습니다 — "+miss.join(" · ")+". 「돌아가서 수정」으로 채운 뒤 다시 제출할 수 있습니다."))
    , w.firstChild.style.marginTop="18px";
}

/* ---------- 부팅 ---------- */
renderSR(); renderMC(); renderFR();
$("#go").onclick=()=>{state.pid=$("#pid").value.trim(); state.startedAt=Date.now(); goto("sr")};
document.querySelectorAll("[data-next]").forEach(b=>b.onclick=()=>goto(b.dataset.next));
$("#submit").onclick=finish;
$("#copy").onclick=async()=>{
  const t=$("#out").value;
  try{await navigator.clipboard.writeText(t); $("#copyMsg").textContent="복사했습니다. 담당자에게 붙여넣어 보내 주십시오.";}
  catch(e){$("#out").focus(); $("#out").select();
    $("#copyMsg").textContent="자동 복사가 막혔습니다. 아래 상자가 전체 선택됐으니 Ctrl/Cmd+C 로 복사하십시오.";}
};
/* 파일 저장: 웹에서는 downloads 권한, 로컬 파일로 열었을 때는 링크 방식 */
let DL=null, LOCAL=!window.claude;
(async()=>{
  try{ DL = window.claude && window.claude.use ? await window.claude.use("downloads") : null; }
  catch(e){ DL=null; }
  if(!DL && !LOCAL) $("#dl").hidden=true;
  $("#copyMsg").textContent = DL
    ? "「파일로 저장」을 누르면 확인 후 JSON 파일로 저장됩니다. 응답은 이 브라우저 밖으로 전송되지 않습니다."
    : LOCAL ? "「파일로 저장」은 이 파일을 브라우저로 직접 열었을 때 동작합니다."
            : "이 환경에서는 파일 저장을 쓸 수 없습니다. 「응답 복사」를 쓰십시오.";
})();
$("#dl").onclick=async()=>{
  const name="axst-"+(state.pid||"anon")+".json", txt=$("#out").value;
  if(DL){
    try{ await DL.save({filename:name, data:txt});
         $("#copyMsg").textContent="저장했습니다. 담당자에게 전달해 주십시오."; }
    catch(e){ const c=e&&e.code;
      $("#copyMsg").textContent = c==="declined" ? "저장을 취소했습니다."
        : c==="rate_limited" ? "잠시 후 다시 눌러 주십시오."
        : "저장할 수 없습니다. 「응답 복사」를 쓰십시오."; }
    return;
  }
  const b=new Blob([txt],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(b);
  a.download=name; a.click(); URL.revokeObjectURL(a.href);
};
state.secStart=Date.now();
</script>
"""

html = TEMPLATE.replace("__DATA__", json.dumps(DATA, ensure_ascii=False, separators=(",", ":")))
for kw in ("정답", "해설", "distractor_dx", "오답 진단"):
    if kw in html:
        sys.exit(f"FAIL: 응시본에 '{kw}' 누출")
OUT.write_text(html, encoding="utf-8")
print(f"생성: {OUT.relative_to(ROOT)}  ({len(html):,}자)")
print(f"  객관식 {len(mc)} / 공통지문 {len(stems)} / 자기보고 {len(sr)} / 주관식 {len(fr)} / 페르소나 {len(personas)}")
