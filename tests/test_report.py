"""scripts/report.py · make_samples.py 테스트. 리포트는 금지 표현 없이, 정본 문서의 문구로 나와야 한다.

    python3 -m unittest discover -s tests
"""
import re, sys, copy, pathlib, tempfile, unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import report, make_samples, score  # noqa: E402


class Sources(unittest.TestCase):
    def test_prescriptions_parsed(self):
        rx = report.load_prescriptions()
        self.assertEqual(sorted(rx['levels']), ['L1', 'L2', 'L3', 'L4'])
        self.assertEqual(rx['levels']['L2']['axes'], ['VER', 'DEL'])
        self.assertEqual(rx['levels']['L4']['axes'], [])
        self.assertEqual(sorted(rx['axes']), sorted(report.AXES))
        self.assertTrue(rx['l4_roles'])
        self.assertEqual(rx['exit_items'], 12)

    def test_template_text_parsed(self):
        tpl = report.load_template_text()
        self.assertEqual(len(tpl['notices']), 2)
        self.assertIn('인사 평가·승진·배치 자료로 사용되지 않습니다', tpl['notices'][1])
        names = [p['name'] for p in tpl['patterns']]
        self.assertEqual(names, ['겉보기 human-in-the-loop', '덧붙이기'])
        self.assertIn((13, 3), tpl['patterns'][0]['mc'])

    def _with_doc(self, rel, old, new):
        real = (ROOT / rel).read_text(encoding='utf-8')
        self.assertIn(old, real)
        orig = pathlib.Path.read_text
        def fake(self_, *a, **k):
            t = orig(self_, *a, **k)
            return t.replace(old, new) if self_.name == pathlib.Path(rel).name else t
        return mock.patch.object(pathlib.Path, 'read_text', fake)

    def test_renamed_table_header_fails_loudly(self):
        with self._with_doc('docs/06-prescription.md', '| 본 진단 레벨 |', '| 레벨 |'):
            with self.assertRaises(report.SourceError):
                report.load_prescriptions()

    def test_missing_notice_fails_loudly(self):
        with self._with_doc('docs/05-report-templates.md',
                            '> 이 진단의 결과는 교육 설계에만 사용되며', '이 진단의 결과는 교육 설계에만 사용되며'):
            with self.assertRaises(report.SourceError):
                report.load_template_text()


