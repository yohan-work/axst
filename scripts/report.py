#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""인쇄용 리포트 생성기. 응답 JSON(+ 주관식 점수) -> 개인 리포트 HTML · 조직 리포트 HTML

    python3 scripts/report.py responses/*.json --fr-scores pilot/work/fr-scores.final.json \\
        --out pilot/reports/ --org "○○본부" --round 파일럿

양식의 정본은 docs/05-report-templates.md, 처방 매핑의 정본은 docs/06-prescription.md 다.
문구와 표는 **그 문서에서 읽는다.** 표 모양이 바뀌어 읽지 못하면 폴백하지 않고 실패한다 —
엉뚱한 처방이 조용히 나가는 것보다 멈추는 편이 낫다.

리포트는 파일 하나로(스크립트·외부 리소스 없음) 만들고, 쓰기 전에 금지 표현을 검사한다.
- 개인: 축별 점수·백분위·순위표·차트 금지, 선택지의 정답 여부를 드러내지 않는다
- 조직: n < 10 이면 만들지 않는다. 5명 미만 셀은 "-" 로 가린다. 개인별 행을 넣지 않는다
"""
import re, sys, json, html, pathlib, argparse, statistics
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score  # noqa: E402
from score import (ROOT, AXIS_LABEL, FR_ITEMS, FR_DIMS, load_key, score_mc, flags,  # noqa: E402
                   level_of, level_text, fr_points, response_key, load_fr_scores, attach_fr_scores)

AXES = ['DEL', 'DSN', 'VER', 'FLW', 'RSK']
DIM_LABEL = {'D1': '위임 경계', 'D2': '규격 구체성', 'D3': '검증 설계', 'D4': '전환 효과'}
FLAG_CHIP = {'강점': ('🟢', '강점 신호', 'ok'), '보류': ('⚪', '판정 보류', 'hold'), '보완': ('🟠', '보완 필요', 'need')}
SR_REF = {'DEL': '(해당 없음)', 'DSN': 'SR-1', 'VER': 'SR-1', 'FLW': 'SR-2, SR-3', 'RSK': '(해당 없음)'}
MIN_ORG_N, MIN_CELL = 10, 5
PILOT_BANNER = "파일럿 참고용 — 문항 검증 회차의 결과입니다. 배치·평가에 쓰지 않습니다."

class SourceError(Exception):
    """정본 문서에서 기대한 표·문구를 찾지 못했다."""

class ForbiddenError(Exception):
    """리포트에 금지 표현이 들어갔다."""

def esc(s):
    return html.escape(str(s), quote=True)

def _md_inline(s):
    s = esc(s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    return s

def _strip_md(s):
    return re.sub(r'\*\*|`', '', s).strip()

# ---------- 정본 문서 읽기 ----------
def _table_after(text, header_cells, src):
    """header_cells 로 시작하는 마크다운 표의 본문 행들을 셀 목록으로 돌려준다."""
    lines = text.split('\n')
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if cells[:len(header_cells)] == header_cells:
            rows = []
            for l in lines[i + 2:]:
                if not l.strip().startswith('|'):
                    break
                rows.append([c.strip() for c in l.strip().strip('|').split('|')])
            if not rows:
                break
            return rows
    raise SourceError(f"{src}: 머리행이 {' | '.join(header_cells)} 인 표를 찾지 못했다")

def load_template_text():
    """docs/05: 필수 고지 2문장과 오개념 패턴 표."""
    src = 'docs/05-report-templates.md'
    t = (ROOT / src).read_text(encoding='utf-8')
    part = t.split('# 개인 리포트 (양식)', 1)
    if len(part) != 2:
        raise SourceError(f"{src}: '# 개인 리포트 (양식)' 절이 없다")
    quotes = re.findall(r'^> (.+)$', part[1].split('## 1.', 1)[0], re.M)
    notices = [q.strip() for q in quotes if q.strip() and q.strip() != '>']
    if len(notices) != 2:
        raise SourceError(f"{src}: 개인 리포트 첫머리의 필수 고지가 2문장이어야 하는데 {len(notices)}개다")
    patterns = []
    for name, where, sentence in _table_after(t, ['패턴', '어디서 드러나나', '피드백 문장'], src):
        mc = []
        for seqs, opt in re.findall(r'([\d·]+)번 선택지 (\d)', where):
            mc += [(int(s), int(opt)) for s in seqs.split('·')]
        d1cap = re.search(r'D1 상한 (\d)점', where)
        if not mc:
            raise SourceError(f"{src}: 패턴 '{name}' 의 드러나는 위치를 읽지 못했다: {where}")
        patterns.append({'name': _strip_md(name), 'mc': mc,
                         'd1cap': d1cap.group(1) if d1cap else None,
                         'sentence': sentence.strip().strip('"“”')})
    return {'notices': [_strip_md(n) for n in notices], 'notices_html': [_md_inline(n) for n in notices],
            'patterns': patterns}

def load_prescriptions():
    """docs/06 §1 레벨 → 트랙·주 처방 축, §2 축 → 교육 내용, L4 역할."""
    src = 'docs/06-prescription.md'
    t = (ROOT / src).read_text(encoding='utf-8')
    levels = {}
    for lv, track, course, axes in _table_after(t, ['본 진단 레벨', '트랙', '시장 실물 과정', '주 처방 대상 축'], src):
        m = re.search(r'L[1-4]', lv)
        if not m:
            raise SourceError(f"{src}: 레벨 칸을 읽지 못했다: {lv}")
        levels[m.group(0)] = {'track': _strip_md(track), 'axes': re.findall(r'\b(DEL|DSN|VER|FLW|RSK)\b', axes),
                              'note': _strip_md(axes)}
    if sorted(levels) != ['L1', 'L2', 'L3', 'L4']:
        raise SourceError(f"{src}: 레벨 표에 L1~L4 가 모두 있어야 한다 (읽은 것: {sorted(levels)})")
    axes = {}
    for ax, dx, edu, non_edu in _table_after(t, ['축', '관찰된 오개념 (리포트에서 그대로 인용)', '교육 내용', '교육이 아닌 것으로 해결'], src):
        m = re.search(r'\b(DEL|DSN|VER|FLW|RSK)\b', ax)
        if not m:
            raise SourceError(f"{src}: 축 칸을 읽지 못했다: {ax}")
        axes[m.group(1)] = {'edu': _strip_md(edu), 'non_edu': _strip_md(non_edu)}
    if sorted(axes) != sorted(AXES):
        raise SourceError(f"{src}: 축 표에 5축이 모두 있어야 한다 (읽은 것: {sorted(axes)})")
    # 문항 id를 가리키는 괄호(예: "(`MC-FLW-003` 정답 구조)")는 설계자용 참조라 응시자에게 내보내지 않는다
    roles = [f"{_strip_md(a)} — {re.sub(r'\s*\([^)]*MC-[A-Z]{3}-\d{3}[^)]*\)', '', _strip_md(b))}"
             for a, b in _table_after(t, ['역할', '구체적으로'], src)]
    exit_sec = re.search(r'^## 4\. 출구 전략 체크리스트.*?(?=^## 5\.)', t, re.S | re.M)
    exit_items = len(re.findall(r'^- \[ \]', exit_sec.group(0), re.M)) if exit_sec else 0
    if not exit_items:
        raise SourceError(f"{src}: §4 출구 전략 체크리스트 항목을 찾지 못했다")
    return {'levels': levels, 'axes': axes, 'l4_roles': roles, 'exit_items': exit_items}

# ---------- 공통 계산 ----------
def evaluate(resp, key):
    pts, correct, picks, missing = score_mc(resp, key)
    fl = flags(correct, key, resp)
    frp, why = fr_points(resp)
    total = None if frp is None else pts + frp
    return {'resp': resp, 'pts': pts, 'correct': correct, 'picks': picks, 'missing': missing,
            'flags': fl, 'fr': frp, 'fr_why': why, 'total': total,
            'level': None if total is None else level_of(total)}

def next_actions(ev, rx):
    """다음 행동 최대 2개. ① 레벨 트랙(L4는 전파 역할) ② 레벨의 주 처방 축 중 🟠, 없으면 DEL→RSK 순서 첫 🟠."""
    out = []
    need = [a for a in AXES if ev['flags'][a]['final'] == '보완']
    if ev['level']:
        code = ev['level'][0]
        lv = rx['levels'][code]
        if code == 'L4':
            out.append(("전파 역할", "교육 대상이 아니라 전파 담당자입니다. " + " / ".join(rx['l4_roles'])))
        else:
            first = next((a for a in lv['axes'] if a in need), None) or (need[0] if need else None)
            out.append((f"{lv['track']} 트랙", f"현재 수준({level_text(ev['total'])})에 맞춘 교육 과정입니다."
                        + (f" 주 처방 축은 {', '.join(AXIS_LABEL[a] for a in lv['axes'])}입니다." if lv['axes'] else "")))
            if first:
                out.append((AXIS_LABEL[first], rx['axes'][first]['edu']))
    else:
        for a in need[:2]:
            out.append((AXIS_LABEL[a], rx['axes'][a]['edu']))
    if len(out) < 2 and not need:
        hold = [a for a in AXES if ev['flags'][a]['final'] == '보류']
        if hold:
            out.append(("판정 보류 축 재확인", f"{', '.join(AXIS_LABEL[a] for a in hold)}은(는) 이번 결과로 판단하지 않고 다음 회차에 다시 확인합니다."))
    return out[:2]

def matched_patterns(ev, tpl):
    hits = []
    frs = ev['resp'].get('fr_scores') or {}
    for p in tpl['patterns']:
        mc = any((ev['picks'].get(s) or {}).get('best') == o for s, o in p['mc'])
        fr = p['d1cap'] and any(str(((frs.get(fid) or {}).get('cap') or {}).get('D1')) == p['d1cap'] for fid, _ in FR_ITEMS)
        if mc or fr:
            hits.append(p)
    return hits

# ---------- 금지 표현 ----------
def visible_text(doc):
    doc = re.sub(r'<style.*?</style>', '', doc, flags=re.S)
    return html.unescape(re.sub(r'<[^>]+>', ' ', doc))

def forbidden_check(doc, kind, tpl, secret_keys=()):
    problems = []
    text = visible_text(doc)
    for pat, why in [(r'\d\s*/\s*4\b', '축별 정답 수(n/4)'), (r'백분위', '백분위'), (r'순위표|등수', '순위'),
                     (r'<svg|<canvas', '차트')]:
        if re.search(pat, text if not pat.startswith('<') else doc):
            problems.append(f"금지 표현: {why}")
    if re.search(r'<script|(?:src|href)\s*=\s*["\']?(?:https?:)?//', doc, re.I):
        problems.append("스크립트·외부 리소스가 있다")
    for n in tpl['notices']:
        if re.sub(r'\s+', '', n) not in re.sub(r'\s+', '', text):
            problems.append(f"필수 고지 누락: {n[:30]}…")
    if kind == 'individual':
        if '정답' in text:
            problems.append("금지 표현: 정답")
        if '%' in text:
            problems.append("금지 표현: 백분율")
    if kind == 'org':
        for k in secret_keys:
            if k and k in text:
                problems.append(f"조직 리포트에 개인 식별 키가 있다: {k}")
    if problems:
        raise ForbiddenError("; ".join(problems))

