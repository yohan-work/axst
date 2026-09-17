#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일럿 운영 명령 모음. 절차 전체는 docs/14-pilot-runbook.md.

    python3 scripts/pilot.py status                       # 받은 응답 점검 (중복·빈칸·보류 예정)
    python3 scripts/pilot.py packets                      # 주관식 채점 패킷 → pilot/work/
    python3 scripts/pilot.py import                       # LLM 답변 out-*.txt 가져오기
    python3 scripts/pilot.py sample                       # 인간 재채점 표본(20%) 뽑기 + 빈 CSV
    python3 scripts/pilot.py compare pilot/work/human.csv # 인간 채점 가져와 대조·병합
    python3 scripts/pilot.py reports --org "○○본부"       # 개인·조직 리포트 → pilot/reports/
    python3 scripts/pilot.py gate                         # 관문 B — 본 시행으로 갈지 기준별 판정 (docs/07)
    python3 scripts/pilot.py purge                        # 삭제일: 지울 파일 목록 (--yes 로 실제 삭제)

기본 폴더는 pilot/responses/(응답), pilot/work/(채점 작업), pilot/reports/(리포트)이고 모두 git 제외다.
"""
import io, sys, csv, copy, json, math, random, shutil, pathlib, argparse
from collections import Counter
from fractions import Fraction

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score, fr_import, report  # noqa: E402
from score import ROOT, FR_ITEMS, response_key  # noqa: E402

RESP = ROOT / 'pilot' / 'responses'
WORK = ROOT / 'pilot' / 'work'
REPORTS = ROOT / 'pilot' / 'reports'


def rel(p):
    try:
        return str(pathlib.Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def load_responses(folder):
    """폴더의 *.json 을 읽는다. 같은 응답 코드가 여럿이면 가장 늦게 제출한 것만 쓴다(재제출)."""
    folder = pathlib.Path(folder)
    files = sorted(folder.glob('*.json'))
    kept, notes, bad = {}, [], []
    for f in files:
        try:
            r = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            bad.append(f"{f.name}: JSON 이 아니다 ({e.__class__.__name__}) — 응시자에게 파일을 다시 받는다"); continue
        if r.get('schema') != 'axst-response-1':
            bad.append(f"{f.name}: 응시본 응답 파일이 아니다 (schema={r.get('schema')!r})"); continue
        k = response_key(r)
        if not k or k == '(미기재)':
            bad.append(f"{f.name}: 응답 코드가 없다 — 옛 응시본이다. 파일 이름으로 대신할 수 없으니 응시자를 확인한다"); continue
        r['_file'] = f.name
        if k in kept:
            old = kept[k]
            newer = r if (r.get('submittedAt') or '') >= (old.get('submittedAt') or '') else old
            older = old if newer is r else r
            notes.append(f"{k}: {older['_file']} 와 {newer['_file']} 가 같은 응답 — 늦게 제출한 {newer['_file']} 를 쓴다")
            kept[k] = newer
        else:
            kept[k] = r
    return list(kept.values()), notes, bad


def _clean(rs):
    return [{k: v for k, v in r.items() if k != '_file'} for r in rs]


def cmd_status(a):
    rs, notes, bad = load_responses(a.responses)
    key = score.load_key()
    print(f"응답 폴더: {rel(a.responses)} — 유효 응답 {len(rs)}명")
    if not rs and not bad:
        print("  응답 파일(*.json)이 없다. 받은 파일을 이 폴더에 넣는다."); return 1
    print()
    print(f"{'응답 코드':<10} {'제출':<17} {'소요':>6} {'객관식':>7} {'21번':>7} {'22번':>12}  비고")
    for r in sorted(rs, key=lambda x: x.get('submittedAt') or ''):
        _, _, _, missing = score.score_mc(r, key)
        fr = r.get('free_response') or {}
        f1 = fr.get('FR-01') or {}; f2 = fr.get('FR-02') or {}
        tot = (r.get('durations_sec') or {}).get('total')
        memo = []
        if missing: memo.append(f"객관식 미응답 {len(missing)}")
        if f2.get('text') and not f2.get('persona'): memo.append("22번 페르소나 미선택 → 판정 보류")
        if (r.get('resumes') or 0) > 0: memo.append(f"이어하기 {r['resumes']}회")
        if isinstance(tot, (int, float)) and tot and tot < 15 * 60: memo.append("소요 15분 미만")
        print(f"{response_key(r):<10} {(r.get('submittedAt') or '')[:16].replace('T', ' '):<17} "
              f"{(f'{int(tot)//60}분' if isinstance(tot, (int, float)) else '—'):>6} "
              f"{20 - len(missing):>4}/20 {f1.get('chars', 0):>5}자 {(f2.get('persona') or '—'):>5} {f2.get('chars', 0):>4}자  "
              f"{', '.join(memo)}")
    for n in notes: print(f"  중복: {n}")
    for b in bad: print(f"  제외: {b}")
    if len(rs) < report.MIN_ORG_N:
        print(f"\n조직 리포트는 {report.MIN_ORG_N}명 이상에서만 만든다 — 지금 {len(rs)}명.")
    return 0


def cmd_packets(a):
    rs, notes, bad = load_responses(a.responses)
    for m in notes + bad: print(f"  참고: {m}")
    if not rs:
        print("응답이 없다."); return 1
    work = pathlib.Path(a.work)
    stale = sorted(work.glob('out-*.txt')) + sorted(work.glob('fr-scores*.json'))
    if stale and not a.force:
        print(f"{rel(work)} 에 이전 채점 결과가 있다: {', '.join(p.name for p in stale)}")
        print("패킷을 다시 만들면 응답 번호(R01…)가 바뀔 수 있어 이전 결과와 섞인다. 치우거나 --force 를 붙인다."); return 1
    for p in stale: p.unlink()
    score.build_prompts(_clean(rs), work, calibration=a.calibration)
    print(f"\n다음: {rel(work)}/pass-*.md 5개를 각각 **새 대화**에 붙여넣고, 답변 전체를 out-<패스>.txt 로 저장한 뒤 "
          f"`python3 scripts/pilot.py import`")
    return 0


def cmd_import(a):
    return fr_import.main([str(a.work)])


def cmd_sample(a):
    work = pathlib.Path(a.work)
    idmap = fr_import.load_idmap(work)
    items = [(pid, fid) for pid, v in idmap.items() for fid in v['items']]
    n = max(1, math.ceil(len(items) * a.rate))
    rng = random.Random(a.seed)
    picked = sorted(rng.sample(items, n))
    out = work / 'human.csv'
    fr_import.write_template(work, out)
    lines = out.read_text(encoding='utf-8-sig').splitlines()
    keep = [lines[0]] + [l for l in lines[1:] if tuple(l.split(',')[:2]) in set(picked)]
    out.write_text("\n".join(keep) + "\n", encoding='utf-8-sig')
    print(f"인간 재채점 표본 {n}건 (전체 {len(items)}건의 {a.rate:.0%}, seed={a.seed}):")
    for pid, fid in picked: print(f"  {pid} {fid}")
    print(f"\n빈 채점표: {rel(out)} — pass-*.md 의 해당 답안을 읽고 루브릭대로 채운다. LLM 점수는 보지 않는다.")
    print("다 채우면: python3 scripts/pilot.py compare " + rel(out))
    return 0


def cmd_compare(a):
    work = pathlib.Path(a.work)
    human = work / 'fr-scores.human.json'
    rc = fr_import.main([str(work), '--csv', str(a.csv), '--out', str(human)])
    if rc: return rc
    return fr_import.main([str(work), '--compare', str(human)])


def cmd_reports(a):
    work = pathlib.Path(a.work)
    final, llm = work / 'fr-scores.final.json', work / 'fr-scores.json'
    if final.exists():
        frs = final
    elif llm.exists():
        print("주의: 인간 표본 대조(pilot.py compare)를 거치지 않은 LLM 점수로 리포트를 만든다.")
        frs = llm
    else:
        print("주관식 점수가 없다 — pilot.py import 를 먼저 한다. (주관식 없이 만들면 레벨이 전부 산출 보류가 된다)")
        if not a.allow_unscored: return 1
        frs = None
    rs, notes, bad = load_responses(a.responses)
    for m in notes + bad: print(f"  참고: {m}")
    files = [str(pathlib.Path(a.responses) / r['_file']) for r in rs]
    args = files + ['--out', str(a.out), '--round', a.round]
    if frs: args += ['--fr-scores', str(frs)]
    if a.org: args += ['--org', a.org]
    rc = report.main(args)
    if rc == 0:
        if frs:
            print_persona_penalties(rs, score.load_fr_scores(frs))
        if a.round == '파일럿':
            try:
                fit, added = write_fit_template(pathlib.Path(a.work) / 'fit.csv', [response_key(r) for r in rs])
            except ValueError as e:
                print(f"\n리포트는 만들었지만 회신 칸을 갱신하지 못했다: {e}", file=sys.stderr); return 1
            if added:
                print(f"\n리포트 납득도 회신 칸 {added}개 추가: {rel(fit)} — 회신(1~5)이 오면 채운다. pilot.py gate 가 읽는다.")
        print("\n배포 전: 개인 리포트는 본인에게만 보낸다. 조직 리포트의 '출구 전략 체크리스트' 칸을 채운다.")
    return rc


def persona_penalties(rs, scores):
    """22번 감점을 페르소나별로 센다. {persona: [응답 수, −5 건수, −2 건수]} — 페르소나 미선택·미채점은 뺀다."""
    out = {}
    for r in rs:
        pk = ((r.get('free_response') or {}).get('FR-02') or {}).get('persona')
        pen = ((scores.get(response_key(r)) or {}).get('FR-02') or {}).get('penalty')
        if not pk or not isinstance(pen, int):
            continue
        row = out.setdefault(pk, [0, 0, 0])
        row[0] += 1; row[1] += pen == -5; row[2] += pen == -2
    return out


def print_persona_penalties(rs, scores):
    """조직 리포트는 5건 미만 페르소나를 가린다(docs/05). 파일럿 규모에서는 거의 다 가려지므로
    운영자에게만 터미널로 보여 주고 pilot/item-analysis.md 에 옮기게 한다. 리포트 파일에는 쓰지 않는다."""
    rows = persona_penalties(rs, scores)
    if not rows:
        return
    print("\n운영자 전용 — 22번 페르소나별 감점 (리포트에 싣지 않는다. pilot/item-analysis.md 에 옮긴다)")
    print(f"  {'페르소나':<6} {'응답':>4} {'−5':>4} {'−2':>4}")
    for pk in ['HR', 'SALES', 'FIN', 'DEV', 'STAFF', 'MFG']:
        if pk in rows:
            n, f5, f2 = rows[pk]
            print(f"  {pk:<6} {n:>4} {f5:>4} {f2:>4}")


# ---------- 관문 B (docs/07-validity-plan.md "관문 B") ----------
GATE_MIN_N = 10
TIME_LIMIT_SEC = 35 * 60
PASS, FAIL, HOLD = '통과', '미달', '판정 불가'


def group_weights(pts, g):
    """상위·하위 g 자리에 각 응답이 차지하는 몫. 경계에 걸린 동점자는 남은 자리를 똑같이 나눠 갖는다.
    그러지 않으면 누가 그룹에 드는지가 파일 이름 순서로 정해져 d 가 우연히 음수가 된다."""
    # 몫은 분수로 계산한다. 부동소수점이면 참값 d=0 이 -1e-16 이 되어 'd<0' 으로 걸린다
    def side(order):
        w, left, i = [Fraction(0)] * len(pts), Fraction(g), 0
        while left > 0 and i < len(order):
            tie = [j for j in order[i:] if pts[j] == pts[order[i]]]
            share = min(Fraction(1), left / len(tie))
            for j in tie: w[j] = share
            left -= share * len(tie); i += len(tie)
        return w
    asc = sorted(range(len(pts)), key=lambda j: pts[j])
    return side(asc[::-1]), side(asc)


def item_stats(evs, key):
    """문항별 p(최선 정답률)·p_worst·d. d 는 객관식 득점 상위 27% − 하위 27% 의 정답률(최소 1명씩)."""
    n = len(evs)
    g = max(1, math.ceil(n * 0.27))
    high, low = group_weights([e['pts'] for e in evs], g)
    out = {}
    for seq, k in key.items():
        best = [e['picks'][seq]['best'] == k['answer'] for e in evs]
        d = (sum(h * b for h, b in zip(high, best)) - sum(l * b for l, b in zip(low, best))) / g
        st = {'p': sum(best) / n, 'd': float(d)}
        if k['worst']:
            st['p_worst'] = sum(1 for e in evs if e['picks'][seq]['worst'] == k['worst']) / n
        out[seq] = st
    return out


def broken_items(stats):
    """관문에서 세는 '명백히 망가진' 문항. d < 0.20 은 n=10~15 에서 흔들리므로 세지 않고 참고로만 낸다."""
    bad = {}
    for seq, st in stats.items():
        why = []
        for name in ('p', 'p_worst'):
            if name in st and st[name] < 0.25: why.append(f"{name} {st[name]:.0%} < 25%")
            if name in st and st[name] > 0.90: why.append(f"{name} {st[name]:.0%} > 90%")
        if st['d'] < 0: why.append(f"d {st['d']:+.0%} < 0")
        if why: bad[seq] = why
    return bad


def read_fit_rows(path):
    """fit.csv 행. 운영자가 한국어 윈도우 엑셀로 저장하면 CP949 가 되므로 UTF-8 다음에 CP949 로 읽는다."""
    raw = pathlib.Path(path).read_bytes()
    for enc in ('utf-8-sig', 'cp949'):
        try:
            text = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{pathlib.Path(path).name}: 글자 인코딩을 읽지 못했다 — 엑셀에서 'CSV UTF-8' 형식으로 다시 저장한다")
    return list(csv.DictReader(io.StringIO(text, newline='')))


def write_fit_template(path, codes):
    """회신 칸을 만든다. 이미 있으면 적힌 회신은 두고 빠진 응답 코드만 덧붙인다(늦게 낸 응답)."""
    path = pathlib.Path(path)
    rows = []
    if path.exists():
        rows = read_fit_rows(path)
    have = {r.get('응답코드', '') for r in rows}
    new = [{'응답코드': c, '납득': ''} for c in sorted(set(codes) - have)]
    if new or not path.exists():
        # 운영자가 엑셀에서 붙인 열(메모·회신일)은 그대로 둔다
        fields = ['응답코드', '납득'] + [k for k in (rows[0].keys() if rows else []) if k not in ('응답코드', '납득') and k]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', restval='')
            w.writeheader(); w.writerows(rows + new)
    return path, len(new)


def load_fit(path):
    """리포트 납득도 회신. 응답코드,납득(1~5). 빈 칸은 미회신."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    out = {}
    for i, row in enumerate(read_fit_rows(p), 2):
        v = (row.get('납득') or '').strip()
        if not v: continue
        if v not in {'1', '2', '3', '4', '5'}:
            raise ValueError(f"{p.name} {i}행: 납득={v!r} — 1~5 정수여야 한다")
        out[(row.get('응답코드') or '').strip()] = int(v)
    return out


