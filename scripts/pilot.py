#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""파일럿 운영 명령 모음. 절차 전체는 docs/14-pilot-runbook.md.

    python3 scripts/pilot.py status                       # 받은 응답 점검 (중복·빈칸·보류 예정)
    python3 scripts/pilot.py packets                      # 주관식 채점 패킷 → pilot/work/
    python3 scripts/pilot.py import                       # LLM 답변 out-*.txt 가져오기
    python3 scripts/pilot.py sample                       # 인간 재채점 표본(20%) 뽑기 + 빈 CSV
    python3 scripts/pilot.py compare pilot/work/human.csv # 인간 채점 가져와 대조·병합
    python3 scripts/pilot.py reports --org "○○본부"       # 개인·조직 리포트 → pilot/reports/
    python3 scripts/pilot.py purge                        # 삭제일: 지울 파일 목록 (--yes 로 실제 삭제)

기본 폴더는 pilot/responses/(응답), pilot/work/(채점 작업), pilot/reports/(리포트)이고 모두 git 제외다.
"""
import sys, json, math, random, shutil, pathlib, argparse

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
        print("\n배포 전: 개인 리포트는 본인에게만 보낸다. 조직 리포트의 '출구 전략 체크리스트' 칸을 채운다.")
    return rc


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
    p = sub.add_parser('purge', help='응답·작업 파일·리포트 삭제')
    p.add_argument('--yes', action='store_true')
    a = ap.parse_args(argv)
    try:
        return {'status': cmd_status, 'packets': cmd_packets, 'import': cmd_import, 'sample': cmd_sample,
                'compare': cmd_compare, 'reports': cmd_reports, 'purge': cmd_purge}[a.cmd](a)
    except fr_import.ImportError_ as e:
        print("\n".join(e.problems), file=sys.stderr); return 1


if __name__ == '__main__':
    sys.exit(main())
