#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주관식 채점 결과 가져오기. 응답 JSON을 손으로 고치지 않고 점수를 붙인다.

    # 1) 패킷 생성
    python3 scripts/score.py responses/*.json --prompts pilot/work/
    # 2) pass-D1.md … pass-penalty.md 를 각각 새 대화에 붙여넣고, LLM 답변 전체를
    #    pilot/work/out-D1.txt … out-penalty.txt 로 저장
    # 3) 가져오기 — 검증을 통과해야 fr-scores.json 이 생긴다
    python3 scripts/fr_import.py pilot/work/
    # 4) 총점·레벨
    python3 scripts/score.py responses/*.json --fr-scores pilot/work/fr-scores.json

인간 채점(20% 표본 이중 채점)은 CSV로 한다.

    python3 scripts/fr_import.py pilot/work/ --template human.csv   # 빈 채점표(엑셀에서 열림)
    python3 scripts/fr_import.py pilot/work/ --csv human.csv --out pilot/work/fr-scores.human.json
    python3 scripts/fr_import.py pilot/work/ --compare pilot/work/fr-scores.human.json

**검증에 실패하면 파일을 쓰지 않는다.** 빠진 줄·범위를 벗어난 점수를 조용히 0으로 채우면
그 응시자는 틀린 레벨을 받는다.
"""
import re, csv, sys, json, pathlib, argparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from score import FR_DIMS, FR_PENALTIES, HELD, MACHINE_OPEN, MACHINE_CLOSE, fr_total  # noqa: E402

PASSES = FR_DIMS + ('penalty',)
CAPS = ('none', '2', '3')
SCHEMA = 'axst-fr-scores-1'


class ImportError_(Exception):
    """사람이 읽을 오류 목록을 담는다."""
    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = problems


def _fields(parts, where, problems):
    out = {}
    for p in parts:
        if '=' not in p:
            problems.append(f"{where}: '{p}' 는 key=value 형식이 아니다")
            continue
        k, v = p.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def parse_block(text, code, src):
    """LLM 답변 전문에서 기계 판독 블록 하나를 읽는다. {(pid, fid): {...}} 와 문제 목록."""
    problems = []
    pat = re.compile(rf'^{re.escape(MACHINE_OPEN)}\s+pass=(\S+)\s*$(.*?)^{re.escape(MACHINE_CLOSE)}\s*$', re.M | re.S)
    blocks = [(m.group(1), m.group(2), text[:m.start()].count('\n') + 2) for m in pat.finditer(text)]
    if not blocks:
        return {}, [f"{src}: `{MACHINE_OPEN} pass={code}` … `{MACHINE_CLOSE}` 블록이 없다 — LLM에게 "
                    "\"맨 마지막의 기계 판독 블록을 출력해\"라고 다시 요청한다"]
    if len(blocks) > 1:
        return {}, [f"{src}: 기계 판독 블록이 {len(blocks)}개다 — 하나만 남기고 지운다"]
    got_code, body, line0 = blocks[0]
    if got_code != code:
        return {}, [f"{src}: 블록이 pass={got_code} 인데 파일은 {code} 패스다 — 파일을 바꿔 저장했는지 확인한다"]

    rows = {}
    for i, raw in enumerate(body.strip('\n').split('\n')):
        line = raw.strip().strip('`')
        if not line:
            continue
        where = f"{src}:{line0 + i}"
        parts = [x.strip() for x in line.split('|', 5 if code != 'penalty' else 3)]
        if len(parts) < 3 or not re.fullmatch(r'R\d{2,}', parts[0]) or parts[1] not in ('FR-01', 'FR-02'):
            problems.append(f"{where}: 줄 형식이 틀렸다 → {line!r}")
            continue
        pid, fid = parts[0], parts[1]
        f = _fields(parts[2:], where, problems)
        if (pid, fid) in rows:
            problems.append(f"{where}: {pid} {fid} 가 두 번 나온다")
            continue
        if code == 'penalty':
            try:
                pen = int(f.get('penalty', 'x'))
            except ValueError:
                pen = None
            if pen not in FR_PENALTIES:
                problems.append(f"{where}: penalty={f.get('penalty')!r} — 0, -2, -5 중 하나여야 한다")
                continue
            rows[(pid, fid)] = {'penalty': pen, 'rule': f.get('rule', '')}
            continue
        base, cap, final = f.get('base'), f.get('cap', 'none'), f.get('final')
        if HELD in (base, final):
            if not (base == final == HELD):
                problems.append(f"{where}: 보류는 base 와 final 이 둘 다 {HELD} 여야 한다")
                continue
            rows[(pid, fid)] = {'score': HELD, 'base': HELD, 'cap': 'none', 'comment': f.get('comment', '')}
            continue
        try:
            b, fin = int(base), int(final)
        except (TypeError, ValueError):
            problems.append(f"{where}: base={base!r} final={final!r} — 정수가 아니다")
            continue
        if not (0 <= b <= 5 and 0 <= fin <= 5):
            problems.append(f"{where}: base={b} final={fin} — 0~5 범위를 벗어났다")
            continue
        if cap not in CAPS:
            problems.append(f"{where}: cap={cap!r} — none, 2, 3 중 하나여야 한다")
            continue
        expect = b if cap == 'none' else min(b, int(cap))
        if fin != expect:
            problems.append(f"{where}: final={fin} 인데 base={b}, cap={cap} 이면 {expect} 여야 한다")
            continue
        rows[(pid, fid)] = {'score': fin, 'base': b, 'cap': cap, 'comment': f.get('comment', '')}
    return rows, problems


def load_idmap(workdir):
    p = pathlib.Path(workdir) / 'idmap.json'
    if not p.exists():
        raise ImportError_([f"{p} 가 없다 — 먼저 score.py --prompts {workdir} 로 패킷을 만든다"])
    return json.loads(p.read_text(encoding='utf-8'))


def assemble(idmap, per_pass, problems):
    """패스별 결과를 응답 키 → 문항 → 점수 로 묶는다. 빠진 줄과 모르는 번호를 잡는다."""
    expected = {(pid, fid) for pid, v in idmap.items() for fid in v['items']}
    for code, rows in per_pass.items():
        for k in sorted(set(rows) - expected):
            problems.append(f"out-{code}.txt: {k[0]} {k[1]} 는 패킷에 없는 답안이다")
        for k in sorted(expected - set(rows)):
            problems.append(f"out-{code}.txt: {k[0]} {k[1]} 줄이 빠졌다")
    if problems:
        return None
    scores = {}
    for pid, v in idmap.items():
        entry = {}
        for fid in v['items']:
            e = {d: per_pass[d][(pid, fid)]['score'] for d in FR_DIMS}
            e['penalty'] = per_pass['penalty'][(pid, fid)]['penalty']
            e['rule'] = per_pass['penalty'][(pid, fid)]['rule']
            e['base'] = {d: per_pass[d][(pid, fid)]['base'] for d in FR_DIMS}
            e['cap'] = {d: per_pass[d][(pid, fid)]['cap'] for d in FR_DIMS}
            e['comment'] = {d: per_pass[d][(pid, fid)]['comment'] for d in FR_DIMS}
            vals = [e[d] for d in FR_DIMS]
            e['held'] = fid in v.get('held', [])
            if e['held'] and any(x != HELD for x in vals):
                problems.append(f"{pid} {fid}: 패킷에서 판정 보류(페르소나 미선택)로 표시했는데 점수가 매겨졌다 — 네 차원 모두 {HELD}여야 한다")
                continue
            if not e['held'] and HELD in vals:
                problems.append(f"{pid} {fid}: 판정 보류 대상이 아닌데 {HELD}로 채점됐다 — 해당 패스를 다시 돌린다")
                continue
            total = fr_total(e)
            if total is not None:
                e['total'] = total
            entry[fid] = e
        scores[v['key']] = entry
    return None if problems else scores


def import_llm(workdir):
    workdir = pathlib.Path(workdir)
    idmap = load_idmap(workdir)
    problems, per_pass = [], {}
    for code in PASSES:
        src = workdir / f'out-{code}.txt'
        if not src.exists():
            problems.append(f"{src} 가 없다 — pass-{code}.md 에 대한 LLM 답변을 이 이름으로 저장한다")
            continue
        rows, pr = parse_block(src.read_text(encoding='utf-8'), code, src.name)
        problems += pr
        per_pass[code] = rows
    if problems:
        raise ImportError_(problems)
    scores = assemble(idmap, per_pass, problems)
    if scores is None:
        raise ImportError_(problems)
    return scores


# ---------- 인간 채점 CSV ----------
CSV_COLS = ['응답', '문항', 'D1', 'D2', 'D3', 'D4', '감점', '감점 규칙',
            'D1 코멘트', 'D2 코멘트', 'D3 코멘트', 'D4 코멘트']

def write_template(workdir, out):
    idmap = load_idmap(workdir)
    with open(out, 'w', encoding='utf-8-sig', newline='') as fh:   # BOM: 엑셀이 한글을 깨뜨리지 않는다
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for pid, v in idmap.items():
            for fid in v['items']:
                w.writerow([pid, fid] + [''] * (len(CSV_COLS) - 2))


def import_csv(workdir, path):
    idmap = load_idmap(workdir)
    problems, per_pass = [], {c: {} for c in PASSES}
    with open(path, encoding='utf-8-sig', newline='') as fh:
        rd = csv.DictReader(fh)
        missing = [c for c in CSV_COLS[:8] if c not in (rd.fieldnames or [])]
        if missing:
            raise ImportError_([f"{path}: 열이 없다 — {', '.join(missing)} (템플릿을 다시 만든다)"])
        for n, row in enumerate(rd, 2):
            where = f"{path}:{n}"
            pid, fid = (row['응답'] or '').strip(), (row['문항'] or '').strip()
            if not any((row.get(c) or '').strip() for c in CSV_COLS[2:7]):
                continue   # 표본에 들지 않아 비워 둔 줄
            key = (pid, fid)
            for d in FR_DIMS:
                v = (row[d] or '').strip()
                if v == HELD:
                    per_pass[d][key] = {'score': HELD, 'base': HELD, 'cap': 'none', 'comment': row.get(f'{d} 코멘트', '')}
                    continue
                try:
                    s = int(v)
                    if not 0 <= s <= 5: raise ValueError
                except ValueError:
                    problems.append(f"{where}: {d}={v!r} — 0~5 정수여야 한다"); continue
                per_pass[d][key] = {'score': s, 'base': s, 'cap': 'none', 'comment': (row.get(f'{d} 코멘트') or '').strip()}
            try:
                pen = int((row['감점'] or '0').strip())
                if pen not in FR_PENALTIES: raise ValueError
            except ValueError:
                problems.append(f"{where}: 감점={row['감점']!r} — 0, -2, -5 중 하나여야 한다"); continue
            per_pass['penalty'][key] = {'penalty': pen, 'rule': (row['감점 규칙'] or '').strip()}
    if problems:
        raise ImportError_(problems)
    # 인간 채점은 표본만 한다: 채운 줄만 대상으로 묶는다
    sampled = {k for k in per_pass['penalty']}
    if not sampled:
        raise ImportError_([f"{path}: 채운 줄이 없다"])
    sub = {}
    for pid, v in idmap.items():
        items = [f for f in v['items'] if (pid, f) in sampled]
        if items:
            sub[pid] = dict(v, items=items, held=[h for h in v.get('held', []) if h in items])
    for k in sampled:
        if k[0] not in idmap or k[1] not in idmap[k[0]]['items']:
            problems.append(f"{path}: {k[0]} {k[1]} 는 패킷에 없는 답안이다")
    scores = assemble(sub, per_pass, problems)
    if scores is None:
        raise ImportError_(problems)
    return scores


def compare(llm, human):
    """차원별 2점 이상 불일치는 인간 판정을 채택한다(rubrics/llm-scorer-prompt.md 4단계)."""
    merged = json.loads(json.dumps(llm))
    report = []
    for key, items in human.items():
        for fid, h in items.items():
            l = (llm.get(key) or {}).get(fid)
            if l is None:
                report.append((key, fid, '-', 'LLM 점수 없음')); continue
            gaps = [d for d in FR_DIMS if isinstance(h[d], int) and isinstance(l[d], int) and abs(h[d] - l[d]) >= 2]
            if h['penalty'] != l['penalty']:
                gaps.append('감점')
            if gaps:
                merged[key][fid] = dict(h, adopted='human')
                report.append((key, fid, ','.join(gaps),
                               ' '.join(f"{d} LLM {l[d]}→인간 {h[d]}" for d in FR_DIMS if d in gaps)
                               + (f" 감점 LLM {l['penalty']}→인간 {h['penalty']}" if '감점' in gaps else '')))
    return merged, report


def write_scores(scores, out, source):
    payload = {'schema': SCHEMA, 'source': source, 'scores': scores}
    pathlib.Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def main(argv=None):
    ap = argparse.ArgumentParser(description="주관식 채점 결과 가져오기 (LLM 답변 또는 인간 채점 CSV)")
    ap.add_argument('workdir', help='score.py --prompts 로 패킷을 만든 폴더 (idmap.json 이 있는 곳)')
    ap.add_argument('--out', help='결과 파일 (기본: WORKDIR/fr-scores.json)')
    ap.add_argument('--template', metavar='CSV', help='인간 채점용 빈 CSV 를 만든다')
    ap.add_argument('--csv', metavar='CSV', help='인간 채점 CSV 를 가져온다')
    ap.add_argument('--compare', metavar='HUMAN_JSON', help='WORKDIR/fr-scores.json 과 인간 채점 결과를 대조해 병합한다')
    a = ap.parse_args(argv)
    work = pathlib.Path(a.workdir)
    try:
        if a.template:
            write_template(work, a.template)
            print(f"빈 채점표: {a.template}  — 표본으로 뽑은 답안의 줄만 채운다. 나머지 줄은 비워 둔다.")
            return 0
        if a.compare:
            llm = json.loads((work / 'fr-scores.json').read_text(encoding='utf-8'))['scores']
            human = json.loads(pathlib.Path(a.compare).read_text(encoding='utf-8'))['scores']
            merged, report = compare(llm, human)
            n = sum(len(v) for v in human.values())
            print(f"인간 표본 {n}건 대조 — 2점 이상 불일치 {len(report)}건")
            for key, fid, gaps, detail in report:
                print(f"  {key} {fid}: {detail}  → 인간 판정 채택. 앵커 추가 후보")
            out = a.out or work / 'fr-scores.final.json'
            write_scores(merged, out, 'llm+human')
            print(f"병합 결과: {out}")
            return 0
        if a.csv:
            scores = import_csv(work, a.csv)
            out = a.out or work / 'fr-scores.human.json'
            write_scores(scores, out, 'human')
        else:
            scores = import_llm(work)
            out = a.out or work / 'fr-scores.json'
            write_scores(scores, out, 'llm')
    except ImportError_ as e:
        print(f"가져오기 실패 — 문제 {len(e.problems)}건. 파일을 쓰지 않았다.", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    held = sum(1 for v in scores.values() for e in v.values() if e.get('held'))
    n = sum(len(v) for v in scores.values())
    print(f"가져왔다: 응답 {len(scores)}명 · 답안 {n}건" + (f" (판정 보류 {held}건)" if held else "") + f" → {out}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