def gate(rs, key, llm=None, human=None, fit=None, final=None):
    """기준별 (이름, 값 문자열, 판정, 근거). docs/07 '관문 B' 표와 1:1.
    레벨은 final(인간 대조 병합본)이 있으면 그것으로, 없으면 llm 점수로 낸다. rs 는 고치지 않는다."""
    rs = copy.deepcopy(rs)
    n = len(rs)
    rows = []
    if n < GATE_MIN_N:
        return [('인원', f"{n}명", HOLD, f"파일럿 최소 {GATE_MIN_N}명 미만 — 문항 통계를 낼 수 없다")]
    # 1 소요 시간
    tots = [(r.get('durations_sec') or {}).get('total') for r in rs]
    tots = [t for t in tots if isinstance(t, (int, float)) and t > 0]
    if len(tots) < n / 2:
        rows.append(('소요 시간', f"기록 {len(tots)}/{n}", HOLD, "온라인 응시본 기록이 절반 미만 — 지필이면 수기 기록으로 판단"))
    else:
        share = sum(t <= TIME_LIMIT_SEC for t in tots) / len(tots)
        rows.append(('소요 시간', f"35분 이내 {share:.0%} ({len(tots)}명 기록)", PASS if share >= 0.80 else FAIL, "기준 ≥ 80%"))
    # 2 주관식 미작성률
    blank = sum(1 for r in rs for fid, _ in FR_ITEMS if not (((r.get('free_response') or {}).get(fid) or {}).get('text') or '').strip())
    rate = blank / (2 * n)
    rows.append(('주관식 미작성률', f"{rate:.0%} ({blank}/{2 * n})", PASS if rate < 0.20 else FAIL, "기준 < 20%"))
    # 3 망가진 문항
    evs = [report.evaluate(r, key) for r in rs]
    bad = broken_items(item_stats(evs, key))
    rows.append(('보류 후보 문항', f"{len(bad)}개" + (f" ({', '.join(f'{s}번' for s in sorted(bad))})" if bad else ''),
                 PASS if len(bad) <= 4 else FAIL, "기준 ≤ 4 (예비 4문항으로 교체 가능). p<25%·p>90%·d<0"))
    # 4 사람–LLM 불일치
    if not llm or not human:
        rows.append(('사람–LLM 불일치', '—', HOLD, "fr-scores.json 과 fr-scores.human.json 이 필요하다 (pilot.py compare)"))
    else:
        _, diffs = fr_import.compare(llm, human)
        missing = [d for d in diffs if d[2] == '-']          # 사람은 채점했는데 LLM 점수가 없다 — 불일치가 아니다
        real = [d for d in diffs if d[2] != '-']
        sampled = sum(len(v) for v in human.values())
        if missing or not sampled:
            rows.append(('사람–LLM 불일치', f"LLM 점수 없음 {len(missing)}건 / 표본 {sampled}답안", HOLD,
                         "표본 답안의 LLM 점수가 빠졌다 — pilot.py import 를 다시 확인한다"))
        else:
            share = len(real) / sampled
            rows.append(('사람–LLM 불일치', f"{share:.0%} ({len(real)}/{sampled}답안)", PASS if share < 0.20 else FAIL,
                         "기준 < 20% — 어느 차원이든 2점 이상 또는 감점 판정 차이"))
    # 5 결과 분산
    if final or llm:
        for r in rs: score.attach_fr_scores(r, final or llm)
        evs = [report.evaluate(r, key) for r in rs]
    lv = Counter(e['level'][0] for e in evs if e['level'])
    scored = sum(lv.values())
    if scored < n / 2:
        rows.append(('결과 분산', f"총점 산출 {scored}/{n}", HOLD, "주관식 점수를 가져온 뒤 판단 (pilot.py import)"))
    else:
        rows.append(('결과 분산', ' · '.join(f"{k} {v}명" for k, v in sorted(lv.items())), PASS if len(lv) >= 2 else FAIL,
                     "기준 레벨 2종 이상 — 한 레벨에 몰리면 반을 나눌 근거가 없다"))
    # 6 리포트 납득도
    if fit is None:
        rows.append(('리포트 납득도', '—', HOLD, "리포트 전달 뒤 회신을 fit.csv 에 적는다"))
    else:
        got = [v for k, v in fit.items() if k in {response_key(r) for r in rs}]
        if len(got) < n / 2:
            rows.append(('리포트 납득도', f"회신 {len(got)}/{n}", HOLD, "회신이 절반 미만"))
        else:
            share = sum(v >= 4 for v in got) / len(got)
            rows.append(('리포트 납득도', f"4점 이상 {share:.0%} ({len(got)}명 회신)", PASS if share > 0.50 else FAIL, "기준 > 50%"))
    return rows


