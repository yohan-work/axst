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


if __name__ == '__main__':
    unittest.main()
