# 검증 실습 키트 — 프론트엔드·웹퍼블리싱

**대상**: 진단 리포트에서 **검증·신뢰 조정**이 🟠 보완 필요 또는 ⚪ 판정 보류로 나온 사람
**소요**: 약 45분 (혼자) · 60분 (팀 세션, [진행안](README.md#팀-세션-진행안-60분))
**준비물**: 이 문서, 펜, 이번 주에 AI로 만든 업무 결과물 1개

> 해설은 [ver-frontend.answers.md](ver-frontend.answers.md)에 있다. **실습 1·2를 끝낸 뒤에 연다.** 먼저 보면 이 키트는 쓸모가 없다.

---

## 0. 시작 전 1분 — 지금의 나를 기록한다

실습 1의 자료를 훑어보지 말고, 아래 질문에 **지금 생각대로** 한 줄만 적는다.

> AI가 써 준 PR 요약을 보고 배포를 승인해야 한다. 가장 먼저 무엇을 확인하는가?

내 답: ______________________________________________

이 답은 45분 뒤 다시 본다.

---

## 1. 규칙 한 장 (5분)

AI 산출물에서 확인할 게 여러 개일 때, **다 보려고 하지 않는다.** 순서를 정하고, 안 볼 것을 정한다.

### 먼저 볼 것을 고르는 기준

| 질문 | 예 → 앞으로 |
|---|---|
| 이 주장이 틀리면 **결정이 바뀌는가**? (머지·배포·공지) | 결정에 직접 쓰이는 주장이 먼저 |
| **가진 자료로 바로 확인**할 수 있는가? (diff·로그·원문) | 싸게 확인되는 것이 먼저 |
| 둘이 비슷하면 → **"없다" · "문제없다"는 주장을 먼저** | 있다고 한 것은 눈에 보이지만, 없다고 한 것은 찾아보지 않으면 안 드러난다 |

### 따로 다루는 두 종류

- **AI가 할 수 없는 일을 했다는 주장** — "브라우저에서 동작 확인했습니다", "배포 후 모니터링 결과 이상 없습니다". AI는 브라우저를 켜지 않는다. 이런 문장은 검증할 대상이 아니라 **근거 없음**이다. 지우고, 사람이 할 일로 넘긴다.
- **출처가 붙은 주장** — 절 번호, 링크, 문서 이름이 있다고 그 문서에 그 말이 있는 건 아니다. 그 주장이 **결정의 근거로 쓰일 때는 원문을 직접 연다.** 결정에 안 쓰이는 참고 수치라면 시간을 쓰지 않는다.

### 안 볼 것을 정하는 것도 검증이다

틀려도 결정이 바뀌지 않는 것(의견, 톤, 참고 수치)은 확인하지 않는다. 대신 **근거 없는 수치는 요약에서 지우거나 "미측정"이라고 적는다.** 확인하지 않는 것과 그대로 두는 것은 다르다.

---

## 2. 실습 1 — 배포 전 PR 요약 (20분)

### 상황

금요일 오후, 상품 상세 페이지 배포를 앞두고 있다. 당신은 옵션 선택 드롭다운을 리팩터링한 PR을 올렸다. 팀에서 쓰는 AI 코드 리뷰 도우미가 **PR 설명과 확인 결과 요약**을 자동으로 써 줬다.

**팀장은 이 요약만 보고 머지와 배포를 승인한다.** 이 레포는 PR 단계에 CI가 없고, 빌드와 전체 테스트는 배포 파이프라인에서만 돈다.

리뷰를 요청하기 전에 10분이 있다.

### AI가 쓴 PR 요약

> **[리팩터링] 상품 옵션 드롭다운을 커스텀 리스트박스로 교체**
>
> ① 옵션 드롭다운을 커스텀 리스트박스로 교체해 디자인 시안과 일치시켰습니다.
> ② 코드 가독성과 유지보수성이 크게 향상되었습니다.
> ③ Breaking change 없음. `OptionSelect`를 쓰는 다른 곳은 영향이 없습니다.
> ④ 전체 테스트 12건이 모두 통과했습니다.
> ⑤ 키보드 조작(방향키·Enter·Esc)을 그대로 유지했고, 팀 접근성 가이드를 준수합니다.
> ⑥ ESLint·Prettier 규칙을 모두 통과했습니다.
> ⑦ 번들 크기가 약 8% 줄었습니다.
> ⑧ Chrome·Safari·Firefox 최신 버전에서 동작을 확인했습니다.

### 자료 1 — 변경 내용 (diff 발췌)

```diff
 // src/components/OptionSelect/OptionSelect.tsx
-type Props = { options: string[]; value: string; onChange: (value: string) => void };
+type Props = { options: Option[]; selected: Option | null; onSelect: (option: Option) => void };

-export function OptionSelect({ options, value, onChange }: Props) {
-  return (
-    <select value={value} onChange={(e) => onChange(e.target.value)}>
-      {options.map((o) => <option key={o} value={o}>{o}</option>)}
-    </select>
-  );
-}
+export function OptionSelect({ options, selected, onSelect }: Props) {
+  const [open, setOpen] = useState(false);
+  return (
+    <div role="listbox" className={styles.box} onClick={() => setOpen(!open)}>
+      <span className={styles.label}>{selected?.name ?? '옵션 선택'}</span>
+      {open && (
+        <ul className={styles.list}>
+          {options.map((o) => (
+            <li key={o.id} role="option" onClick={() => onSelect(o)}>{o.name}</li>
+          ))}
+        </ul>
+      )}
+    </div>
+  );
+}

 // src/pages/product/[id].tsx
-      <OptionSelect options={names} value={opt} onChange={setOpt} />
+      <OptionSelect options={options} selected={opt} onSelect={setOpt} />
```

변경된 파일은 위 두 개와 `OptionSelect.module.scss`, `OptionSelect.test.tsx`뿐이다.

### 자료 2 — 로컬 테스트 로그 (AI가 요약에 쓴 원본)

```text
$ npx jest src/components/OptionSelect
 PASS  src/components/OptionSelect/OptionSelect.test.tsx
  OptionSelect
    ✓ 옵션 목록을 렌더링한다
    ✓ 선택한 옵션 이름을 표시한다
    ... (10건 생략)

Test Suites: 1 passed, 1 total
Tests:       12 passed, 12 total

$ npx eslint src/components/OptionSelect && npx prettier --check src/components/OptionSelect
Checking formatting...
All matched files use Prettier code style!
```

### 자료 3 — `OptionSelect`를 쓰는 곳

```text
$ grep -rn "OptionSelect" src/ --include=*.tsx
src/components/OptionSelect/OptionSelect.tsx:12:export function OptionSelect({ options, selected, onSelect }: Props) {
src/components/OptionSelect/OptionSelect.test.tsx:3:import { OptionSelect } from './OptionSelect';
src/pages/product/[id].tsx:48:      <OptionSelect options={options} selected={opt} onSelect={setOpt} />
src/components/CartDrawer/CartDrawer.tsx:71:        <OptionSelect options={item.optionNames} value={item.option} onChange={(v) => updateOption(item.id, v)} />
src/components/CartDrawer/CartDrawer.test.tsx:9:import { OptionSelect } from '../OptionSelect/OptionSelect';
src/components/QuickBuy/QuickBuy.tsx:33:      <OptionSelect options={names} value={opt} onChange={setOpt} />
```

### 자료 4 — 팀 접근성 가이드 발췌 (사내 위키)

> **4.2 커스텀 드롭다운**
> 네이티브 `<select>`를 커스텀 리스트박스로 대체할 때는 다음을 모두 지원해야 한다.
> ① Tab 키로 포커스 진입 ② 위·아래 방향키로 옵션 이동 ③ Enter로 선택 ④ Esc로 닫기.
> 대체하는 PR에는 네 항목의 지원 여부를 적는다. 하나라도 빠지면 배포하지 않는다.

### 과제

**A. 확인 순서** — ①~⑧ 중 **확인할 것**을 먼저 볼 순서대로 적는다. 각각 어느 자료로 확인하는지도 적는다.

| 순서 | 번호 | 확인에 쓸 자료 | 확인 결과 (참 / 거짓 / 근거 없음) |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

**B. 안 볼 것** — 확인하지 않을 번호와 이유. 그 문장을 요약에서 어떻게 처리할지도.

______________________________________________

**C. 따로 처리할 것** — 검증 대상이 아니라 다른 방식으로 다뤄야 할 번호가 있는가? 어떻게 처리하는가?

______________________________________________

**D. 틀린 게 나오면** — 무엇을 하는가? 누가, 언제?

______________________________________________

---

## 3. 실습 2 — 출처가 붙은 AI 답변 (5분)

### 상황

팀 슬랙에서 AI 도우미가 한 질문에 이렇게 답했다. 당신은 이 답을 **팀 위키의 성능 FAQ에 옮기려** 한다. 앞으로 팀원들은 LCP 이미지 설정을 정할 때 이 FAQ를 본다.

> LCP 이미지도 `next/image` 기본 설정 그대로 두면 됩니다. 사내 성능 가이드 v2 **3.2절**에 "기본값을 유지한다"고 되어 있습니다. 다른 AI 챗봇에 물어봐도 같은 답이 나옵니다.

### 자료 5 — 사내 성능 가이드 v2, 3.2절 원문

> **3.2 이미지 로딩**
> 첫 화면의 LCP 후보 이미지(히어로 배너, 상품 대표 이미지)는 지연 로딩에서 제외하고 `priority`를 지정한다.
> 그 외 이미지는 기본값을 유지한다.

### 과제

위키에 올리기 전에 무엇을 근거로 이 답을 믿을지, 무엇을 하겠는지 **세 줄**로 적는다.

1. ______________________________________________
2. ______________________________________________
3. ______________________________________________

**생각해 볼 것**: 실습 1의 ⑦(번들 8% 감소)은 확인하지 않아도 됐다. 이 답의 출처는 왜 확인해야 하는가?

---

## 4. 실습 3 — 내 업무에 적용 (15분)

이번 주에 AI로 만든 결과물 하나를 고른다. PR 설명, 코드, 테스트, QA 결과 요약, 문서, 회의록 — 무엇이든 된다.

**1) 이 결과물은 어떤 결정에 쓰이는가?** (머지, 배포, 공유, 보고 …)

______________________________________________

**2) 결과물 속 주장을 최대 5개 뽑는다.** 그리고 표시한다.

