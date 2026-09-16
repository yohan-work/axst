#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""응답 채점기. 온라인 응시본이 낸 JSON을 받아 객관식을 채점하고 축 플래그를 낸다.

    python3 scripts/score.py pilot/responses/*.json
    python3 scripts/score.py pilot/responses/*.json --prompts out/   # 주관식 5패스 프롬프트 생성
    python3 scripts/score.py pilot/responses/*.json --cohort         # 조직 집계 (n>=10)

정답은 items/ 에서 읽는다(SSOT). forms/ 는 린트가 items/ 와 대조하므로 어느 쪽을 읽어도
같지만, 원본을 읽는 편이 안전하다.

**이 스크립트는 개인의 축별 점수를 숫자로 내보내지 않는다.** 축당 4문항으로는 2/4와 3/4가
구별되지 않는다(docs/04-scoring.md). 축 결과는 3단 플래그로만 낸다.
"""
import re, io, json, sys, pathlib, argparse
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
AXIS_CODE = {'위임판단력':'DEL','작업설계':'DSN','검증신뢰':'VER',
             '워크플로우':'FLW','리스크거버넌스':'RSK'}
AXIS_LABEL = {'DEL':'위임 판단력','DSN':'작업 설계','VER':'검증·신뢰 조정',
              'FLW':'워크플로우 재설계','RSK':'리스크·거버넌스'}
FLAG = {'강점':'🟢 강점 신호','보류':'⚪ 판정 보류','보완':'🟠 보완 필요'}
LEVELS = [(0,39,'L1','미착수'),(40,59,'L2','개인 활용'),
          (60,79,'L3','업무 내재화'),(80,100,'L4','재설계자')]

def parse_item(path):
    t = path.read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', t, re.S)
    fm = {}
    for line in m.group(1).split('\n'):
        km = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if km: fm[km.group(1)] = km.group(2).strip()
    dx = dict(re.findall(r'^  ([1-4]): (.*)$', t, re.M))
    return fm, dx

def load_key():
    """MANIFEST 순서 + 문항 파일 정답. 린트가 둘의 일치를 보장한다."""
    mani = (ROOT/'forms/MANIFEST.yml').read_text(encoding='utf-8')
    order = re.findall(r'^  - \{seq: (\d+),\s*id: (MC-[A-Z]{3}-\d{3})', mani, re.M)
    key = {}
    for seq, iid in order:
        path = list(ROOT.glob(f'items/mc/*/{iid}.md'))[0]
        fm, dx = parse_item(path)
        worst = fm.get('answer_worst')
        key[int(seq)] = {
            'id': iid, 'axis': AXIS_CODE[fm['axis']], 'level': fm['level'],
            'answer': int(fm['answer']),
            'worst': None if worst in (None,'null','') else int(worst),
            'dx': {int(k): v for k, v in dx.items()},
        }
    if len(key) != 20:
        sys.exit(f"정답 로드 실패: {len(key)}문항")
    return key

def score_mc(resp, key):
    """객관식 채점. 최선차선은 최선 2점 + 최악 1점."""
    pts, correct_items, picks, missing = 0, {}, {}, []
    for seq, k in key.items():
        a = (resp.get('mc') or {}).get(str(seq)) or (resp.get('mc') or {}).get(seq) or {}
        best, worst = a.get('best'), a.get('worst')
        if best is None or (k['worst'] and worst is None):
            missing.append(seq)
        got_best = best == k['answer']
        if k['worst']:
            got_worst = worst == k['worst']
            pts += (2 if got_best else 0) + (1 if got_worst else 0)
            # 축 집계는 득점이 아니라 정답 문항 수 — 부분 정답은 정답으로 세지 않는다
            correct_items[seq] = got_best and got_worst
        else:
            pts += 3 if got_best else 0
            correct_items[seq] = got_best
        picks[seq] = {'best': best, 'worst': worst}
    return pts, correct_items, picks, missing