# ---------- HTML 틀 ----------
CSS = """
@page{size:A4;margin:14mm 14mm 16mm}
*{box-sizing:border-box}
body{margin:0;background:#f4f5f7;color:#1a1d23;font-family:system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
  font-size:13.5px;line-height:1.65;word-break:keep-all;overflow-wrap:anywhere}
.page{max-width:780px;margin:24px auto;background:#fff;padding:36px 40px;border:1px solid #e2e5eb;border-radius:6px}
@media(max-width:600px){.page{margin:0;padding:22px 16px;border:0;border-radius:0}}
@media print{body{background:#fff}.page{margin:0;padding:0;border:0;max-width:none}section{break-inside:avoid-page}}
.banner{background:#fbf1e6;border-left:3px solid #9a5716;padding:8px 12px;font-size:12.5px;margin-bottom:18px}
.eyebrow{font-size:11px;letter-spacing:.12em;color:#666e7a;font-weight:600;margin:0}
h1{font-size:24px;margin:4px 0 6px;letter-spacing:-.01em}
h2{font-size:16px;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid #e2e5eb}
.meta{color:#4f5764;font-size:12.5px;margin:0}
.notice{background:#eef3f8;border-radius:6px;padding:12px 14px;margin:16px 0 4px;font-size:12.5px}
.notice p{margin:0}.notice p+p{margin-top:6px}
table{border-collapse:collapse;width:100%;font-size:12.5px;margin:6px 0}
th,td{border-bottom:1px solid #e2e5eb;padding:7px 8px;text-align:left;vertical-align:top}
th{font-weight:600;color:#4f5764;background:#f7f8fa}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.big{font-size:28px;font-weight:600;letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.summary{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid #e2e5eb;border-radius:6px;overflow:hidden}
.summary>div{padding:14px 16px}.summary>div+div{border-left:1px solid #e2e5eb}
@media(max-width:600px){.summary{grid-template-columns:1fr}.summary>div+div{border-left:0;border-top:1px solid #e2e5eb}}
.label{font-size:11.5px;color:#666e7a;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 10px}
.chip{border:1px solid #cbd1da;border-radius:999px;padding:3px 10px;font-size:12.5px;white-space:nowrap}
.chip.need{background:#fbf1e6;border-color:#e5c9a8}.chip.ok{background:#eaf5ef;border-color:#b9dcc8}
.muted{color:#666e7a}
.callout{border-left:3px solid #2f5d8c;padding:8px 12px;background:#f7f8fa;margin:8px 0}
ol.actions{padding-left:20px;margin:6px 0}ol.actions li{margin:6px 0}
.foot{margin-top:28px;font-size:11.5px;color:#666e7a;border-top:1px solid #e2e5eb;padding-top:10px}
"""

