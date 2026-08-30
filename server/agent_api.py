"""homework-lab AI 服务接入 API —— 把 agent/cli.py 的能力以 JSON HTTP 接口暴露。

给「只能发 HTTP 请求、不能跑本地命令」的在线 AI 服务（ChatGPT 自定义 GPT / 豆包 /
Kimi / Dify / n8n 等）使用：AI 老师通过本 API 对数据库读写，完成出题、批改、单词本
与题目目标检查。能跑本地命令的 agent（Hermes / Claude Code / Codex）直接用 CLI 即可。

约定：
- 所有路由前缀 /api/agent/*
- 默认只绑定 127.0.0.1。若在设置页把监听地址改成 0.0.0.0（局域网可访问），强烈建议
  同时设置 api_token；设置了 token 后，本 API 所有请求必须带
  `Authorization: Bearer <token>` 或 `X-API-Token: <token>` 头。
- 请求体一律 JSON；响应一律 JSON。错误返回 {"error": "..."} 加 4xx/5xx 状态码。
- 完整的 AI 接入协议见 docs/HTTP_API.md；试卷/批改 JSON 规范见 docs/AGENT_PROTOCOL.md。
"""
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from agent import db, settings

CLI_FILE = Path(__file__).resolve().parent.parent / "agent" / "cli.py"

# ---------------------------------------------------------------- 鉴权
def check_auth(handler) -> bool:
    cfg = settings.effective_config()
    token = str(cfg.get("api_token") or "").strip()
    if not token:
        return True
    header = handler.headers.get("Authorization") or handler.headers.get("X-API-Token") or ""
    if header.startswith("Bearer "):
        header = header[7:]
    if header.strip() == token:
        return True
    handler._send_error_json(401, "api_token 无效：请求需带 Authorization: Bearer <token>")
    return False


# ---------------------------------------------------------------- GET
def agent_state(handler):
    with db.connect() as conn:
        return handler._send_json(200, db.state_snapshot(conn))


def agent_pending(handler):
    with db.connect() as conn:
        return handler._send_json(200, {"submissions": db.pending_submissions(conn)})


def agent_goals(handler):
    """题目目标总览 —— AI 出题前必读：教学规则 + 学生画像 + 图谱下一个未掌握点。"""
    with db.connect() as conn:
        profile = db.profile_get(conn)
        diags = db.list_diagnoses(conn, only_open=True)
        weak = [r for r in db.knowledge_table(conn) if r["status"] in ("weak", "learning")]
        wk = db.last_weekly_review(conn)
        weekly = {
            "last_review": dict(wk) if wk else None,
            "candidates": db.weekly_candidates(conn),
        }
        kmap_next = _kmap_next(conn, limit=3)
    rules = settings.get_rules()
    return handler._send_json(200, {
        "rules": rules,
        "profile": profile,
        "kmap_next": kmap_next,
        "open_diagnoses": diags,
        "weakpoints": weak,
        "weekly": weekly,
        "priority_legend": _PRIORITY_LEGEND,
    })


_PRIORITY_LEGEND = {
    "student_request": "学生口头指定方向（永远最高优先级）",
    "open_diag": "未解决诊断 → 出对应知识点验证卷",
    "kmap_next": "图谱顺序下一个未掌握点 → 语法卷主攻",
    "weekly_wrong": "周回顾出错知识点 → 重练",
    "weakpoints": "掌握度 <50% 的薄弱点 → 专项练习",
    "writing_curriculum": "写作路线推进或画像勾选的翻译/阅读训练",
    "vocab_dictation": "学生要求默写/抽查 → 一键生成卷",
}


def _kmap_next(conn, limit=3):
    stages = db.kmap_list(conn)
    todo = []
    for st in stages:
        for p in st["points"]:
            if p["status"] != "mastered":
                todo.append(p)
    return todo[:limit]


def agent_papers(handler):
    with db.connect() as conn:
        return handler._send_json(200, {"homeworks": db.list_homeworks(conn)})


