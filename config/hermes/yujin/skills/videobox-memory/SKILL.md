---
name: videobox-memory
description: Use when explaining the VideoBox-owned explicit memory approval boundary.
---

# VideoBox 명시적 메모리 승인

## 범위

대화형 Yujin은 대화 내용을 자동 수집하거나 자동 저장하지 않습니다. 메모리 후보의
검토와 명시적 승인은 VideoBox 화면과 서버가 소유합니다. 이 스킬은 그 경계를
설명할 뿐, 메모리 제공자를 직접 호출하거나 저장 결과를 추측하지 않습니다.

## 상태 원칙

- `pending` 후보와 `rejected` 후보는 외부 저장 요청을 만들지 않습니다.
- 사용자가 VideoBox에서 명시적 승인한 후보만 격리된 저장 경계로 전달됩니다.
- `failed` 후보의 기존 승인은 유지하지만 자동 재시도하지 않습니다. 사용자가
  VideoBox에서 명시적 재시도 버튼을 눌러야 다시 저장을 요청할 수 있습니다.
- 저장 근거가 없으면 저장됐다고 말하지 않습니다.
- 메모리 기능이 막혀도 편집 대화와 수동 대체 절차는 계속 사용할 수 있어야 합니다.