def sr_signal(resp, axis):
    """자기보고 신호. docs/04-scoring.md 삼각검증 절."""
    sr = resp.get('selfreport') or {}
    g = lambda k: (sr.get(k) or {}).get('choice')
    if axis in ('DSN','VER'):
        v = g('SR-01')
        if v in ('3~4개','5개 이상'): return '활발'
        if v == '0개': return '없음'
        return '중간'
    if axis == 'FLW':
        s2, s3 = sr.get('SR-02') or {}, g('SR-03')
        if (s2.get('choice') == '있다' and (s2.get('text') or '').strip()) or s3 in ('1명','2명 이상'):
            return '활발'
        if s2.get('choice') == '없다' and s3 == '없다': return '없음'
        return '중간'
    return None   # DEL·RSK 는 대응 자기보고가 없다

def flags(correct_items, key, resp):
    out = {}
    for code in ['DEL','DSN','VER','FLW','RSK']:
        seqs = [s for s, k in key.items() if k['axis'] == code]
        n = sum(1 for s in seqs if correct_items.get(s))
        base = '강점' if n == 4 else ('보류' if n == 3 else '보완')
        sig = sr_signal(resp, code)
        final, note = base, ''
        if sig:
            if base == '강점' and sig != '활발':
                final, note = '보류', f'자기보고가 뒷받침하지 않음({sig})'
            elif base == '보완' and sig == '활발':
                final, note = '보류', '자기보고와 상충(실사용 활발)'
        out[code] = {'n': n, 'of': len(seqs), 'base': base, 'final': final,
                     'signal': sig, 'note': note}
    return out

def level_of(total):
    for lo, hi, code, name in LEVELS:
        if lo <= total <= hi:
            edge = any(abs(total - b) <= 0 for b in (39,40,59,60,79,80))
            return code, name, edge
    return '?', '?', False

