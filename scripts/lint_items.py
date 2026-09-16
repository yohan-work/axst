#!/usr/bin/env python3
"""문항 뱅크 정합성 린트. 기준은 docs/03-item-writing-rules.md."""
import re, sys, pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAIL, WARN = [], []

def fail(m): FAIL.append(m)
def warn(m): WARN.append(m)

def parse(path):
    t = path.read_text()
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', t, re.S)
    if not m: fail(f"{path.name}: frontmatter 없음"); return None, None
    fm = {}
    for line in m.group(1).split('\n'):
        km = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if km: fm[km.group(1)] = km.group(2).strip()
    return fm, m.group(2)

def section(body, name):
    m = re.search(rf'^## {name}\n(.*?)(?=^## |\Z)', body, re.S | re.M)
    return m.group(1).strip() if m else None

ID_RE = re.compile(r'^MC-(DEL|DSN|VER|FLW|RSK)-\d{3}$')
AXES = {'위임판단력','작업설계','검증신뢰','워크플로우','리스크거버넌스'}
AXIS_BY_CODE = {'DEL':'위임판단력','DSN':'작업설계','VER':'검증신뢰','FLW':'워크플로우','RSK':'리스크거버넌스'}
FORMS = {'SJT','산출물비평','최선차선'}
LEVELS = {'인지','적용','판단'}
STANCES = {'적극','보수','중립'}
STATUS = {'초안','검토','파일럿','채택','보류','폐기'}
BANNED = re.compile(r'위 모든|정답 없음|A와 B')

items = []
for p in sorted(ROOT.glob('items/mc/*/MC-*.md')):
    fm, body = parse(p)
    if not fm: continue
    iid = fm.get('id','')
    if not ID_RE.match(iid): fail(f"{p.name}: id 형식 위반 ({iid})")
    code = iid.split('-')[1] if '-' in iid else ''
    if fm.get('axis') not in AXES: fail(f"{iid}: axis 값 오류")
    elif AXIS_BY_CODE.get(code) != fm.get('axis'):
        fail(f"{iid}: id 코드({code})와 axis({fm.get('axis')}) 불일치")
    if not fm.get('axis_note','').strip(' "'): fail(f"{iid}: axis_note 누락")
    if fm.get('form') not in FORMS: fail(f"{iid}: form 값 오류")
    if fm.get('level') not in LEVELS: fail(f"{iid}: level 값 오류")
    if fm.get('key_stance') not in STANCES: fail(f"{iid}: key_stance 값 오류")
    if fm.get('status') not in STATUS: fail(f"{iid}: status 값 오류")
    if not fm.get('decision_dimension','').strip(' "'): fail(f"{iid}: decision_dimension 누락")
    if fm.get('axis') == '워크플로우' and fm.get('subelement') in (None,'null',''):
        fail(f"{iid}: FLW 문항에 subelement 누락")

    ans = fm.get('answer'); worst = fm.get('worst') or fm.get('answer_worst')
    if ans not in {'1','2','3','4'}: fail(f"{iid}: answer 범위 오류")
    if fm.get('form') == '최선차선':
        if worst in (None,'null',''): fail(f"{iid}: 최선차선인데 answer_worst 없음")
        elif worst == ans: fail(f"{iid}: answer와 answer_worst가 같다")
    else:
        if worst not in (None,'null',''): warn(f"{iid}: 최선차선이 아닌데 answer_worst 있음")

    # distractor_dx 1..4
    dx = re.search(r'^distractor_dx:\n((?:  \d: .*\n)+)', body if False else p.read_text(), re.M)
    keys = set(re.findall(r'^  ([1-4]):', p.read_text(), re.M))
    if keys != {'1','2','3','4'}: fail(f"{iid}: distractor_dx 키 불완전 ({sorted(keys)})")
    dxmap = dict(re.findall(r'^  ([1-4]): (.*)$', p.read_text(), re.M))
    if ans in dxmap and '정답' not in dxmap[ans]: fail(f"{iid}: distractor_dx[{ans}]가 '정답'이 아니다")
    for k,v in dxmap.items():
        if k != ans and ('정답' in v or not v.strip(' "')):
            fail(f"{iid}: distractor_dx[{k}] 오답 진단 누락 또는 '정답' 표기")

    # 선택지
    opts = section(body, '선택지')
    olist = re.findall(r'^\d\.\s*(.+)$', opts, re.M) if opts else []
    if len(olist) != 4: fail(f"{iid}: 선택지 4개가 아님 ({len(olist)})")
    else:
        lens = [len(o) for o in olist]
        ratio = max(lens)/min(lens)
        limit = 200 if fm.get('stem_ref') not in (None,'null','') else 240
        if ratio > 1.25: fail(f"{iid}: 선택지 길이 비율 {ratio:.2f} > 1.25 (길이 {lens})")
        if sum(lens) > limit: fail(f"{iid}: 선택지 합계 {sum(lens)}자 > {limit}자")

    # 지문
    stem = section(body, '상황')
    if fm.get('stem_ref') in (None,'null',''):
        if not stem or '참조' in stem: fail(f"{iid}: 단독 문항인데 상황 절이 없다")
        elif len(stem) > 120: warn(f"{iid}: 단독 지문 {len(stem)}자 > 120자")
    # 해설·오답 진단
    for s in ('질문','해설','오답 진단'):
        if not section(body, s): fail(f"{iid}: '{s}' 절 누락")

    if BANNED.search(p.read_text()): fail(f"{iid}: 금지 패턴 검출")

    items.append(fm)

