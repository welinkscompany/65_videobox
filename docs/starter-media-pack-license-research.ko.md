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

### 승인 확장 — OpenGameArt individual music

각 행은 creator page의 Music + CC0 field와 individual direct file을 함께 확인했다. 모두 commercial/raw redistribution/conversion=`true`, attribution=`false`다.

| candidate asset_id | title / creator | official page · evidence SHA-256 | direct source |
| --- | --- | --- | --- |

### 승인 확장 — OpenGameArt individual music (브이로그용, 2026-09-05)

owner 지시(2026-09-05): "브이로그용 30곡 찾아서 넣어줘. 게임음악은 다 삭제해."

세어 보니 기존 30곡은 **전부 게임 음악이 아니었다** -- FMA HoliznaCC0의
lo-fi/chill 12곡이 이미 들어 있었다(`Ocean Memory Lo-Fi Chill` 앨범 등).
그래서 명백한 게임 음악 12곡만 빼고(8bit 타이틀·아케이드·초원 테마·포털…)
그 자리를 같은 규칙(CC0 + raw 재배포 허용)으로 채웠다.

**곡을 듣고 고른 것이 아니다.** OpenGameArt에서 라이선스가 CC0로 명시된
음악만 추린 뒤 제목·태그로 골랐다 -- owner가 들어 보고 빼라고 하면 뺀다.

