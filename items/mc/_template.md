---
id: MC-XXX-000
axis: 위임판단력            # 위임판단력|작업설계|검증신뢰|워크플로우|리스크거버넌스
axis_note: "결정트리 N단계. ___이므로 ___ 축이 아니다"
subelement: null            # FLW 전용: 단계소멸|핸드오프전파|전환증명
form: SJT                   # SJT|산출물비평|최선차선
level: 적용                 # 인지|적용|판단
decision_dimension: "___"   # 4개 선택지가 달라지는 단 하나의 차원
stem_ref: null              # 공통 지문 id 또는 null
answer: 0                   # 1..4
answer_worst: null          # 최선차선 문항만
points: 3
key_stance: 중립            # 적극|보수|중립
time_sec: 70                # 단독 70 / 블록 내 40 / 최선차선 +10
pools: [A]                  # [A] 배포 / [예비] 미배포
distractor_dx:              # 1..4 전부 필수. 정답 키는 "정답"
  1: ""
  2: ""
  3: ""
  4: ""
chars_stem: 0
chars_options: 0
status: 초안                # 초안|검토|파일럿|채택|보류|폐기
stats: null
tags: []
updated: 2026-09-16
---

## 상황

(단독 문항만. 공통 지문을 쓰면 이 절을 비우고 `stem_ref`를 채운다. 120자 이내)

## 질문

## 선택지

1.
2.
3.
4.

## 해설

(정답의 근거 → 오답을 하나씩 진단 → 결정 차원이 하나임을 확인. "가장 먼저" 문항이면 우선순위 규칙을 명시)

## 오답 진단

1. ―
2. ―
3. ―
4. ―