def page(title, body):
    return (f'<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n<main class="page">\n'
            f'{body}\n</main>\n</body>\n</html>\n')

def notices_html(tpl):
    return '<div class="notice">' + ''.join(f'<p>{n}</p>' for n in tpl['notices_html']) + '</div>'

def _date(iso):
    return (iso or '')[:10] or '—'

# ---------- 개인 리포트 ----------
def individual_html(ev, key, tpl, rx, round_label='파일럿'):
    r = ev['resp']
    who = r.get('respondent') if r.get('respondent') not in (None, '', '(미기재)') else None
    ident = f"응답 코드 {r['rid']}" if r.get('rid') else ''
    ident += (' · ' if ident and who else '') + (f"식별 코드 {who}" if who else '')
    B = []
    if round_label == '파일럿':
        B.append(f'<div class="banner">{esc(PILOT_BANNER)}</div>')
    B.append('<p class="eyebrow">AX LITERACY 진단 · 개인 리포트</p>')
    B.append('<h1>진단 결과</h1>')
    B.append(f'<p class="meta">응시일 {esc(_date(r.get("submittedAt")))} · 폼 {esc(r.get("form", "A"))} · {esc(ident or "무기명")}</p>')
    B.append(notices_html(tpl))

    # 1. 종합
    B.append('<section><h2>1. 종합</h2><div class="summary">')
    if ev['total'] is None:
        B.append(f'<div><div class="label">총점 구간</div><div class="big">산출 보류</div>'
                 f'<p class="muted">주관식이 {esc(ev["fr_why"])} 상태입니다.</p></div>'
                 '<div><div class="label">수준</div><div class="big">산출 보류</div></div>')
    else:
        lo, hi = max(0, ev['total'] - 5), min(100, ev['total'] + 5)
        B.append(f'<div><div class="label">총점 구간 (±5점)</div><div class="big">{lo} ~ {hi}점</div></div>'
                 f'<div><div class="label">수준</div><div class="big">{esc(level_text(ev["total"]))}</div></div>')
    B.append('</div>')
    B.append('<table><thead><tr><th>레벨</th><th>상태</th></tr></thead><tbody>')
    for code, name, desc in LEVEL_DESC:
        mark = ' style="background:#eef3f8;font-weight:600"' if ev['level'] and ev['level'][0] == code else ''
        B.append(f'<tr{mark}><td>{code} {esc(name)}</td><td>{esc(desc)}</td></tr>')
    B.append('</tbody></table></section>')

    # 2. 축별 신호
    B.append('<section><h2>2. 축별 신호</h2>')
    B.append('<p class="muted">축별 결과는 점수가 아니라 추가 확인이 필요한 영역을 가리키는 신호입니다.</p>')
    B.append('<div class="chips">' + ''.join(
        f'<span class="chip {FLAG_CHIP[ev["flags"][a]["final"]][2]}">{FLAG_CHIP[ev["flags"][a]["final"]][0]} '
        f'{esc(AXIS_LABEL[a])} · {FLAG_CHIP[ev["flags"][a]["final"]][1]}</span>' for a in AXES) + '</div>')
    B.append('<table><thead><tr><th>축</th><th>신호</th><th>자기보고 대조</th></tr></thead><tbody>')
    for a in AXES:
        f = ev['flags'][a]
        e, lab, _ = FLAG_CHIP[f['final']]
        note = f" — {f['note']}" if f['note'] else ''
        B.append(f'<tr><td>{esc(AXIS_LABEL[a])}</td><td>{e} {lab}</td><td>{esc(SR_REF[a])}{esc(note)}</td></tr>')
    B.append('</tbody></table><p class="muted">🟢 강점 신호 · ⚪ 판정 보류 · 🟠 보완 필요</p>')
    wrong = [(s, (ev['picks'].get(s) or {}).get('best')) for s in sorted(key)
             if (ev['picks'].get(s) or {}).get('best') and not ev['correct'].get(s)
             and ev['picks'][s]['best'] != key[s]['answer']]
    if wrong:
        B.append('<p><strong>고른 선택지에서 보인 생각의 습관</strong></p><table><thead><tr><th>문항</th><th>축</th><th>드러난 습관</th></tr></thead><tbody>')
        for s, pick in wrong:
            dx = key[s]['dx'].get(pick, '').strip(' "')
            B.append(f'<tr><td class="num">{s}번</td><td>{esc(AXIS_LABEL[key[s]["axis"]])}</td><td>{esc(dx)}</td></tr>')
        B.append('</tbody></table>')
    B.append('</section>')

    # 3. 주관식
    B.append('<section><h2>3. 주관식 피드백</h2>')
    frs = r.get('fr_scores') or {}
    if not frs:
        B.append('<p class="muted">주관식은 아직 채점되지 않았습니다.</p>')
    else:
        B.append('<table><thead><tr><th>문항</th><th>차원</th><th class="num">점수</th><th>한 줄 피드백</th></tr></thead><tbody>')
        pen_lines = []
        for fid, seq in FR_ITEMS:
            e = frs.get(fid)
            if not e:
                B.append(f'<tr><td>{seq}번</td><td colspan="3" class="muted">답안 없음</td></tr>')
                continue
            for i, d in enumerate(FR_DIMS):
                v = e.get(d)
                shown = '판정 보류' if v == score.HELD else (f'{v} / 5' if isinstance(v, int) else '—')
                comment = ((e.get('comment') or {}).get(d) or '').strip()
                B.append(f'<tr><td>{f"{seq}번" if i == 0 else ""}</td><td>{DIM_LABEL[d]}</td>'
                         f'<td class="num">{esc(shown)}</td><td>{esc(comment)}</td></tr>')
            if e.get('penalty'):
                pen_lines.append(f"{seq}번 감점 {e['penalty']}점 — 해당 규칙: {e.get('rule') or '(규칙 미기재)'}")
        B.append('</tbody></table>')
        B.append('<p><strong>감점</strong>: ' + (esc('; '.join(pen_lines)) if pen_lines else '없음') + '</p>')
    hits = matched_patterns(ev, tpl)
    for p in hits:
        B.append(f'<div class="callout"><strong>{esc(p["name"])}</strong><br>{esc(p["sentence"])}</div>')
    B.append('</section>')

    # 4. 다음 행동
    acts = next_actions(ev, rx)
    B.append('<section><h2>4. 다음 행동</h2>')
    if acts:
        B.append('<ol class="actions">' + ''.join(f'<li><strong>{esc(t)}</strong> — {esc(d)}</li>' for t, d in acts) + '</ol>')
    else:
        B.append('<p class="muted">이번 결과에서 따로 권할 행동이 없습니다.</p>')
    B.append('</section>')
    if round_label == '파일럿':
        # 관문 B 의 리포트 납득도(docs/07). 응시 시점에는 리포트를 보지 못했으므로 여기서 묻는다
        B.append('<section><h2>담당자에게 한 가지만 회신해 주십시오</h2>'
                 '<p>이 리포트가 <strong>본인의 실제 AI 활용 모습과 맞다고 느끼십니까?</strong> '
                 '1(전혀 아니다) ~ 5(매우 그렇다) 중 숫자 하나와 응답 코드를 담당자에게 보내 주십시오. '
                 '진단을 계속 쓸지 판단하는 데만 씁니다.</p></section>')
    B.append('<p class="foot">이 리포트는 본인과 본인이 지정한 상급자에게만 전달합니다. '
             '축 신호는 어떤 경우에도 인사·승진 자료로 쓰지 않습니다.</p>')
    return page(f"AX Literacy 진단 개인 리포트 {r.get('rid') or ''}".strip(), "\n".join(B))

