<div align="center">

# AX Literacy 진단

**조직 구성원이 AI를 업무에 제대로 쓸 역량이 있는지 35분 지필로 진단하고, 결과를 교육 처방으로 연결한다.**

[![CI](https://github.com/yohan-work/axst/actions/workflows/ci.yml/badge.svg)](https://github.com/yohan-work/axst/actions/workflows/ci.yml)
[![status](https://img.shields.io/badge/status-pilot--pending-orange)](docs/12-open-issues.md)
[![items](https://img.shields.io/badge/items-24%20banked%20%2F%2020%20deployed-blue)](forms/MANIFEST.yml)
[![code: MIT](https://img.shields.io/badge/code-MIT-green)](LICENSE)
[![content: CC BY 4.0](https://img.shields.io/badge/content-CC%20BY%204.0-lightgrey)](LICENSE-CONTENT)

[English summary](README.en.md)

</div>

> [!IMPORTANT]
> **공개 참조 구현입니다.** 폼 A는 정답과 해설이 함께 공개되어 있어서, 점수가 나가는 실제 진단에는 쓸 수 없습니다. 실제 시행에는 이 저장소의 방법론으로 [비공개 시행 폼](docs/08-administration.md#폼-분리-공개-참조-폼과-시행-폼)을 따로 만드세요.

> [!NOTE]
> **아직 사람 대상 파일럿 전입니다.** 린트·채점 리허설·합성 파일럿(LLM 에이전트 10명)까지 끝났고, 실제 응시자 파일럿과 소요 시간 실측이 남았습니다. → [열린 과제](docs/12-open-issues.md)

---

## 무엇인가

문항 뱅크 하나가 아니라 **진단부터 처방까지 한 묶음**입니다.

```
스폰서 합의 ─▶ 응시(35분) ─▶ 채점 ─▶ 축 플래그 · 레벨 ─▶ 개인/조직 리포트 ─▶ 교육 처방
 docs/09        forms/         scripts/score.py   docs/04           docs/05                docs/06
                               rubrics/
```

| 구성 | 내용 |
|---|---|
| 문항 뱅크 | 객관식 24(배포 20 + 예비 4) · 주관식 2 · 공통 지문 4 · 직무 페르소나 6 |
| 채점 | 객관식 자동 채점, 주관식은 4차원 × 5점 루브릭 + 리스크 감점, LLM 차원별 독립 채점 프로토콜 |
| 산출물 | 개인: 총점 ±5점 밴드 · 레벨 4단계 · 축 플래그 3단 / 조직(n≥10): 축별 평균·신뢰구간·오답 집중 문항 |
| 도구 | 뱅크 정합성 린터 · 온라인 응시본 생성기 · 채점기. **Python 표준 라이브러리만** 사용 |

## 왜 필요한가

교육 결정권자 330명 조사에서 97%가 AI 교육이 필요하다고 답했지만, **82%는 교육 후 현업에서 활용하지 못했습니다.** 역량 진단이 필요하다는 조직은 절반이 넘는데, 진단 결과를 교육 설계에 실제로 반영한 조직은 **3.6%** 였습니다. 진단 후 수준별로 설계한 교육의 성공률(32%)은 직무별 설계(18%)보다 높았습니다.<sup>[출처](https://blog.bloomworld.ai/why-ai-training-doesnt-stick/)</sup>

부족한 것은 문항이 아니라 **점수를 처방으로 번역하는 층**입니다. 이 저장소는 그 층을 만듭니다.

## 무엇이 다른가

**툴 상식을 묻지 않습니다.** "다음 중 Claude 모델이 아닌 것은" 같은 문항은 6개월이면 낡고, 실제로 업무에 쓰는 능력과도 상관이 거의 없습니다. 출제 규칙에서 금지하고, 린트가 일부를 기계적으로 잡습니다. 허용 유형은 세 가지뿐입니다 — 상황 판단형(SJT) · 산출물 비평형 · 최선–최악형.

**"무엇을 AI에게 맡길 것인가"를 첫 번째 축으로 둡니다.**

| 축 | 묻는 것 |
|---|---|
| **DEL** 위임 판단력 | 어떤 일을 어디까지 맡기고, 최종 판단은 누가 쥐는가 |
| **DSN** 작업 설계 | AI에게 줄 지시·조건·형식을 설계할 수 있는가 |
| **VER** 검증·신뢰 조정 | 산출물의 결함을 찾고 신뢰 수준을 조정하는가 |
| **FLW** 워크플로우 재설계 | 여러 단계·여러 사람의 일하는 방식을 바꿀 수 있는가 |
| **RSK** 리스크·거버넌스 | 규정·권리·계약 위반을 피하는가 |

축 정의와 배정 결정트리는 [docs/01-axes.md](docs/01-axes.md)에 있습니다.

**측정이 감당할 수 있는 만큼만 보고합니다.** 축당 4문항으로는 2/4와 3/4가 통계적으로 구별되지 않으므로, 개인에게 축별 점수를 숫자로 주지 않고 🟢 강점 신호 / ⚪ 판정 보류 / 🟠 보완 필요 3단 플래그만 줍니다. 총점도 ±5점 밴드로만 해석하고, 밴드가 레벨 경계에 걸치면 낮은 쪽 처방을 적용합니다.

## 빠른 시작

```bash
git clone https://github.com/yohan-work/axst.git && cd axst

python3 scripts/lint_items.py          # 문항 뱅크 정합성 검사
python3 scripts/build_web_form.py      # items/ → forms/form-A.web.html (온라인 응시본)
```

응시본(`forms/form-A.web.html`)을 브라우저로 열면 35분 타이머와 구간별 시간 기록이 붙은 시험을 볼 수 있습니다. 정답은 들어 있지 않고, 응답은 서버로 가지 않으며 응시자가 JSON으로 직접 내보냅니다.

모은 응답은 이렇게 채점합니다.

```bash
python3 scripts/score.py responses/*.json --prompts work/          # 주관식 LLM 채점 패킷 생성
python3 scripts/fr_import.py work/                                  # LLM 답변(out-*.txt) 가져오기·검증
python3 scripts/score.py responses/*.json --fr-scores work/fr-scores.json   # 채점표·총점·레벨
python3 scripts/score.py responses/*.json --cohort                  # 조직 집계 (n≥10)
```

> [!CAUTION]
> 응답은 개인정보입니다. `pilot/responses/`에 두면 `.gitignore`로 커밋에서 제외됩니다.

### 누가 무엇을 읽나

| 나는 | 읽을 것 |
|---|---|
| 진단 도입을 검토하는 HRD 담당자 | [헌장](docs/00-charter.md) → [스폰서 합의문](docs/09-sponsor-agreement.md) → [시행 절차](docs/08-administration.md) |
| 채점자 | [채점 기준](docs/04-scoring.md) → 루브릭 [FR-01](rubrics/fr-01.md) · [FR-02](rubrics/fr-02.md) → [LLM 채점 프로토콜](rubrics/llm-scorer-prompt.md) |
| 결과를 해석·처방하는 사람 | [리포트 템플릿](docs/05-report-templates.md) → [처방](docs/06-prescription.md) |
| 문항을 쓰거나 고치는 사람 | [CONTRIBUTING.md](CONTRIBUTING.md) → [축 정의](docs/01-axes.md) → [출제 규칙](docs/03-item-writing-rules.md) |
| 타당도가 궁금한 사람 | [검증 계획](docs/07-validity-plan.md) → [캘리브레이션 결함](docs/10-calibration-findings.md) → [합성 파일럿](docs/11-synthetic-pilot.md) |

## 진단 구성

| 항목 | 값 |
|---|---|
| 응시 시간 | **35분** — 안내·자기보고 2분 + 객관식 20분 + 주관식 13분 |
| 문항 | 객관식 20(축별 4) + 주관식 2 |
| 배점 | 객관식 60 + 주관식 40 = 100 |
| 레벨 | L1 미착수(0–39) · L2 개인 활용(40–59) · L3 업무 내재화(60–79) · L4 재설계자(80–100) |
| 주관식 | FR-01 본인 업무 / FR-02 직무 페르소나 6종 중 택1. D1 위임 경계 · D2 규격 구체성 · D3 검증 설계 · D4 전환 효과 + 리스크 감점 |
| 자기보고 | 3문항. 점수에 반영하지 않고 플래그 삼각검증에만 사용 |

## 저장소 구조

```
axst/
├── items/          문항 뱅크 (SSOT) — mc/ 축별 객관식 · fr/ 주관식 · stems/ 공통 지문
├── rubrics/        주관식 루브릭 · 앵커 답안 · 감점 규칙 · LLM 채점 프로토콜
├── personas/       직무 페르소나 6종 (HR · SALES · MFG · FIN · DEV · STAFF)
├── selfreport/     자기보고 3문항
├── forms/          응시본 · 정답지 · MANIFEST — 모든 값이 items/ 와 일치해야 한다
├── scripts/        lint_items.py · build_web_form.py · score.py
├── tests/          채점기 회귀 테스트
├── pilot/          문항 분석 기록 (responses/ 는 커밋하지 않음)
└── docs/           설계 문서
    ├── 00-charter             헌장 · 진단용/인증용 겸용 금지
    ├── 01-axes                5축 정의 · 축 배정 결정트리
    ├── 02-blueprint           배분표 · frontmatter 스키마
    ├── 03-item-writing-rules  출제 규칙
    ├── 04-scoring             채점 · 플래그 · 레벨
    ├── 05-report-templates    개인/조직 리포트
    ├── 06-prescription        처방 · 출구 전략
    ├── 07-validity-plan       타당도 검증 계획
    ├── 08-administration      시행 절차 · 폼 분리 정책
    ├── 09-sponsor-agreement   스폰서 합의문
    ├── 10-calibration-findings  채점 리허설 결함 기록
    ├── 11-synthetic-pilot     합성 파일럿 S0
    ├── 12-open-issues         열린 과제
    └── 99-changelog           변경 기록과 설계 결정 근거
```

**마크다운이 source of truth입니다.** 문항 1개 = 파일 1개(YAML frontmatter + 고정 H2 섹션)이고, DB나 스프레드시트를 따로 두지 않습니다. `forms/`의 정답·축·배점 등은 린트가 `items/`와 전수 대조합니다 — 정답지의 정답 하나가 어긋나면 그 문항은 전원 오채점되기 때문입니다.

## 지키는 원칙

어기면 진단이 무효가 되는 규칙입니다. 전문은 [AGENTS.md](AGENTS.md)와 [헌장](docs/00-charter.md).

1. **축별 점수를 숫자로 내보내지 않고, 개인 리포트에 레이더 차트를 그리지 않는다.** 4문항으로는 과잉 주장이다.
2. **툴 상식 문항을 추가하지 않는다.**
3. **교육 설계용과 인사 평가용을 한 폼으로 겸하지 않는다.** 겸하면 응시자가 점수를 방어하기 시작해 진단 데이터가 오염된다.
4. **스폰서 합의문 서명 없이 시행하지 않는다.** 결과를 쓸 계획이 없는 진단은 리포트 한 장으로 끝난다.
5. **응답을 커밋하지 않는다.** 조직 리포트는 n≥10에서만 만들고, n<5 셀은 표에 넣지 않는다.

## 검증 현황

문항 뱅크는 실행되는 코드가 아니므로 **린트 → 채점 리허설 → 파일럿** 순서로 검증합니다.

| 단계 | 상태 | 요약 |
|---|:---:|---|
| 뱅크 정합성 린트 | ✅ | 축 배분·정답 위치·길이 비율·금지 패턴·시간 예산·정답 누출·폼↔문항 동기화 등. CI에서 매 커밋 실행 |
| 채점 리허설 C0 | ✅ | 앵커 12개 + 페이킹 답안 2개로 결함 11건 발견 → 전부 반영 |
| 교차 모델 재검증 C1 | ✅ | 채점 모델을 바꿔 재실행. 네 차원 모두 ±1 이내 |
| 합성 파일럿 S0 | ✅ | 직무·수준·오개념을 부여한 LLM 에이전트 10명 응시. 오개념→오답 적중 15/18 |
| 소요 시간 | ◐ | 추정 32~35분. 사람의 실측 필요 |
| 실제 파일럿 (10~15명) | ⬜ | 스폰서 서명이 선행 조건 |

> [!WARNING]
> 채점 리허설은 앵커를 쓴 모델과 같은 계열이 채점했으므로 **독립 검증이 아닙니다.** 일치는 타당도의 증거가 아니고 불일치만 신호로 봅니다. 리허설에서 드러난 페이킹 방어 상한의 발동 불안정, FIN 페르소나 감점 편향, 주관식 질문이 D3 만점 요건을 노출하는 문제는 2026-09-17에 루브릭을 고쳐 반영했습니다([결정 기록](docs/10-calibration-findings.md)). 남은 것은 [열린 과제](docs/12-open-issues.md)에 있습니다.

### 알려진 한계

| 한계 | 완화 |
|---|---|
| 축당 4문항이라 개인 축별 점수를 낼 수 없다 | 3단 플래그 + 자기보고 삼각검증, 축 간 비교는 코호트(n≥30) 단위로 |
| 공통 지문 때문에 문항 간 국소 종속성이 있다 | 블록 내 축을 전부 다르게 배치, 내적 일관성(alpha)을 리포트에 쓰지 않음 |
| 지필 시험이라 실제 도구 사용을 관측하지 못한다 | 주관식에 사용한 프롬프트 첨부 요구. 실제 수행 과제는 v2 과제 |
| 자기보고는 조작 가능하다 | 점수에 반영하지 않고 플래그 하향에만 사용 |

## FAQ

<details>
<summary><b>응시자가 AI로 주관식을 대신 쓰면요?</b></summary>

막지 않고 쓸모없게 만듭니다. AI 사용을 허용하되 사용한 프롬프트를 첨부하게 하고, 그것도 채점 자료로 씁니다. 실제 업무명·시스템명·데이터 항목명이나 선택한 페르소나에만 있는 데이터 항목명이 없는 범용 답안은 네 차원 전부 상한에 갇힙니다. 페르소나 쪽 판정은 채점기가 기계적으로 내립니다. 다만 이 상한이 실제 응답에서 점수를 바꾼 사례는 아직 없습니다([열린 과제](docs/12-open-issues.md)).
</details>

<details>
<summary><b>인사 평가에 쓰면 안 되나요?</b></summary>

안 됩니다. 같은 시험을 교육 설계와 인사 평가에 겸용하면 응시자가 점수를 방어하기 시작해 진단 데이터가 오염됩니다. 인증 용도라면 별도 문항풀을 새로 만들어야 하고, 인증에 쓴 문항은 진단용으로 폐기합니다. → [헌장 2트랙 정책](docs/00-charter.md)
</details>

<details>
<summary><b>주관식 LLM 채점은 믿을 만한가요?</b></summary>

아직 검증 중입니다. 프로토콜은 차원별 독립 4패스 + 감점 1패스를 요구하고(한 번에 채점하면 차원 점수가 서로 끌려갑니다), 회차 시작 전 앵커 캘리브레이션 통과를 조건으로 둡니다. 실제 시행에서는 LLM 전수 채점 + 인간 20% 표본 이중 채점을 하고, 2점 이상 불일치하면 인간 판정을 따릅니다.
</details>

<details>
<summary><b>이 문항으로 우리 회사 진단을 해도 되나요?</b></summary>

폼 A 그대로는 안 됩니다. 정답이 공개되어 있어 점수가 역량이 아니라 검색 여부를 재게 됩니다. 이 저장소의 축·출제 규칙·루브릭·채점기·리포트 체계는 그대로 쓰고, **문항만 새로 출제한 비공개 시행 폼**을 만드세요. 문항 분석이 목적인 파일럿은 폼 A로 해도 됩니다. → [시행 폼 만드는 절차](docs/08-administration.md#시행-폼을-만드는-절차)
</details>

## 기여

결함 제보가 가장 반가운 기여입니다 — 정답이 모호한 문항, 두 축에 걸치는 문항, 도달할 수 없는 루브릭 칸. 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다. 루브릭·채점 규칙 변경은 이슈로 먼저 논의해 주세요.

## 라이선스

- 코드(`scripts/`, `tests/`, `.github/`): [MIT](LICENSE)
- 문항·루브릭·페르소나·문서 등 그 밖의 콘텐츠: [CC BY 4.0](LICENSE-CONTENT) — 출처를 밝히면 상업적 이용·수정·재배포가 가능합니다

인용 예: `AX Literacy 진단 (axst), https://github.com/yohan-work/axst, CC BY 4.0`