# --- 공통 지문 검사 (상한은 docs/03-item-writing-rules.md 글자수 표)
STEM_LIMIT = 200
stem_ids = set()
for p in sorted(ROOT.glob('items/stems/STEM-*.md')):
    fm, body = parse(p)
    if not fm: continue
    sid = fm.get('id','')
    stem_ids.add(sid)
    text = section(body, '지문')
    if not text:
        fail(f"{sid}: '지문' 절 누락"); continue
    if len(text) > STEM_LIMIT:
        fail(f"{sid}: 공통 지문 {len(text)}자 > {STEM_LIMIT}자")
    dec = fm.get('chars')
    if dec and dec.isdigit() and abs(int(dec) - len(text)) > 10:
        warn(f"{sid}: frontmatter chars={dec} vs 실제 {len(text)}자")

for i in items:
    sr = i.get('stem_ref')
    if sr not in (None,'null','') and sr not in stem_ids:
        fail(f"{i.get('id')}: stem_ref가 가리키는 {sr} 없음")

# --- 폼 A 수준 검사
dep = [i for i in items if i.get('pools') == '[A]']
if len(dep) != 20: fail(f"배포 문항 수 {len(dep)} != 20")
axc = Counter(i['axis'] for i in dep)
if set(axc.values()) != {4}: fail(f"축 배분 불균등: {dict(axc)}")
lvc = Counter(i['level'] for i in dep)
if lvc != Counter({'적용':10,'판단':6,'인지':4}): fail(f"난이도 배분 오류: {dict(lvc)}")
anc = Counter(i['answer'] for i in dep)
for k in '1234':
    if not 4 <= anc[k] <= 6: fail(f"정답 위치 {k}번 {anc[k]}회 (5±1 벗어남)")
stc = Counter(i['key_stance'] for i in dep)
for s in ('적극','보수'):
    if not 6 <= stc[s] <= 10: fail(f"stance {s} {stc[s]}개 (8±2 벗어남)")
total = sum(int(i['time_sec']) for i in dep) + 4*30
if total > 1200: fail(f"시간 예산 {total}초 > 1200초")

# 블록별 축 중복
blocks = {}
for i in dep:
    sr = i.get('stem_ref')
    if sr not in (None,'null',''): blocks.setdefault(sr, []).append(i['axis'])
for sr, axs in blocks.items():
    if len(axs) != 3: fail(f"{sr}: 블록 문항 {len(axs)}개 (3개여야 함)")
    if len(set(axs)) != len(axs): fail(f"{sr}: 블록 내 축 중복 {axs}")

# FLW 하위요소
flw = [i for i in dep if i['axis']=='워크플로우']
sub = Counter(i.get('subelement') for i in flw)
if set(sub.keys()) != {'단계소멸','핸드오프전파','전환증명'}:
    fail(f"FLW 하위요소 3종 미충족: {dict(sub)}")

