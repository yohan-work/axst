"""scripts/pilot.py 운영 흐름 테스트 — 합성 응답 12명으로 status → packets → import → sample → compare → reports → purge.

    python3 -m unittest discover -s tests
"""
import io, sys, json, copy, pathlib, tempfile, unittest, contextlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import pilot, make_samples, score  # noqa: E402


def quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = fn(*a)
    return rc, buf.getvalue()


class PilotFlow(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.resp, self.work, self.out = self.d / 'resp', self.d / 'work', self.d / 'reports'
        self.resp.mkdir()
        key = score.load_key()
        self.truth = {}
        for r in make_samples.synth(key):
            self.truth[r['rid']] = r.pop('fr_scores')
            (self.resp / f"axst-{r['rid']}.json").write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8')

    def run_cmd(self, *args):
        return quiet(pilot.main, ['--responses', str(self.resp), '--work', str(self.work), '--out', str(self.out), *args])

    def write_outs(self):
        idmap = json.loads((self.work / 'idmap.json').read_text(encoding='utf-8'))
        for code in ('D1', 'D2', 'D3', 'D4', 'penalty'):
            lines = [f'<<<AXST pass={code}']
            for pid, v in idmap.items():
                for fid in v['items']:
                    s = self.truth[v['key']][fid]
                    lines.append(f"{pid}|{fid}|penalty={s['penalty']}|rule={s['rule']}" if code == 'penalty'
                                 else f"{pid}|{fid}|base={s[code]}|cap=none|final={s[code]}|comment=c")
            lines.append('>>>')
            (self.work / f'out-{code}.txt').write_text("\n".join(lines), encoding='utf-8')

    def test_dedup_keeps_latest_and_skips_bad(self):
        first = json.loads((self.resp / 'axst-SMPL01.json').read_text(encoding='utf-8'))
        later = copy.deepcopy(first); later['submittedAt'] = '2026-10-20T00:00:00.000Z'; later['mc']['1'] = {'best': 4}
        (self.resp / 'axst-SMPL01-late.json').write_text(json.dumps(later), encoding='utf-8')
        (self.resp / 'broken.json').write_text('{oops', encoding='utf-8')
        old = copy.deepcopy(first); old.pop('rid'); old['respondent'] = '(미기재)'
        (self.resp / 'old.json').write_text(json.dumps(old), encoding='utf-8')
        rs, notes, bad = pilot.load_responses(self.resp)
        self.assertEqual(len(rs), 12)
        self.assertEqual(next(r for r in rs if r['rid'] == 'SMPL01')['_file'], 'axst-SMPL01-late.json')
        self.assertEqual(len(notes), 1)
        self.assertEqual(len(bad), 2)

    def test_full_flow(self):
        self.assertEqual(self.run_cmd('status')[0], 0)
        self.assertEqual(self.run_cmd('packets')[0], 0)
        self.assertNotIn('_file', (self.work / 'pass-D1.md').read_text(encoding='utf-8'))
        self.write_outs()
        self.assertEqual(self.run_cmd('import')[0], 0)
        # 이전 결과가 있으면 패킷 재생성을 막는다(번호가 바뀌어 결과가 섞인다)
        rc, out = self.run_cmd('packets')
        self.assertEqual(rc, 1); self.assertIn('--force', out)
        # 표본은 seed 가 같으면 같다
        _, s1 = self.run_cmd('sample'); _, s2 = self.run_cmd('sample')
        self.assertEqual(s1, s2)
        rows = (self.work / 'human.csv').read_text(encoding='utf-8-sig').splitlines()
        self.assertEqual(len(rows) - 1, 5)                       # 24건의 20% → 5건
        filled = [rows[0]] + [','.join(r.split(',')[:2] + ['3', '3', '3', '3', '0', '없음', '', '', '', '']) for r in rows[1:]]
        (self.work / 'human.csv').write_text("\n".join(filled) + "\n", encoding='utf-8-sig')
        self.assertEqual(self.run_cmd('compare', str(self.work / 'human.csv'))[0], 0)
        self.assertTrue((self.work / 'fr-scores.final.json').exists())
        rc, out = self.run_cmd('reports', '--org', '테스트')
        self.assertEqual(rc, 0, out)
        self.assertIn('운영자 전용 — 22번 페르소나별 감점', out)
        self.assertTrue((self.work / 'fit.csv').exists())                 # 납득도 회신 칸
        rc, out = self.run_cmd('gate')
        self.assertIn('관문 B', out)
        self.assertIn('[판정 불가] 리포트 납득도', out)                     # 회신 전이라 보류
        self.assertEqual(rc, 1)
        from unittest import mock
        with mock.patch.object(pilot, 'read_fit_rows', side_effect=PermissionError('locked')):   # 엑셀이 잠근 파일
            rc, out = self.run_cmd('gate')
            self.assertEqual(rc, 1); self.assertIn('닫고 다시 실행', out)
            rc, out = self.run_cmd('reports', '--org', '테스트')
            self.assertEqual(rc, 1); self.assertIn('닫고 다시 실행', out)
        with (self.work / 'fit.csv').open('a', encoding='utf-8') as f:
            f.write('ZZZZZZ,5\n')                                                   # 오타 코드
        _, out = self.run_cmd('gate')
        self.assertIn('어느 응답과도 맞지 않아 빠졌다 — ZZZZZZ', out)
        self.assertEqual(len(list(self.out.glob('report-*.html'))), 13)
        # purge 는 --yes 없이는 지우지 않는다
        self.run_cmd('purge')
        self.assertTrue(self.work.exists())
        self.run_cmd('purge', '--yes')
        self.assertFalse(self.work.exists()); self.assertFalse(self.out.exists())
        self.assertEqual(list(self.resp.glob('*.json')), [])

    def test_persona_penalty_counts(self):
        mk = lambda k, pk: {'rid': k, 'free_response': {'FR-02': {'persona': pk, 'text': 'x'}}}
        rs = [mk('a', 'SALES'), mk('b', 'SALES'), mk('c', 'FIN'), mk('d', None), mk('e', 'FIN')]
        scores = {'a': {'FR-02': {'penalty': -5}}, 'b': {'FR-02': {'penalty': 0}},
                  'c': {'FR-02': {'penalty': -2}}, 'd': {'FR-02': {'penalty': -5}}}   # e 는 미채점
        self.assertEqual(pilot.persona_penalties(rs, scores), {'SALES': [2, 1, 0], 'FIN': [1, 0, 1]})

    def test_reports_refuse_without_scores(self):
        rc, out = self.run_cmd('reports')
        self.assertEqual(rc, 1)
        self.assertIn('import', out)


class Gate(unittest.TestCase):
    """docs/07 관문 B. 기준마다 경계값 양쪽을 본다."""

    @classmethod
    def setUpClass(cls):
        cls.key = score.load_key()
        cls.base = make_samples.synth(cls.key)          # 12명, fr_scores 포함

    def rows(self, rs=None, **kw):
        return {name: (val, verdict) for name, val, verdict, _ in pilot.gate(rs or self.base, self.key, **kw)}

    def with_time(self, over):
        rs = copy.deepcopy(self.base)
        for i, r in enumerate(rs):
            r['durations_sec'] = {'total': 40 * 60 if i < over else 30 * 60}
        return rs

    def test_small_n_holds(self):
        rows = pilot.gate(self.base[:9], self.key)
        self.assertEqual([(r[0], r[2]) for r in rows], [('인원', pilot.HOLD)])

    def test_time_boundary(self):
        self.assertEqual(self.rows(self.with_time(2))['소요 시간'][1], pilot.PASS)    # 10/12 = 83%
        self.assertEqual(self.rows(self.with_time(3))['소요 시간'][1], pilot.FAIL)    # 9/12 = 75%
        self.assertEqual(self.rows()['소요 시간'][1], pilot.HOLD)                      # 기록 없음

    def test_blank_fr_boundary(self):
        rs = copy.deepcopy(self.base)
        for r in rs[:4]: r['free_response']['FR-01']['text'] = ''                  # 4/24 = 17%
        self.assertEqual(self.rows(rs)['주관식 미작성률'][1], pilot.PASS)
        rs[4]['free_response']['FR-01']['text'] = '  '                              # 5/24 = 21%
        self.assertEqual(self.rows(rs)['주관식 미작성률'][1], pilot.FAIL)

    def test_broken_items_rules(self):
        st = {1: {'p': 0.24, 'd': 0.5}, 2: {'p': 0.25, 'd': 0.5}, 3: {'p': 0.91, 'd': 0.5},
              4: {'p': 0.5, 'd': -0.01}, 5: {'p': 0.5, 'd': 0.0}, 6: {'p': 0.5, 'd': 0.1, 'p_worst': 0.2}}
        self.assertEqual(sorted(pilot.broken_items(st)), [1, 3, 4, 6])             # d 0~20% 는 세지 않는다

    def test_item_stats_top_bottom(self):
        evs = [{'pts': i, 'picks': {s: {'best': (k['answer'] if i >= 6 else 0), 'worst': k['worst']}
                                   for s, k in self.key.items()}} for i in range(12)]
        st = pilot.item_stats(evs, self.key)
        self.assertEqual((st[1]['p'], st[1]['d']), (0.5, 1.0))

    def test_ties_do_not_depend_on_file_order(self):
        # 12명, g=4. 점수 30 이 4~7위에 네 명 몰려 있으면 상위 마지막 자리 하나를 넷이 1/4씩 나눈다
        pts = [50, 45, 40, 30, 30, 30, 30, 20, 15, 10, 5, 0]
        high, low = pilot.group_weights(pts, 4)
        self.assertEqual(high, [1, 1, 1, .25, .25, .25, .25, 0, 0, 0, 0, 0])
        self.assertEqual(low, [0] * 8 + [1] * 4)
        mk = lambda p, ok: {'pts': p, 'picks': {s: {'best': k['answer'] if ok else 0, 'worst': k['worst']}
                                                 for s, k in self.key.items()}}
        # 동점자 넷 중 하나만 1번을 맞혔다 — 파일 순서를 바꿔도 d 는 같아야 한다
        oks = [True, True, True, False, False, False, True, False, False, False, False, False]
        base = [mk(p, ok) for p, ok in zip(pts, oks)]
        import random
        rng, ds = random.Random(7), set()
        for _ in range(40):
            rng.shuffle(base)
            ds.add(round(pilot.item_stats(base, self.key)[1]['d'], 6))
        self.assertEqual(ds, {round((3 + .25) / 4 - 0, 6)})
        # 부동소수점이면 참값 0 이 -1e-16 이 되어 'd<0' 으로 걸리던 경우(PR 리뷰 재현값)
        pts2 = [0, 0, 1, 0, 1, 3, 3, 4, 3, 2, 0, 0, 4, 4, 0]
        ok2 = [0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1]
        st = pilot.item_stats([mk(p, o) for p, o in zip(pts2, ok2)], self.key)[1]
        self.assertEqual(st['d'], 0.0)
        self.assertNotIn(1, pilot.broken_items({1: st}))
        # 모두 동점이면 d = 0
        flat = [mk(10, i % 2 == 0) for i in range(12)]
        self.assertAlmostEqual(pilot.item_stats(flat, self.key)[1]['d'], 0)

    def test_disagreement_and_spread(self):
        llm = {r['rid']: r['fr_scores'] for r in self.base}
        human = {k: copy.deepcopy(v) for k, v in list(llm.items())[:5]}
        self.assertEqual(self.rows(llm=llm, human=human)['사람–LLM 불일치'][1], pilot.PASS)   # 0/10
        human[next(iter(human))]['FR-01']['D1'] += 2                                           # 1/10 = 10%
        self.assertEqual(self.rows(llm=llm, human=human)['사람–LLM 불일치'][1], pilot.PASS)
        for k in list(human)[1:3]: human[k]['FR-02']['D2'] -= 2                                # 3/10 = 30%
        self.assertEqual(self.rows(llm=llm, human=human)['사람–LLM 불일치'][1], pilot.FAIL)
        self.assertEqual(self.rows(llm=llm)['결과 분산'][1], pilot.PASS)
        partial = {k: v for k, v in llm.items() if k != next(iter(human))}                   # LLM 점수 누락
        got = self.rows(llm=partial, human={k: llm[k] for k in list(llm)[:5]})['사람–LLM 불일치']
        self.assertEqual(got[1], pilot.HOLD)

    def test_fit(self):
        codes = [r['rid'] for r in self.base]
        self.assertEqual(self.rows(fit={c: 4 for c in codes[:5]})['리포트 납득도'][1], pilot.HOLD)       # 회신 5/12
        self.assertEqual(self.rows(fit={c: (4 if i < 3 else 2) for i, c in enumerate(codes[:6])})['리포트 납득도'][1], pilot.FAIL)  # 50%
        self.assertEqual(self.rows(fit={c: (5 if i < 4 else 3) for i, c in enumerate(codes[:7])})['리포트 납득도'][1], pilot.PASS)  # 57%
        f = pathlib.Path(tempfile.mkdtemp()) / 'fit.csv'                                       # 메일 회신을 옮겨 적은 소문자·공백
        f.write_text('응답코드,납득\n' + ''.join(f' {c.lower()} ,{5 if i < 4 else 3}\n' for i, c in enumerate(codes[:7])), encoding='utf-8-sig')
        self.assertEqual(self.rows(fit=pilot.load_fit(f))['리포트 납득도'][1], pilot.PASS)
        bad = pathlib.Path(tempfile.mkdtemp()) / 'fit.csv'
        bad.write_text('응답코드,납득\nSMPL01,6\n', encoding='utf-8-sig')
        with self.assertRaises(ValueError):
            pilot.load_fit(bad)

    def test_gate_does_not_mutate(self):
        llm = {r['rid']: r['fr_scores'] for r in self.base}
        rs = copy.deepcopy(self.base)
        for r in rs: r.pop('fr_scores')                  # 응답 파일에는 점수가 없다
        before = json.dumps(rs, sort_keys=True)
        pilot.gate(rs, self.key, llm=llm)
        self.assertEqual(json.dumps(rs, sort_keys=True), before)

    def test_broken_count_boundary(self):
        from unittest import mock
        for n, want in ((4, pilot.PASS), (5, pilot.FAIL)):
            with self.subTest(n=n), mock.patch.object(pilot, 'broken_items', lambda st, n=n: {i: ['x'] for i in range(1, n + 1)}):
                self.assertEqual(self.rows()['보류 후보 문항'][1], want)

    def test_fit_template_merges_late_codes(self):
        f = pathlib.Path(tempfile.mkdtemp()) / 'fit.csv'
        self.assertEqual(pilot.write_fit_template(f, ['A', 'B'])[1], 2)
        f.write_text('응답코드,납득\nA,5\nB,\n', encoding='utf-8-sig')                 # A 회신 적음
        self.assertEqual(pilot.write_fit_template(f, ['A', 'B', 'C'])[1], 1)            # 늦게 낸 C
        self.assertEqual(pilot.load_fit(f), {'A': 5})
        self.assertIn('C,', f.read_text(encoding='utf-8-sig'))
        self.assertEqual(pilot.write_fit_template(f, ['A', 'B', 'C'])[1], 0)
        # 운영자가 붙인 열은 늦은 응답이 덧붙여져도 남는다
        f.write_text('응답코드,납득,메모\nA,5,회신 9/30\nB,,\nC,,\n', encoding='utf-8-sig')
        pilot.write_fit_template(f, ['A', 'B', 'C', 'D'])
        text = f.read_text(encoding='utf-8-sig')
        self.assertIn('메모', text); self.assertIn('A,5,회신 9/30', text); self.assertIn('D,,', text)

    def test_fit_excel_encodings(self):
        # 한국어 윈도우 엑셀의 기본 CSV 저장은 CP949 다
        f = pathlib.Path(tempfile.mkdtemp()) / 'fit.csv'
        f.write_bytes('응답코드,납득\nA,5\n'.encode('cp949'))
        self.assertEqual(pilot.load_fit(f), {'A': 5})
        self.assertEqual(pilot.write_fit_template(f, ['A', 'B'])[1], 1)
        self.assertEqual(pilot.load_fit(f), {'A': 5})                    # 덧붙인 뒤에도 회신 유지
        for header in ('응답코드,납득(1~5)', '??????,??'):                          # 열 이름 변경 · 맥 엑셀 CSV 로 깨진 헤더
            f.write_text(header + '\nA,5\n', encoding='utf-8')
            with self.subTest(header=header), self.assertRaises(ValueError) as cm:
                pilot.load_fit(f)
            self.assertIn('응답코드,납득', str(cm.exception))
            with self.assertRaises(ValueError):
                pilot.write_fit_template(f, ['A', 'B'])                                 # 빈 행을 한 벌 더 붙이지 않는다
        f.write_text(' 응답코드 , 납득 \nA,4\n', encoding='utf-8')                  # 앞뒤 공백만 있는 헤더는 받는다
        self.assertEqual(pilot.load_fit(f), {'A': 4})
        f.write_bytes(b'\x80\x81\xff\xfe\x00')
        with self.assertRaises(ValueError) as cm:
            pilot.load_fit(f)
        self.assertIn('CSV UTF-8', str(cm.exception))

    def test_survey_summary(self):
        rs = copy.deepcopy(self.base)
        rs[0]['survey'] = {'ambiguous': [11, 18], 'realism': 4, 'persona_fit': '없었다', 'role': '웹 퍼블리싱'}
        rs[1]['survey'] = {'ambiguous': [18], 'realism': 2, 'persona_fit': '있었다', 'role': ''}
        rs[2]['survey'] = {'ambiguous': [], 'realism': None, 'persona_fit': None, 'why': '', 'role': ' 퍼블리셔 '}   # 직무만 씀
        rs[3]['survey'] = {'ambiguous': [], 'realism': None, 'persona_fit': None, 'why': '  ', 'role': ''}          # 공백뿐
        sv = pilot.survey_summary(rs)
        self.assertEqual(sv['ambiguous'][0], (18, 2))
        self.assertEqual((sv['answered'], sv['realism'], sv['roles']), (3, [4, 2], ['웹 퍼블리싱', '퍼블리셔']))


if __name__ == '__main__':
    unittest.main()
