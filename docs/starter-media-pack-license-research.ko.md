# Starter media pack — 공식 라이선스 조사 ledger

> SSOT: Starter Media Pack Task 5 Step 1의 후보별 라이선스 판단과 evidence snapshot이다. 이 문서는 **실제 pack manifest도, pack release 승인도 아니다.** 각 후보는 실제 download 후 SHA-256·duration·FFmpeg/ffprobe format 검증을 통과해야만 manifest asset이 될 수 있다.

## 조사 기준

- 조사 일시: `2026-07-14T01:13:16+09:00`
- 허용: 권리자가 붙인 **CC0 1.0** 또는 commercial use, raw-file redistribution, technical conversion/adaptation을 모두 명시적으로 허용하는 동등 라이선스.
- CC0 근거: [CC0 1.0 legal code](https://creativecommons.org/publicdomain/zero/1.0/legalcode.en)는 reproduce/adapt/distribute와 commercial purposes를 명시한다. 이 페이지의 raw HTML SHA-256은 `001e3d1c905c18b1d034b34200cc952026abb38457c2294c23eaef7f6bda64df`다.
- 제외: NC, ND, 저작자/권리자 불명, asset page와 download file의 대응 불명, 혹은 standalone raw file 재배포를 금지하는 source.
- hash 방식: 각 `evidence_sha256`은 selection 시점에 official asset page를 HTTPS로 읽은 raw UTF-8 HTML의 SHA-256이다. 실제 release에서는 이 문서의 URL·hash·selection time을 각 `evidence/<asset_id>.txt`로 text snapshot화하고 그 파일 hash를 manifest에 기록한다. HTML은 pack에 포함하지 않는다.
- attribution: CC0의 법적 의무는 없지만, source가 요청한 credit은 `recommended_credit`으로 보존한다. product `ATTRIBUTION.md`는 manifest의 `attribution_required`가 true인 asset만 의무로 생성한다.

## 명시적으로 제외한 source

| source | 판정 | 이유 / official evidence |
| --- | --- | --- |
| Pixabay music | 제외 | 상업 영상 사용은 허용하지만 original/standalone audio distribution은 금지한다. starter pack은 사용자가 raw file을 받으므로 적합하지 않다. [FAQ](https://pixabay.com/service/faq/) raw HTML SHA-256: selection 시점 수집 대상이며, FAQ는 standalone distribution 금지를 명시한다. |
| Mixkit | 제외 | Free License가 commercial project use를 허용해도 item을 third party에게 make available/resell/sublicense하지 못하게 한다. [official information](https://mixkit.co/llm-info/)가 이를 명시한다. |
| Uppbeat free tier | 보류/제외 | 개별 plan·credit 조건과 raw redistribution 권한을 starter-pack 배포 계약으로 명확히 증명하지 못했다. 명확한 CC0 후보가 있으므로 사용하지 않는다. |

## 승인 후보 — music

모든 아래 page는 OpenGameArt의 원 author asset page이며 license field가 CC0이다. final pack에는 asset별로 320kbps CBR MP3로 변환한 뒤 source bytes와 converted bytes의 provenance를 기록한다. 변환은 CC0가 허용하지만, 품질·duration·loop는 아직 build gate다.

| candidate asset_id | title / creator | official asset page · evidence SHA-256 | source file | commercial | raw redistribute | convert/adapt | attribution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `music-mindstream` | MindStream — DST | [page](https://opengameart.org/content/mindstream) · `7cd0cb4b07e2a317d65db4aef06376e93f827899598077b67105429ea1170625` | [DST-MindStream.mp3](https://opengameart.org/sites/default/files/DST-MindStream.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `DST` recommended |
| `music-chills` | Chills — Holizna | [page](https://opengameart.org/content/chills) · `e98f02392dfa2a2b2d04221b980dc965958d0cd8c5b18ba8a194acaee228119a` | [01_holiznacc0_-_chills_0.mp3](https://opengameart.org/sites/default/files/01_holiznacc0_-_chills_0.mp3) | yes | yes | yes | not required; `Holizna` recommended |
| `music-one-step` | One Step at a time — Alex McCulloch / Pro Sensory | [page](https://opengameart.org/content/one-step-at-a-time) · `53cd8d41d1533dd19cba3a7281a0e4e1f534918d72a6f329fa11368f0e8e0f3d` | [OneStepAtATIme.wav](https://opengameart.org/sites/default/files/OneStepAtATIme.wav) | yes | yes | yes | not required; `Alex McCulloch` appreciated |
| `music-title-x` | Title-X — poinl | [page](https://opengameart.org/content/title-x) · `4359af8045e86b1f34dd8ec3903e61b0969fea138d3967055bdd837193ea52f2` | [gba1complete.mp3](https://opengameart.org/sites/default/files/gba1complete.mp3) | yes | yes | yes | not required; source requests notification only, not a license condition |
| `music-dialogue` | Dialogue — Umplix | [page](https://opengameart.org/content/dialogue) · `b3eab221be2a3208fefc029b5e6755680f1f2e1ec2666a0b2c5c41771af474cc` | [dialogue.wav](https://opengameart.org/sites/default/files/dialogue.wav) | yes | yes | yes | not required; `Umplix` recommended |
| `music-mysterious` | Mysterious — nene | [page](https://opengameart.org/content/mysterious) · `3f581ae0c62d2b4ab6ee6b7482e765aa7d50cd267ae12fc3c02c34ba9bcb999b` | [Mysterious.wav](https://opengameart.org/sites/default/files/Mysterious.wav) | yes | yes | yes | not required; `nene` recommended |
| `music-arcade-background` | arcade background music — aqrezes | [page](https://opengameart.org/content/arcade-background-music) · `4f7d80f475815e03dfb3b3808b2c6d3a24e7be8b0d5e1780d998a6c63172a5a2` | [arcade song.wav](https://opengameart.org/sites/default/files/arcade%20song.wav) | yes | yes | yes | not required; source asks for a project link only |

### 승인 확장 — FMA HoliznaCC0 개별 tracks

아래는 모두 FMA의 **개별 track** page를 HTTPS로 다시 읽어 raw-page hash를 남긴 CC0 asset이다. direct URL은 해당 page의 download/audio metadata에서 얻었다. creator 표시는 선택 사항이다.

| candidate asset_id | title | official page · evidence SHA-256 | direct MP3 |
| --- | --- | --- | --- |
| `music-i-dont-understand` | I Don't Understand A Thing — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/ocean-memory-lo-fi-chill/i-dont-understand-a-thing/) · `44fd695effd8ab6da75be18df130034cfa413191a063244b1e5105f525a657c5` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/Bz0kzsVrBpdQQ7bvzfxBXu2A3qAiKf22DV1YCXTE.mp3) |
| `music-classic` | Classic — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/rock-montage/classic/) · `bac5fb68e7cd7c45846e99111cc54812564080a119bed01c907e7498c5b97ab7` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/7KkRfJDj7UGWOt25IdkSNisMJSHXC7P9LwIUxIVL.mp3) |
| `music-i-need-you` | I Need You — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/be-happy-with-who-you-are/i-need-you/) · `066ed7a55d35df70a83ce71cbb617b4e85b5dba47841a7f51d0cd6ea86f80fea` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/bu0ohSLICdZU3aGVe3g0trLNZGUhg4Eu0xR2xRGL.mp3) |
| `music-what` | WHAT — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/straight-to-vhs/what-1/) · `2549d34ef580dd9f6eaafa4e3cf2e04f819225c80c07a798cea4b83b8fd9f2ff` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/3vrWVqmMWY1j88PFekPqRg26yxNY1DzupihQclB7.mp3) |
| `music-strange-enough` | Strange enough — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/left-overs/strange-enough/) · `846a5c45ce8169ba3cc659625aa96986dc1c3fe08f9327b986e57498bffe1d27` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/41EmPKcevRV0e6OKNCtEwADaYqLZqdJDwav8OhFM.mp3) |
| `music-down-in-basement` | Down In The Basement — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/forager/down-in-the-basement/) · `3b3738ea8eae0d829ed2d2e7c190370e6e50d95fb8c470c369085e98064139e4` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/mvhXzkdFO9pjnQRu9capsVMiLaOOxjvMSqsr6iFZ.mp3) |
| `music-whatever` | Whatever — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/lo-fi-and-chill/whatever-2/) · `bdac90d4c965f4095860687f744c5ba4dd509e816f99c785bd0058dc00cda37e` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/3pCv4Il8crs9bd9x5bJEWlqNFUQ6Truj4qLacyHa.mp3) |
| `music-bouncing` | Bouncing — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/power-pop/bouncing/) · `e524bbf8ddb787e48d355ffdf500951e1ca84f5c7f74798c00c6be57e5a1cfcf` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/jlbq3zqaGWo0V4gnuXk0cF9e5GVUbKGAqNb2C9T5.mp3) |
| `music-movement` | Movement — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/left-overs/movement-1/) · `175cfbb5af23cdfb01279d90e6dcc6ce648f28f7c953976c9e2fd190521d43af` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/drE9EuSyUbnMnhnrD7K0Pivsdsv4knYjQ2CpV7aX.mp3) |
| `music-lost-in-city` | Lost In The City — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/lost/lost-in-the-city/) · `6ddf702a107d0021a0720bfea53ae4a0f1763d3ee3dcce850898167ef5e49570` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/eBslofVZ8bIRqxjGjy3HJcclP5CZriMx1iv5yCAB.mp3) |
| `music-busted-ac` | Busted AC Unit — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/city-slacker/busted-ac-unit/) · `7f6dd718c70ec21fa650f47fba5e20ecc96c0d25bdb42e45dc080119314b6f4d` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/4BMpQmAdFMCQnZ1fyqZc0ZluDgJ3K59vCQjyJqWX.mp3) |
| `music-peaceful-drift` | Peaceful Drift — HoliznaCC0 | [page](https://freemusicarchive.org/music/holiznacc0/public-domain-lofi/peaceful-drift-lofi-nostalgic-calm/) · `0c48e149809c180ddf4188e344931910333c373f92aed9d5313a9655cc0e2b15` | [MP3](https://files.freemusicarchive.org/storage-freemusicarchive-org/tracks/SQvtLguk6S1VSthv0oXWycoB6ipUS0pt8jzAxxPq.mp3) |

**FMA extension judgement:** each row is CC0 1.0 and therefore commercial/raw redistribution/conversion=`true`, attribution=`false` (HoliznaCC0 recommended credit only).

## 승인 후보 — SFX

| candidate asset_id | title / creator | official asset page · evidence SHA-256 | source file | commercial | raw redistribute | convert/adapt | attribution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `sfx-power-up-v1` | Power-Up Sound Effects v1 — Spring Spring | [page](https://opengameart.org/content/power-up-sound-effects) · `30fe1f14ae356136a47b7aa89b6f35827aefdcb5313adc520ecf27521cecff09` | [power_up_sound_v1_0.ogg](https://opengameart.org/sites/default/files/power_up_sound_v1_0.ogg) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Spring Spring` recommended |
| `sfx-power-up-v2` | Power-Up Sound Effects v2 — Spring Spring | same page/hash above | [power_up_sound_v2_0.ogg](https://opengameart.org/sites/default/files/power_up_sound_v2_0.ogg) | yes | yes | yes | not required; `Spring Spring` recommended |
| `sfx-power-up-v3` | Power-Up Sound Effects v3 — Spring Spring | same page/hash above | [power_up_sound_v3_0.ogg](https://opengameart.org/sites/default/files/power_up_sound_v3_0.ogg) | yes | yes | yes | not required; `Spring Spring` recommended |

### 승인 확장 — OpenGameArt individual SFX files

아래 각 file은 source page의 `File(s)`에 개별적으로 열거되고, page creator와 `License(s): CC0`가 확인됐다. 두 source page는 raw HTML hash로 snapshot했으며 commercial/raw redistribution/conversion=`true`, attribution=`false`다.

| candidate asset_id | file / creator | official page · evidence SHA-256 | direct source |
| --- | --- | --- | --- |
| `sfx-n4-bell1` | bell1.mp3 — n4 | [Basic Sound Effects](https://opengameart.org/content/basic-sound-effects) · `749f72369861d45b675417da12866ec917d6a1405b3d3da6f526ced856ec3237` | [bell1_0.mp3](https://opengameart.org/sites/default/files/bell1_0.mp3) |
| `sfx-n4-bell2` | bell2.mp3 — n4 | same page/hash | [bell2_0.mp3](https://opengameart.org/sites/default/files/bell2_0.mp3) |
| `sfx-n4-bell3` | bell3.mp3 — n4 | same page/hash | [bell3_0.mp3](https://opengameart.org/sites/default/files/bell3_0.mp3) |
| `sfx-n4-button` | button.mp3 — n4 | same page/hash | [button_0.mp3](https://opengameart.org/sites/default/files/button_0.mp3) |
| `sfx-n4-coin1` | coin1.mp3 — n4 | same page/hash | [coin1_0.mp3](https://opengameart.org/sites/default/files/coin1_0.mp3) |
| `sfx-n4-coin2` | coin2.mp3 — n4 | same page/hash | [coin2_0.mp3](https://opengameart.org/sites/default/files/coin2_0.mp3) |
| `sfx-n4-explosion` | explosion.mp3 — n4 | same page/hash | [explosion_0.mp3](https://opengameart.org/sites/default/files/explosion_0.mp3) |
| `sfx-n4-explosion-distant` | explosion_distant.mp3 — n4 | same page/hash | [explosion_distant_0.mp3](https://opengameart.org/sites/default/files/explosion_distant_0.mp3) |
| `sfx-n4-gunshot` | gunshot.mp3 — n4 | same page/hash | [gunshot_0.mp3](https://opengameart.org/sites/default/files/gunshot_0.mp3) |
| `sfx-n4-splash1` | splash1.mp3 — n4 | same page/hash | [splash1_0.mp3](https://opengameart.org/sites/default/files/splash1_0.mp3) |
| `sfx-n4-splash2` | splash2.mp3 — n4 | same page/hash | [splash2_0.mp3](https://opengameart.org/sites/default/files/splash2_0.mp3) |
| `sfx-n4-success` | success.mp3 — n4 | same page/hash | [success_0.mp3](https://opengameart.org/sites/default/files/success_0.mp3) |
| `sfx-n4-tom1` | tom1.mp3 — n4 | same page/hash | [tom1_0.mp3](https://opengameart.org/sites/default/files/tom1_0.mp3) |
| `sfx-n4-tom2` | tom2.mp3 — n4 | same page/hash | [tom2_0.mp3](https://opengameart.org/sites/default/files/tom2_0.mp3) |
| `sfx-n4-tom3` | tom3.mp3 — n4 | same page/hash | [tom3_0.mp3](https://opengameart.org/sites/default/files/tom3_0.mp3) |
| `sfx-n4-tom4` | tom4.mp3 — n4 | same page/hash | [tom4_0.mp3](https://opengameart.org/sites/default/files/tom4_0.mp3) |
| `sfx-n4-tom5` | tom5.mp3 — n4 | same page/hash | [tom5_0.mp3](https://opengameart.org/sites/default/files/tom5_0.mp3) |
| `sfx-n4-tom6` | tom6.mp3 — n4 | same page/hash | [tom6_0.mp3](https://opengameart.org/sites/default/files/tom6_0.mp3) |
| `sfx-n4-vibrophone1` | vibrophone1.mp3 — n4 | same page/hash | [vibrophone1_0.mp3](https://opengameart.org/sites/default/files/vibrophone1_0.mp3) |
| `sfx-n4-vibrophone2` | vibrophone2.mp3 — n4 | same page/hash | [vibrophone2_0.mp3](https://opengameart.org/sites/default/files/vibrophone2_0.mp3) |
| `sfx-pop1` | pop1.ogg — cogitollc | [Pop sounds](https://opengameart.org/content/pop-sounds) · `575419ccab01bfd14320fb3bebf39e7a5c51035dea89e9823b5ee913acead8a4` | [pop1.ogg](https://opengameart.org/sites/default/files/pop1.ogg) |
| `sfx-pop2` | pop2.ogg — cogitollc | same page/hash | [pop2.ogg](https://opengameart.org/sites/default/files/pop2.ogg) |
| `sfx-pop3` | pop3.ogg — cogitollc | same page/hash | [pop3.ogg](https://opengameart.org/sites/default/files/pop3.ogg) |
| `sfx-pop4` | pop4.ogg — cogitollc | same page/hash | [pop4.ogg](https://opengameart.org/sites/default/files/pop4.ogg) |
| `sfx-pop5` | pop5.ogg — cogitollc | same page/hash | [pop5.ogg](https://opengameart.org/sites/default/files/pop5.ogg) |
| `sfx-pop6` | pop6.ogg — cogitollc | same page/hash | [pop6.ogg](https://opengameart.org/sites/default/files/pop6.ogg) |
| `sfx-pop7` | pop7.ogg — cogitollc | same page/hash | [pop7.ogg](https://opengameart.org/sites/default/files/pop7.ogg) |
| `sfx-pop8` | pop8.ogg — cogitollc | same page/hash | [pop8.ogg](https://opengameart.org/sites/default/files/pop8.ogg) |
| `sfx-pop9` | pop9.ogg — cogitollc | same page/hash | [pop9.ogg](https://opengameart.org/sites/default/files/pop9.ogg) |
| `sfx-pop10` | pop10.ogg — cogitollc | same page/hash | [pop10.ogg](https://opengameart.org/sites/default/files/pop10.ogg) |

## Gate 판정과 다음 행동

- **approved research candidate (19 music / 33 SFX): PASS.** 각 후보는 author page, creator, exact source file, CC0 license, official license evidence hash, commercial/raw redistribution/conversion 판단을 갖췄다.
- **starter-v1 research gate (30 music / 100 SFX): NOT GREEN.** 19/30 music, 33/100 SFX만 asset-level evidence가 확정됐다. 따라서 300–500 MiB pack build는 아직 시작하지 않는다.
- 다음 작업은 같은 기준으로 나머지 11 music·67 SFX를 asset-level ledger에 채운 뒤, 다운로드 source hash → transcode/probe → evidence text snapshot → manifest build 순서로 진행한다.