# ---------- 리포트 ----------
def render(resp, key, pts, correct_items, picks, missing, fl):
    L = []
    rid = resp.get('respondent') or '(미기재)'
    d = resp.get('durations_sec') or {}
    L.append(f"# 채점 결과 — {rid}")
    L.append("")
    L.append(f"- 제출: {resp.get('submittedAt','?')}")
    if d:
        mm = lambda s: f"{int(s)//60}:{int(s)%60:02d}"
        L.append(f"- 소요: 전체 {mm(d.get('total',0))} "
                 f"(0부 {mm(d.get('sr',0))} · 1부 {mm(d.get('mc',0))} · 2부 {mm(d.get('fr',0))})")
    L.append("")
    L.append(f"## 객관식 {pts} / 60")
    if missing:
        L.append("")
        L.append(f"> **미응답 {len(missing)}문항**: {', '.join(map(str, missing))}번")
    L.append("")
    L.append("| 순서 | 문항 | 축 | 응답 | 정답 | 판정 |")
    L.append("|---|---|---|---|---|---|")
    for seq in sorted(key):
        k, p = key[seq], picks[seq]
        if k['worst']:
            got = f"최선 {p['best'] or '—'} / 최악 {p['worst'] or '—'}"
            ans = f"최선 {k['answer']} / 최악 {k['worst']}"
        else:
            got, ans = str(p['best'] or '—'), str(k['answer'])
        mark = '✅' if correct_items.get(seq) else ('⚠️' if p['best'] is not None else '—')
        L.append(f"| {seq} | `{k['id']}` | {k['axis']} | {got} | {ans} | {mark} |")

    L.append("")
    L.append("## 축 플래그")
    L.append("")
    L.append("| 축 | 정답 문항 | 1차 플래그 | 자기보고 | 확정 |")
    L.append("|---|---|---|---|---|")
    for code in ['DEL','DSN','VER','FLW','RSK']:
        f = fl[code]
        sig = f['signal'] or '해당 없음'
        L.append(f"| {code} {AXIS_LABEL[code]} | {f['n']}/{f['of']} | {FLAG[f['base']]} "
                 f"| {sig} | **{FLAG[f['final']]}** |")
    notes = [f"{c}: {fl[c]['note']}" for c in fl if fl[c]['note']]
    if notes:
        L.append("")
        for n in notes: L.append(f"- {n}")
    L.append("")
    L.append("> 축 결과는 점수가 아니라 **추가 확인이 필요한 영역을 가리키는 신호**다. "
             "축당 4문항으로는 2/4와 3/4가 통계적으로 구별되지 않는다(docs/04-scoring.md).")

    # 오답 진단 — 리포트 서술 피드백의 근거
    wrong = [(s, picks[s]['best']) for s in sorted(key)
             if picks[s]['best'] and picks[s]['best'] != key[s]['answer']]
    if wrong:
        L.append("")
        L.append("## 오답 진단 (서술 피드백 근거)")
        L.append("")
        for s, pick in wrong:
            dx = key[s]['dx'].get(pick, '').strip(' "')
            L.append(f"- **{s}번** 선택지 {pick} — {dx}")

    fr = resp.get('free_response') or {}
    L.append("")
    L.append("## 주관식 (별도 채점)")
    L.append("")
    L.append("| 문항 | 페르소나 | 글자수 | 상태 |")
    L.append("|---|---|---|---|")
    for fid, seq in (('FR-01', 21), ('FR-02', 22)):
        v = fr.get(fid) or {}
        n = v.get('chars', 0)
        st = '미작성' if not v.get('text') else ('분량 미달' if n < 400 else '작성됨')
        L.append(f"| {seq} `{fid}` | {v.get('persona') or '—'} | {n}자 | {st} |")
    L.append("")
    L.append("주관식 40점은 [llm-scorer-prompt.md](../rubrics/llm-scorer-prompt.md) 프로토콜로 "
             "따로 채점한다 — 차원별 독립 4패스 + 감점 1패스. `--prompts` 로 패킷을 생성한다.")

    frp = resp.get('fr_scores') or {}
    if frp:
        tot = pts + sum(int(v.get('total', 0)) for v in frp.values())
        code, name, edge = level_of(tot)
        L.append("")
        L.append("## 총점")
        L.append("")
        L.append(f"객관식 {pts} + 주관식 {tot-pts} = **{tot} / 100**  → "
                 f"**{code} {name}**{' (경계 — 낮은 쪽 처방 적용)' if edge else ''}")
        L.append("")
        L.append(f"> 총점은 ±5점 밴드로만 해석한다. 구간 **{max(0,tot-5)}~{min(100,tot+5)}**.")
    else:
        L.append("")
        L.append("> 주관식이 채점되지 않아 총점과 레벨을 산출하지 않았다. "
                 "채점 후 응답 JSON에 `fr_scores` 를 넣고 다시 실행한다.")
    return "\n".join(L)

# ---------- 주관식 채점 패킷 ----------
def _scrub(s):
    return "\n".join(l for l in s.split("\n")
                     if not re.search(r'회차 C[01]|결함 \d|10-calibration-findings', l))

def _sec(path, head):
    txt = (ROOT/path).read_text(encoding='utf-8')
    for b in re.split(r'\n---\n', txt):
        if re.search(r'^##\s*' + re.escape(head), b.strip(), re.M):
            return _scrub(b.strip())
    raise KeyError(head)

def _principles(path):
    m = re.search(r'## 공통 채점 원칙\n(.*?)\n---', (ROOT/path).read_text(encoding='utf-8'), re.S)
    return _scrub("## 공통 채점 원칙\n" + m.group(1).strip())

def _anchors(path):
    """실제 응답 채점에는 앵커를 준다(캘리브레이션 회차와 반대)."""
    return _scrub((ROOT/path).read_text(encoding='utf-8').split('## 캘리브레이션 채점표')[0])