def survey_summary(rs):
    """참고 — 관문 판정에 쓰지 않는다. 응시 후 설문(점수 미반영)."""
    sv = [r.get('survey') or {} for r in rs]
    amb = Counter(q for s in sv for q in (s.get('ambiguous') or []))
    real = [s['realism'] for s in sv if isinstance(s.get('realism'), int)]
    fitc = Counter(s['persona_fit'] for s in sv if s.get('persona_fit'))
    roles = sorted({(s.get('role') or '').strip() for s in sv} - {''})
    return {'answered': sum(1 for s in sv if any(s.get(k) for k in ('ambiguous', 'realism', 'persona_fit'))),
            'ambiguous': amb.most_common(), 'realism': real, 'persona_fit': dict(fitc), 'roles': roles}


def cmd_gate(a):
    rs, notes, bad = load_responses(a.responses)
    for m in notes + bad: print(f"  참고: {m}")
    work = pathlib.Path(a.work)
    load = lambda p: score.load_fr_scores(p) if p.exists() else None
    llm, human, final = load(work / 'fr-scores.json'), load(work / 'fr-scores.human.json'), load(work / 'fr-scores.final.json')
    try:
        fit = load_fit(work / 'fit.csv')
    except ValueError as e:
        print(e, file=sys.stderr); return 1
    rows = gate(rs, score.load_key(), llm, human, fit, final)
    print(f"관문 B — 본 시행으로 갈지 (응답 {len(rs)}명, 기준: docs/07-validity-plan.md)\n")
    w = max(len(r[0]) for r in rows)
    for name, val, verdict, why in rows:
        print(f"  [{verdict}] {name:<{w}}  {val}  — {why}")
    fails = [r[0] for r in rows if r[2] == FAIL]
    holds = [r[0] for r in rows if r[2] == HOLD]
    print()
    if fails:
        print(f"결론: 관문 B 미달 — {', '.join(fails)}. 본 시행 제안 전에 원인을 기록하고 조치한다.")
    elif holds:
        print(f"결론: 판정 보류 — {', '.join(holds)}. 채운 뒤 다시 실행한다.")
    else:
        print("결론: 관문 B 통과 — 본 시행 제안으로 갈 수 있다.")
    if len(rs) >= GATE_MIN_N:
        evs = [report.evaluate(r, score.load_key()) for r in rs]
        st = item_stats(evs, score.load_key())
        weak = sorted(s for s, v in st.items() if 0 <= v['d'] < 0.20)
        sv = survey_summary(rs)
        print("\n참고 (판정에 쓰지 않음)")
        print(f"  d 0~20% 문항: {', '.join(f'{s}번' for s in weak) or '없음'} — n이 작아 흔들린다. 설문 지목과 겹치는지 본다")
        print(f"  응시 후 설문 응답 {sv['answered']}/{len(rs)}명")
        if sv['ambiguous']:
            print("  헷갈린 문항 지목: " + ', '.join(f"{q}번 {c}명" for q, c in sv['ambiguous'][:6]))
        if sv['realism']:
            print(f"  업무 현실성 평균 {sum(sv['realism']) / len(sv['realism']):.1f} / 5 ({len(sv['realism'])}명)")
        if sv['persona_fit']:
            print("  22번 페르소나 적합: " + ', '.join(f"{k} {v}명" for k, v in sv['persona_fit'].items())
                  + (f" — 맞지 않았던 직무: {', '.join(sv['roles'])}" if sv['roles'] else ''))
    return 0 if not fails and not holds else 1


