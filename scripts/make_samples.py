#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제안용 샘플 리포트 생성기. 합성 응답 12명 -> docs/samples/*.sample.html

    python3 scripts/make_samples.py

**실제 사람의 응답이 아니다.** 정답 키에서 결정적으로 만든 가상의 응답이며, 조직에 파일럿을
제안할 때 "이런 리포트가 나온다"를 보여주는 용도다. 같은 입력이면 같은 파일이 나와야 하므로
CI가 재생성 결과와 커밋본을 대조한다.
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import report  # noqa: E402
from score import ROOT, load_key  # noqa: E402

OUT = ROOT / 'docs' / 'samples'

# (응답 코드, 틀리는 문항 수, 주관식 차원 점수 [FR-01 D1..D4, FR-02 D1..D4], FR-02 페르소나, FR-02 감점, SR-02 서술)
PROFILES = [
    ('SMPL01', 2,  [4, 4, 4, 4, 4, 5, 4, 4], 'SALES', 0,  '주간 실적 취합 메일'),
    ('SMPL02', 4,  [4, 3, 4, 3, 3, 4, 4, 3], 'HR',    0,  '면접 일정 조율표 수작업'),
    ('SMPL03', 5,  [3, 3, 4, 3, 3, 3, 4, 3], 'FIN',   0,  ''),
    ('SMPL04', 6,  [3, 3, 3, 2, 3, 3, 3, 3], 'DEV',   0,  '장애 보고서 초안 작성'),
    ('SMPL05', 7,  [3, 2, 3, 2, 3, 3, 3, 2], 'STAFF', -2, ''),
    ('SMPL06', 8,  [2, 3, 3, 2, 2, 3, 3, 2], 'SALES', 0,  '고객 문의 1차 분류'),
    ('SMPL07', 9,  [2, 2, 3, 2, 2, 2, 3, 2], 'HR',    0,  ''),
    ('SMPL08', 10, [2, 2, 2, 2, 2, 3, 2, 2], 'MFG',   0,  '작업일보 요약'),
    ('SMPL09', 11, [2, 2, 2, 1, 2, 2, 2, 1], 'FIN',   -5, ''),
    ('SMPL10', 12, [2, 1, 2, 1, 2, 2, 2, 1], 'DEV',   0,  '회의록 정리'),
    ('SMPL11', 13, [1, 1, 2, 1, 1, 2, 1, 1], 'STAFF', 0,  ''),
    ('SMPL12', 15, [1, 1, 1, 1, 1, 1, 2, 1], 'SALES', -5, ''),
]

COMMENTS = {
    'D1': ('최종 판단을 누가 쥐는지 분명하게 적었습니다', '맡기는 범위는 있지만 되돌릴 수 없는 판단의 경계가 빠져 있습니다'),
    'D2': ('수신자와 산출물 형식이 지시에 들어 있습니다', '품질 기준을 형용사로만 적어 AI가 받을 수 있는 조건이 부족합니다'),
    'D3': ('무엇을 먼저 확인할지 순서가 있습니다', '확인할 항목은 있지만 결론을 바꾸는 항목이 먼저 오지 않습니다'),
    'D4': ('없어지는 단계와 그 이유를 짚었습니다', '빨라지는 단계는 있지만 없어지는 단계가 보이지 않습니다'),
}


def synth(key):
    seqs = sorted(key)
    out = []
    for i, (rid, n_wrong, dims, persona, pen, sr2) in enumerate(PROFILES):
        # 사람마다 다른 문항을 틀리게 한다(결정적). 겉보기 HITL(1번 3)·덧붙이기(5번 1) 패턴이 섞이도록 고른다
        order = sorted(seqs, key=lambda s: ((s * 7 + i * 5) % 20, s))
        wrong = set(order[:n_wrong])
        mc = {}
        for s in seqs:
            k = key[s]
            if s in wrong:
                best = {1: 3, 5: 1, 9: 1, 13: 3}.get(s) or (k['answer'] % 4) + 1
                if best == k['answer']:
                    best = (best % 4) + 1
            else:
                best = k['answer']
            a = {'best': best}
            if k['worst']:
                a['worst'] = k['worst']
            mc[str(s)] = a
        fr_scores = {}
        for j, fid in enumerate(('FR-01', 'FR-02')):
            d = dims[j * 4:(j + 1) * 4]
            e = {f'D{x + 1}': d[x] for x in range(4)}
            e['penalty'] = pen if fid == 'FR-02' else 0
            e['rule'] = '민감 데이터 외부 투입' if e['penalty'] == -5 else ('승인 절차 미언급' if e['penalty'] == -2 else '없음')
            e['comment'] = {k2: COMMENTS[k2][0 if e[k2] >= 4 else 1] for k2 in ('D1', 'D2', 'D3', 'D4')}
            e['cap'] = {k2: 'none' for k2 in ('D1', 'D2', 'D3', 'D4')}
            e['total'] = max(0, sum(d) + e['penalty'])
            fr_scores[fid] = e
        out.append({
            'form': 'A', 'schema': 'axst-response-1', 'respondent': '(미기재)', 'rid': rid,
            'startedAt': f'2026-10-{12 + i % 3:02d}T01:00:00.000Z', 'submittedAt': f'2026-10-{12 + i % 3:02d}T01:36:00.000Z',
            'selfreport': {'SR-01': {'choice': ['3~4개', '1~2개', '0개'][i % 3]},
                           'SR-02': {'choice': '있다' if sr2 else '없다', 'text': sr2},
                           'SR-03': {'choice': ['1명', '없다', '없다'][i % 3]}},
            'mc': mc,
            'free_response': {'FR-01': {'persona': None, 'text': '(합성 답안)', 'chars': 420},
                              'FR-02': {'persona': persona, 'text': '(합성 답안)', 'chars': 410}},
            'fr_scores': fr_scores,
        })
    return out


def build():
    """{파일 이름: HTML}. 쓰지 않고 돌려준다(테스트·CI 대조용)."""
    key, tpl, rx = load_key(), report.load_template_text(), report.load_prescriptions()
    responses = synth(key)
    evs = [report.evaluate(r, key) for r in responses]
    pick = next(e for e in evs if e['level'] and e['level'][2])   # 경계 사례를 샘플로 보여준다
    ind = report.individual_html(pick, key, tpl, rx)
    org = report.org_html(evs, key, tpl, rx, org='샘플 조직 (합성 데이터)')
    report.forbidden_check(ind, 'individual', tpl)
    report.forbidden_check(org, 'org', tpl, secret_keys=[r['rid'] for r in responses])
    stamp = '<div class="banner">이 샘플은 가상의 응답 12명으로 만든 예시입니다. 실제 사람의 결과가 아닙니다.</div>'
    ind = ind.replace('<main class="page">\n', '<main class="page">\n' + stamp + '\n', 1)
    org = org.replace('<main class="page">\n', '<main class="page">\n' + stamp + '\n', 1)
    return {'report-individual.sample.html': ind, 'report-org.sample.html': org}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, doc in build().items():
        (OUT / name).write_text(doc, encoding='utf-8')
        print(f"생성: {(OUT / name).relative_to(ROOT)}")


if __name__ == '__main__':
    main()
