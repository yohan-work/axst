# 기여 가이드

이 저장소는 코드보다 **문항·루브릭·방법론 문서**가 본체입니다. 오타 하나도 정답지와 어긋나면 전원 오채점으로 이어지기 때문에, 기여 절차가 일반 소프트웨어보다 조금 엄격합니다.

## 무엇을 기여할 수 있나

| 기여 | 방법 |
|---|---|
| 문항·루브릭의 결함 제보 | [이슈 — 문항·루브릭 결함](https://github.com/yohan-work/axst/issues/new?template=item-defect.yml). 가장 가치 있는 기여입니다 |
| 스크립트 버그 | [이슈 — 스크립트 버그](https://github.com/yohan-work/axst/issues/new?template=bug.yml) 또는 바로 PR |
| 문서 오류·표현 개선 | 바로 PR |
| 새 문항 | PR. 아래 "문항을 추가·수정할 때" 순서를 따릅니다 |
| 루브릭·채점 규칙 변경 | **이슈로 먼저 논의합니다.** 진단 전체의 기준이 바뀌므로 PR부터 올리지 않습니다 |
| 파일럿 결과 공유 | 집계 결과만 이슈로. 응답 원본은 절대 올리지 않습니다 |

남은 과제와 결정 대기 항목은 [docs/12-open-issues.md](docs/12-open-issues.md)에 있습니다.

## 개발 환경

Python 3.9 이상, **표준 라이브러리만** 씁니다. 설치할 것이 없습니다.

```bash
git clone https://github.com/yohan-work/axst.git
cd axst
python3 scripts/lint_items.py              # 문항 뱅크 정합성
python3 -m unittest discover -s tests      # 채점기 테스트
```

새 의존성을 추가하지 마세요. HRD 담당자가 사내 PC에서 그대로 돌릴 수 있어야 합니다.

## 문항을 추가·수정할 때

순서를 지킵니다. 규약 전문은 [AGENTS.md](AGENTS.md)입니다.

1. [축 결정트리](docs/01-axes.md)를 실행하고, 몇 번에서 걸렸는지 `axis_note`에 한 줄 남깁니다.
2. [출제 규칙](docs/03-item-writing-rules.md)을 확인합니다. 허용 유형은 SJT · 산출물비평 · 최선차선 세 가지뿐이고, 툴 상식 문항은 금지입니다.
3. `items/mc/_template.md`를 복사해 작성합니다. 모든 오답에 `distractor_dx`(어떤 오개념을 가진 사람이 고르는가)를 씁니다. 이름 붙일 수 없는 오답은 필러이므로 버립니다.
4. [배분표](docs/02-blueprint.md)를 갱신합니다.
5. 배포 폼에 들어가는 문항이면 `forms/form-A.md` · `form-A.answers.md` · `MANIFEST.yml`을 손으로 갱신합니다. 린트가 `items/`와 전수 대조합니다.
6. 다음을 실행합니다.
   ```bash
   python3 scripts/build_web_form.py
   python3 scripts/lint_items.py
   ```
7. [docs/99-changelog.md](docs/99-changelog.md)에 문항 id와 **무엇을 왜 바꿨는지** 남깁니다.

## PR 전 체크

CI가 같은 것을 확인합니다.

- `python3 scripts/lint_items.py` → `결과: PASS`
- `python3 -m unittest discover -s tests` → `OK`
- `forms/form-A.web.html`이 `build_web_form.py` 재생성 결과와 같다

그리고 CI가 잡지 못하는 것:

- **검사를 추가했다면 대상을 고의로 깨뜨려 FAIL이 나는지 확인하고 원복합니다.** 이 저장소에서 "PASS인데 사실 검사가 없었던" 사고가 여러 번 있었습니다.
- **축별 점수를 숫자로 보고하는 기능을 넣지 않습니다.** 축당 4문항으로는 통계적으로 구별되지 않습니다([docs/04-scoring.md](docs/04-scoring.md)).

## 데이터와 개인정보

- 실제 응시 응답은 `pilot/responses/`에만 두고, 이 폴더는 `.gitignore` 대상입니다. **이슈·PR·커밋 어디에도 응답 원문을 올리지 마세요.**
- 버그 재현에 응답 JSON이 필요하면 이름과 주관식 원문을 지우거나 합성 응답을 만듭니다(`tests/test_score.py`의 `response_from` 참고).

## 공개 저장소라서 생기는 제약

문항 파일은 정답·해설을 함께 들고 있고 저장소가 공개이므로, **폼 A는 점수가 나가는 실제 진단에 쓸 수 없는 공개 참조 폼**입니다. 실제 시행은 비공개 시행 폼으로 합니다([docs/08-administration.md](docs/08-administration.md#폼-분리-공개-참조-폼과-시행-폼)). 기여하신 문항도 공개되며, 공개된 문항은 시행 폼에 재사용하지 않는 것이 원칙입니다.

## 라이선스

기여하신 내용은 저장소의 라이선스를 따릅니다 — 코드(`scripts/`, `tests/`, `.github/`)는 [MIT](LICENSE), 그 밖의 문항·루브릭·문서는 [CC BY 4.0](LICENSE-CONTENT).