# 응시본 정답 누출
form = (ROOT/'forms/form-A.md').read_text()
for kw in ('정답','해설','distractor','answer:'):
    if kw in form: fail(f"응시본에 '{kw}' 누출")

# 응시본 선택지가 문항 파일과 일치하는가 (forms/ 는 생성물이므로 드리프트 검출)
order = re.findall(r'^  - \{seq: (\d+),\s+id: (MC-[A-Z]{3}-\d{3})', (ROOT/'forms/MANIFEST.yml').read_text(), re.M)
if len(order) != 20: fail(f"MANIFEST order에 MC 문항 {len(order)}개 (20개여야 함)")
fb = re.split(r'^\*\*(\d+)\.\*\*', form, flags=re.M)
form_opts = {fb[i]: re.findall(r'^\d\.\s*(.+)$', fb[i+1], re.M) for i in range(1, len(fb), 2)}
form_opts_raw = {fb[i]: fb[i+1] for i in range(1, len(fb), 2)}
if len(form_opts) != 20: fail(f"응시본 객관식 {len(form_opts)}문항 (20문항이어야 함)")
for seq, iid in order:
    cand = list(ROOT.glob(f'items/mc/*/{iid}.md'))
    if not cand: fail(f"MANIFEST가 참조하는 {iid} 파일 없음"); continue
    _, ibody = parse(cand[0])
    iopts = re.findall(r'^\d\.\s*(.+)$', section(ibody, '선택지') or '', re.M)
    if form_opts.get(seq) != iopts:
        fail(f"응시본 {seq}번({iid}) 선택지가 문항 파일과 불일치 — forms/를 재생성할 것")

# 파생 필드 검증 — forms/ 는 손으로 유지되므로 파생값은 전부 문항 파일과 대조한다.
# 정답지·MANIFEST의 정답이 문항과 어긋나면 그 문항은 전원 오채점된다.
mani = (ROOT/'forms/MANIFEST.yml').read_text()
AXIS_SHORT = {v: k for k, v in AXIS_BY_CODE.items()}
by_id = {}
for p2 in sorted(ROOT.glob('items/mc/*/MC-*.md')):
    fm2, body2 = parse(p2)
    if fm2: by_id[fm2.get('id')] = (fm2, body2)

def _n(s):
    return re.sub(r'[\s*`>_—–\-]', '', re.sub(r'<[^>]+>', '', s or ''))

# (1) MANIFEST order 행의 파생값 ↔ 문항 frontmatter
mrows = re.findall(
    r'^  - \{seq: (\d+),\s*id: ([^,\s]+),\s*stem: ([^,\s]+),\s*axis: ([^,\s]+),\s*level: ([^,\s]+),\s*'
    r'answer: ([^,\s]+),\s*worst: ([^,\s]+),\s*stance: ([^,\s]+),\s*time_sec: (\d+)\}', mani, re.M)
if len(mrows) != 20:
    fail(f"MANIFEST order 행 파싱 {len(mrows)}개 (20개여야 함) — 형식이 바뀌었는지 확인")
for seq, iid, stem, ax, lv, ans2, wo, st, ts in mrows:
    if iid not in by_id: fail(f"MANIFEST가 참조하는 {iid} 없음"); continue
    fm2, _ = by_id[iid]
    exp_stem = fm2.get('stem_ref') or 'null'
    checks = [('stem', stem, exp_stem), ('axis', ax, AXIS_SHORT.get(fm2.get('axis'), '?')),
              ('level', lv, fm2.get('level')), ('answer', ans2, fm2.get('answer')),
              ('worst', wo, fm2.get('answer_worst') or 'null'),
              ('stance', st, fm2.get('key_stance')), ('time_sec', ts, fm2.get('time_sec'))]
    for name, got, want in checks:
        if got != want:
            fail(f"MANIFEST {seq}번({iid}) {name}={got} 인데 문항 파일은 {want} — forms/를 갱신할 것")

# (2) 정답지 객관식 표 ↔ 문항 파일
ansdoc = (ROOT/'forms/form-A.answers.md').read_text()
arows = re.findall(r'^\| (\d+) \| `(MC-[A-Z]{3}-\d{3})` \| (\w+) [^|]*\| (\S+) \| \*\*(\d)\*\* \| '
                   r'(—|\*\*\d\*\*) \| ([^|]+)\|', ansdoc, re.M)
