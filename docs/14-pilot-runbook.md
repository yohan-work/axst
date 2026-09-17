# 14. 파일럿 런북

터미널에서 스크립트를 직접 돌리는 운영자용 체크리스트다. 규칙과 근거는 링크한 문서에 있고, 이 문서는 **순서와 명령**만 다룬다. Python 3.9 이상이면 설치할 것이 없다.

모든 명령은 저장소 루트에서 실행한다. 폴더는 `pilot/responses/`(응답) · `pilot/work/`(채점 작업) · `pilot/reports/`(리포트)이고 전부 git에서 제외된다.

---

## 0. 먼저 혼자 해 보기 (약 1시간)

제안하기 전에 운영자가 한 바퀴 돌아 본다. 문항·시간·리포트를 직접 겪어 봐야 결정권자의 질문에 답할 수 있다.

1. `forms/form-A.web.html`을 브라우저로 열어 35분 안에 푼다. 타이머는 실제로 켠다
2. 완료 화면에서 **응답 파일 저장** → 받은 파일을 `pilot/responses/`로 옮긴다
3. `python3 scripts/pilot.py status` — 내 응답이 보이는지 확인
4. `python3 scripts/pilot.py packets` — `pilot/work/pass-*.md` 5개가 생긴다
5. 사내 허용 LLM에서 **패스마다 새 대화**를 열고 `pass-D1.md` 전체를 붙여넣는다 → 답변 전체를 `pilot/work/out-D1.txt`로 저장. D2·D3·D4·penalty도 같은 방식
6. `python3 scripts/pilot.py import` — 실패하면 메시지가 가리키는 파일·줄을 고치거나 그 패스만 다시 요청한다
7. `python3 scripts/pilot.py reports` — 1명이라 조직 리포트는 건너뛰고 개인 리포트만 `pilot/reports/`에 생긴다
8. 리포트를 열어 **내가 받았을 때 납득이 되는지** 본다. 걸리는 문항·문구는 [열린 과제](12-open-issues.md)나 이슈로 남긴다

> 1명 결과는 문항 검증 근거가 아니다. 목적은 흐름과 소요 시간을 몸으로 확인하는 것이다.

---

## 1. 제안 (D-21 ~ D-14)

