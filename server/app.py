#!/usr/bin/env python3
"""homework-lab 本地服务器 —— 学生端网页 API + 静态资源。

纯标准库（http.server），零依赖。
启动：python3 server/app.py
环境变量：HOMELAB_PORT（默认 8877）、HOMELAB_DB（默认 data/homework.db）
只绑定 127.0.0.1，仅本机可用。

安全约定：发给前端的试卷数据绝不包含 answer / explanation 字段（批改后才会出现在结果页）。
"""
import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("HOMELAB_PORT", "8877"))
STATIC = Path(__file__).resolve().parent / "static"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeworkLab/1.0"

    # ---------------- 基础工具 ----------------
    def _send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json(status, {"error": message})

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("请求体为空")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("请求体不是合法 JSON")

    def log_message(self, fmt, *args):
        pass  # 安静模式；调试时可去掉本方法

    # ---------------- API ----------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/state":
                with db.connect() as conn:
                    return self._send_json(200, db.state_snapshot(conn))
            m = re.fullmatch(r"/api/homeworks/(\d+)", path)
            if m:
                with db.connect() as conn:
                    paper = db.paper_for_student(conn, int(m.group(1)))
                if not paper:
                    return self._send_error_json(404, "试卷不存在")
                return self._send_json(200, paper)
            m = re.fullmatch(r"/api/submissions/(\d+)", path)
            if m:
                with db.connect() as conn:
                    detail = db.submission_detail(conn, int(m.group(1)))
                if not detail:
                    return self._send_error_json(404, "提交不存在")
                return self._send_json(200, detail)
            if path == "/api/review":
                with db.connect() as conn:
                    items = db.wrong_items(conn)
                grouped = {}
                for it in items:
                    grouped.setdefault(it["knowledge_point"] or "未标注", []).append(it)
                return self._send_json(200, {"groups": grouped, "count": len(items)})
            if path == "/api/knowledge":
                with db.connect() as conn:
                    kps = db.knowledge_table(conn)
                    wrongs = db.wrong_items(conn)
                by_kp = {}
                for it in wrongs:
                    by_kp.setdefault(it["knowledge_point"] or "未标注", []).append(it)
                return self._send_json(200, {"knowledge": kps, "wrongs_by_kp": by_kp})
            return self._serve_static(path)
        except Exception as e:  # noqa: BLE001 —— 本地服务，返回给前端便于排障
            return self._send_error_json(500, f"服务器错误: {e}")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_body()
        except ValueError as e:
            return self._send_error_json(400, str(e))
        try:
            if path == "/api/submit":
                return self._handle_submit(body)
            if path == "/api/request":
                kp = (body.get("knowledge_point") or "").strip()
                if not kp:
                    return self._send_error_json(400, "knowledge_point 不能为空")
                with db.connect() as conn:
                    rid = db.add_request(conn, kp, (body.get("note") or "").strip())
                return self._send_json(200, {"id": rid})
            return self._send_error_json(404, "未知接口")
        except ValueError as e:
            return self._send_error_json(400, str(e))
        except Exception as e:  # noqa: BLE001
            return self._send_error_json(500, f"服务器错误: {e}")

    def _handle_submit(self, body):
        hw_id = body.get("homework_id")
        answers = body.get("answers")
        if not isinstance(hw_id, int) or not isinstance(answers, dict) or not answers:
            raise ValueError("需要 homework_id(int) 和 answers(非空对象)")
        with db.connect() as conn:
            hw = conn.execute("SELECT * FROM homeworks WHERE id=?", (hw_id,)).fetchone()
            if not hw:
                raise ValueError(f"试卷 #{hw_id} 不存在")
            if hw["status"] not in ("published", "archived"):
                raise ValueError("该试卷当前不可作答")
            qs = conn.execute("SELECT id FROM questions WHERE homework_id=?", (hw_id,)).fetchall()
            qids = {str(q["id"]) for q in qs}
            clean = {}
            for k, v in answers.items():
                if k not in qids:
                    raise ValueError(f"答案包含无效题目 id: {k}")
                if isinstance(v, dict):
                    clean[k] = {str(bk): (bv or "") for bk, bv in v.items()}
                else:
                    clean[k] = v or ""
            cur = conn.execute(
                "INSERT INTO submissions (homework_id, answers) VALUES (?,?)",
                (hw_id, json.dumps(clean, ensure_ascii=False)),
            )
        return self._send_json(200, {"submission_id": cur.lastrowid,
                                     "message": "已交卷，等待批改"})

    # ---------------- 静态文件 ----------------
    def _serve_static(self, path):
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/")
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            self._send_error_json(404, "资源不存在")
            return
        data = target.read_bytes()
        ctype = MIME.get(target.suffix.lower()) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if target.suffix == ".html":
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "max-age=60")
        self.end_headers()
        self.wfile.write(data)


def main():
    db.ensure_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"✅ Homework Lab 已启动 → http://{HOST}:{PORT}")
    print(f"📁 数据库：{db.get_db_path()}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