if len(arows) != 20:
    fail(f"정답지 객관식 표 {len(arows)}행 (20행이어야 함) — 형식이 바뀌었는지 확인")
mani_seq = {s: i for s, i, *_ in mrows}
for seq, iid, ax, lv, ans2, wo, pts in arows:
    if mani_seq.get(seq) != iid:
        fail(f"정답지 {seq}번이 {iid} 인데 MANIFEST는 {mani_seq.get(seq)}")
    if iid not in by_id: continue
    fm2, _ = by_id[iid]
    want_wo = f"**{fm2.get('answer_worst')}**" if fm2.get('answer_worst') not in (None,'null','') else '—'
    for name, got, want in [('축', ax, AXIS_SHORT.get(fm2.get('axis'), '?')),
                            ('난이도', lv, fm2.get('level')),
                            ('정답', ans2, fm2.get('answer')), ('최악', wo, want_wo)]:
        if got != want:
            fail(f"정답지 {seq}번({iid}) {name}={got} 인데 문항 파일은 {want} — 이 문항은 전원 오채점된다")
    want_pts = '2+1' if want_wo != '—' else '3'
    if pts.strip() != want_pts:
        fail(f"정답지 {seq}번({iid}) 배점={pts.strip()} 인데 {want_pts}이어야 함")

# (3) 정답지 축별 집계표 ↔ 실제 축 배정
axis_of_seq = {}
for seq, iid, *_ in mrows:
    if iid in by_id: axis_of_seq[int(seq)] = by_id[iid][0].get('axis')
for line in re.findall(r'^\| (\w+) [^|]*\| ([\d, ]+) \| __ /4 \|', ansdoc, re.M):
    code, seqs = line
    listed = sorted(int(x) for x in seqs.replace(' ', '').split(','))
    actual = sorted(s for s, a in axis_of_seq.items() if AXIS_SHORT.get(a) == code)
    if listed != actual:
        fail(f"정답지 축별 집계표 {code} 문항이 {listed} 인데 실제는 {actual}")

# (4) 응시본 문항 본문 ↔ 문항 파일 (고유 상황 + 질문)
for seq, iid, stem, *_ in mrows:
    if iid not in by_id or seq not in form_opts: continue
    fm2, body2 = by_id[iid]
    blk = _n(form_opts_raw.get(seq, ''))
    sit = section(body2, '상황') or ''
    if stem != 'null':
        sit = re.sub(r'^\(STEM-\d{3}\s*참조\)\s*', '', sit).strip()
    for label, txt in [('고유 상황', sit), ('질문', section(body2, '질문') or '')]:
        if _n(txt) and _n(txt) not in blk:
            fail(f"응시본 {seq}번({iid}) {label}이 문항 파일과 불일치 — forms/를 갱신할 것")

# (5) 응시본 공통 지문 ↔ STEM 파일
for sp in sorted(ROOT.glob('items/stems/STEM-*.md')):
    sfm, sbody = parse(sp)
    stxt = _n(section(sbody, '지문') or '')
    if stxt and stxt not in _n(form):
        fail(f"{sfm.get('id')} 지문이 응시본에 없거나 불일치 — forms/를 갱신할 것")

# 폼 공개 범위 가드 (docs/08 '폼 분리' 정책)
# 실패 모드는 하나다 — 정답이 공개된 폼으로 점수 나가는 회차를 시행하는 것.
mani = (ROOT/'forms/MANIFEST.yml').read_text()
vm = re.search(r'^visibility:\s*(\S+)', mani, re.M)
VIS = {'공개참조', '비공개시행'}
if not vm:
    fail("MANIFEST에 visibility 선언 없음 (공개참조 | 비공개시행)")
elif vm.group(1) not in VIS:
    fail(f"MANIFEST visibility 값 오류 ({vm.group(1)}) — 공개참조 | 비공개시행")