def cmd_purge(a):
    targets = [p for p in sorted(pathlib.Path(a.responses).glob('*.json'))]
    targets += [p for p in (pathlib.Path(a.work), pathlib.Path(a.out)) if p.exists()]
    if not targets:
        print("지울 것이 없다."); return 0
    print("삭제 대상 (docs/08 응답 데이터 취급 — 조직 리포트는 따로 보관했는지 먼저 확인한다):")
    for p in targets: print(f"  {rel(p)}{'/' if p.is_dir() else ''}")
    if not a.yes:
        print("\n실제로 지우려면 --yes 를 붙인다."); return 0
    for p in targets:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    print("삭제했다.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="파일럿 운영 명령 (docs/14-pilot-runbook.md)")
    ap.add_argument('--responses', default=str(RESP), help='응답 폴더 (기본 pilot/responses)')
    ap.add_argument('--work', default=str(WORK), help='채점 작업 폴더 (기본 pilot/work)')
    ap.add_argument('--out', default=str(REPORTS), help='리포트 폴더 (기본 pilot/reports)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='받은 응답 점검')
    p = sub.add_parser('packets', help='주관식 채점 패킷 생성')
    p.add_argument('--calibration', action='store_true', help='판단형 패스에 앵커를 싣지 않는다(캘리브레이션 회차)')
    p.add_argument('--force', action='store_true', help='이전 채점 결과를 지우고 다시 만든다')
    sub.add_parser('import', help='LLM 답변 가져오기')
    p = sub.add_parser('sample', help='인간 재채점 표본과 빈 CSV')
    p.add_argument('--rate', type=float, default=0.2)
    p.add_argument('--seed', type=int, default=20260917, help='같은 seed 면 같은 표본')
    p = sub.add_parser('compare', help='인간 채점 CSV 가져와 대조·병합')
    p.add_argument('csv')
    p = sub.add_parser('reports', help='개인·조직 리포트 생성')
    p.add_argument('--org', default='')
    p.add_argument('--round', default='파일럿', choices=['파일럿', '진단'])
    p.add_argument('--allow-unscored', action='store_true', help='주관식 점수 없이도 만든다')
    sub.add_parser('gate', help='관문 B — 본 시행으로 갈지 기준별 판정')
    p = sub.add_parser('purge', help='응답·작업 파일·리포트 삭제')
    p.add_argument('--yes', action='store_true')
    a = ap.parse_args(argv)
    try:
        return {'status': cmd_status, 'packets': cmd_packets, 'import': cmd_import, 'sample': cmd_sample,
                'compare': cmd_compare, 'reports': cmd_reports, 'gate': cmd_gate, 'purge': cmd_purge}[a.cmd](a)
    except fr_import.ImportError_ as e:
        print("\n".join(e.problems), file=sys.stderr); return 1


if __name__ == '__main__':
    sys.exit(main())