def agent_paper_detail(handler, m):
    with db.connect() as conn:
        full = db.paper_full(conn, int(m.group(1)))
    if not full:
        return handler._send_error_json(404, f"试卷 #{m.group(1)} 不存在")
    return handler._send_json(200, full)


def agent_submission(handler, m):
    with db.connect() as conn:
        detail = db.submission_detail(conn, int(m.group(1)))
    if not detail:
        return handler._send_error_json(404, f"提交 #{m.group(1)} 不存在")
    return handler._send_json(200, detail)


def agent_vocab(handler):
    filter_ = (handler.path.split("?", 1)[1] if "?" in handler.path else "")
    kv = dict(x.split("=", 1) for x in filter_.split("&") if "=" in x)
    f = kv.get("filter", "all")
    filters = {
        "unfilled": {"unfilled_only": True},
        "confirmed": {"confirmed_only": True},
        "await-detail": {"await_detail": True},
        "pool": {"pool_only": True},
    }.get(f, {})
    with db.connect() as conn:
        words = db.vocab_list(conn, **filters)
    return handler._send_json(200, {"words": words, "filter": f})


def agent_weakpoints(handler):
    with db.connect() as conn:
        return handler._send_json(200, {"knowledge": db.knowledge_table(conn)})


def agent_diag_list(handler):
    only_open = "open=1" in handler.path
    with db.connect() as conn:
        return handler._send_json(200, {"diagnoses": db.list_diagnoses(conn, only_open=only_open)})


def agent_weekly_status(handler):
    with db.connect() as conn:
        last = db.last_weekly_review(conn)
        due = False
        if last:
            try:
                ts = datetime.datetime.strptime(last["reviewed_ts"], "%Y-%m-%d %H:%M:%S")
                due = (datetime.datetime.now() - ts).days >= settings.get_rules()["weekly_interval_days"]
            except ValueError:
                due = True
        else:
            due = True
        return handler._send_json(200, {
            "due": due,
            "last_review": dict(last) if last else None,
            "candidates": db.weekly_candidates(conn),
            "interval_days": settings.get_rules()["weekly_interval_days"],
        })


def agent_requests(handler):
    with db.connect() as conn:
        return handler._send_json(200, {"requests": db.list_requests(conn, only_open=True)})


def agent_profile_get(handler):
    with db.connect() as conn:
        return handler._send_json(200, db.profile_get(conn))


def agent_kmap(handler):
    with db.connect() as conn:
        stages = db.kmap_list(conn)
        summary = db.kmap_summary(conn)
    if "next=1" in handler.path:
        return handler._send_json(200, {"next": _kmap_next(conn, limit=3), "summary": summary})
    return handler._send_json(200, {"stages": stages, "summary": summary})


def agent_timeline(handler):
    with db.connect() as conn:
        return handler._send_json(200, {"logs": db.list_logs(conn)})


def agent_wronglist(handler):
    with db.connect() as conn:
        return handler._send_json(200, {"wrong_items": db.wrong_items(conn)})


# ---------------------------------------------------------------- POST
def agent_paper_create(handler, body):
    paper = body.get("paper")
    if not isinstance(paper, dict):
        raise ValueError("需要 {paper: {...}}，试卷 JSON 规范见 docs/AGENT_PROTOCOL.md")
    status = body.get("status", "published")
    with db.connect() as conn:
        hw_id = db.create_paper(conn, paper, status=status)
        n = conn.execute("SELECT COUNT(*) c FROM questions WHERE homework_id=?", (hw_id,)).fetchone()["c"]
    return handler._send_json(200, {"homework_id": hw_id, "question_count": n, "title": paper.get("title")})


def agent_autograde(handler, body):
    sub_id = body.get("submission_id")
    with db.connect() as conn:
        if sub_id:
            ids = [int(sub_id)]
        else:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM submissions WHERE status IN ('pending','partial') ORDER BY id")]
        if not ids:
            return handler._send_json(200, {"graded": [], "message": "没有待批改的提交"})
        out = []
        for sid in ids:
            r = db.autograde_submission(conn, sid)
            s = conn.execute("SELECT status FROM submissions WHERE id=?", (sid,)).fetchone()
            out.append({"submission_id": sid, "auto_graded": len(r["auto_graded"]),
                        "needs_review": len(r["needs_review"]), "status": s["status"]})
    return handler._send_json(200, {"graded": out})


