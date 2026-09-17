"""scripts/build_web_form.py 회귀 테스트. 응시본은 네트워크 없이, 정답 없이 동작해야 한다.

    python3 -m unittest discover -s tests
"""
import re, sys, json, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import build_web_form as bwf  # noqa: E402


class WebForm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.html, cls.problems = bwf.build()

    def test_builds_clean(self):
        self.assertEqual(self.problems, [])

    def test_committed_form_is_current(self):
        committed = (ROOT / 'forms' / 'form-A.web.html').read_text(encoding='utf-8')
        self.assertEqual(committed, self.html,
                         "forms/form-A.web.html 이 최신이 아니다 — build_web_form.py 를 실행할 것")

    def test_document_basics(self):
        self.assertTrue(self.html.startswith('<!DOCTYPE html>'))
        for need in ('<html lang="ko">', '<meta charset="utf-8">', 'name="viewport"', '[hidden]{display:none!important}'):
            self.assertIn(need, self.html)

    def test_no_network_dependency(self):
        self.assertNotRegex(self.html, r'''(?:src|href)\s*=\s*["']?\s*(https?:)?//''')
        self.assertNotIn('fonts.googleapis', self.html)

    def test_data_block_parseable_by_lint(self):
        # lint_items.py 가 이 줄 모양에 의존한다
        m = re.search(r'^const DATA = (\{.*\});$', self.html, re.M)
        self.assertIsNotNone(m)
        self.assertEqual(len(json.loads(m.group(1))['mc']), 20)

    def test_draft_restore_wired(self):
        # 새로고침하면 응답이 사라지던 사고: 저장만 하고 복원을 부르지 않았다
        self.assertIn('readDraft()', self.html)
        self.assertRegex(self.html, r'\(function boot\(\)\{\s*const d=readDraft\(\)')
        self.assertIn('applyState()', self.html)

    def test_response_fields(self):
        for key in ('schema:"axst-response-1"', 'rid:state.rid', 'ai_prompt:v.ai_prompt', 'total:r.sr+r.mc+r.fr'):
            self.assertIn(key, self.html)

    def test_survey_wired(self):
        # 응시 후 설문: 제출 뒤·파일 저장 전. 응답 파일에 담기고, 이어하기에서 복원되고, 점수와 무관하다
        self.assertIn('survey:Object.assign(newState().survey, state.survey)', self.html)
        self.assertIn('renderSurvey();', self.html)
        self.assertIn('const sv=Object.assign(newState().survey, state.survey);', self.html)   # applyState 복원
        done = self.html[self.html.index('<section id="s-done"'):]
        self.assertLess(done.index('class="survey"'), done.index('id="dl"'))              # 저장 버튼보다 위
        self.assertIn('점수와 무관', done)

    def test_wipe_stops_all_saves(self):
        # 공용 PC: 「이 PC에서 응답 지우기」 뒤 설문을 고쳐도 응답이 브라우저에 다시 저장되면 안 된다.
        # 지우기는 save 를 빈 함수로 바꾸고, 설문(svSet)은 save() 를 통해서만 저장한다 — 둘 중 하나가 바뀌면 깨진다.
        wipe = re.search(r'\$\("#wipe"\)\.onclick=\(\)=>\{(.*?)\n\};', self.html, re.S).group(1)
        self.assertIn('save = function(){};', wipe)
        self.assertRegex(self.html, r'\nfunction save\(\)\{')                          # const 면 재할당이 실패한다
        sv = re.search(r'function svSet\(k,v\)\{(.*?)\}\n', self.html).group(1)
        self.assertNotIn('localStorage', sv)
        self.assertIn('save()', sv)

    def test_worst_seqs_from_items(self):
        seqs = '·'.join(str(m['seq']) for m in self.data['mc'] if m['worst'])
        self.assertIn(seqs + '번은', self.html)
        self.assertNotIn('__WORST_SEQS__', self.html)


class LeakCheck(unittest.TestCase):
    """check_leaks 가 실제로 잡는지 — 검사는 고의로 깨뜨려 확인한다."""

    @classmethod
    def setUpClass(cls):
        _, cls.html, _ = bwf.build()

    def assertCaught(self, html, fragment):
        problems = bwf.check_leaks(html)
        self.assertTrue(any(fragment in p for p in problems), problems)

    def test_catches_answer_keyword(self):
        self.assertCaught(self.html.replace('</main>', '<p>정답은 3번</p></main>'), '정답')

    def test_catches_google_fonts(self):
        bad = self.html.replace('<style>', '<link rel="stylesheet" href="https://fonts.googleapis.com/css2"><style>')
        self.assertCaught(bad, '외부')

    def test_catches_protocol_relative_script(self):
        self.assertCaught(self.html.replace('<script>', '<script src="//cdn.example.com/x.js"></script><script>'), '외부 리소스')

    def test_catches_missing_viewport(self):
        self.assertCaught(self.html.replace('name="viewport"', 'name="x"'), 'viewport')

    def test_catches_answer_key_in_data(self):
        data = bwf.collect()
        data['mc'][0]['answer'] = 2
        self.assertTrue(bwf.check_data(data))


if __name__ == '__main__':
    unittest.main()
