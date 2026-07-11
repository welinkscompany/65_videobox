# 개인 음성 TTS 청취 승인 게이트 handoff

완료: 개인 음성 `tts_candidate_*`의 청취 승인/거부를 SQLite·API·UI에 연결했다. 승인 전 또는 거부 후보는 TTS replacement에 적용되지 않으며 기존 narration을 유지한다.

검증: frontend 88 passed/build, backend 635 passed 분할 실행, 600초 Korean smoke 14/14 true. 실제 사람의 청취 품질 평가는 자동화 대상이 아니므로 다음 운영 단계에서 실제 녹음으로 수행한다.

다음 goal 프롬프트: `VideoBox의 실제 사용자 녹음으로 개인 음성 TTS 후보를 3개 생성하고, 각 후보를 청취 승인/거부한 뒤 승인본의 SRT·MP4·CapCut draft 품질을 사람이 검수하는 운영 QA를 수행하라. 다중 실제 프로젝트 CapCut open/edit/export UX도 함께 기록하라.`
