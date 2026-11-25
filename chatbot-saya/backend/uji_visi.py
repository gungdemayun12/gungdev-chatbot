import json
import urllib.error
import urllib.request

# PNG 4x4 merah (valid, kecil)
PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAFklEQVR42mP8z8BQz0AEYBxV"
    "SF+FjP9RAQCg2wcBAAAAAElFTkSuQmCC"
)

URL = "https://gungdev-chatbot-rq5l.vercel.app/chat"

for model in ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]:
    body = json.dumps(
        {
            "message": "Warna apa yang dominan pada gambar ini? Jawab satu kata.",
            "model": model,
            "images": ["data:image/png;base64," + PNG],
            "max_tokens": 100,
        }
    ).encode()

    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=110) as r:
            data = json.loads(r.read())
            isi = data.get("reply", "")
            print(f"{model:22s} -> HTTP {r.status} | {isi[:130]!r}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="replace")
        print(f"{model:22s} -> HTTP {exc.code} | {detail}")
    except Exception as exc:  # noqa: BLE001
        print(f"{model:22s} -> ERROR {type(exc).__name__}: {exc}")