class Reports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key, cls.tpl, cls.rx = score.load_key(), report.load_template_text(), report.load_prescriptions()
        cls.responses = make_samples.synth(cls.key)

    def ev(self, i=0, **patch):
        r = copy.deepcopy(self.responses[i]); r.update(patch)
        return report.evaluate(r, self.key)

    def test_individual_has_no_forbidden_and_no_answers(self):
        for i in range(len(self.responses)):
            e = self.ev(i)
            doc = report.individual_html(e, self.key, self.tpl, self.rx)
            report.forbidden_check(doc, 'individual', self.tpl)      # 예외가 없어야 한다
            text = report.visible_text(doc)
            self.assertNotRegex(text, r'\d\s*/\s*4\b')
            self.assertNotIn('정답', text)

    def test_notices_first(self):
        doc = report.individual_html(self.ev(), self.key, self.tpl, self.rx)
        text = re.sub(r'\s+', '', report.visible_text(doc))
        first_section = text.index('1.종합')
        for n in self.tpl['notices']:
            self.assertLess(text.index(re.sub(r'\s+', '', n)), first_section)

    def test_forbidden_check_catches_injections(self):
        doc = report.individual_html(self.ev(), self.key, self.tpl, self.rx)
        for bad in ('<p>위임 판단력 3/4</p>', '<p>백분위 80</p>', '<svg></svg>', '<p>정답은 2번</p>', '<p>상위 10%</p>'):
            with self.subTest(bad=bad), self.assertRaises(report.ForbiddenError):
                report.forbidden_check(doc.replace('</main>', bad + '</main>'), 'individual', self.tpl)
        with self.assertRaises(report.ForbiddenError):
            report.forbidden_check(doc.replace(self.tpl['notices_html'][1], ''), 'individual', self.tpl)

    def test_boundary_gets_lower_prescription(self):
        r = copy.deepcopy(self.responses[0])
        # 객관식 54 + 주관식 합이 61이 되도록 맞춘다 → L2~L3 경계 → L2 처방
        pts = report.evaluate(r, self.key)['pts']
        r['fr_scores'] = {'FR-01': {'total': 61 - pts}, 'FR-02': {'total': 0}}
        e = report.evaluate(r, self.key)
        self.assertEqual(e['total'], 61)
        acts = report.next_actions(e, self.rx)
        self.assertEqual(acts[0][0], f"{self.rx['levels']['L2']['track']} 트랙")
        self.assertIn('L2~L3 경계 → L2 처방', report.individual_html(e, self.key, self.tpl, self.rx))

    def test_at_most_two_actions_and_axis_choice(self):
        for i in range(len(self.responses)):
            self.assertLessEqual(len(report.next_actions(self.ev(i), self.rx)), 2)
        e = self.ev(8)   # L1, 보완 DEL·DSN·FLW·RSK → L1 주 처방 축(DSN, RSK) 중 첫 🟠 = DSN
        self.assertEqual(e['level'][0], 'L1')
        self.assertEqual(report.next_actions(e, self.rx)[1][0], score.AXIS_LABEL['DSN'])

    def test_unscored_fr_holds_level(self):
        e = self.ev(0, fr_scores={})
        self.assertIsNone(e['total'])
        doc = report.individual_html(e, self.key, self.tpl, self.rx)
        self.assertIn('산출 보류', doc)

    def test_pattern_callout(self):
        e = self.ev(11)
        names = [p['name'] for p in report.matched_patterns(e, self.tpl)]
        picks = e['picks']
        expect_hitl = picks[1]['best'] == 3 or picks[13]['best'] == 3
        self.assertEqual('겉보기 human-in-the-loop' in names, expect_hitl)

    def test_org_requires_ten(self):
        evs = [self.ev(i) for i in range(9)]
        with self.assertRaises(ValueError):
            report.org_html(evs, self.key, self.tpl, self.rx)

    def test_org_suppresses_small_cells(self):
        evs = [self.ev(i) for i in range(12)]
        doc = report.org_html(evs, self.key, self.tpl, self.rx)
        report.forbidden_check(doc, 'org', self.tpl, secret_keys=[e['resp']['rid'] for e in evs])
        l34 = sum(1 for e in evs if e['level'][0] in ('L3', 'L4'))
        self.assertLess(l34, 5)
        self.assertRegex(doc, r'<td>L3–L4</td><td class="num">-</td>')
        self.assertEqual(report.cell(4, 12), '-')
        self.assertEqual(report.cell(5, 12), '5명 (42%)')

    def test_org_persona_penalty_cells(self):
        # docs/05: 22번 감점은 페르소나별로. 응답 5건 미만 페르소나는 칸을 가린다("2명 중 1건"은 사람을 가리킨다)
        evs = []
        for i in range(12):
            r = copy.deepcopy(self.responses[i])
            pk, pen = ('SALES', -5 if i < 2 else 0) if i < 7 else ('STAFF', -5 if i == 7 else 0)
            r['free_response']['FR-02']['persona'] = pk
            sc = r['fr_scores']['FR-02']
            sc['penalty'] = pen
            sc['total'] = max(0, sum(sc[d] for d in ('D1', 'D2', 'D3', 'D4')) + pen)
            evs.append(report.evaluate(r, self.key))
        doc = report.org_html(evs, self.key, self.tpl, self.rx)
        self.assertRegex(doc, r'<td>SALES</td><td class="num">7명</td><td class="num">2건 \(29%\)</td>')
        self.assertRegex(doc, r'<td>STAFF</td><td class="num">5명</td><td class="num">1건 \(20%\)</td>')
        few = copy.deepcopy(evs)
        for e in few[8:]:
            e['resp']['free_response']['FR-02']['persona'] = 'FIN'
        doc = report.org_html(few, self.key, self.tpl, self.rx)
        self.assertRegex(doc, r'<td>STAFF</td><td class="num">-</td><td class="num">-</td><td class="num">-</td>')

    def test_org_catches_individual_key(self):
        evs = [self.ev(i) for i in range(12)]
        doc = report.org_html(evs, self.key, self.tpl, self.rx)
        with self.assertRaises(report.ForbiddenError):
            report.forbidden_check(doc.replace('</main>', '<p>SMPL03</p></main>'), 'org', self.tpl,
                                   secret_keys=[e['resp']['rid'] for e in evs])

    def test_cli_writes_reports(self):
        import json
        d = pathlib.Path(tempfile.mkdtemp())
        files = []
        for r in self.responses:
            p = d / f"{r['rid']}.json"; p.write_text(json.dumps(r, ensure_ascii=False), encoding='utf-8'); files.append(str(p))
        out = d / 'out'
        self.assertEqual(report.main(files + ['--out', str(out), '--org', '테스트']), 0)
        self.assertEqual(len(list(out.glob('report-*.html'))), 13)


class Samples(unittest.TestCase):
    def test_committed_samples_are_current(self):
        for name, doc in make_samples.build().items():
            with self.subTest(name=name):
                committed = (ROOT / 'docs' / 'samples' / name).read_text(encoding='utf-8')
                self.assertEqual(committed, doc, f"docs/samples/{name} 이 최신이 아니다 — make_samples.py 를 실행할 것")


if __name__ == '__main__':
    unittest.main()