def build_prompts(responses, outdir):
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    personas = {}
    for p in sorted(ROOT.glob('personas/*.md')):
        t = p.read_text(encoding='utf-8')
        personas[re.search(r'^key:\s*(\w+)', t, re.M).group(1)] = t.split('## 페르소나',1)[1].strip()

    body = []
    for r in responses:
        rid = r.get('respondent') or '(미기재)'
        for fid, seq in (('FR-01', 21), ('FR-02', 22)):
            v = (r.get('free_response') or {}).get(fid) or {}
            if not v.get('text'): continue
            body.append(f"### 응답 {rid} · {seq}번 ({fid})")
            if fid == 'FR-02' and v.get('persona'):
                body.append(f"\n**선택한 페르소나: {v['persona']}**\n")
                body.append("```\n" + personas.get(v['persona'], '') + "\n```\n")
            body.append("\n**답안 전문:**\n")
            body.append("```\n" + v['text'] + "\n```\n")
            body.append("---\n")
    answers_block = "\n".join(body)
    if not answers_block:
        print("채점할 주관식 답안이 없다.", file=sys.stderr); return

    specs = [('D1','D1 위임 경계와 책임 귀속',True), ('D2','D2 규격 구체성',False),
             ('D3','D3 검증 설계',False), ('D4','D4 업무 전환 효과',True)]
    for code, title, judge in specs:
        parts = [f"# 채점 패스 — {title}", "",
                 f"아래 루브릭의 **{code} 한 차원만** 채점한다. 다른 차원은 채점하지 않고 총점을 추정하지 않는다.",
                 "", "## 절대 규칙", "",
                 "- **이 파일 밖의 어떤 파일도 읽지 마라.**",
                 "- **반드시 근거 인용 → 요건/카운트 점검 → 상한 점검 → 점수** 순서로 출력한다.",
                 "- 원문에 없는 내용을 요약하거나 보충하지 마라. 형용사만 있으면 \"없음\"으로 처리한다.",
                 "- **상한 규칙은 네 차원 전부에 적용된다.** 모든 답안에 명시적으로 판정하라.",
                 "- 상한이 걸리면 **상한 적용 전(base) 점수와 최종 점수를 둘 다** 쓴다.", ""]
        parts += ["## FR-01 루브릭 (21번)", "", _principles('rubrics/fr-01.md'), "",
                  _sec('rubrics/fr-01.md', code + '.'), "",
                  "## FR-02 루브릭 (22번)", "", _principles('rubrics/fr-02.md'), "",
                  _sec('rubrics/fr-02.md', code + '.'), ""]
        if judge:
            parts += ["---", "", "# 대조용 앵커", "",
                      _anchors('rubrics/fr-01-anchors.md'), "", "---", "",
                      _anchors('rubrics/fr-02-anchors.md'), ""]
        parts += ["---", "", "# 채점할 답안", "", answers_block, "", "---", "",
                  "# 출력", "", "답안 전부에 대해 위 순서로 출력하고, 마지막에 "
                  "요약표(응답 · 근거 요약 · base · 상한 · 최종)를 붙인다."]
        (outdir/f"pass-{code}.md").write_text("\n".join(parts), encoding='utf-8')

    pen = ["# 채점 패스 — 리스크 감점 판정", "",
           "점수를 매기지 않고 감점 해당 여부만 판정한다. 차원 점수를 추정하지 마라.", "",
           "## 절대 규칙", "",
           "- **이 파일 밖의 어떤 파일도 읽지 마라.**",
           "- 리스크 미언급만으로는 감점하지 않는다. 사내 전용 도구 사용은 감점하지 않는다.",
           "- 판정이 애매하면 감점하지 않는다(0).",
           "- AI를 쓰지 않겠다는 답안에 가점하지 않는다.", "", "---", "", "# 감점 규칙 전문", "",
           (ROOT/'rubrics/penalty-risk.md').read_text(encoding='utf-8'), "", "---", "",
           "# 판정할 답안", "", answers_block, "", "---", "",
           "# 출력", "", "답안마다 1) 인용 2) 감점 예외 대조 3) 판정(−5/−2/0)과 적용 규칙. "
           "마지막에 요약표."]
    (outdir/"pass-penalty.md").write_text("\n".join(pen), encoding='utf-8')
    print(f"주관식 채점 패킷 5개 생성: {outdir}/pass-{{D1,D2,D3,D4,penalty}}.md", file=sys.stderr)
    print("  프로토콜: 패스마다 독립 컨텍스트, temperature 0, 이전 패스 점수를 보여주지 않는다.",
          file=sys.stderr)

