---
paths:
  - "packages/core-engine/**"
  - "services/**"
  - "compose*.yaml"
  - "scripts/*hermes*"
  - "scripts/*yujin*"
  - "docker/**"
  - "config/**"
  - "docs/decisions/**"
  - "tests/*memory*"
  - "tests/*yujin*"
  - "tests/*hermes*"
---
# 유진 기억 — Mem0 제거와 남은 §10.14 조항 (CLAUDE.md §6)

CLAUDE.md §6 에서 2026-10-09 W1428 에 원문 그대로 옮겼다. CLAUDE.md 에는 §6 승인 목록과 한 줄 안내가 남아 있다. 유진·기억·컨테이너 파일을 다룰 때 자동으로 읽힌다.

**Mem0는 2026-09-18에 완전히 걷어냈다**(owner 지시, `docs/decisions/2026-09-18-mem0-removed-native-memory-librarian.ko.md`).
유진의 승인된 기억은 이제 외부 provider 없이 로컬 Postgres(`yujin_memory_candidates`)에만
저장된다. 대화(`director_conversations`/`director_messages`)를 사서가 훑어 후보를
만들고(`packages/core-engine/.../memory_librarian.py`), owner가 승인해야 저장되는
구조는 그대로다. 외부로 나가는 것이 아예 없으니 §10.14 2-A 조항은 폐기됐다 —
남은 조항 1·2·2-B·2-C·3·4는 그대로 유효하다.
