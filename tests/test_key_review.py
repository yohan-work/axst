"""scripts/key_review.py 테스트 — 검토지에 답이 새지 않고, 판정이 docs/15 사전 등록 기준대로 나오는지.

    python3 -m unittest discover -s tests
"""
import re, sys, json, pathlib, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import key_review as kr, score  # noqa: E402

KEY = score.load_key()


def rater(name, vendor, cond, flip=(), tie=()):
    items = {}
    for s, k in KEY.items():
        b = (k['answer'] % 4) + 1 if s in flip else k['answer']
        r = [2, 2, 2, 2]; r[b - 1] = 5
        if s in tie:
            r[(k['answer'] % 4)] = 5; r[k['answer'] - 1] = 5
        if k['worst']:
            r[k['worst'] - 1] = 1
        items[s] = {'best': b, 'worst': k['worst'], 'ratings': r, 'confidence': 2, 'ambiguous': False, 'note': ''}
    return {'rater': name, 'vendor': vendor, 'condition': cond, 'items': items}


class Packet(unittest.TestCase):
    def test_no_answers_leak(self):
        for rules in (True, False):
            p = kr.packet(rules)
            for kw in ('정답', '해설', 'distractor', '오답 진단', 'answer'):
                self.assertNotIn(kw, p)
            self.assertEqual(len(re.findall(r'^\*\*\d+번\*\*', p, re.M)), 20)
            self.assertEqual('우선순위 규칙' in p and '없다고 한 것' in p, rules)

    def test_options_match_web_form(self):
        p = kr.packet(True)
        self.assertIn('1. CSV를 AI에 넣어', p)


class Judge(unittest.TestCase):
    def rows(self, results):
        return {w['seq']: w for w in kr.analyze(results, KEY)}

    def test_unanimous_is_supported(self):
        rows = self.rows([rater(c, 'x', 'rules') for c in 'abc'])
        self.assertTrue(all(w['verdict'] == '지지' for w in rows.values()))

    def test_majority_elsewhere_is_disputed(self):
        rows = self.rows([rater('a', 'x', 'rules'), rater('b', 'y', 'rules', flip=(11,)), rater('c', 'y', 'rules', flip=(11,))])
        self.assertEqual(rows[11]['verdict'], '논쟁')
        self.assertTrue(rows[11]['vendor_split'])

    def test_tie_in_ratings_is_caution_not_support(self):
        rows = self.rows([rater(c, 'x', 'rules', tie=(3,)) for c in 'abc'])
        self.assertEqual(rows[3]['verdict'], '주의')      # 일치 100%지만 적절성 차이 0 < 0.5

    def test_worst_side_can_downgrade(self):
        s = next(s for s, k in KEY.items() if k['worst'])
        rs = [rater(c, 'x', 'rules') for c in 'abc']
        for r in rs:
            r['items'][s]['worst'] = (KEY[s]['worst'] % 4) + 1
        self.assertEqual(self.rows(rs)[s]['verdict'], '논쟁')

    def test_rule_dependence(self):
        rs = [rater(c, 'x', 'rules') for c in 'ab'] + [rater(c, 'x', 'norules', flip=(8,)) for c in 'cd']
        rows = self.rows(rs)
        self.assertTrue(rows[8]['rule_dep'])
        self.assertFalse(rows[1]['rule_dep'])

    def test_read_result_block_and_validation(self):
        d = pathlib.Path(tempfile.mkdtemp())
        r = rater('a', 'x', 'rules')
        good = d / 'rater=a__vendor=x__condition=rules.txt'
        good.write_text('설명…\n<<<KEYREVIEW\n' + json.dumps({'items': {str(k): v for k, v in r['items'].items()}}) + '\n>>>\n', encoding='utf-8')
        got = kr.read_result(good, KEY)
        self.assertEqual((got['rater'], got['vendor'], got['condition']), ('a', 'x', 'rules'))
        bad = d / 'rater=b__vendor=x__condition=rules.txt'
        items = {str(k): v for k, v in r['items'].items()}; items['3'] = dict(items['3'], ratings=[1, 2, 3])
        bad.write_text('<<<KEYREVIEW\n' + json.dumps({'items': items}) + '\n>>>', encoding='utf-8')
        with self.assertRaises(ValueError):
            kr.read_result(bad, KEY)


if __name__ == '__main__':
    unittest.main()