LEVEL_DESC = [
    ('L1', '미착수', 'AI를 쓸 이유를 못 찾은 상태'),
    ('L2', '개인 활용', '개별 태스크에는 쓰지만 검증과 위임 경계가 불안정'),
    ('L3', '업무 내재화', '자기 업무에 안정적으로 쓰고 검증 습관이 있음. 흐름은 아직 못 바꿈'),
    ('L4', '재설계자', '업무 흐름을 다시 짜고 타인에게 전파할 수 있음'),
]

# ---------- 조직 리포트 ----------
def cell(count, n, pct=True):
    """5명 미만 셀은 가린다."""
    if count < MIN_CELL:
        return '-'
    return f"{count}명 ({count / n:.0%})" if pct else f"{count}명"

def org_html(evs, key, tpl, rx, org='', round_label='파일럿'):
    n = len(evs)
    if n < MIN_ORG_N:
        raise ValueError(f"응답 {n}명 — 조직 리포트는 {MIN_ORG_N}명 이상에서만 만든다(docs/04-scoring.md)")
    dates = sorted(_date(e['resp'].get('submittedAt')) for e in evs if e['resp'].get('submittedAt'))
    period = f"{dates[0]} ~ {dates[-1]}" if dates else '—'
    scored = [e for e in evs if e['total'] is not None]
    B = []
    if round_label == '파일럿':
        B.append(f'<div class="banner">{esc(PILOT_BANNER)}</div>')
    B.append('<p class="eyebrow">AX LITERACY 진단 · 조직 리포트</p>')
    B.append(f'<h1>{esc(org) + " " if org else ""}진단 결과</h1>')
    B.append(f'<p class="meta">응시 인원 {n}명 · 응시 기간 {esc(period)} · 회차 유형 {esc(round_label)}</p>')
    B.append(notices_html(tpl))
    B.append(f'<p class="muted">5명 미만인 칸은 개인을 식별할 수 있어 "-"로 가렸습니다. '
             f'{"n이 30명 미만이므로 축 사이의 차이는 해석하지 않습니다." if n < 30 else ""}</p>')

    # 1. 수준 분포 (2구간)
    bands = [('L1–L2', ('L1', 'L2')), ('L3–L4', ('L3', 'L4'))]
    held = n - len(scored)
    B.append('<section><h2>1. 수준 분포</h2><table><thead><tr><th>구간</th><th class="num">인원</th></tr></thead><tbody>')
    for label, codes in bands:
        c = sum(1 for e in scored if e['level'][0] in codes)
        B.append(f'<tr><td>{label}</td><td class="num">{cell(c, n)}</td></tr>')
    if held:
        B.append(f'<tr><td>산출 보류 (주관식 미채점·판정 보류)</td><td class="num">{cell(held, n)}</td></tr>')
    B.append('</tbody></table><p class="muted">파일럿 규모에서는 레벨을 두 구간으로 묶어 표시합니다.</p></section>')

    # 2. 축별 평균
    B.append('<section><h2>2. 축별 평균</h2><table><thead><tr><th>축</th><th class="num">평균 정답률</th>'
             '<th class="num">n</th><th class="num">95% 신뢰구간</th><th class="num">보완 필요</th></tr></thead><tbody>')
    for a in AXES:
        seqs = [s for s, k in key.items() if k['axis'] == a]
        rates = [sum(1 for s in seqs if e['correct'].get(s)) / len(seqs) for e in evs]
        avg = sum(rates) / n
        se = (avg * (1 - avg) / (n * len(seqs))) ** 0.5
        need = sum(1 for e in evs if e['flags'][a]['final'] == '보완')
        B.append(f'<tr><td>{esc(AXIS_LABEL[a])}</td><td class="num">{avg:.0%}</td><td class="num">{n}</td>'
                 f'<td class="num">±{1.96 * se:.0%}</td><td class="num">{cell(need, n)}</td></tr>')
    B.append('</tbody></table>')
    B.append('<p class="muted">n ≥ 30에서 축 간 15%p 이상 차이만 실질적으로 판별할 수 있습니다.</p></section>')

    # 3. 편차
    B.append('<section><h2>3. 구성원 간 편차</h2><table><tbody>')
    if len(scored) >= MIN_CELL:
        sd = statistics.pstdev([e['total'] for e in scored])
        B.append(f'<tr><th>총점 표준편차</th><td class="num">{sd:.1f}점 (산출 {len(scored)}명 기준)</td></tr>')
    else:
        B.append('<tr><th>총점 표준편차</th><td class="num">-</td></tr>')
    for code in ('L1', 'L4'):
        c = sum(1 for e in scored if e['level'][0] == code)
        B.append(f'<tr><th>{code} 인원</th><td class="num">{cell(c, n)}</td></tr>')
    B.append('</tbody></table><p class="muted">평균이 올라도 편차가 크면 팀 단위 적용이 되지 않고, 잘 쓰는 소수에게 일이 쏠립니다.</p></section>')

    # 4. 오답 집중 문항
    miss = Counter()
    for e in evs:
        for s, k in key.items():
            b = (e['picks'].get(s) or {}).get('best')
            if b and b != k['answer']:
                miss[s] += 1
    B.append('<section><h2>4. 오답 집중 문항 3개</h2><table><thead><tr><th class="num">문항</th><th>축</th>'
             '<th class="num">오답</th><th>가장 많이 고른 오답의 오개념</th></tr></thead><tbody>')
    for s, c in miss.most_common(3):
        picks = Counter((e['picks'].get(s) or {}).get('best') for e in evs
                        if (e['picks'].get(s) or {}).get('best') not in (None, key[s]['answer']))
        top, tc = picks.most_common(1)[0]
        dx = key[s]['dx'].get(top, '').strip(' "') if tc >= MIN_CELL else '-'
        B.append(f'<tr><td class="num">{s}번</td><td>{esc(AXIS_LABEL[key[s]["axis"]])}</td>'
                 f'<td class="num">{cell(c, n)}</td><td>{esc(dx)}</td></tr>')
    B.append('</tbody></table><p class="muted">오개념 문구가 교육 콘텐츠의 직접 입력값입니다.</p></section>')

    # 5. 감점
    B.append('<section><h2>5. 감점 발생</h2>')
    fr1 = [((e['resp'].get('fr_scores') or {}).get('FR-01') or {}).get('penalty') for e in evs]
    fr1 = [p for p in fr1 if isinstance(p, int)]
    B.append('<table><thead><tr><th>21번 감점</th><th class="num">건수</th></tr></thead><tbody>')
    for p, lab in ((-5, '−5 (민감 데이터 외부 투입 / 사외 무검증 게재)'), (-2, '−2 (승인 절차 미언급)')):
        B.append(f'<tr><td>{lab}</td><td class="num">{cell(fr1.count(p), max(len(fr1), 1))}</td></tr>')
    B.append('</tbody></table>')
    by_p = {}
    for e in evs:
        v = ((e['resp'].get('free_response') or {}).get('FR-02') or {})
        sc = (e['resp'].get('fr_scores') or {}).get('FR-02') or {}
        if v.get('persona') and isinstance(sc.get('penalty'), int):
            by_p.setdefault(v['persona'], []).append(sc['penalty'])
    B.append('<table><thead><tr><th>22번 페르소나</th><th class="num">응답</th><th class="num">−5</th><th class="num">−2</th></tr></thead><tbody>')
    for pk in ['HR', 'SALES', 'FIN', 'DEV', 'STAFF', 'MFG']:
        ps = by_p.get(pk, [])
        if not ps:
            continue
        cnt = len(ps)
        # 응답이 MIN_CELL 미만인 페르소나는 감점 칸을 가린다(docs/05). "2명 중 1건"은 사람을 가리킨다
        f5, f2 = ps.count(-5), ps.count(-2)
        show = lambda x: f"{x}건 ({x / cnt:.0%})" if cnt >= MIN_CELL else "-"
        B.append(f'<tr><td>{pk}</td><td class="num">{cell(cnt, n, pct=False)}</td>'
                 f'<td class="num">{show(f5)}</td><td class="num">{show(f2)}</td></tr>')
    B.append('</tbody></table><p class="muted">페르소나마다 위반할 기회가 달라 22번은 페르소나별로만 봅니다.</p></section>')

    # 6. 없어진 업무
    tasks = sorted(((e['resp'].get('selfreport') or {}).get('SR-02') or {}).get('text', '').strip()
                   for e in evs if ((e['resp'].get('selfreport') or {}).get('SR-02') or {}).get('choice') == '있다')
    tasks = [t for t in tasks if t]
    B.append('<section><h2>6. 없어진 업무 (자기보고 취합)</h2>')
    if len(tasks) >= MIN_CELL:
        B.append('<ul>' + ''.join(f'<li>{esc(t)}</li>' for t in tasks) + '</ul>')
        B.append(f'<p class="muted">{len(tasks)}건. 재진단의 기준선입니다. 순서는 가나다순이며 응답자와 연결되지 않습니다.</p>')
    else:
        B.append(f'<p class="muted">응답이 5건 미만이라 목록을 싣지 않습니다.</p>')
    B.append('</section>')

    # 7. 처방
    B.append('<section><h2>7. 처방 — 코호트 편성</h2><table><thead><tr><th>코호트</th><th class="num">인원</th>'
             '<th>편성 트랙</th><th>주 처방 축</th></tr></thead><tbody>')
    lv = rx['levels']
    cohorts = [('A', 'L1–L2', ('L1', 'L2')), ('B', 'L3', ('L3',)), ('—', 'L4', ('L4',))]
    for name, label, codes in cohorts:
        c = sum(1 for e in scored if e['level'][0] in codes)
        tracks = ' / '.join(dict.fromkeys(lv[x]['track'] for x in codes))
        axes = ', '.join(AXIS_LABEL[a] for a in dict.fromkeys(a for x in codes for a in lv[x]['axes'])) or lv[codes[0]]['note']
        if codes == ('L4',):
            tracks = '(전파 역할)'
        B.append(f'<tr><td>{name} · {label}</td><td class="num">{cell(c, n, pct=False)}</td><td>{esc(tracks)}</td><td>{esc(axes)}</td></tr>')
    B.append('</tbody></table>')
    B.append('<p class="muted">레벨로 반을 나누고 부서·직급으로 나누지 않습니다. 반 정원은 20명 이하입니다. '
             '경계에 걸린 응시자는 낮은 쪽 반에 배치합니다.</p>')
    need_axes = [(a, sum(1 for e in evs if e['flags'][a]['final'] == '보완')) for a in AXES]
    need_axes = [(a, c) for a, c in need_axes if c >= MIN_CELL]
    if need_axes:
        B.append('<table><thead><tr><th>보완 필요가 5명 이상인 축</th><th>교육 내용</th><th>교육이 아닌 것으로 해결</th></tr></thead><tbody>')
        for a, c in sorted(need_axes, key=lambda x: -x[1]):
            B.append(f'<tr><td>{esc(AXIS_LABEL[a])}</td><td>{esc(rx["axes"][a]["edu"])}</td><td>{esc(rx["axes"][a]["non_edu"])}</td></tr>')
        B.append('</tbody></table>')
    B.append(f'<p><strong>출구 전략 체크리스트</strong>: 교육 개강 전에 docs/06 §4의 {rx["exit_items"]}개 항목을 확인해 미충족 개수를 이 칸에 적습니다 → ____개</p>')
    B.append('</section>')
    B.append('<p class="foot">이 리포트에는 개인별 결과가 없습니다. 개인 리포트는 본인에게만 전달됩니다.</p>')
    return page(f"AX Literacy 진단 조직 리포트{' ' + org if org else ''}", "\n".join(B))