# ---------- 조직 집계 ----------
def cohort(rows, key):
    n = len(rows)
    L = ["# 조직 리포트 (집계)", "", f"응시 인원 **n = {n}**", ""]
    if n < 10:
        L += ["> **n < 10 이므로 조직 리포트를 생성하지 않는다.**(docs/04-scoring.md) "
              "개인 리포트만 쓴다."]
        return "\n".join(L)
    L += ["| 축 | 평균 정답률 | 보완 필요 비율 |", "|---|---|---|"]
    for code in ['DEL','DSN','VER','FLW','RSK']:
        seqs = [s for s, k in key.items() if k['axis'] == code]
        rates = [sum(1 for s in seqs if r['correct'].get(s))/len(seqs) for r in rows]
        avg = sum(rates)/n
        need = sum(1 for r in rows if r['flags'][code]['final'] == '보완')/n
        se = (avg*(1-avg)/(n*len(seqs)))**0.5
        L.append(f"| {code} {AXIS_LABEL[code]} | {avg:.0%} (±{1.96*se:.0%}) | {need:.0%} |")
    L += ["", "> 축 간 비교는 **n ≥ 30** 에서만 한다. 신뢰구간은 95%.", ""]
    miss = Counter()
    for r in rows:
        for s, k in key.items():
            if r['picks'][s]['best'] and r['picks'][s]['best'] != k['answer']:
                miss[s] += 1
    L += ["## 오답 집중 문항 상위 3", "", "| 순서 | 문항 | 축 | 오답률 | 최다 오답 |", "|---|---|---|---|---|"]
    for s, c in miss.most_common(3):
        picks = Counter(r['picks'][s]['best'] for r in rows
                        if r['picks'][s]['best'] and r['picks'][s]['best'] != key[s]['answer'])
        top = picks.most_common(1)[0][0] if picks else '—'
        dx = key[s]['dx'].get(top, '').strip(' "')
        L.append(f"| {s} | `{key[s]['id']}` | {key[s]['axis']} | {c/n:.0%} | 선택지 {top} — {dx} |")
    L += ["", "> 개인을 식별할 수 있는 셀(n<5)은 표에 넣지 않는다. 개인 순위표를 만들지 않는다."]
    return "\n".join(L)

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="AX Literacy 진단 응답 채점기")
    ap.add_argument('files', nargs='+', help='응답 JSON (온라인 응시본이 낸 것)')
    ap.add_argument('--prompts', metavar='DIR', help='주관식 5패스 채점 패킷을 DIR 에 생성')
    ap.add_argument('--cohort', action='store_true', help='조직 집계도 출력 (n>=10)')
    a = ap.parse_args()

    key = load_key()
    rows, responses, out = [], [], []
    for f in a.files:
        r = json.loads(pathlib.Path(f).read_text(encoding='utf-8'))
        if r.get('schema') != 'axst-response-1':
            print(f"건너뜀 (schema 불일치): {f}", file=sys.stderr); continue
        responses.append(r)
        pts, correct, picks, missing = score_mc(r, key)
        fl = flags(correct, key, r)
        rows.append({'r': r, 'pts': pts, 'correct': correct, 'picks': picks, 'flags': fl})
        out.append(render(r, key, pts, correct, picks, missing, fl))
    if not rows: sys.exit("채점할 응답이 없다.")
    if a.cohort:
        out.append(cohort(rows, key))
    print("\n\n---\n\n".join(out))
    if a.prompts:
        build_prompts(responses, a.prompts)

if __name__ == '__main__':
    main()
