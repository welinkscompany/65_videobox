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
있던 것을 2026-08-20에 명시 설치로 바꿨다. 아이콘은 **글꼴에 이미 있는 글자
하나**로 그리므로 아이콘용 자산 파일을 따로 담지 않는다.

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
| Pretendard v1.3.9 | SIL OFL-1.1 | https://github.com/orioncactus/pretendard/blob/5c41199ea0024a9e0b2cb31735265056e5472d76/LICENSE.txt |
