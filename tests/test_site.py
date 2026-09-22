"""공개 체험 사이트(site/ + .github/workflows/pages.yml) 테스트. 첫 화면의 링크가 실제로 배포되는 파일을 가리켜야 한다.

    python3 -m unittest discover -s tests
"""
import re, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = (ROOT / 'site' / 'index.html').read_text(encoding='utf-8')
WORKFLOW = (ROOT / '.github' / 'workflows' / 'pages.yml').read_text(encoding='utf-8')


def deployed_paths():
    """pages.yml 의 cp 줄에서 배포되는 경로를 읽는다."""
    out = set()
    for src, dst in re.findall(r'^\s*cp (\S+) (\S+)$', WORKFLOW, re.M):
        dst = dst.replace('_site/', '', 1)
        for f in ROOT.glob(src):
            out.add(dst + f.name if dst.endswith('/') else dst)
    return out


class Site(unittest.TestCase):
    def test_document_basics(self):
        for need in ('<!DOCTYPE html>', '<html lang="ko">', 'name="viewport"'):
            self.assertIn(need, SITE)

    def test_no_external_resources(self):
        # 바깥으로 가는 링크(<a href>)는 괜찮지만, 불러오는 리소스는 없어야 한다
        self.assertNotRegex(SITE, r'<(?:script|img|link|iframe)[^>]+(?:src|href)\s*=\s*["\']?(?:https?:)?//')

    def test_relative_links_are_deployed(self):
        paths = deployed_paths()
        self.assertIn('form/index.html', paths)
        for href in re.findall(r'href="([^"#:]+)"', SITE):
            target = href + 'index.html' if href.endswith('/') else href
            with self.subTest(href=href):
                self.assertIn(target, paths)

    def test_sources_exist(self):
        for src, _ in re.findall(r'^\s*cp (\S+) (\S+)$', WORKFLOW, re.M):
            with self.subTest(src=src):
                self.assertTrue(list(ROOT.glob(src)), src)


if __name__ == '__main__':
    unittest.main()
