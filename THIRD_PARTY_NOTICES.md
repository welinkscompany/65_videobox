# VideoBox third-party notices

## Current status

Task 4 materializes the reviewed Pretendard v1.3.9 variable WOFF2 byte stream
and the locked shadcn/ui new-york-v4 source files. Their upstream and local
SHA256 values are recorded in the source map and registry lock.
No Apache-2.0 source is materialized, modified, or attributed as copied yet.

Task 6 adapts the structural shell composition of shadcn-admin's pinned
`authenticated-layout.tsx` into `apps/web/src/app/ProductShell.tsx`. The
MIT-licensed source is recorded with its raw upstream and local SHA256 values
in the source map. VideoBox rewrites navigation, project data, copy, and all
authentication/team/administration behavior; none of those upstream features
are materialized.

Task 22 adds local, read-only voice readiness to that adapted shell. It reads
existing VideoBox state only and does not add upstream authentication, provider,
or administration behavior.

## Fonts shipped inside the container image

컨테이너 이미지에 글꼴을 담는 것은 **재배포**에 해당한다. 2026-08-20 owner 결정
(`docs/decisions/2026-08-20-overlay-and-caption-scope-expansion.ko.md` 3항)이
정한 조건은 "재배포·임베딩을 명시 허용하는 라이선스만, 근거를 여기 남긴다"이다.
아래 둘은 그 조건을 만족한다. 둘 다 Debian 패키지로 설치하며 저장소에 글꼴
바이트를 커밋하지 않는다(`docker/workspace.Dockerfile`).

| 패키지 | 글꼴 | 라이선스 | 쓰는 곳 |
|---|---|---|---|
| `fonts-nanum` | 나눔고딕 등 | SIL OFL-1.1 | 자막과 글줄 오버레이의 한글 |
| `fonts-dejavu-core` | DejaVu Sans 등 | Bitstream Vera / DejaVu 라이선스 (재배포 허용) | "여기를 보세요" 아이콘이 그리는 기호(✔ ✕ ⚠ 등) — 한글 글꼴에 없다 |

`fonts-nanum`은 이전부터 있었고, `fonts-dejavu-core`는 다른 패키지에 딸려 들어와
있던 것을 2026-08-20에 명시 설치로 바꿨다. 아이콘은 **글꼴에 있는 글자 하나**로
그리므로 아이콘마다 딸린 그림 파일은 없다. 다만 아래 아이콘 글꼴 한 벌은
저장소에 담는다.

## 아이콘 글꼴 (컨테이너에 함께 배포)

`docs/decisions/2026-08-20-overlay-and-caption-scope-expansion.ko.md` 1항이
"나중에 Material Symbols 글꼴(Apache-2.0) 한 장을 더해 아이콘 폭을 넓히는 것"까지
승인 범위로 정해 두었다. 위 두 글꼴 꾸러미가 가진 기호만으로는 정작 자주 쓰는
전구·돋보기·물음표·느낌표를 그릴 수 없었다 — 실측하면 넷 다 같은 픽셀 수, 곧
두부(빠진 글자 상자)로 나왔다.

| 글꼴 | 파일 | 라이선스 | 원본 | 라이선스 원문 |
|---|---|---|---|---|
| Material Symbols Outlined | `MaterialSymbolsOutlined-Variable.ttf` | Apache-2.0 | https://raw.githubusercontent.com/google/material-design-icons/e083cc60a0828fdd3b404cea0cb8a5b900e9c23e/variablefont/MaterialSymbolsOutlined%5BFILL%2CGRAD%2Copsz%2Cwght%5D.ttf | https://raw.githubusercontent.com/google/material-design-icons/e083cc60a0828fdd3b404cea0cb8a5b900e9c23e/LICENSE |

