"""브라우저가 보내는 그대로 — 파일명을 원시 UTF-8 바이트로 실어 보낸다."""
import json, sys, urllib.request, uuid
from pathlib import Path

path = Path(sys.argv[1])
url = sys.argv[2]
boundary = "----videobox" + uuid.uuid4().hex
body = (
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
    f"Content-Type: video/mp4\r\n\r\n"
).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
request = urllib.request.Request(url, data=body, method="POST")
request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
with urllib.request.urlopen(request, timeout=300) as response:
    print(response.status, response.read().decode("utf-8"))