# ---------- 실행 ----------
def build_reports(responses, outdir, fr_scores=None, org='', round_label='파일럿', individual=True, organization=True):
    key, tpl, rx = load_key(), load_template_text(), load_prescriptions()
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    evs, written = [], []
    for r in responses:
        if fr_scores is not None:
            attach_fr_scores(r, fr_scores)
        evs.append(evaluate(r, key))
    if individual:
        for ev in evs:
            doc = individual_html(ev, key, tpl, rx, round_label)
            forbidden_check(doc, 'individual', tpl)
            name = re.sub(r'[^0-9A-Za-z가-힣_-]', '_', response_key(ev['resp']) or 'unknown')
            path = outdir / f"report-{name}.html"
            path.write_text(doc, encoding='utf-8'); written.append(path)
    if organization:
        doc = org_html(evs, key, tpl, rx, org, round_label)
        forbidden_check(doc, 'org', tpl, secret_keys=[e['resp'].get('rid') for e in evs])
        path = outdir / "report-org.html"
        path.write_text(doc, encoding='utf-8'); written.append(path)
    return written

def main(argv=None):
    ap = argparse.ArgumentParser(description="AX Literacy 진단 인쇄용 리포트 생성")
    ap.add_argument('files', nargs='+', help='응답 JSON')
    ap.add_argument('--fr-scores', metavar='FILE', help='fr_import.py 결과 (fr-scores.json / fr-scores.final.json)')
    ap.add_argument('--out', default='pilot/reports', help='출력 폴더 (기본: pilot/reports, git 제외)')
    ap.add_argument('--org', default='', help='조직 리포트에 적을 대상 조직 이름')
    ap.add_argument('--round', default='파일럿', choices=['파일럿', '진단'], help='회차 유형')
    ap.add_argument('--no-org', action='store_true', help='조직 리포트를 만들지 않는다')
    a = ap.parse_args(argv)
    responses = []
    for f in a.files:
        r = json.loads(pathlib.Path(f).read_text(encoding='utf-8'))
        if r.get('schema') != 'axst-response-1':
            print(f"건너뜀 (schema 불일치): {f}", file=sys.stderr); continue
        responses.append(r)
    if not responses:
        print("리포트를 만들 응답이 없다.", file=sys.stderr); return 1
    frs = load_fr_scores(a.fr_scores) if a.fr_scores else None
    org_ok = not a.no_org and len(responses) >= MIN_ORG_N
    if not a.no_org and not org_ok:
        print(f"응답 {len(responses)}명 — 조직 리포트는 {MIN_ORG_N}명 이상에서만 만든다. 개인 리포트만 만든다.", file=sys.stderr)
    try:
        written = build_reports(responses, a.out, frs, a.org, a.round, organization=org_ok)
    except (SourceError, ForbiddenError, ValueError) as e:
        print(f"리포트 생성 실패: {e}", file=sys.stderr); return 1
    print(f"리포트 {len(written)}개 → {a.out}")
    for p in written:
        print(f"  {p}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