| 주장 | 틀리면 결정이 바뀌나 | 가진 자료로 바로 확인되나 | "없다·문제없다" 주장인가 | AI가 할 수 없는 일인가 |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

**3) 검증 계획을 쓴다.**

- 먼저 볼 것과 그 순서: ______________________________________________
- 어떻게 확인하나 (원자료 대조 / 다시 계산 / 직접 실행 / 동료 리뷰): ______________________________________________
- 보지 않을 것과 이유: ______________________________________________
- 틀렸을 때 할 일: ______________________________________________
- 누가, 언제 (예: 내가, 리뷰 요청 전): ______________________________________________

### 스스로 점검

| | 내 계획에 있다 |
|---|---|
| 확인할 **대상**을 구체적으로 적었다 ("결과물 전체"가 아니라 "③의 breaking change 여부") | ☐ |
| 확인 **방법**을 적었다 ("꼼꼼히 본다"는 방법이 아니다. 무엇과 무엇을 대조하는가) | ☐ |
| 틀렸을 때 **할 일**을 적었다 | ☐ |
| **누가·언제** 확인하는지 적었다 | ☐ |
| **보지 않을 것**을 정했고 이유가 있다 | ☐ |

다섯 칸이 모두 차면 이 키트의 목표에 도달한 것이다.

---

## 5. 끝나고 1분

0번에 적은 답을 다시 본다. 지금이라면 무엇을 먼저 확인하는가? 두 답이 다르면 무엇이 바뀌었는지 한 줄로 적는다.

______________________________________________

**팀에 가져갈 것**: 실습 1이 불편했다면 팀 PR 템플릿에 [세 줄 점검](README.md#팀에-두는-장치-pr-템플릿-세-줄)을 넣자고 제안한다. 교육보다 오래 간다.
