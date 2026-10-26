"""W1 临时 mock 接口：给三端空壳一个能请求的 8000。

零依赖，只用标准库。W3 由 Django 接管 8000 后删除本文件。

用法：
    python tools/mock_api.py
    python tools/mock_api.py --port 18000
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

BODIES = {
    "/api/v1/health": {"ok": True, "version": "w1"},
    "/api/v1/episodes/ep_001": {"id": "ep_001", "status": "ARRIVED", "staff_contact": "stf_01"},
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = BODIES.get(self.path.split("?")[0])
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # 三个前端跑在 5173 / 5174 / 5176，缺这一行浏览器会拦掉跨端口请求
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print("[mock-api] " + fmt % args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"mock api: http://127.0.0.1:{args.port}/api/v1/health")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
