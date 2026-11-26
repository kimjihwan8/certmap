"""정답지 라벨링 도구를 띄운다. 브라우저에서 고르면 바로 CSV에 저장된다.

사용: python3 scripts/label_server.py dev|test   → 브라우저가 자동으로 열린다 (보통 http://localhost:8765, 사용 중이면 다음 번호)
      (끝내려면 터미널에서 Ctrl+C. 다시 켜면 이어서 할 수 있다)
읽는 것: data/labels/{set}_items.json   (make_pairs.py 가 만든 300건)
쓰는 것: data/labels/{set}_human.csv    (사람이 단 라벨 — AI 라벨과 비교용. item_id, answer, memo, labeled_at)

answer 값:
    상가업소번호   그 후보가 인증과 같은 가게
    NONE         후보 중에 같은 가게가 없다 (상가에 없거나, 이름이 완전히 바뀜)
    UNSURE       판단할 수 없다 (나중에 다시 보거나 채점에서 뺀다)

파이썬 표준 라이브러리만 쓴다. 화면은 tools/label.html 이다.
"""
import csv
import json
import os
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WHICH = sys.argv[1] if len(sys.argv) > 1 else "test"
ITEMS = os.path.join(ROOT, "data", "labels", f"{WHICH}_items.json")
LABELS = os.path.join(ROOT, "data", "labels", f"{WHICH}_human.csv")
PAGE = os.path.join(ROOT, "tools", "label.html")
PORT = 8765
FIELDS = ["item_id", "answer", "memo", "labeled_at"]


def public_items():
    """채점용 필드(_ 로 시작)는 빼고 보낸다. 라벨링하는 사람이 규칙 답을 못 보게."""
    with open(ITEMS, encoding="utf-8") as f:
        items = json.load(f)
    return [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]


def read_labels():
    """item_id → 라벨 한 줄. 파일이 없으면 빈 사전."""
    if not os.path.exists(LABELS):
        return {}
    with open(LABELS, encoding="utf-8") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def write_label(item_id, answer, memo):
    """한 건을 저장한다. 같은 item_id 를 다시 고르면 덮어쓴다(고쳐 쓰기).

    매번 파일 전체를 새로 쓴다. 300줄이라 빠르고, 중간에 꺼져도 파일이 깨지지 않게
    임시 파일에 쓴 뒤 바꿔치기한다.
    """
    labels = read_labels()
    labels[item_id] = {"item_id": item_id, "answer": answer, "memo": memo,
                       "labeled_at": datetime.now().isoformat(timespec="seconds")}
    tmp = LABELS + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(labels.values())
    os.replace(tmp, LABELS)


class Handler(BaseHTTPRequestHandler):
    """GET /        화면
       GET /items   300건
       GET /labels  지금까지 단 라벨
       POST /label  라벨 하나 저장  {item_id, answer, memo}"""

    def _send(self, body, ctype="application/json; charset=utf-8", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            with open(PAGE, "rb") as f:
                self._send(f.read(), "text/html; charset=utf-8")
        elif self.path == "/items":
            self._send(public_items())
        elif self.path == "/labels":
            self._send(read_labels())
        else:
            self._send({"error": "not found"}, code=404)

    def do_POST(self):
        if self.path != "/label":
            return self._send({"error": "not found"}, code=404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        write_label(body["item_id"], body["answer"], body.get("memo", ""))
        self._send({"ok": True})

    def log_message(self, *args):   # 요청마다 찍히는 로그는 끈다
        pass


def main():
    if not os.path.exists(ITEMS):
        raise SystemExit(f"{ITEMS} 가 없다. 먼저 python3 scripts/make_pairs.py {WHICH}")
    # 포트를 먼저 잡고 나서 브라우저를 연다. 다른 프로그램이 쓰고 있으면 다음 번호를 시도한다.
    # 127.0.0.1 에만 연다 — 같은 와이파이의 다른 기기에서는 접속할 수 없다
    for port in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"{PORT}~{PORT + 19} 포트가 모두 사용 중이다")
    done = len(read_labels())
    url = f"http://localhost:{port}"
    print(f"라벨링 도구: {url}   (지금까지 {done}건, Ctrl+C 로 종료)")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
