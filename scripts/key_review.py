#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정답 키 검토 — 정답을 가린 검토지를 만들고, 검토자(AI·사람)의 답을 키와 대조한다.

    python3 scripts/key_review.py packet --rules    > review-rules.md     # 실제 시험 조건(사전 안내 규칙 포함)
    python3 scripts/key_review.py packet --no-rules > review-norules.md   # 규칙 없이
    python3 scripts/key_review.py template > sme.csv                      # 사람 검토자용 빈 표(엑셀)
    python3 scripts/key_review.py analyze results/*.json results/*.csv    # 판정

판정 기준은 docs/15-key-review.md 에 사전 등록되어 있다. 이 스크립트의 상수는 그 문서와 같아야 한다.
검토지에는 정답·해설·오답 진단이 없다(build_web_form 의 누출 검사를 그대로 쓴다).
"""
import re, csv, sys, json, html, pathlib, argparse
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_web_form as bwf  # noqa: E402
import score  # noqa: E402

ROOT = score.ROOT
SUPPORT_AGREE, SUPPORT_GAP = 2 / 3, 0.5      # 지지: 일치 ≥ 2/3 그리고 평균 적절성 차이 ≥ 0.5
DISPUTE_AGREE = 1 / 2                        # 논쟁: 일치 < 1/2 또는 다른 선택지가 더 적절
RULE_DEP = 0.5                               # 규칙 의존: rules − norules 일치율 ≥ 0.5
OPEN, CLOSE = '<<<KEYREVIEW', '>>>'


def _text(h):
    return html.unescape(re.sub(r'<[^>]+>', '', h.replace('</p>', '\n').replace('<br>', '\n'))).strip()


def rules_text():
    t = (ROOT / 'docs' / '08-administration.md').read_text(encoding='utf-8')
    m = re.search(r'### 이 진단이 쓰는 우선순위 규칙.*?\n(.*?)(?=\n### )', t, re.S)
    if not m:
        raise SystemExit("docs/08 에서 우선순위 규칙 절을 찾지 못했다")
    return m.group(1).strip()


def packet(with_rules):
    data = bwf.collect()
    problems = bwf.check_data(data)
    if problems:
        raise SystemExit("검토지 데이터에 누출: " + "; ".join(problems))
    L = ["# AI 활용 판단 문항 검토지", "",
         "당신은 기업에서 생성형 AI를 실무에 깊게 써 온 **AX(AI 전환) 실무 전문가**다. 아래는 조직 구성원의 AI 활용 판단력을 보는 "
         "객관식 문항 20개다. 출제자가 정한 답은 보여 주지 않는다. **당신의 실무 판단**으로 답하라.", "",
         "## 규칙", "",
         "- 어떤 파일도 읽지 말고, 도구나 명령을 쓰지 마라. 이 텍스트만으로 답한다",
         "- 문항마다: 가장 적절한 선택지(`best`), 최선–최악형이면 가장 부적절한 선택지(`worst`), "
         "선택지 4개 각각의 적절성(`ratings`, 1=매우 부적절 … 5=매우 적절), 확신도(`confidence`, 1~3), "
         "답이 둘 이상으로 갈릴 만큼 모호하면 `ambiguous: true`와 이유(`note`, 한 문장)",
         "- 출제 의도를 추측하지 말고, 실제 업무에서 어떻게 하는 것이 맞는지로 판단한다", ""]
    if with_rules:
        L += ["## 응시자가 사전에 안내받는 우선순위 규칙", "",
              "응시자는 시험 전에 아래 안내를 받는다. 이 안내를 받은 응시자 입장에서 판단하라.", "", rules_text(), ""]
    L += ["---", "", "## 문항", ""]
    seen = set()
    for m in data['mc']:
        if m['stem'] and m['stem'] not in seen:
            seen.add(m['stem'])
            st = data['stems'][m['stem']]
            L += [f"### 공통 상황 — {st['label']}", "", _text(st['html']), ""]
        L += [f"**{m['seq']}번**" + (" (최선–최악형: 가장 적절한 것과 가장 부적절한 것을 각각 고른다)" if m['worst'] else ""), ""]
        if m['solo']:
            L += [_text(m['solo']), ""]
        L += [_text(m['q']), ""]
        L += [f"{j}. {_text(o)}" for j, o in enumerate(m['options'], 1)] + [""]
    L += ["---", "", "## 출력", "",
          "설명은 원하는 만큼 써도 되지만, 맨 마지막에 아래 형식의 블록을 **정확히 한 번** 출력한다. 블록 안은 JSON 한 개다.", "",
          "```", OPEN,
          '{"items": {"1": {"best": 2, "worst": null, "ratings": [2, 5, 3, 1], "confidence": 2, "ambiguous": false, "note": ""}, "...": "20번까지"}}',
          CLOSE, "```"]
    out = "\n".join(L)
    for kw in ("정답", "해설", "distractor", "오답 진단"):
        if kw in out:
            raise SystemExit(f"검토지에 '{kw}' 가 들어갔다")
    return out


# ---------- 결과 읽기 ----------
def read_result(path, key):
    """AI 결과(.txt/.json, 블록 포함) 또는 사람 CSV 를 {'rater','vendor','condition','items'} 로."""
    p = pathlib.Path(path)
    meta = dict(re.findall(r'(rater|vendor|condition)=([^_]+)', p.stem.replace('__', '_')))
    if p.suffix == '.csv':
        items = {}
        with open(p, encoding='utf-8-sig', newline='') as fh:
            for row in csv.DictReader(fh):
                s = int(row['문항'])
                items[s] = {'best': int(row['가장 적절']), 'worst': int(row['가장 부적절']) if row.get('가장 부적절') else None,
                            'ratings': [int(row[f'선택지{j} 적절성']) for j in range(1, 5)],
                            'confidence': int(row.get('확신도') or 2), 'ambiguous': (row.get('모호') or '').strip() in ('1', 'Y', 'y', '예'),
                            'note': row.get('메모', '')}
    else:
        text = p.read_text(encoding='utf-8')
        blocks = re.findall(rf'{re.escape(OPEN)}\s*(\{{.*?\}})\s*{re.escape(CLOSE)}', text, re.S)
        if len(blocks) != 1:
            raise ValueError(f"{p.name}: 결과 블록이 {len(blocks)}개다")
        raw = json.loads(blocks[-1])['items']
        items = {int(k): v for k, v in raw.items() if k.isdigit()}
    missing = sorted(set(key) - set(items))
    if missing:
        raise ValueError(f"{p.name}: 문항 {missing} 답이 없다")
    for s, v in items.items():
        r = v.get('ratings') or []
        if len(r) != 4 or not all(isinstance(x, int) and 1 <= x <= 5 for x in r):
            raise ValueError(f"{p.name}: {s}번 적절성 {r!r} — 1~5 정수 4개여야 한다")
        if v.get('best') not in (1, 2, 3, 4):
            raise ValueError(f"{p.name}: {s}번 best {v.get('best')!r}")
        if key[s]['worst'] and v.get('worst') not in (1, 2, 3, 4):
            raise ValueError(f"{p.name}: {s}번은 최선–최악형인데 worst 가 없다")
    return {'rater': meta.get('rater', p.stem), 'vendor': meta.get('vendor', '?'),
            'condition': meta.get('condition', 'rules'), 'items': items}


# ---------- 판정 ----------
def judge_side(results, s, key_opt, side):
    """side='best' 또는 'worst'. (일치율, 키 평균 적절성, 비교 대상 평균, 판정)"""
    n = len(results)
    agree = sum(1 for r in results if r['items'][s].get(side) == key_opt) / n
    means = [sum(r['items'][s]['ratings'][j] for r in results) / n for j in range(4)]
    k = means[key_opt - 1]
    others = [m for j, m in enumerate(means) if j != key_opt - 1]
    if side == 'best':
        gap = k - max(others)
        worse = max(others) > k
    else:                                   # 최악 키는 가장 덜 적절해야 한다
        gap = min(others) - k
        worse = min(others) < k
    if agree >= SUPPORT_AGREE and gap >= SUPPORT_GAP:
        verdict = '지지'
    elif agree < DISPUTE_AGREE or worse:
        verdict = '논쟁'
    else:
        verdict = '주의'
    return agree, means, gap, verdict


RANK = {'지지': 0, '주의': 1, '논쟁': 2}


def analyze(results, key):
    by_cond = defaultdict(list)
    for r in results:
        by_cond[r['condition']].append(r)
    main = by_cond.get('rules') or []
    if not main:
        raise ValueError("rules 조건 결과가 없다 — 실제 시험 조건 판정이 불가능하다")
    rows = []
    for s in sorted(key):
        k = key[s]
        a, means, gap, v = judge_side(main, s, k['answer'], 'best')
        row = {'seq': s, 'id': k['id'], 'axis': k['axis'], 'key': k['answer'], 'agree': a, 'means': means,
               'gap': gap, 'verdict': v, 'picks': [r['items'][s]['best'] for r in main],
               'ambiguous': sum(1 for r in main if r['items'][s].get('ambiguous')),
               'notes': [f"{r['rater']}: {r['items'][s].get('note')}" for r in main if r['items'][s].get('note')]}
        if k['worst']:
            wa, _, wgap, wv = judge_side(main, s, k['worst'], 'worst')
            row.update(worst_agree=wa, worst_gap=wgap, worst_verdict=wv,
                       worst_picks=[r['items'][s].get('worst') for r in main])
            if RANK[wv] > RANK[v]:
                row['verdict'] = wv
        nr = by_cond.get('norules') or []
        if nr:
            na = sum(1 for r in nr if r['items'][s]['best'] == k['answer']) / len(nr)
            row['norules_agree'] = na
            row['rule_dep'] = a - na >= RULE_DEP
        vendors = defaultdict(list)
        for r in main:
            vendors[r['vendor']].append(r['items'][s]['best'] == k['answer'])
        full = {vd: all(xs) for vd, xs in vendors.items()}
        none_ = {vd: not any(xs) for vd, xs in vendors.items()}
        row['vendor_split'] = len(vendors) > 1 and any(full.values()) and any(none_.values())
        row['vendor_agree'] = {vd: sum(xs) / len(xs) for vd, xs in vendors.items()}
        rows.append(row)
    return rows


def render(rows, results):
    main = [r for r in results if r['condition'] == 'rules']
    L = [f"검토자 (rules 조건) {len(main)}명: " + ", ".join(f"{r['rater']}({r['vendor']})" for r in main)]
    nr = [r for r in results if r['condition'] == 'norules']
    if nr:
        L.append(f"검토자 (norules 조건) {len(nr)}명: " + ", ".join(r['rater'] for r in nr))
    L += ["", "| 문항 | 축 | 키 | 검토자 선택 | 일치 | 평균 적절성 1~4 | 키−최고 | 판정 | 규칙 의존 | 회사별 | 모호 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in rows:
        means = " / ".join(f"{m:.1f}" for m in w['means'])
        worst = f" · 최악 {w['worst_agree']:.0%} {w['worst_verdict']}" if 'worst_agree' in w else ''
        dep = ('예 (' + f"{w['norules_agree']:.0%}" + ')') if w.get('rule_dep') else (f"{w['norules_agree']:.0%}" if 'norules_agree' in w else '—')
        vend = ' / '.join(f"{k}{v:.0%}" for k, v in w['vendor_agree'].items()) + (' ⚠' if w['vendor_split'] else '')
        L.append(f"| {w['seq']} | {w['axis']} | {w['key']} | {' '.join(map(str, w['picks']))} | {w['agree']:.0%}{worst} | {means} | "
                 f"{w['gap']:+.1f} | **{w['verdict']}** | {dep} | {vend} | {w['ambiguous'] or ''} |")
    cnt = defaultdict(int)
    for w in rows:
        cnt[w['verdict']] += 1
    L += ["", f"판정: 지지 {cnt['지지']} · 주의 {cnt['주의']} · 논쟁 {cnt['논쟁']} · 규칙 의존 {sum(1 for w in rows if w.get('rule_dep'))}"
          f" · 회사별 불일치 {sum(1 for w in rows if w['vendor_split'])}"]
    notes = [(w['seq'], n) for w in rows if w['verdict'] != '지지' for n in w['notes']]
    if notes:
        L += ["", "지지가 아닌 문항의 검토자 메모:"] + [f"- {s}번 {n}" for s, n in notes]
    return "\n".join(L)


def template():
    key = score.load_key()
    w = csv.writer(sys.stdout)
    w.writerow(['문항', '가장 적절', '가장 부적절', '선택지1 적절성', '선택지2 적절성', '선택지3 적절성', '선택지4 적절성', '확신도', '모호', '메모'])
    for s in sorted(key):
        w.writerow([s, '', '' if key[s]['worst'] else '(해당 없음)', '', '', '', '', '', '', ''])


def main(argv=None):
    ap = argparse.ArgumentParser(description="정답 키 검토 (docs/15-key-review.md)")
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('packet'); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--rules', action='store_true'); g.add_argument('--no-rules', action='store_true')
    sub.add_parser('template')
    p = sub.add_parser('analyze'); p.add_argument('files', nargs='+')
    p.add_argument('--json', metavar='FILE', help='판정 결과를 JSON 으로도 쓴다')
    a = ap.parse_args(argv)
    if a.cmd == 'packet':
        print(packet(a.rules)); return 0
    if a.cmd == 'template':
        template(); return 0
    key = score.load_key()
    results, bad = [], []
    for f in a.files:
        try:
            results.append(read_result(f, key))
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            bad.append(f"{f}: {e}")
    for b in bad:
        print(f"제외: {b}", file=sys.stderr)
    rows = analyze(results, key)
    print(render(rows, results))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