else:
    em = re.search(r'^exposures:\s*(\d+)', mani, re.M)
    exp = int(em.group(1)) if em else None
    if exp is None:
        fail("MANIFEST에 exposures 없음")
    elif vm.group(1) == '공개참조' and exp > 0:
        fail(f"공개참조 폼의 exposures={exp} — 정답이 공개된 폼으로 시행했다는 뜻이다. "
             f"점수가 나가는 회차는 비공개 시행 폼으로 한다 (docs/08 '폼 분리')")

# 온라인 응시본 검사 (생성물 — scripts/build_web_form.py 로 재생성)
import json as _json
web_path = ROOT/'forms/form-A.web.html'
if not web_path.exists():
    fail("forms/form-A.web.html 없음 — build_web_form.py 를 실행할 것")
else:
    web = web_path.read_text()
    for kw in ('해설', '오답 진단', 'distractor', 'answer_worst'):
        if kw in web: fail(f"온라인 응시본에 '{kw}' 누출")
    m = re.search(r'^const DATA = (\{.*\});$', web, re.M)
    if not m:
        fail("온라인 응시본에서 DATA 블록을 찾지 못함")
    else:
        try: D = _json.loads(m.group(1))
        except Exception as e: D = None; fail(f"온라인 응시본 DATA 파싱 실패: {e}")
        if D:
            ALLOWED = {'seq','id','stem','solo','q','options','worst'}
            if len(D.get('mc',[])) != 20:
                fail(f"온라인 응시본 객관식 {len(D.get('mc',[]))}문항 (20문항이어야 함)")
            for q in D.get('mc',[]):
                extra = set(q) - ALLOWED
                if extra: fail(f"{q.get('id')}: 응시본 데이터에 허용되지 않은 키 {sorted(extra)}")
                cand = list(ROOT.glob(f"items/mc/*/{q['id']}.md"))
                if not cand: fail(f"온라인 응시본이 참조하는 {q['id']} 파일 없음"); continue
                _, ib = parse(cand[0])
                iopts = re.findall(r'^\d\.\s*(.+)$', section(ib, '선택지') or '', re.M)
                strip = lambda s: re.sub(r'<[^>]+>', '', s).replace('&amp;','&').replace('&lt;','<').replace('&gt;','>')
                if [strip(o) for o in q['options']] != iopts:
                    fail(f"온라인 응시본 {q['seq']}번({q['id']}) 선택지가 문항 파일과 불일치 — forms/를 재생성할 것")
                # 문항 고유 자료(블록 문항의 '(STEM-00N 참조)' 뒤에 붙는 검증 대상 등)가 실렸는가
                sit = section(ib, '상황') or ''
                if q['stem']:
                    sit = re.sub(r'^\(STEM-\d{3}\s*참조\)\s*', '', sit).strip()
                norm = lambda s: re.sub(r'[\s*>`_]', '', strip(s))
                if norm(sit) and norm(sit) not in norm(q.get('solo','')):
                    fail(f"온라인 응시본 {q['seq']}번({q['id']}) 문항 고유 자료 누락 — 답할 수 없는 문항이 된다")
            if len(D.get('stems',{})) != 4: fail("온라인 응시본 공통 지문 4개가 아님")
            if len(D.get('personas',[])) != 6: fail("온라인 응시본 페르소나 6종이 아님")

# 상대 링크 검증
for p in list(ROOT.glob('**/*.md')):
    if '.git' in p.parts: continue
    for link in re.findall(r'\]\((?!https?://)([^)#]+)', p.read_text()):
        if not (p.parent/link).exists(): fail(f"{p.relative_to(ROOT)}: 깨진 링크 → {link}")

print(f"검사 문항: {len(items)}개 (배포 {len(dep)})")
print(f"축 배분: {dict(axc)}")
print(f"난이도: {dict(lvc)}")
print(f"정답 위치: {dict(sorted(anc.items()))}")
print(f"stance: {dict(stc)}")
print(f"FLW 하위요소: {dict(sub)}")
print(f"시간 예산: {total}초 ({total/60:.1f}분)")
print()
for w in WARN: print(f"WARN  {w}")
for f in FAIL: print(f"FAIL  {f}")
print()
print(f"결과: {'PASS' if not FAIL else 'FAIL'}  (실패 {len(FAIL)} / 경고 {len(WARN)})")
sys.exit(1 if FAIL else 0)