| candidate asset_id | title / creator | official asset page · evidence SHA-256 | source file | commercial | raw redistribute | convert/adapt | attribution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `music-chill-lofi` | Chill Lofi Inspired — omfgdude | [page](https://opengameart.org/content/chill-lofi-inspired) · `dc3f91195a90ad1d24e1a124ca9cdf1b4da8dee5d1672ae9f13b6624b608cd4f` | [source](https://opengameart.org/sites/default/files/ChillLofiR_0.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `omfgdude` recommended |
| `music-lofi-compilation` | Lofi Compilation — TAD | [page](https://opengameart.org/content/lofi-compilation) · `1f51ab0e78a63755e8e6584eb95dd19e9c2cf28e902a4b44ac59157bf7a56afe` | [source](https://opengameart.org/sites/default/files/A%20cup%20of%20tea_0.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `TAD` recommended |
| `music-apple-cider` | Apple Cider — Zane Little Music | [page](https://opengameart.org/content/apple-cider) · `e1b755fa6d289efbec699095aec4232f04d4944767dccc10e8219f6caaf7f97a` | [source](https://opengameart.org/sites/default/files/apple_cider.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Zane Little Music` recommended |
| `music-napping-cloud` | Napping on a Cloud — congusbongus | [page](https://opengameart.org/content/napping-on-a-cloud) · `ddd656fe9b296049c88d1dcd6fa212b36f8a07f99535a1ed3ffd6a880a92b9b9` | [source](https://opengameart.org/sites/default/files/napping_on_a_cloud.ogg) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `congusbongus` recommended |
| `music-calm-loop` | Calm Loop — wipics | [page](https://opengameart.org/content/calm-loop) · `2b1981397965f70b7b7d9a2e8b0eb2042d9aa430ac0bc24b7e0f905a72999ae7` | [source](https://opengameart.org/sites/default/files/Relaxing_0.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `wipics` recommended |
| `music-chill-fever` | A Chill Fever — Pro Sensory | [page](https://opengameart.org/content/a-chill-fever-loopable) · `a81fa924820a4f7342e8e230bc2573ba2d3268155cbee66403046143dacc5b64` | [source](https://opengameart.org/sites/default/files/a_chill_fever_0.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Pro Sensory` recommended |
| `music-mocha-frapp` | Mocha Frapp — Pro Sensory | [page](https://opengameart.org/content/mocha-frapp) · `7b63c3e43052d426014e3789615e67b4cd63d3bc60cf3217e444df349e032af4` | [source](https://opengameart.org/sites/default/files/mocha_frapp_2.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Pro Sensory` recommended |
| `music-slow-stride` | Slow Stride — isaiah658 | [page](https://opengameart.org/content/slow-stride) · `7c8ac37890588e38f401e864ec5f40b4fa40517546c24067073fc87771cb4157` | [source](https://opengameart.org/sites/default/files/Slow%20Stride%20Loop.flac) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `isaiah658` recommended |
| `music-calm-piano` | Calm Piano 1 — cynicmusic | [page](https://opengameart.org/content/calm-piano-1-vaporware) · `54274f92b2fca2a08aab7359c3ca4f79b05e93775b3f5cc4c0ca0268f0664fb0` | [source](https://opengameart.org/sites/default/files/003_Vaporware_2.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `cynicmusic` recommended |
| `music-calm-ambient` | Calm Ambient 3 — cynicmusic | [page](https://opengameart.org/content/calm-ambient-3-lifewave-2k) · `600a222081b2619cf8736148867cd76bcb2956911234273c4843a1a3dd48fbfd` | [source](https://opengameart.org/sites/default/files/006_lifeWave2k_0.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `cynicmusic` recommended |
| `music-lofi-again` | Lofi Again — omfgdude | [page](https://opengameart.org/content/lofi-again) · `c64df46aec7c3d11929f4e9626bb911d0d2a618d3cac7e95bf24466695f73c1b` | [source](https://opengameart.org/sites/default/files/lofiagain.ogg) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `omfgdude` recommended |
| `music-ambient-relax` | Ambient Relaxing Loop — isaiah658 | [page](https://opengameart.org/content/ambient-relaxing-loop) · `e8ef7e6cab4ad976410fb12708b0f45ca0c269fd87cd9baa1a1f419ce31eb888` | [source](https://opengameart.org/sites/default/files/Ambient-Loop-isaiah658_0.ogg) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `isaiah658` recommended |

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

### 승인 확장 — Various Sound Effects (47 individual WAV)

`Spring Spring`의 [official CC0 page](https://opengameart.org/content/various-sound-effects-0) raw HTML SHA-256은 `925a53041ff971e46ad4b5e8ac0857ce753ba0dcad4e6ddf30dac20031f14682`다. 아래 **각 token이 one asset**이며 direct source는 `https://opengameart.org/sites/default/files/<file>`이다. 모든 candidate의 commercial/raw redistribution/conversion=`true`, attribution=`false`다.

`sfx-various-bangs=bangs.wav`, `sfx-various-beep1=beep1.wav`, `sfx-various-click=click_1.wav`, `sfx-various-fall=fall_0.wav`, `sfx-various-glug=glug.wav`, `sfx-various-nom=nom.wav`, `sfx-various-pop=pop.wav`, `sfx-various-powered-door=powered_door.wav`, `sfx-various-weeds=rustling_of_the_weeds.wav`, `sfx-various-scooter=scooter_p.wav`, `sfx-various-swim=swim_0.wav`, `sfx-various-tap-stone=tap_stone.wav`, `sfx-various-tick=tick_0.wav`, `sfx-various-ambient-impact=snd_ambient_impact1.wav`, `sfx-various-footsteps=snd_footsteps1.wav`, `sfx-various-menu-move=snd_menu_move.wav`, `sfx-various-menu-select=snd_menu_select.wav`, `sfx-various-npc-message=snd_npc_message.wav`, .

### 승인 확장 — RPG / battle individual SFX (20)

| candidate asset_id | creator / official page · evidence SHA-256 | direct source |
| --- | --- | --- |
| `sfx-rpg-door` | same page/hash | [door_1.ogg](https://opengameart.org/sites/default/files/door_1.ogg) |
| `sfx-rpg-grass` | same page/hash | [grass_1.ogg](https://opengameart.org/sites/default/files/grass_1.ogg) |
| `sfx-rpg-steps` | same page/hash | [steps_1.ogg](https://opengameart.org/sites/default/files/steps_1.ogg) |

## Gate 판정과 다음 행동

- **approved research candidate (30 music / 100 SFX): PASS.** 각 후보는 author page, creator, exact source file, CC0 license, official license evidence hash, commercial/raw redistribution/conversion 판단을 갖췄다. Direct asset URL 130개와 official asset page URL 36개를 2026-07-14 HTTPS HEAD 200으로 다시 확인했다.
- **starter-v1 research gate (30 music / 100 SFX): GREEN.** 이것은 license/provenance research만 green이라는 뜻이다. 실제 source bytes, duration, codec, converted bytes와 manifest integrity는 아직 검증되지 않았다.
- 다음 작업은 이 ledger의 approved asset만 대상으로 source download SHA-256 → transcode/probe → evidence text snapshot → manifest build 순서로 진행한다. 이 순서를 건너뛰어 build artifact를 배포하지 않는다.

### 승인 확장 — 브이로그용 SFX (2026-09-05)

**왜 넣나.** 효과음 100개가 전부 게임용이었다 -- 대포·총소리·박쥐날개·보물.
대표님은 1인칭 내레이션 + B-roll 브이로그를 만든다. 유진에게 "팝 하고 터지는
짧은 소리 넣어줘"라고 했더니 RPG 폭발음이 나왔는데, 유진 탓이 아니라 **재료가
그것뿐**이어서였다. 브이로그가 실제로 쓰는 세 가지를 넣는다: 장면 전환음(휙),
타이핑, 종이.

**기존 것은 아직 빼지 않았다.** 게임 전용을 덜어내는 것은 지금 만들어 둔
영상이 그 소리를 참조하고 있는지 확인한 뒤에 한다 -- 참조를 끊으면 되돌릴 수 없다.

**묶음 주소 표기.** 이 세 출처는 개별 파일 주소가 없고 zip으로만 받는다.
`...zip#묶음안/경로.wav`로 적으면 빌더가 그 파일 하나만 꺼내 쓴다. 보관하는
원본·해시·증거는 전부 **꺼낸 파일**의 것이다.

| asset_id | 제목 — 만든이 | 출처 페이지 · 증거 SHA-256 | 받는 주소 | CC0 | 원본 재배포 | 상업적 사용 | 표기 |
|---|---|---|---|---|---|---|---|
| `sfx-swish-1` | Swishes Sound Pack swish-1 — artisticdude | [page](https://opengameart.org/content/swishes-sound-pack) · `565b61c868a7e6baa08945ee502114fa788accf092bef48166bfba4da497e1d9` | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-1.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-2` | Swishes Sound Pack swish-2 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-2.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-3` | Swishes Sound Pack swish-3 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-3.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-4` | Swishes Sound Pack swish-4 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-4.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-5` | Swishes Sound Pack swish-5 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-5.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-6` | Swishes Sound Pack swish-6 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-6.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-7` | Swishes Sound Pack swish-7 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-7.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-8` | Swishes Sound Pack swish-8 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-8.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-9` | Swishes Sound Pack swish-9 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-9.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-10` | Swishes Sound Pack swish-10 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-10.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-11` | Swishes Sound Pack swish-11 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-11.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-12` | Swishes Sound Pack swish-12 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-12.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-swish-13` | Swishes Sound Pack swish-13 — artisticdude | same page/hash above | [swishes.zip](https://opengameart.org/sites/default/files/swishes.zip#swishes/swish-13.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `artisticdude` recommended |
| `sfx-typing-slow` | Keyboard Soundpack #1 generated-003_slow.wav — unicaegames | [page](https://opengameart.org/content/keyboard-soundpack-1-typing-and-single-keystrokes) · `58962c9b4dc194070114c4b86475ec2e68751dfcdc1ba6cdbe8a0c9c15511fa3` | [keyboard.zip](https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip#Generated Typing/generated-003_slow.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `unicaegames` recommended |
| `sfx-typing-medium` | Keyboard Soundpack #1 generated-004_medium.wav — unicaegames | same page/hash above | [keyboard.zip](https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip#Generated Typing/generated-004_medium.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `unicaegames` recommended |
| `sfx-typing-fast` | Keyboard Soundpack #1 generated-005_fast.wav — unicaegames | same page/hash above | [keyboard.zip](https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip#Generated Typing/generated-005_fast.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `unicaegames` recommended |
| `sfx-keypress-1` | Keyboard Soundpack #1 keypress-001.wav — unicaegames | same page/hash above | [keyboard.zip](https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip#Single Keys/keypress-001.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `unicaegames` recommended |
| `sfx-keypress-2` | Keyboard Soundpack #1 keypress-005.wav — unicaegames | same page/hash above | [keyboard.zip](https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip#Single Keys/keypress-005.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `unicaegames` recommended |
| `sfx-keypress-3` | Keyboard Soundpack #1 keypress-010.wav — unicaegames | same page/hash above | [keyboard.zip](https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip#Single Keys/keypress-010.wav) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `unicaegames` recommended |
| `sfx-paper-1` | Various Paper Sound Effects paper_sound_-_1.mp3 — Luckius | [page](https://opengameart.org/content/various-paper-sound-effects) · `721d853b13a449b3cb31375682a9a37b3b65f0d11540af76903575654b7eb482` | [paper_sound_-_1.mp3](https://opengameart.org/sites/default/files/paper_sound_-_1.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Luckius` recommended |
| `sfx-paper-2` | Various Paper Sound Effects paper_sound_-_2.mp3 — Luckius | same page/hash above | [paper_sound_-_2.mp3](https://opengameart.org/sites/default/files/paper_sound_-_2.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Luckius` recommended |
| `sfx-paper-3` | Various Paper Sound Effects paper_sound_-_3.mp3 — Luckius | same page/hash above | [paper_sound_-_3.mp3](https://opengameart.org/sites/default/files/paper_sound_-_3.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Luckius` recommended |
| `sfx-paper-ripped` | Various Paper Sound Effects paper_ripped_-_1.mp3 — Luckius | same page/hash above | [paper_ripped_-_1.mp3](https://opengameart.org/sites/default/files/paper_ripped_-_1.mp3) | yes (CC0) | yes (CC0) | yes (CC0) | not required; `Luckius` recommended |

### 승인 축소 — 게임 전용 효과음 49개 제거 (2026-09-06)

owner가 음악에 대해 한 말을 효과음에도 적용했다(위임): "게임음악은 다 삭제해.
어차피 필요없잖아."

1인칭 내레이션 + B-roll 브이로그에 **대포 8종·총소리·폭발 4종·야구방망이·
몬스터 피격·박쥐날개·보물·순간이동·신음**은 쓸 자리가 없다. 유진에게 "팝 하고
터지는 짧은 소리"를 시켰더니 RPG 폭발음이 나온 것도 이 재료들 때문이었다.

**쓸 수 있는 것은 남겼다**(74개): 종 3·단추·성공 알림·동전 2·물 튀는 소리 2·
북 6·비브라폰 2·딸깍·팝 11·똑딱·삐·메뉴 2·발소리 2·문 2·풀숲·풀 스치는 소리·
마시는 소리·먹는 소리·스쿠터·헤엄·톡 두드리는 소리·떨어지는 소리·쾅·기운 차는
소리 3, 그리고 2026-09-05에 넣은 브이로그용 23개(전환음 13·타이핑 3·키 3·종이 4).

**빼기 전에 참조를 확인했다.** 팩 효과음을 가리키는 프로젝트가 하나도 없었다
(라이브러리 등록부에만 있었다) -- 참조를 끊으면 되돌릴 수 없으므로 이 확인 없이
빼지 않는다.

123 → 74. 전체 후보는 153 → 104(음악 30 + 효과음 74).
