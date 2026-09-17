"""scripts/score.py 회귀 테스트. 표준 라이브러리만 쓴다.

    python3 -m unittest discover -s tests

응답 원본(pilot/responses/)은 커밋하지 않으므로 응답은 정답 키에서 합성한다.
"""
import sys, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import score  # noqa: E402


def response_from(key, *, wrong=(), axis_wrong=None, fr_totals=None):
    """정답 키에서 응답을 만든다. wrong 의 seq 와 axis_wrong 축 문항은 오답으로 둔다."""
    mc = {}
    for seq, k in key.items():
        miss = seq in wrong or k['axis'] == axis_wrong
        best = (k['answer'] % 4) + 1 if miss else k['answer']
        a = {'best': best}
        if k['worst']:
            a['worst'] = k['worst']
        mc[str(seq)] = a
    r = {'schema': 'axst-response-1', 'form': 'A', 'respondent': 'test',
         'mc': mc, 'selfreport': {}}
    if fr_totals is not None:
        r['fr_scores'] = {f'FR-0{i+1}': {'total': t} for i, t in enumerate(fr_totals)}
    return r


class LevelOf(unittest.TestCase):
    """docs/04-scoring.md: ±5점 밴드가 39/40·59/60·79/80에 걸치면 경계, 낮은 쪽 처방."""

    def test_boundary_ranges(self):
        edges = {t for t in range(101) if score.level_of(t)[2]}
        self.assertEqual(edges, set(range(35, 45)) | set(range(55, 65)) | set(range(75, 85)))

    def test_boundary_uses_lower_level(self):
        self.assertEqual(score.level_of(44)[:2], ('L1', '미착수'))
        self.assertEqual(score.level_of(61)[:2], ('L2', '개인 활용'))
        self.assertEqual(score.level_of(84)[:2], ('L3', '업무 내재화'))

    def test_non_boundary(self):
        for total, code in [(0, 'L1'), (34, 'L1'), (45, 'L2'), (54, 'L2'),
                            (65, 'L3'), (74, 'L3'), (85, 'L4'), (100, 'L4')]:
            with self.subTest(total=total):
                self.assertEqual(score.level_of(total), (code, score.level_of(total)[1], False))

    def test_s0_expected(self):
        # 합성 파일럿 S0 10명의 기대값 (docs/11-synthetic-pilot.md)
        expected = {84: ('L3', True), 73: ('L3', False), 61: ('L2', True),
                    56: ('L2', True), 55: ('L2', True), 46: ('L2', False),
                    45: ('L2', False), 42: ('L1', True), 23: ('L1', False),
                    20: ('L1', False)}
        for total, (code, edge) in expected.items():
            with self.subTest(total=total):
                got = score.level_of(total)
                self.assertEqual((got[0], got[2]), (code, edge))


class ScoreMc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = score.load_key()

    def test_key_shape(self):
        self.assertEqual(len(self.key), 20)
        per_axis = {}
        for k in self.key.values():
            per_axis[k['axis']] = per_axis.get(k['axis'], 0) + 1
        self.assertEqual(per_axis, {'DEL': 4, 'DSN': 4, 'VER': 4, 'FLW': 4, 'RSK': 4})

    def test_all_correct_is_60(self):
        pts, correct, _, missing = score.score_mc(response_from(self.key), self.key)
        self.assertEqual((pts, missing), (60, []))
        self.assertTrue(all(correct.values()))

    def test_best_worst_partial_credit(self):
        seq = next(s for s, k in self.key.items() if k['worst'])
        r = response_from(self.key)
        r['mc'][str(seq)]['worst'] = (self.key[seq]['worst'] % 4) + 1
        pts, correct, _, _ = score.score_mc(r, self.key)
        self.assertEqual(pts, 59)          # 최선 2점만 인정 (3점 중 2점)
        self.assertFalse(correct[seq])      # 축 집계에서는 정답으로 세지 않는다

    def test_axis_flags_three_levels(self):
        r = response_from(self.key, axis_wrong='RSK')
        _, correct, _, _ = score.score_mc(r, self.key)
        fl = score.flags(correct, self.key, r)
        self.assertEqual(fl['RSK']['final'], '보완')
        self.assertEqual(fl['DEL']['final'], '강점')   # DEL 은 자기보고 대응이 없다


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = score.load_key()

    def render(self, r):
        pts, correct, picks, missing = score.score_mc(r, self.key)
        return score.render(r, self.key, pts, correct, picks, missing,
                            score.flags(correct, self.key, r))

    def test_boundary_label_in_report(self):
        out = self.render(response_from(self.key, fr_totals=(0, 1)))   # 61점
        self.assertIn('**61 / 100**', out)
        self.assertIn('L2~L3 경계 → L2 처방', out)


