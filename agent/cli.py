#!/usr/bin/env python3
"""homework-lab Agent CLI —— AI（或任何 agent）操作学习数据库的统一入口。

核心循环：
  1. create    发布新试卷（JSON 规范见 docs/AGENT_PROTOCOL.md）
  2. pending   查看待批改提交（含需要 AI 复核的题目详情）
  3. autograde 自动批改客观题
  4. grade     写入 AI 批改结果（JSON）→ 提交置为 graded → 知识点统计更新
  5. report    查看某次提交的完整结果（用于对话框讲解）
  6. wronglist 导出错题（用于生成变式题 / 周错题重练卷）
  7. weakpoints 查看知识点掌握度（决定下一份卷子的方向）
  8. requests  查看学员的重练请求

所有命令自动建库；用 --json 输出机器可读 JSON。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

SKILL_LABELS = {
    "grammar": "语法", "vocabulary": "词汇", "reading": "阅读",
    "writing": "写作", "listening": "听力", "mixed": "综合",
}
KP_STATUS_LABELS = {"new": "未练过", "weak": "薄弱⚠", "learning": "学习中", "mastered": "已掌握✓"}
SUB_STATUS_LABELS = {"pending": "待批改", "partial": "部分批改", "graded": "已批改"}


def _fmt_score(sub):
    if sub.get("total_score") is None:
        return "-"
    return f"{sub['total_score']:g}/{sub['max_score']:g}"


def _fmt_wrong_count(sub):
    if sub.get("correct_count") is None or sub.get("total_count") is None:
        return "-"
    return str(sub["total_count"] - sub["correct_count"])


def cmd_init(args):
    path = db.init_db()
    print(f"数据库已初始化：{path}")


def cmd_create(args):
    with open(args.paper_json, encoding="utf-8") as f:
        data = json.load(f)
    with db.connect() as conn:
        hw_id = db.create_paper(conn, data, status=args.status)
        n = conn.execute("SELECT COUNT(*) c FROM questions WHERE homework_id=?", (hw_id,)).fetchone()["c"]
    print(f"✅ 已发布试卷 #{hw_id}《{data.get('title')}》：{n} 题（status={args.status}）")


def cmd_list(args):
    with db.connect() as conn:
        rows = db.list_homeworks(conn)
    if not rows:
        print("（还没有试卷，用 create 发布一份）")
        return
    print(f"{'ID':>3}  {'状态':<4} {'题目':>4}  {'最新提交':<16} {'得分':<8} {'错题':>4}  标题")
    print("-" * 88)
    for h in rows:
        s = h["latest_submission"]
        st = SUB_STATUS_LABELS.get(s["status"], s["status"]) if s else "未作答"
        score = _fmt_score(s) if s else "-"
        wrong = _fmt_wrong_count(s) if s else "-"
        print(f"{h['id']:>3}  {h['status']:<4} {h['question_count']:>4}  {st:<16} {score:<8} {wrong:>4}  {h['title']}")


def cmd_paper(args):
    with db.connect() as conn:
        full = db.paper_full(conn, args.hw_id)
    if not full:
        print(f"试卷 #{args.hw_id} 不存在")
        sys.exit(1)
    h, qs = full["homework"], full["questions"]
    print(f"试卷 #{h['id']}《{h['title']}》 skill={h['skill']} topic={h['topic']}")
    print(f"目标：{h['goal']}")
    print(f"题目数：{len(qs)}")
    for q in qs:
        ans = json.loads(q["answer"])
        print(f"  [{q['id']}] {q['type']} ({q['knowledge_point'] or '未标注'}) {q['prompt'][:60]}")
        print(f"       答案: {json.dumps(ans, ensure_ascii=False)[:80]}")


def _print_todo_question(q):
    print(f"  [Q{q['id']} {q['type']}] {q['prompt'][:120]}")
    if q.get("passage"):
        print(f"    短文: {q['passage'][:200]}")
    if q.get("options"):
        print(f"    选项: {' | '.join(q['options'])}")
    print(f"    你的答案: {json.dumps(q['user_answer'], ensure_ascii=False)[:200]}")
    print(f"    参考答案: {json.dumps(q['answer_spec'], ensure_ascii=False)[:120]}")
    if q.get("knowledge_point"):
        print(f"    知识点: {q['knowledge_point']}")


def cmd_pending(args):
    with db.connect() as conn:
        subs = db.pending_submissions(conn)
    if not subs:
        print("没有待批改的提交 ✓")
        return
    for s in subs:
        print(f"── 提交 #{s['id']} · 《{s['homework_title']}》 · {s['submitted_at']} · {s['status']}")
        if not s["todo_questions"]:
            print("   （无待 AI 项？检查状态）")
        for q in s["todo_questions"]:
            _print_todo_question(q)
        print()


def cmd_autograde(args):
    with db.connect() as conn:
        if args.sub_id:
            ids = [args.sub_id]
        else:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM submissions WHERE status IN ('pending','partial') ORDER BY id")]
        if not ids:
            print("没有待批改的提交")
            return
        for sid in ids:
            r = db.autograde_submission(conn, sid)
            s = conn.execute("SELECT status FROM submissions WHERE id=?", (sid,)).fetchone()
            print(f"提交 #{sid}：自动批改 {len(r['auto_graded'])} 题，"
                  f"需 AI 复核 {len(r['needs_review'])} 题 → 状态 {s['status']}")


def cmd_grade(args):
    if args.grades_json:
        with open(args.grades_json, encoding="utf-8") as f:
            payload = json.load(f)
        grades = payload.get("grades", payload if isinstance(payload, list) else [])
        note = payload.get("note") if isinstance(payload, dict) else None
    else:
        print("用法：grade <sub_id> --json grades.json  （文件含 {grades:[...], note?}）")
        sys.exit(1)
    if args.note:
        note = args.note
    with db.connect() as conn:
        applied = db.apply_grades(conn, args.sub_id, grades, note=note)
        s = conn.execute("SELECT * FROM submissions WHERE id=?", (args.sub_id,)).fetchone()
    print(f"✅ 提交 #{args.sub_id} 已写入 {len(applied)} 条批改 → 状态 {s['status']}")
    if s["total_score"] is not None:
        print(f"   得分 {s['total_score']:g}/{s['max_score']:g} · "
              f"全对 {s['correct_count']}/{s['total_count']}")


def cmd_report(args):
    with db.connect() as conn:
        d = db.submission_detail(conn, args.sub_id)
    if not d:
        print(f"提交 #{args.sub_id} 不存在")
        sys.exit(1)
    print(f"提交 #{d['id']} · 《{d['homework_title']}》 · {d['submitted_at']} · {d['status']}")
    if d["total_score"] is not None:
        print(f"得分 {d['total_score']:g}/{d['max_score']:g} · 全对 {d['correct_count']}/{d['total_count']}")
    if d["overall_feedback"]:
        print(f"总评：{d['overall_feedback']}")
    print()
    for it in d["items"]:
        mark = {1.0: "✓", 0.0: "✗"}.get(it["correct"], "◐" if it["correct"] else "?")
        print(f"{mark} [Q{it['question_id']} {it['type']}] {it['prompt'][:80]}")
        print(f"    你的答案: {json.dumps(it['user_answer'], ensure_ascii=False)[:160]}")
        if it["correct"] != 1.0 and it["correct_answer"] is not None:
            print(f"    正确答案: {json.dumps(it['correct_answer'], ensure_ascii=False)[:160]}")
        if it["feedback"]:
            print(f"    批改评语: {it['feedback'][:200]}")
        if it["correct"] != 1.0 and it["explanation"]:
            print(f"    解析: {it['explanation'][:200]}")
        print()


def cmd_wronglist(args):
    with db.connect() as conn:
        items = db.wrong_items(conn, kp=args.kp, limit=args.limit)
    payload = {"count": len(items), "items": items}
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"已导出 {len(items)} 条错题 → {args.out_json}")
        return
    if not items:
        print("没有错题 ✓")
        return
    for it in items:
        print(f"[{it['knowledge_point'] or '未标注'}] {it['graded_at'][:16]} · "
              f"Q{it['question_id']} ({it['type']}) {it['prompt'][:70]}")
        print(f"    错答: {json.dumps(it['user_answer'], ensure_ascii=False)[:100]}")
        print(f"    正解: {json.dumps(it['correct_answer'], ensure_ascii=False)[:100]}")
        print()


def cmd_weakpoints(args):
    with db.connect() as conn:
        kps = db.knowledge_table(conn)
    if not kps:
        print("还没有知识点数据（交卷并批改后自动生成）")
        return
    print(f"{'知识点':<16} {'掌握度':<8} {'状态':<8} {'答题':>4} {'对':>6}")
    print("-" * 52)
    for k in kps:
        pct = f"{k['mastery'] * 100:.0f}%"
        print(f"{k['name']:<16} {pct:<8} {KP_STATUS_LABELS.get(k['status'], k['status']):<8} "
              f"{k['attempts']:>4} {k['correct']:g}")


def cmd_requests(args):
    with db.connect() as conn:
        reqs = db.list_requests(conn, only_open=True)
    if not reqs:
        print("没有待处理的重练请求 ✓")
        return
    for r in reqs:
        print(f"#{r['id']} [{r['knowledge_point']}] {r['note']} · {r['created_at']}")
    print("\n处理方式：出针对性试卷后，用 `request done <id>` 关闭请求")


def cmd_request_done(args):
    with db.connect() as conn:
        db.set_request_status(conn, args.req_id, "done")
    print(f"请求 #{args.req_id} 已标记完成")


def cmd_archive(args):
    status = "published" if args.unarchive else "archived"
    with db.connect() as conn:
        db.set_homework_status(conn, args.hw_id, status)
    print(f"试卷 #{args.hw_id} → {status}")


def cmd_state(args):
    with db.connect() as conn:
        snap = db.state_snapshot(conn)
    print(json.dumps(snap, ensure_ascii=False, indent=2))


def main(argv=None):
    db.ensure_db()
    p = argparse.ArgumentParser(
        prog="homework-lab",
        description="homework-lab Agent CLI：发布试卷 / 批改 / 错题与知识点管理。")
    p.add_argument("--json", action="store_true", help="输出 JSON（部分命令支持）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化数据库")

    pc = sub.add_parser("create", help="从 JSON 发布试卷")
    pc.add_argument("paper_json", help="试卷 JSON 路径（规范见 docs/AGENT_PROTOCOL.md）")
    pc.add_argument("--status", default="published", choices=["draft", "published"])

    sub.add_parser("list", help="试卷列表与最新提交状态")

    pp = sub.add_parser("paper", help="查看试卷（含答案，仅供 agent）")
    pp.add_argument("hw_id", type=int)

    sub.add_parser("pending", help="列出待 AI 批改/复核的提交与题目详情")

    pa = sub.add_parser("autograde", help="自动批改客观题（默认处理所有待批改提交）")
    pa.add_argument("sub_id", nargs="?", type=int, help="只处理该提交")

    pg = sub.add_parser("grade", help="写入 AI 批改结果")
    pg.add_argument("sub_id", type=int)
    pg.add_argument("--json", dest="grades_json", help="批改 JSON 文件 {grades:[...], note?}")
    pg.add_argument("--note", help="总体点评（可选）")

    pr = sub.add_parser("report", help="查看某次提交完整结果（用于讲解）")
    pr.add_argument("sub_id", type=int)

    pw = sub.add_parser("wronglist", help="导出错题集合（用于出变式题/重练卷）")
    pw.add_argument("--kp", help="按知识点过滤")
    pw.add_argument("--limit", type=int, default=200)
    pw.add_argument("--json", dest="out_json", help="导出到 JSON 文件")

    sub.add_parser("weakpoints", help="知识点掌握度总览")

    sub.add_parser("requests", help="查看学员的重练请求")

    prq = sub.add_parser("request", help="管理重练请求")
    prq.add_argument("action", choices=["done"])
    prq.add_argument("req_id", type=int)

    pa2 = sub.add_parser("archive", help="归档/恢复试卷")
    pa2.add_argument("hw_id", type=int)
    pa2.add_argument("--unarchive", action="store_true")

    sub.add_parser("state", help="总览 JSON（首页数据/供定时任务）")

    args = p.parse_args(argv)
    handlers = {
        "init": cmd_init, "create": cmd_create, "list": cmd_list, "paper": cmd_paper,
        "pending": cmd_pending, "autograde": cmd_autograde, "grade": cmd_grade,
        "report": cmd_report, "wronglist": cmd_wronglist, "weakpoints": cmd_weakpoints,
        "requests": cmd_requests, "request": cmd_request_done, "archive": cmd_archive,
        "state": cmd_state,
    }
    try:
        handlers[args.cmd](args)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
