#!/usr/bin/env python3
"""homework-lab 本地服务器 —— 学生端网页 API + 静态资源。

纯标准库（http.server），零依赖。
启动：python3 server/app.py
配置优先级：环境变量（HOMELAB_DB / HOMELAB_HOST / HOMELAB_PORT）> config.json（设置页写入）
默认只绑定 127.0.0.1:8877。

安全约定：发给前端的试卷数据绝不包含 answer / explanation 字段（批改后才会出现在结果页）。
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

APP_FILE = Path(__file__).resolve()
PROJECT_ROOT = APP_FILE.parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.json"
STATIC = APP_FILE.parent / "static"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "HomeworkLab/1.1"

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
        pass  # 安静模式

    # ---------------- GET ----------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/state":
                with db.connect() as conn:
                    return self._send_json(200, db.state_snapshot(conn))
            if path == "/api/vocabulary":
                with db.connect() as conn:
                    words = db.vocab_list(conn)
                unfilled = sum(1 for w in words
                               if not (w.get("meaning_cn") and w.get("pos")))
                return self._send_json(200, {"words": words, "unfilled": unfilled})
            if path == "/api/profile":
                with db.connect() as conn:
                    return self._send_json(200, db.profile_get(conn))
            if path == "/api/knowledge-map":
                with db.connect() as conn:
                    return self._send_json(200, {"stages": db.kmap_list(conn),
                                                 "summary": db.kmap_summary(conn)})
            if path == "/api/settings":
                cfg = load_config()
                return self._send_json(200, {
                    "host": self.server.server_address[0],
                    "port": self.server.server_address[1],
                    "db_path": str(db.get_db_path()),
                    "config": cfg or None,
                })
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
        except Exception as e:  # noqa: BLE001
            return self._send_error_json(500, f"服务器错误: {e}")

    # ---------------- POST ----------------
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path in ("/api/restart",):
            return self._handle_restart()
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
            if path == "/api/vocabulary":
                with db.connect() as conn:
                    row, created = db.vocab_add(conn, body.get("word") or "",
                                                note=(body.get("note") or "").strip(),
                                                source=(body.get("source") or "").strip())
                return self._send_json(200, {"id": row["id"], "created": created,
                                             "word": row["word"]})
            if path == "/api/profile":
                with db.connect() as conn:
                    for key in ("goals", "topics", "question_types"):
                        if key in body:
                            val = body[key]
                            if not isinstance(val, list):
                                raise ValueError(f"{key} 应为数组")
                            db.profile_set(conn, key, val)
                    if "notes" in body:
                        db.profile_set(conn, "notes", str(body["notes"]))
                return self._send_json(200, {"saved": True})
            if path == "/api/settings":
                return self._handle_save_settings(body)
            return self._send_error_json(404, "未知接口")
        except ValueError as e:
            return self._send_error_json(400, str(e))
        except Exception as e:  # noqa: BLE001
            return self._send_error_json(500, f"服务器错误: {e}")

    # ---------------- PATCH / DELETE ----------------
    def do_PATCH(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_body()
        except ValueError as e:
            return self._send_error_json(400, str(e))
        m = re.fullmatch(r"/api/vocabulary/(\d+)", path)
        if not m:
            return self._send_error_json(404, "未知接口")
        with db.connect() as conn:
            db.vocab_update(conn, [{"id": int(m.group(1)),
                                    "meaning_cn": body.get("meaning_cn", ""),
                                    "pos": body.get("pos", ""),
                                    "note": body.get("note", "")}])
        return self._send_json(200, {"updated": True})

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        try:
            m = re.fullmatch(r"/api/vocabulary/(\d+)", path)
            if m:
                with db.connect() as conn:
                    db.vocab_delete(conn, int(m.group(1)))
                return self._send_json(200, {"deleted": True})
            m = re.fullmatch(r"/api/homeworks/(\d+)", path)
            if m:
                with db.connect() as conn:
                    h = db.delete_homework(conn, int(m.group(1)))
                return self._send_json(200, {"deleted": True, "title": h["title"]})
            return self._send_error_json(404, "未知接口")
        except ValueError as e:
            return self._send_error_json(400, str(e))
        except Exception as e:  # noqa: BLE001
            return self._send_error_json(500, f"服务器错误: {e}")

    # ---------------- 具体处理 ----------------
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
            db.add_log(conn, "submit", summary=f"交卷《{hw['title']}》（{len(clean)} 题已作答）",
                       ref_type="submission", ref_id=cur.lastrowid)
        return self._send_json(200, {"submission_id": cur.lastrowid,
                                     "message": "已交卷，等待批改"})

    def _handle_save_settings(self, body):
        cfg = load_config()
        new = {}
        if body.get("db_path"):
            p = Path(str(body["db_path"])).expanduser()
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise ValueError(f"数据库目录无法创建: {e}")
            new["db_path"] = str(p)
        if body.get("host"):
            new["host"] = str(body["host"]).strip()
        if body.get("port"):
            try:
                port = int(body["port"])
            except (TypeError, ValueError):
                raise ValueError("端口必须是数字")
            if not 1 <= port <= 65535:
                raise ValueError("端口范围 1-65535")
            new["port"] = port
        cfg.update(new)
        save_config(cfg)
        return self._send_json(200, {"saved": True, "config": cfg,
                                     "restart_required": True,
                                     "message": "已保存，重启服务后生效"})

    def _handle_restart(self):
        """重启：1 秒后在独立会话中拉起新进程，旧进程随后退出。"""
        env = dict(os.environ)
        launcher = f"sleep 1; exec {sys.executable} {APP_FILE}"
        try:
            subprocess.Popen(["sh", "-c", launcher], env=env, start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, cwd=str(PROJECT_ROOT))
        except Exception as e:  # noqa: BLE001
            return self._send_error_json(500, f"重启失败: {e}")
        self._send_json(200, {"message": "正在重启，约 1 秒后生效，请刷新页面"})
        threading.Timer(0.6, lambda: os._exit(0)).start()

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
    cfg = load_config()
    # 环境变量优先，config.json 兜底
    os.environ.setdefault("HOMELAB_DB", str(cfg.get("db_path") or ""))
    host = os.environ.get("HOMELAB_HOST") or cfg.get("host") or "127.0.0.1"
    port = int(os.environ.get("HOMELAB_PORT") or cfg.get("port") or 8877)
    db.ensure_db()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"✅ Homework Lab 已启动 → http://{host}:{port}")
    print(f"📁 数据库：{db.get_db_path()}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
