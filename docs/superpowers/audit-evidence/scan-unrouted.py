"""계획 I Task 0 Step 4 (d): 백엔드 경로 중 프런트가 안 부르는 것(휴리스틱).
사용법(저장소 루트): .venv/Scripts/python.exe docs/superpowers/audit-evidence/scan-unrouted.py
routers/*.py 의 APIRouter(prefix=...) + @router.<method>("...") 를 읽어, 경로의 마지막 고정 조각이
apps/web/src/**/*.ts(x)(시험 제외)에 '/<조각>' 으로 나오지 않는 것을 낸다. 템플릿 문자열로 부르는 것이 섞일 수 있다.
"""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[3]
web = "\n".join(
    p.read_text(encoding="utf-8", errors="ignore")
    for p in (root / "apps/web/src").rglob("*")
    if p.suffix in {".ts", ".tsx"} and ".test." not in p.name
)
rows = []
for router in sorted((root / "services/api/src/videobox_api/routers").glob("*.py")):
    text = router.read_text(encoding="utf-8", errors="ignore")
    prefix_match = re.search(r"APIRouter\([^)]*prefix\s*=\s*[\"']([^\"']*)[\"']", text, re.S)
    prefix = prefix_match.group(1) if prefix_match else ""
    for m in re.finditer(r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']", text):
        full = (prefix + m.group(2)).rstrip("/") or "/"
        fixed = [seg for seg in full.split("/") if seg and not seg.startswith("{")]
        if not fixed:
            continue
        if f"/{fixed[-1]}" not in web:
            rows.append((router.name, m.group(1).upper(), full))
print(f"프런트 소스에 마지막 고정 조각이 안 보이는 경로: {len(rows)}")
for name, method, full in rows:
    print(f"{name:34s} {method:6s} {full}")