Apache-2.0은 재배포를 명시적으로 허용하므로 3항이 정한 조건("재배포·임베딩을
명시 허용하는 라이선스만")을 만족한다. §4가 요구하는 대로 라이선스 원문 사본을
`assets/fonts/icons/licenses/`에 함께 두고, 글꼴은 고치지 않고 원본 그대로 싣는다
(파일 이름만 바꿨다 — 상류 이름의 대괄호·쉼표가 ffmpeg 필터 문자열과 Dockerfile에서
다루기 나쁘다. 바이트는 그대로이며 해시로 확인한다).

파일 해시와 출처는 `assets/fonts/icons/provenance.json`에 있고,
`tests/test_icon_font_asset.py`가 파일·해시·라이선스 원문·이미지 설치 지시가
서로 어긋나면 잡는다. **자막 글꼴 목록에는 넣지 않는다** — owner가 자막에 고를
글꼴이 아니고, 같은 테스트가 그것도 함께 지킨다.

## Future materialization rule

Before a source file or generated component is added, record its pinned source
path and raw SHA256, repository-relative generated/local path and normalized
SHA256, test path, and any exact runtime dependency version, license, and
`package-lock.json` entry. A live npx `shadcn add` output is never accepted as
proof: the checked-in normalized diff and hashes must match the lock.

For any Apache-2.0 adapted materialized source, add an exact change summary,
the direct upstream LICENSE and NOTICE links, and the required attribution to
`docs/oss/editor-ui-source-map.json` and this notice file before use.

## Pinned upstream notices

| Source | License | Direct license / notice |
|---|---|---|
| shadcn-admin | MIT | https://github.com/satnaing/shadcn-admin/blob/e16c87f213a5ba5e45964e9b67c792105ec74d26/LICENSE |
| shadcn/ui | MIT | https://github.com/shadcn-ui/ui/blob/4396d5b2a5ee4e2ad5705e9b2522f92112f811a0/LICENSE.md |
| OpenCut current | AGPL-3.0-or-later; rejected runtime | https://github.com/OpenCut-app/OpenCut/blob/bab8af831b354a0b5a98a4a6e818ab7d633b94df/LICENSE |
| OpenCut classic | MIT | https://github.com/OpenCut-app/opencut-classic/blob/cf5e79e919144200294fb9fed22a222592a0aeea/LICENSE |
| Opencast editor | Apache-2.0 | https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/LICENSE ; https://github.com/opencast/editor/blob/1208afb64d9de0ab50b321f84f9dd2695780db87/NOTICE |
| Supabase | Apache-2.0; reference only | https://github.com/supabase/supabase/blob/1c827c5cbb29cacc6e9052adff2e1659e3cb05fb/LICENSE |
| Pretendard v1.3.9 | SIL OFL-1.1 | https://github.com/orioncactus/pretendard/blob/5c41199ea0024a9e0b2cb31735265056e5472d76/LICENSE |

## 자막 글꼴 (컨테이너에 함께 배포)

owner가 2026-08-20에 스타터 팩의 라이선스 범위를 CC0 전용에서 **OFL/ISC 계열까지**
넓히는 것을 승인했다. 글꼴을 이미지에 넣는 것은 법적으로 **재배포**라서, "사용은
무료지만 재배포 금지"인 글꼴(눈누에 흔하다)은 쓸 수 없다. 아래는 전부 SIL Open
Font License 1.1이며, 라이선스 원문이 `use, study, copy, merge, **embed**, modify,
**redistribute**, and sell` 을 명시적으로 허용한다 — 각 파일의 원문을 직접 받아
확인했고, 원문은 `assets/fonts/korean/licenses/` 에 함께 둔다.

OFL이 금지하는 것은 **글꼴만 따로 파는 것**과 예약 이름(Reserved Font Name)을
단 채 고친 글꼴을 배포하는 것이다. VideoBox는 글꼴을 고치지 않고 원본 그대로
싣는다.

| 글꼴 | 파일 | 라이선스 | 원본 | 라이선스 원문 |
|---|---|---|---|---|
| Black Han Sans | `BlackHanSans-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/blackhansans/BlackHanSans-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/blackhansans/OFL.txt |
| Do Hyeon | `DoHyeon-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/dohyeon/DoHyeon-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/dohyeon/OFL.txt |
| Gaegu | `Gaegu-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/gaegu/Gaegu-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/gaegu/OFL.txt |
| Gothic A1 | `GothicA1-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/gothica1/GothicA1-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/gothica1/OFL.txt |
| Gugi | `Gugi-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/gugi/Gugi-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/gugi/OFL.txt |
| IBM Plex Sans KR | `IBMPlexSansKR-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/ibmplexsanskr/IBMPlexSansKR-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/ibmplexsanskr/OFL.txt |
| Jua | `Jua-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/jua/Jua-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/jua/OFL.txt |
| Nanum Brush Script | `NanumBrushScript-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/nanumbrushscript/NanumBrushScript-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/nanumbrushscript/OFL.txt |
| Nanum Pen | `NanumPenScript-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/nanumpenscript/NanumPenScript-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/nanumpenscript/OFL.txt |
| Noto Sans KR | `NotoSansKR-Variable.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/notosanskr/OFL.txt |
| Pretendard | `Pretendard-Regular.otf` | SIL OFL-1.1 | https://raw.githubusercontent.com/orioncactus/pretendard/5c41199ea0024a9e0b2cb31735265056e5472d76/packages/pretendard/dist/public/static/Pretendard-Regular.otf | https://raw.githubusercontent.com/orioncactus/pretendard/5c41199ea0024a9e0b2cb31735265056e5472d76/LICENSE |
| Song Myung | `SongMyung-Regular.ttf` | SIL OFL-1.1 | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/songmyung/SongMyung-Regular.ttf | https://raw.githubusercontent.com/google/fonts/e1118da94a8cb00cf6d06cdac9ef13eb1e5c6ab7/ofl/songmyung/OFL.txt |

파일 해시와 출처는 `assets/fonts/korean/provenance.json`에 있고,
`tests/test_caption_fonts.py`가 목록·파일·해시·이미지 설치 지시가 서로 어긋나면
잡는다.

나눔고딕·나눔명조·나눔스퀘어는 Debian `fonts-nanum` 꾸러미가 넣어 준다(같은
SIL OFL-1.1). 이미지에 파일을 따로 싣지 않으므로 위 표에는 없다.
