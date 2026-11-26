"""의미 검색 시험지 판정 도구. 브라우저에서 맞음/아님을 누르면 바로 CSV에 저장된다. 결정 일지 34번.

사용: python3 scripts/sem_label_server.py   → 브라우저가 자동으로 열린다 (끝내려면 Ctrl+C, 다시 켜면 이어서)
읽는 것: data/labels/sem_queries.csv  (질문)
         data/labels/sem_pool.csv     (질문마다 각 검색 방식이 뽑은 가게 — packages/db 의 sem-pool 이 만든다)
         data/labels/sem_docs.csv     (가게 소개글)
쓰는 것: data/labels/sem_judgments.csv (query_id, store_id, label, labeled_at)

label 값:  1 맞음  /  0 아님  /  U 애매 (채점에서 뺀다)

판정 기준: "이 소개글을 근거로, 이 가게가 질문에 맞는 곳이라고 말할 수 있나?"
    검색은 소개글만 보고 찾으므로, 판정도 소개글에 적힌 것만 본다. 실제로는 맞는 가게라도 소개글에 근거가 없으면 '아님'.

공정하게 판정하려고 어느 방식이 몇 등으로 뽑았는지는 화면에 보여주지 않고, 질문 안에서 순서를 섞는다.
파이썬 표준 라이브러리만 쓴다. 화면은 tools/sem_label.html 이다.
"""
import csv
import json
import os
import random
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LABELS_DIR = os.path.join(ROOT, "data", "labels")
JUDGMENTS = os.path.join(LABELS_DIR, "sem_judgments.csv")
PAGE = os.path.join(ROOT, "tools", "sem_label.html")
PORT = 8785
FIELDS = ["query_id", "store_id", "label", "labeled_at"]


def read_csv(name):
    with open(os.path.join(LABELS_DIR, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def items():
    """판정할 (질문, 가게) 목록. 같은 쌍을 여러 방식이 뽑았어도 한 번만. 질문 순서대로, 질문 안에서는 섞는다."""
    queries = {q["query_id"]: q for q in read_csv("sem_queries.csv")}
    docs = {d["store_id"]: d for d in read_csv("sem_docs.csv")}
    pairs = sorted({(p["query_id"], p["store_id"]) for p in read_csv("sem_pool.csv")})
    rng = random.Random(20261126)          # 같은 순서가 나오게 고정 (다시 켜도 순서가 그대로)
    out = []
    for qid in sorted(queries):
        group = [s for q, s in pairs if q == qid]
        rng.shuffle(group)
        for sid in group:
            d = docs[sid]
            out.append({"query_id": qid, "query": queries[qid]["query"], "kind": queries[qid]["kind"],
                        "store_id": sid, "name": d["name"], "sgg": d["sgg"], "text": d["text"]})
    return out


def read_judgments():
    """'질문|가게' → 판정 한 줄"""
    if not os.path.exists(JUDGMENTS):
        return {}
    with open(JUDGMENTS, encoding="utf-8") as f:
        return {f'{r["query_id"]}|{r["store_id"]}': r for r in csv.DictReader(f)}


def write_judgment(query_id, store_id, label):
    """한 건 저장. 같은 쌍을 다시 누르면 덮어쓴다. 중간에 꺼져도 파일이 깨지지 않게 임시 파일에 쓰고 바꿔치기한다."""
    rows = read_judgments()
    rows[f"{query_id}|{store_id}"] = {"query_id": query_id, "store_id": store_id, "label": label,
                                       "labeled_at": datetime.now().isoformat(timespec="seconds")}
    tmp = JUDGMENTS + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows.values())
    os.replace(tmp, JUDGMENTS)


class Handler(BaseHTTPRequestHandler):
    """GET / 화면 · GET /items 판정할 목록 · GET /judgments 지금까지 판정 · POST /judge {query_id, store_id, label}"""

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
            self._send(items())
        elif self.path == "/judgments":
            self._send(read_judgments())
        else:
            self._send({"error": "not found"}, code=404)

    def do_POST(self):
        if self.path != "/judge":
            return self._send({"error": "not found"}, code=404)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body.get("label") not in ("1", "0", "U"):
            return self._send({"error": "label 은 1, 0, U 중 하나"}, code=400)
        write_judgment(body["query_id"], body["store_id"], body["label"])
        self._send({"ok": True})

    def log_message(self, *args):   # 요청마다 찍히는 로그는 끈다
        pass


def main():
    if not os.path.exists(os.path.join(LABELS_DIR, "sem_pool.csv")):
        raise SystemExit("sem_pool.csv 가 없다. 먼저: pnpm --filter @restaurant-map/db sem-pool")
    # 포트를 먼저 잡고 나서 브라우저를 연다. 127.0.0.1 에만 연다 (같은 와이파이의 다른 기기에서는 접속할 수 없다)
    for port in range(PORT, PORT + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"{PORT}~{PORT + 19} 포트가 모두 사용 중이다")
    total, done = len(items()), len(read_judgments())
    url = f"http://localhost:{port}"
    print(f"의미 검색 판정 도구: {url}   ({done}/{total} 판정함, Ctrl+C 로 종료)")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