def agent_grade(handler, body):
    sub_id = body.get("submission_id")
    grades = body.get("grades")
    if not isinstance(sub_id, int) or not isinstance(grades, list):
        raise ValueError("需要 {submission_id: int, grades: [{question_id, correct, feedback}], note?}")
    note = body.get("note")
    with db.connect() as conn:
        applied = db.apply_grades(conn, sub_id, grades, note=note)
        s = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    return handler._send_json(200, {"applied": len(applied), "status": s["status"],
                                    "total_score": s["total_score"], "max_score": s["max_score"]})


def agent_vocab_detail(handler, body):
    updates = body.get("updates")
    if not isinstance(updates, list):
        raise ValueError("需要 {updates: [{word, detail}]}，AI 只补词典词性+详细释义")
    with db.connect() as conn:
        updated = db.vocab_update(conn, updates)
    return handler._send_json(200, {"updated_ids": updated, "count": len(updated)})


def agent_vocab_check_result(handler, body):
    sub_id = body.get("submission_id")
    if not isinstance(sub_id, int):
        raise ValueError("需要 {submission_id: int}")
    with db.connect() as conn:
        result = db.vocab_apply_check(conn, sub_id)
    return handler._send_json(200, result)


def agent_diag(handler, body):
    action = body.get("action")
    with db.connect() as conn:
        if action == "add":
            kp = (body.get("knowledge_point") or "").strip()
            if not kp:
                raise ValueError("add 需要 knowledge_point")
            did = db.add_diagnosis(conn, kp, body.get("finding") or "", body.get("severity") or "mid",
                                   body.get("evidence") or "", body.get("submission_id"))
            return handler._send_json(200, {"id": did, "created": True})
        if action == "resolve":
            diag_id = body.get("diag_id")
            if not isinstance(diag_id, int):
                raise ValueError("resolve 需要 diag_id")
            db.resolve_diagnosis(conn, diag_id, body.get("note") or "")
            return handler._send_json(200, {"id": diag_id, "resolved": True})
        if action == "list":
            return handler._send_json(200, {"diagnoses": db.list_diagnoses(conn, only_open=body.get("open", True))})
    raise ValueError("action 应为 add / resolve / list")


def agent_weekly(handler, body):
    action = body.get("action")
    with db.connect() as conn:
        if action == "record":
            sampled = [s.strip() for s in str(body.get("sampled") or "").split(",") if s.strip()]
            wrong = [s.strip() for s in str(body.get("wrong") or "").split(",") if s.strip()]
            if not sampled:
                raise ValueError("record 需要 sampled（抽查的知识点，逗号分隔）")
            wid = db.add_weekly_review(conn, sampled, wrong, body.get("homework_id"), body.get("note") or "")
            return handler._send_json(200, {"id": wid, "recorded": True})
        if action == "status":
            last = db.last_weekly_review(conn)
            return handler._send_json(200, {
                "last_review": dict(last) if last else None,
                "candidates": db.weekly_candidates(conn),
            })
    raise ValueError("action 应为 record / status")


def agent_request_done(handler, body):
    req_id = body.get("id")
    if not isinstance(req_id, int):
        raise ValueError("需要 {id: int}")
    with db.connect() as conn:
        db.set_request_status(conn, req_id, "done")
    return handler._send_json(200, {"id": req_id, "done": True})


def agent_profile_set(handler, body):
    with db.connect() as conn:
        for key in ("goals", "topics", "question_types"):
            if key in body:
                val = body[key]
                if not isinstance(val, list):
                    raise ValueError(f"{key} 应为数组")
                db.profile_set(conn, key, val)
        if "notes" in body:
            db.profile_set(conn, "notes", str(body["notes"]))
    return handler._send_json(200, {"saved": True})


