"""scripts/fr_import.py 와 score.py 의 주관식 점수 경로 테스트.

    python3 -m unittest discover -s tests
"""
import sys, json, pathlib, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import score, fr_import  # noqa: E402

PASSES = ('D1', 'D2', 'D3', 'D4', 'penalty')


def responses():
    return [
        {'rid': 'AAA111', 'respondent': 'navy07', 'free_response': {
            'FR-01': {'text': '① 주간 매출 보고서 …'}, 'FR-02': {'persona': 'FIN', 'text': '`계정 과목`별 합계'}}},
        {'rid': 'BBB222', 'respondent': '(미기재)', 'free_response': {
            'FR-01': {'text': '① 채용 공고 …'}, 'FR-02': {'persona': None, 'text': '정리해라'}}},
    ]


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        score.build_prompts(responses(), self.dir)
        self.lines = {
            'D1': ['R01|FR-01|base=4|cap=none|final=4|comment=책임 귀속이 분명하다',
                   'R01|FR-02|base=3|cap=none|final=3|comment=되돌림 조건이 없다',
                   'R02|FR-01|base=5|cap=2|final=2|comment=업무명이 없다',
                   'R02|FR-02|base=보류|cap=none|final=보류|comment=페르소나 미선택'],
            'penalty': ['R01|FR-01|penalty=0|rule=없음', 'R01|FR-02|penalty=-5|rule=민감 데이터 외부 투입',
                        'R02|FR-01|penalty=0|rule=없음', 'R02|FR-02|penalty=0|rule=없음'],
        }
        for d in ('D2', 'D3', 'D4'):
            self.lines[d] = [l.replace('base=4|cap=none|final=4', 'base=1|cap=none|final=1')
                             .replace('base=3|cap=none|final=3', 'base=2|cap=none|final=2') for l in self.lines['D1']]

    def write(self, code=None, lines=None, raw=None):
        for c in PASSES:
            if code is not None and c != code:
                continue
            body = raw if raw is not None else "\n".join(
                ['요약표 …', '```', f'<<<AXST pass={c}', *(lines if lines is not None else self.lines[c]), '>>>', '```'])
            (self.dir / f'out-{c}.txt').write_text(body, encoding='utf-8')

    def assertRejects(self, fragment):
        with self.assertRaises(fr_import.ImportError_) as cm:
            fr_import.import_llm(self.dir)
        self.assertTrue(any(fragment in p for p in cm.exception.problems), cm.exception.problems)


class Packets(Base):
    def test_opaque_ids_not_pseudonyms(self):
        p = (self.dir / 'pass-D2.md').read_text(encoding='utf-8')
        self.assertIn('### 응답 R01 · 21번', p)
        self.assertNotIn('navy07', p)
        idmap = json.loads((self.dir / 'idmap.json').read_text(encoding='utf-8'))
        self.assertEqual(idmap['R01']['key'], 'AAA111')
        self.assertEqual(idmap['R02']['held'], ['FR-02'])

    def test_machine_block_instructions(self):
        for c in PASSES:
            p = (self.dir / f'pass-{c}.md').read_text(encoding='utf-8')
            self.assertIn(f'<<<AXST pass={c}', p)
            self.assertIn('`R02|FR-02`', p)

    def test_calibration_drops_anchors_only_for_judgement(self):
        d = pathlib.Path(tempfile.mkdtemp())
        score.build_prompts(responses(), d, calibration=True)
        self.assertNotIn('# 대조용 앵커', (d / 'pass-D1.md').read_text(encoding='utf-8'))
        self.assertNotIn('# 대조용 앵커', (d / 'pass-D4.md').read_text(encoding='utf-8'))
        self.assertIn('# 대조용 앵커', (self.dir / 'pass-D1.md').read_text(encoding='utf-8'))

    def test_duplicate_response_key_fails(self):
        rs = responses(); rs[1]['rid'] = 'AAA111'
        with self.assertRaises(ValueError):
            score.build_prompts(rs, tempfile.mkdtemp())