- [ ] [13-pilot-proposal.md](13-pilot-proposal.md)의 빈칸을 채운다. 샘플 리포트 2개(`docs/samples/`)를 함께 보낸다
- [ ] 결정권자 미팅에서 [스폰서 합의문](09-sponsor-agreement.md) 서명을 받는다. **서명 없이 진행하지 않는다**
- [ ] 사내 허용 LLM을 확인한다. 없으면 주관식 채점을 사람이 한다(`pilot.py sample --rate 1.0`으로 전수 CSV)
- [ ] [관문 B](07-validity-plan.md#관문-b--본-시행으로-갈지-) 6개 기준을 스폰서에게 보여 주고 **파일럿 전에** 확인받는다. 결과를 본 뒤 기준을 바꾸지 않는다

## 2. 준비 (D-7 ~ D-1)

- [ ] 참여자 10~15명을 **레벨이 섞이게** 고른다. 한 부서만 모으지 않는다
- [ ] `python3 scripts/lint_items.py` → PASS
- [ ] 응시본 파일을 사내 공유 위치(메일 첨부·사내 드라이브·인트라넷)에 올리고, **사내 PC에서 네트워크를 끊은 채 한 번 열어** 끝까지 넘겨 본다
- [ ] [사전 안내자료](08-administration.md#사전-안내자료-응시자에게-미리-배포)를 D-1까지 보낸다. 파일럿이므로 다음 두 문장을 추가한다
  - "이 폼의 정답은 공개되어 있습니다. 찾아보면 문항 검증이 무의미해집니다."
  - "개인 리포트는 참고용이며 배치·평가에 쓰지 않습니다."
- [ ] 응답 파일 받을 곳을 정한다(담당자 메일 등). 파일 이름에 응답 코드가 들어가므로 이름을 바꾸지 말라고 안내한다
- [ ] 제출 화면의 **질문 3개(선택)에 답한 뒤 파일을 저장**해 달라고 안내한다. 점수와 무관하고, 문항을 고치는 데 쓴다

## 3. 응시 (D-day)

- [ ] 같은 시간대에 일괄 응시, 업무 시간 35분 보장
- [ ] 질문 응대는 [08 응대 스크립트](08-administration.md#응시-중-질문-대응)를 따른다
- [ ] 끝나면 "응답 파일을 보내야 완료", "공용 PC면 「이 PC에서 응답 지우기」"를 한 번 더 말한다

## 4. 수집 (D+0 ~ D+2)

```bash
python3 scripts/pilot.py status
```

- 같은 응답 코드 파일이 둘이면 **늦게 제출한 것**을 자동으로 쓴다(수정 후 재제출)
- `제외`로 뜬 파일은 응시자에게 다시 받는다
- `22번 페르소나 미선택`은 22번이 판정 보류가 되어 그 사람의 레벨이 나오지 않는다. 필요하면 응시자에게 확인해 응답 파일을 다시 받는다
- `소요 15분 미만`은 성실 응답 여부를 확인한다

## 5. 채점 (D+2 ~ D+7)

```bash
python3 scripts/pilot.py packets              # 캘리브레이션 회차면 --calibration
# pass-*.md 를 패스마다 새 대화에 → out-D1.txt … out-penalty.txt 로 저장
python3 scripts/pilot.py import
python3 scripts/pilot.py sample               # 20% 표본 + pilot/work/human.csv
# human.csv 를 루브릭(rubrics/fr-01.md, fr-02.md)만 보고 채운다. LLM 점수는 보지 않는다
python3 scripts/pilot.py compare pilot/work/human.csv
```

- `import`가 실패하면 **파일을 쓰지 않는다.** 메시지대로 고친다. 점수를 손으로 JSON에 넣지 않는다
- `compare`에서 2점 이상 불일치가 나온 답안은 앵커 추가 후보다. [캘리브레이션 결함 기록](10-calibration-findings.md)에 남긴다
- 패킷을 다시 만들어야 하면 `packets --force`. 이전 `out-*.txt`는 지워진다

## 6. 리포트 (D+7 ~ D+10)

```bash
python3 scripts/pilot.py reports --org "○○본부"
```

- [ ] 개인 리포트 `pilot/reports/report-<응답코드>.html`을 **본인에게만** 보낸다. 응답 코드로 사람을 찾는 표는 운영자만 갖는다
- [ ] 리포트 끝의 회신 요청(납득도 1~5)에 답이 오면 `pilot/work/fit.csv`에 적는다. 3~4일 기다려 응답의 절반 이상 모은다
- [ ] 조직 리포트 §7 "출구 전략 체크리스트" 칸을 [06 §4](06-prescription.md#4-출구-전략-체크리스트-)로 채운다
- [ ] 브라우저에서 열어 인쇄(PDF 저장)해 스폰서에게 보고한다

## 7. 정리 (보고 후)

- [ ] `python3 scripts/pilot.py gate` — [관문 B](07-validity-plan.md#관문-b--본-시행으로-갈지-) 판정. 출력 전체를 [pilot/item-analysis.md](../pilot/item-analysis.md)의 관문 B 표에 옮긴다
- [ ] 문항 검증 결과(문항별 정답률·오답 분포·실측 소요 시간)와 `gate`의 참고 출력(헷갈린 문항 지목·업무 현실성·페르소나 적합)을 같은 파일에 기록한다
- [ ] `pilot.py reports`가 터미널에 출력한 **22번 페르소나별 감점**을 같은 파일의 감점 표에 옮긴다. 조직 리포트에서는 5건 미만이라 가려지는 값이다([05](05-report-templates.md) §5)
- [ ] 본 시행 여부를 스폰서와 정한다. **관문 B 미달·판정 불가가 있으면 본 시행을 제안하지 않는다.** 본 시행은 **비공개 시행 폼**으로 한다([08](08-administration.md#시행-폼을-만드는-절차))
- [ ] [99-changelog.md](99-changelog.md)에 회차를 기록한다

## 8. 삭제 (리포트 전달 2주 뒤)

```bash
python3 scripts/pilot.py purge          # 지울 목록 확인
python3 scripts/pilot.py purge --yes    # 실제 삭제
```

조직 리포트를 따로 보관했는지 먼저 확인한다. 근거는 [08 응답 데이터 취급](08-administration.md#응답-데이터-취급).
