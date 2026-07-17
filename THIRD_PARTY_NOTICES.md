# VideoBox third-party notices

## Current status

Task 4 materializes the reviewed Pretendard v1.3.9 variable WOFF2 byte stream
and the locked shadcn/ui new-york-v4 source files. Their upstream and local
SHA256 values are recorded in the source map and registry lock.
No Apache-2.0 source is materialized, modified, or attributed as copied yet.

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