class ImportLLM(Base):
    def test_happy_path(self):
        self.write()
        s = fr_import.import_llm(self.dir)
        a = s['AAA111']
        self.assertEqual(a['FR-01']['total'], 4 + 1 + 1 + 1)
        self.assertEqual(a['FR-02']['total'], 3 + 2 + 2 + 2 - 5)
        self.assertEqual(s['BBB222']['FR-01']['cap']['D1'], '2')
        self.assertTrue(s['BBB222']['FR-02']['held'])
        self.assertNotIn('total', s['BBB222']['FR-02'])
        self.assertEqual(a['FR-01']['comment']['D1'], '책임 귀속이 분명하다')

    def test_rejects_out_of_range(self):
        self.write(); self.lines['D2'][0] = 'R01|FR-01|base=6|cap=none|final=6|comment=x'; self.write('D2')
        self.assertRejects('0~5')

    def test_rejects_bad_penalty(self):
        self.write(); self.lines['penalty'][0] = 'R01|FR-01|penalty=-3|rule=x'; self.write('penalty')
        self.assertRejects('penalty')

    def test_rejects_cap_mismatch(self):
        self.write(); self.lines['D3'][2] = 'R02|FR-01|base=5|cap=2|final=5|comment=x'; self.write('D3')
        self.assertRejects('여야 한다')

    def test_rejects_missing_line(self):
        self.write(); self.write('D4', self.lines['D4'][:-1])
        self.assertRejects('R02 FR-02 줄이 빠졌다')

    def test_rejects_duplicate_line(self):
        self.write(); self.write('D1', self.lines['D1'] + [self.lines['D1'][0]])
        self.assertRejects('두 번')

    def test_rejects_missing_pass_file(self):
        self.write(); (self.dir / 'out-D3.txt').unlink()
        self.assertRejects('out-D3.txt 가 없다')

    def test_rejects_wrong_pass_code(self):
        self.write(); (self.dir / 'out-D2.txt').write_text((self.dir / 'out-D1.txt').read_text(encoding='utf-8'), encoding='utf-8')
        self.assertRejects('pass=D1')

    def test_rejects_no_block_and_two_blocks(self):
        self.write(); self.write('D1', raw='요약표만 있고 블록이 없다')
        self.assertRejects('블록이 없다')
        body = (self.dir / 'out-D2.txt').read_text(encoding='utf-8')
        self.write('D1', raw=body.replace('D2', 'D1') * 2)
        self.assertRejects('2개')

    def test_rejects_score_on_held_answer(self):
        self.write()
        self.lines['D1'][3] = 'R02|FR-02|base=3|cap=none|final=3|comment=x'; self.write('D1')
        self.assertRejects('판정 보류')

    def test_cli_writes_nothing_on_failure(self):
        self.write(); self.write('D4', self.lines['D4'][:-1])
        self.assertEqual(fr_import.main([str(self.dir)]), 1)
        self.assertFalse((self.dir / 'fr-scores.json').exists())


class HumanCSV(Base):
    def test_template_fill_import_compare(self):
        self.write()
        self.assertEqual(fr_import.main([str(self.dir)]), 0)
        tpl = self.dir / 'human.csv'
        fr_import.write_template(self.dir, tpl)
        raw = tpl.read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))   # 엑셀용 BOM
        rows = raw.decode('utf-8-sig').splitlines()
        # 표본 1건만 채운다: R01 FR-01 — D1 을 LLM(4)보다 2점 낮게
        rows[1] = 'R01,FR-01,2,1,1,1,0,없음,,,,'
        tpl.write_text("\n".join(rows) + "\n", encoding='utf-8-sig')
        human = fr_import.import_csv(self.dir, tpl)
        self.assertEqual(list(human), ['AAA111'])
        llm = json.loads((self.dir / 'fr-scores.json').read_text(encoding='utf-8'))['scores']
        merged, report = fr_import.compare(llm, human)
        self.assertEqual(len(report), 1)
        self.assertEqual(merged['AAA111']['FR-01']['D1'], 2)
        self.assertEqual(merged['AAA111']['FR-01']['adopted'], 'human')
        self.assertEqual(merged['AAA111']['FR-02'], llm['AAA111']['FR-02'])

    def test_csv_rejects_bad_value(self):
        tpl = self.dir / 'h.csv'
        fr_import.write_template(self.dir, tpl)
        rows = tpl.read_text(encoding='utf-8-sig').splitlines()
        rows[1] = 'R01,FR-01,7,1,1,1,0,없음,,,,'
        tpl.write_text("\n".join(rows), encoding='utf-8-sig')
        with self.assertRaises(fr_import.ImportError_):
            fr_import.import_csv(self.dir, tpl)


class FrTotal(unittest.TestCase):
    def test_floor_zero(self):
        self.assertEqual(score.fr_total({'D1': 0, 'D2': 0, 'D3': 0, 'D4': 1, 'penalty': -5}), 0)

    def test_held_is_none(self):
        self.assertIsNone(score.fr_total({'D1': '보류', 'D2': '보류', 'D3': '보류', 'D4': '보류', 'penalty': 0}))

    def test_rejects_tampered_total(self):
        with self.assertRaises(ValueError):
            score.fr_total({'D1': 3, 'D2': 3, 'D3': 3, 'D4': 3, 'penalty': 0, 'total': 20})

    def test_rejects_bad_values(self):
        for bad in ({'D1': 6, 'D2': 0, 'D3': 0, 'D4': 0}, {'D1': 1, 'D2': 1, 'D3': 1, 'D4': 1, 'penalty': -3},
                    {'total': 21}, {}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                score.fr_total(bad)

    def test_unscored_answer_holds_level(self):
        r = {'free_response': {'FR-01': {'text': 'x'}, 'FR-02': {'text': 'y'}},
             'fr_scores': {'FR-01': {'total': 10}}}
        self.assertEqual(score.fr_points(r), (None, '미채점'))
        r['free_response']['FR-02']['text'] = ''
        self.assertEqual(score.fr_points(r), (10, ''))

    def test_attach_by_rid(self):
        r = {'rid': 'AAA111', 'respondent': 'navy07'}
        score.attach_fr_scores(r, {'AAA111': {'FR-01': {'total': 9}}})
        self.assertEqual(r['fr_scores']['FR-01']['total'], 9)


if __name__ == '__main__':
    unittest.main()