class PersonaCap(unittest.TestCase):
    """rubrics/fr-02.md: 페르소나 고유 항목명을 하나도 지목하지 않으면 네 차원 전부 상한 3점."""

    @classmethod
    def setUpClass(cls):
        cls.personas = score.load_personas()

    def test_all_six_personas_loaded(self):
        self.assertEqual(set(self.personas), {'HR', 'SALES', 'MFG', 'FIN', 'DEV', 'STAFF'})

    def test_spacing_ignored(self):
        hits = score.persona_anchor_hits('반려사유코드는 건수만 집계해라', self.personas['STAFF']['anchor_items'])
        self.assertEqual(hits, ['반려 사유 코드'])

    def test_generic_template_is_capped(self):
        # 결함 17: 어느 페르소나에도 붙일 수 있는 문구로는 상한을 피하지 못한다
        generic = ('아래 자료를 바탕으로 부서별 현황을 담당자가 보기 좋게 1장으로 정리해라. '
                   '자료에 없는 내용은 쓰지 마라. 수신자는 임원이다.')
        for key, p in self.personas.items():
            with self.subTest(persona=key):
                self.assertEqual(score.persona_anchor_hits(generic, p['anchor_items']), [])

    def test_other_persona_items_do_not_count(self):
        mfg_answer = '`불량 유형 코드`별 `불량 수량`을 집계해라'
        self.assertEqual(score.persona_anchor_hits(mfg_answer, self.personas['FIN']['anchor_items']), [])
        self.assertTrue(score.persona_anchor_hits(mfg_answer, self.personas['MFG']['anchor_items']))


class Prompts(unittest.TestCase):
    """채점 패킷에 상한 규칙이 실제로 실린다. _scrub 이 규칙 줄을 지우던 사고의 회귀 방지."""

    def build(self, persona='FIN', text='아래 자료를 바탕으로 정리해라.'):
        import tempfile
        d = tempfile.mkdtemp()
        r = {'respondent': 't', 'free_response': {
            'FR-01': {'text': '업무 설명'}, 'FR-02': {'persona': persona, 'text': text}}}
        score.build_prompts([r], d)
        return {c: (pathlib.Path(d) / f'pass-{c}.md').read_text(encoding='utf-8')
                for c in ('D1', 'D2', 'D3', 'D4', 'penalty')}

    def test_cap_rules_survive_scrub(self):
        packets = self.build()
        for code in ('D1', 'D2', 'D3', 'D4'):
            with self.subTest(code=code):
                p = packets[code]
                self.assertIn('상한을 2점으로 제한한다', p)          # FR-01
                self.assertIn('상한을 3점**으로 제한한다', p)        # FR-02
                self.assertIn('어느 페르소나에도 붙일 수 있는 일반 서술은 지목이 아니다', p)

    def test_verdict_written_into_packet(self):
        capped = self.build(text='아래 자료를 바탕으로 정리해라.')['D2']
        self.assertIn('상한 적용 — 페르소나 항목명 지목 없음', capped)
        ok = self.build(text='`계정 과목`별 합계를 표로 정리해라.')['D2']
        self.assertIn('상한 미적용 — 지목: `계정 과목`', ok)

    def test_unknown_persona_fails_loudly(self):
        with self.assertRaises(ValueError):
            self.build(persona='XYZ')


if __name__ == '__main__':
    unittest.main()