def agent_log(handler, body):
    event_type = body.get("event_type")
    if event_type not in ("assign", "submit", "graded", "explain", "verify", "weekly", "diag", "request", "other"):
        raise ValueError("event_type 应为 assign/submit/graded/explain/verify/weekly/diag/request/other")
    with db.connect() as conn:
        log_id = db.add_log(conn, event_type, body.get("summary") or "", body.get("knowledge_point") or "",
                            body.get("ref_type") or "", body.get("ref_id"), body.get("detail"))
    return handler._send_json(200, {"id": log_id, "logged": True})


def agent_exec(handler, body):
    """兜底：执行任意 cli.py 子命令（如 {"args": ["vocab", "dictation", "--limit", "5"]}）。
    仅用于结构化端点未覆盖的命令。args 为字符串数组，不经过 shell。"""
    args = body.get("args")
    if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
        raise ValueError("需要 {args: [\"命令\", \"参数\", ...]}，例如 [\"pending\"]")
    env = dict(os.environ)
    env.setdefault("HOMELAB_DB", str(settings.get_db_path()))
    try:
        r = subprocess.run([sys.executable, str(CLI_FILE), *args], cwd=str(settings.PROJECT_ROOT),
                           env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return handler._send_error_json(504, "命令执行超时（120s）")
    return handler._send_json(200, {
        "ok": r.returncode == 0,
        "exit_code": r.returncode,
        "stdout": r.stdout[-4000:],
        "stderr": r.stderr[-2000:],
    })


# ---------------------------------------------------------------- 路由表
GET_ROUTES = [
    (r"/api/agent/state", agent_state),
    (r"/api/agent/pending", agent_pending),
    (r"/api/agent/goals", agent_goals),
    (r"/api/agent/papers", agent_papers),
    (r"/api/agent/papers/(\d+)", agent_paper_detail),
    (r"/api/agent/submissions/(\d+)", agent_submission),
    (r"/api/agent/vocab", agent_vocab),
    (r"/api/agent/weakpoints", agent_weakpoints),
    (r"/api/agent/diag", agent_diag_list),
    (r"/api/agent/weekly", agent_weekly_status),
    (r"/api/agent/requests", agent_requests),
    (r"/api/agent/profile", agent_profile_get),
    (r"/api/agent/kmap", agent_kmap),
    (r"/api/agent/timeline", agent_timeline),
    (r"/api/agent/wronglist", agent_wronglist),
]

POST_ROUTES = [
    (r"/api/agent/papers", agent_paper_create),
    (r"/api/agent/autograde", agent_autograde),
    (r"/api/agent/grade", agent_grade),
    (r"/api/agent/vocab-detail", agent_vocab_detail),
    (r"/api/agent/vocab-check-result", agent_vocab_check_result),
    (r"/api/agent/diag", agent_diag),
    (r"/api/agent/weekly", agent_weekly),
    (r"/api/agent/requests", agent_request_done),
    (r"/api/agent/profile", agent_profile_set),
    (r"/api/agent/log", agent_log),
    (r"/api/agent/exec", agent_exec),
]


def handle(handler, method: str, path: str, body):
    """app.py 调用入口。返回 True 表示已处理（含 404/鉴权失败）；False 表示路由未命中。"""
    if not path.startswith("/api/agent/"):
        return False
    if not check_auth(handler):
        return True
    routes = GET_ROUTES if method == "GET" else POST_ROUTES
    for pattern, fn in routes:
        m = re.fullmatch(pattern, path)
        if m:
            try:
                if method == "GET":
                    fn(handler, m) if m.groups() else fn(handler)
                else:
                    fn(handler, body)
            except ValueError as e:
                handler._send_error_json(400, str(e))
            except Exception as e:  # noqa: BLE001
                handler._send_error_json(500, f"服务器错误: {e}")
            return True
    handler._send_error_json(404, "未知 agent 接口")
    return True
