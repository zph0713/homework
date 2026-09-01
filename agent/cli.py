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

from agent import db, settings  # noqa: E402

SKILL_LABELS = {
    "grammar": "语法", "vocabulary": "词汇", "reading": "阅读",
    "writing": "写作", "listening": "听力", "mixed": "综合",
    # 雅思专项训练四个栏目（与前端导航一致）
    "ielts_reading": "雅思·阅读节选小题", "ielts_stem": "雅思·题干翻译",
    "ielts_essay": "雅思·作文中译英", "ielts_speaking": "雅思·口语话题",
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


def cmd_setup(args):
    """首次初始化（网页向导的 CLI 等价物）：写 config.json + 部署数据库。"""
    if settings.is_initialized():
        print("已完成初始化，如需修改请到网页设置页（或直接编辑 config.json）")
        return
    payload = {"db_path": args.db, "host": args.host, "port": args.port,
               "api_token": args.api_token}
    if args.rules_json:
        with open(args.rules_json, encoding="utf-8") as f:
            payload["rules"] = json.load(f)
    if args.profile_json:
        with open(args.profile_json, encoding="utf-8") as f:
            payload["profile"] = json.load(f)
    r = db.perform_setup(payload)
    print(f"✅ 初始化完成：数据库 {r['db_path']} · http://{r['host']}:{r['port']}")
    print("启动网页：python3 server/app.py（或双击 start.command）")


def cmd_config(args):
    """查看当前生效配置（数据库路径/端口/教学规则/画像默认值）。"""
    cfg = settings.effective_config()
    if args.json:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return
    print(f"数据库文件：{settings.get_db_path()}")
    print(f"监听地址：{cfg['host']}:{cfg['port']}")
    print(f"AI API 令牌：{'已设置' if cfg.get('api_token') else '未设置（仅本机可访问）'}")
    print("\n教学规则（题目目标）：")
    from agent.settings import RULE_LABELS
    for k, v in cfg["rules"].items():
        label = RULE_LABELS.get(k, k)
        print(f"  {label}：{v}")
    print("\n学生画像默认值：")
    for k, v in cfg["profile"].items():
        print(f"  {k}：{v}")


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


# ---------------------------------------------------------------- 学习路径 / 诊断 / 周回顾
EVENT_LABELS = {
    "assign": "出卷", "submit": "交卷", "graded": "批改", "explain": "讲解",
    "verify": "验证卷", "weekly": "周回顾", "diag": "诊断", "request": "重练申请",
    "other": "其他",
}
SEV_LABELS = {"high": "严重⚠", "mid": "中等", "low": "轻微"}


def cmd_log(args):
    ref_type, ref_id = "", None
    if args.ref:
        parts = args.ref.split(":", 1)
        ref_type = parts[0]
        if len(parts) > 1:
            ref_id = int(parts[1])
    with db.connect() as conn:
        lid = db.add_log(conn, args.type, summary=args.summary,
                         knowledge_point=args.kp or "", ref_type=ref_type, ref_id=ref_id)
    print(f"已记录学习事件 #{lid} [{EVENT_LABELS.get(args.type, args.type)}] {args.summary}")


def cmd_timeline(args):
    with db.connect() as conn:
        logs = db.list_logs(conn, limit=args.limit)
    if not logs:
        print("学习路径还是空的（出卷/交卷/批改后会自动记录）")
        return
    for r in logs:
        kp = f" · {r['knowledge_point']}" if r["knowledge_point"] else ""
        ref = f" · {r['ref_type']}#{r['ref_id']}" if r["ref_type"] else ""
        print(f"{r['ts'][:16]}  [{EVENT_LABELS.get(r['event_type'], r['event_type'])}]{kp}{ref}")
        print(f"    {r['summary']}")


def cmd_diag_add(args):
    with db.connect() as conn:
        did = db.add_diagnosis(conn, args.kp, args.finding,
                               severity=args.severity, evidence=args.evidence or "",
                               submission_id=args.sub)
    print(f"已记录诊断 #{did} [{args.kp}]（{SEV_LABELS.get(args.severity, args.severity)}）{args.finding}")


def cmd_diag_list(args):
    with db.connect() as conn:
        rows = db.list_diagnoses(conn, only_open=args.open)
    if not rows:
        print("没有诊断记录 ✓")
        return
    for d in rows:
        mark = "未解决" if d["status"] == "open" else f"已解决({(d['resolved_ts'] or '')[:10]})"
        print(f"#{d['id']} [{d['knowledge_point']}] {SEV_LABELS.get(d['severity'], d['severity'])} · {mark} · {d['created_ts'][:10]}")
        print(f"    问题: {d['finding']}")
        if d["evidence"]:
            print(f"    证据: {d['evidence'][:100]}")
        if d["resolve_note"]:
            print(f"    解决: {d['resolve_note'][:100]}")
        print()


def cmd_diag_resolve(args):
    with db.connect() as conn:
        db.resolve_diagnosis(conn, args.diag_id, note=args.note or "")
    print(f"诊断 #{args.diag_id} 已标记解决")


def cmd_weekly_status(args):
    from datetime import datetime
    with db.connect() as conn:
        last = db.last_weekly_review(conn)
        cands = db.weekly_candidates(conn)
        kps = {k["name"]: k["mastery"] for k in db.knowledge_table(conn)}
    if last:
        last_ts = last["reviewed_ts"]
        try:
            days = (datetime.now() - datetime.strptime(last_ts[:19], "%Y-%m-%d %H:%M:%S")).days
        except ValueError:
            days = "?"
        print(f"上次周回顾: {last_ts}（{days} 天前）· 抽查 {json.loads(last['sampled'])}"
              f" · 出错 {json.loads(last['wrong'])}")
        due = isinstance(days, int) and days >= 7
    else:
        print("还没有做过周回顾")
        due = True
    print(f"状态: {'🔔 到期了，本次会话安排一次抽查' if due else '未到期（≥7 天才回顾）'}")
    if cands:
        print("候选知识点（上周学过/近期出现的，随机抽 2-3 个）：")
        for c in cands[:12]:
            pct = kps.get(c)
            print(f"  - {c}" + (f"（掌握度 {pct*100:.0f}%）" if pct is not None else ""))


def cmd_weekly_record(args):
    sampled = [s.strip() for s in args.sampled.split(",") if s.strip()]
    wrong = [s.strip() for s in (args.wrong or "").split(",") if s.strip()]
    with db.connect() as conn:
        wid = db.add_weekly_review(conn, sampled, wrong, homework_id=args.hw,
                                   note=args.note or "")
    print(f"周回顾 #{wid} 已记录：抽查 {sampled}，出错 {wrong or '无 ✓'}")
    if wrong:
        print("提示：出错知识点记得用 `diag add` 记录为练习目标")


# ---------------------------------------------------------------- 单词本 / 画像 / 图谱 / 删除
def cmd_vocab(args):
    if args.vocab_cmd == "list":
        with db.connect() as conn:
            words = db.vocab_list(conn, unfilled_only=args.unfilled,
                                  confirmed_only=args.confirmed,
                                  await_detail=args.await_detail,
                                  pool_only=args.pool)
        if not words:
            print("（没有符合条件的词）")
            return
        if args.out_json:
            with open(args.out_json, "w", encoding="utf-8") as f:
                json.dump({"words": words}, f, ensure_ascii=False, indent=2)
            print(f"已导出 {len(words)} 个单词 → {args.out_json}")
            return
        print(f"共 {len(words)} 词"
              + ("（缺中文/词性——提醒学生在网页补填）" if args.unfilled else "")
              + ("（已确认，待补详细）" if args.await_detail else ""))
        print(f"{'ID':>4}  {'单词':<18} {'词性':<14} {'中文':<16} {'池':<4} {'确认':<4} 详细")
        print("-" * 100)
        for w in words:
            pool = "✓绿" if (w["in_pool"] == 0 and w["times_checked"]) else (
                "错池" if (w["in_pool"] == 1 and w["last_check_ok"] == 0) else "待抽")
            print(f"{w['id']:>4}  {w['word']:<18} {'/'.join(w['pos']) or '—':<14} "
                  f"{(w['meaning_cn'] or '（待填）'):<16} {pool:<4} {'✓' if w['confirmed'] else '—':<4} "
                  f"{(w['detail'] or '')[:40]}")
    elif args.vocab_cmd == "add":
        with db.connect() as conn:
            row, created = db.vocab_add(conn, args.word, source=args.source or "")
        print(f"{'已加入' if created else '已存在'}：{row['word']}（#{row['id']}）")
    elif args.vocab_cmd == "update":
        with open(args.json_file, encoding="utf-8") as f:
            payload = json.load(f)
        updates = payload.get("updates", payload if isinstance(payload, list) else [])
        with db.connect() as conn:
            ids = db.vocab_update(conn, updates)
        print(f"已更新 {len(ids)} 个单词")
    elif args.vocab_cmd == "delete":
        with db.connect() as conn:
            db.vocab_delete(conn, args.vid)
        print(f"已删除单词 #{args.vid}")
    elif args.vocab_cmd == "dictation":
        cmd_vocab_dictation(args)
    elif args.vocab_cmd == "check":
        cmd_vocab_check(args)
    elif args.vocab_cmd == "check-result":
        cmd_vocab_check_result(args)
    elif args.vocab_cmd == "homework":
        cmd_vocab_homework(args)


def _vocab_question(w, tag):
    """把词转成 fill 题目。tag: '词汇-默写' | '词汇-抽查'。"""
    pos = "/".join(w["pos"]) if isinstance(w.get("pos"), list) else (w.get("pos") or "")
    hint = f"（{pos}）" if pos else ""
    verb = "默写" if tag == "词汇-默写" else "抽查"
    return {
        "type": "fill",
        "prompt": f"{verb}：{w['meaning_cn']}{hint}____",
        "answer": [w["word"]],
        "explanation": " ".join(x for x in (w["word"], pos, w.get("meaning_cn")) if x),
        "knowledge_point": tag,
        "score": 1,
    }


def cmd_vocab_dictation(args):
    """从单词本生成默写卷 JSON：看中文释义写英文单词（fill 题型，自动判分）。
    只收录已填中文释义的词；不足 limit 时全部使用并提示。"""
    import random
    with db.connect() as conn:
        words = db.vocab_list(conn)
    ready = [w for w in words if w.get("meaning_cn")]
    unfilled = len(words) - len(ready)
    if not ready:
        print("❌ 单词本里还没有带中文释义的词，无法出默写卷。")
        print("   学生在网页填好中文并确认后，再生成。")
        sys.exit(1)
    if unfilled:
        print(f"⚠ 跳过 {unfilled} 个未填中文释义的词")
    n = min(args.limit, len(ready))
    if len(ready) < args.limit:
        print(f"⚠ 只有 {len(ready)} 个词可用（需求 {args.limit}），将全部使用")
    picked = random.sample(ready, n) if args.random else list(reversed(ready))[:n]
    paper = {
        "title": f"单词默写 · 词本 {n} 词",
        "skill": "vocabulary",
        "topic": "单词本默写",
        "goal": "看中文释义默写英文单词（来自单词本）。答完后老师核对：错词讲记法，并安排变式重默。",
        "questions": [_vocab_question(w, "词汇-默写") for w in picked],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已生成默写卷（{n} 词）→ {out}")
    print("   发布：python3 agent/cli.py create " + str(out))


def cmd_vocab_check(args):
    """从抽查池随机抽词生成抽查卷（可整卷发布，也可把 questions 并入其他作业）。"""
    import random
    with db.connect() as conn:
        cands = db.vocab_check_candidates(conn)
    if not cands:
        print("抽查池为空：需要已确认且填了中文的词（学生在网页填词性/中文后点「确认」）。")
        sys.exit(1)
    n = min(args.limit, len(cands))
    if len(cands) < args.limit:
        print(f"⚠ 池里只有 {len(cands)} 个词（需求 {args.limit}），将全部抽取")
    picked = random.sample(cands, n)  # 抽查永远随机抽词
    paper = {
        "title": f"单词抽查 · 词本池 {n} 词",
        "skill": "vocabulary",
        "topic": "单词本抽查",
        "goal": "随机抽查单词本里的词：写对即过关出池（绿色），拼错继续留在抽查池直到下次再考。",
        "questions": [_vocab_question(w, "词汇-抽查") for w in picked],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已生成抽查卷（{n} 词）→ {out}")
    print("   发布：python3 agent/cli.py create " + str(out))
    print("   ⚠ 批改完成后必须回写池状态：vocab check-result --sub <提交id>")


def cmd_vocab_check_result(args):
    with db.connect() as conn:
        r = db.vocab_apply_check(conn, args.sub_id)
    print(f"✅ 抽查池已更新：")
    print(f"   对 → 出池（绿色）：{len(r['correct'])} 个 {r['correct']}")
    print(f"   错 → 留池待重抽：{len(r['wrong'])} 个 {r['wrong']}")
    if r["wrong"]:
        print("   错词会在下次抽查中再次出现，直到写对为止。")


# ---------------------------------------------------------------- 词汇短语作业生成器
IELTS_BANK_FILE = Path(__file__).resolve().parent.parent / "curriculum" / "ielts_answer_words.json"
PHRASE_BANK_FILE = Path(__file__).resolve().parent.parent / "curriculum" / "phrase_bank.json"
POS_OPTIONS = ["n.", "v.", "adj.", "adv.", "prep.", "conj.", "phr."]


def _vocab_hw_question(item, distractors):
    """把词转成随机形式的词汇题：拼写 / 汉译英 / 英译汉 / 词性。"""
    import random
    word, pos, cn = item["word"], (item.get("pos") or "n."), (item.get("cn") or "")
    other_cns = [d for d in distractors if d and d != cn]
    form = random.choice(["spell", "cn2en", "en2cn", "pos"])
    if form == "spell":
        return {"type": "fill",
                "prompt": f"拼写：{cn}（{pos}）首字母 {word[0]} ____",
                "answer": [word],
                "explanation": f"{word} {pos} {cn}",
                "knowledge_point": "", "score": 1}
    if form == "cn2en":
        return {"type": "fill",
                "prompt": f"汉译英：{cn}（{pos}）____",
                "answer": [word],
                "explanation": f"{word} {pos} {cn}",
                "knowledge_point": "", "score": 1}
    if form == "en2cn":
        opts = [cn] + random.sample(other_cns, min(3, len(other_cns)))
        random.shuffle(opts)
        letter = "ABCD"[opts.index(cn)]
        return {"type": "choice",
                "prompt": f"选出 {word}（{pos}）的中文意思：",
                "options": [f"{'ABCD'[i]}. {o}" for i, o in enumerate(opts)],
                "answer": letter,
                "explanation": f"{word} {pos} {cn}",
                "knowledge_point": "", "score": 1}
    # form == "pos"
    other_pos = [p for p in POS_OPTIONS if p != pos]
    opts = [pos] + random.sample(other_pos, 3)
    random.shuffle(opts)
    letter = "ABCD"[opts.index(pos)]
    return {"type": "choice",
            "prompt": f"选出 {word}（{cn}）的词性：",
            "options": [f"{'ABCD'[i]}. {o}" for i, o in enumerate(opts)],
            "answer": letter,
            "explanation": f"{word} {pos} {cn}",
            "knowledge_point": "", "score": 1}


def cmd_vocab_homework(args):
    """生成「词汇短语作业」卷：雅思听力阅读答案词 + 单词本词汇（随机拼写/汉英互译/词性）
    + 常用口语作文短语讲解卡（AI 老师教，学生可收藏进短语本）。skill=vocabulary，
    学生交卷即自动批改、自行对照答案验证，老师不参与批改。"""
    import random
    if not IELTS_BANK_FILE.is_file():
        print(f"❌ 缺少词库 {IELTS_BANK_FILE}")
        sys.exit(1)
    if not PHRASE_BANK_FILE.is_file():
        print(f"❌ 缺少短语库 {PHRASE_BANK_FILE}")
        sys.exit(1)
    bank = json.loads(IELTS_BANK_FILE.read_text(encoding="utf-8"))
    phrase_bank = json.loads(PHRASE_BANK_FILE.read_text(encoding="utf-8"))
    with db.connect() as conn:
        words = db.vocab_list(conn)
    ready = [{"word": w["word"],
              "pos": "/".join(w["pos"]) if w.get("pos") else "",
              "cn": w.get("meaning_cn") or ""}
             for w in words if w.get("meaning_cn") and w.get("pos")]

    n_ielts = min(args.ielts, len(bank))
    n_wb = min(args.wordbook, len(ready))
    n_ph = min(args.phrases, len(phrase_bank))
    ielts_picked = random.sample(bank, n_ielts)
    wb_picked = random.sample(ready, n_wb) if n_wb else []
    ph_picked = random.sample(phrase_bank, n_ph)
    distractors = [b.get("cn") for b in bank] + [w.get("cn") for w in ready]

    questions = []
    for w in ielts_picked + wb_picked:
        questions.append(_vocab_hw_question(w, distractors))
    for ph in ph_picked:
        questions.append({
            "type": "phrase",
            "prompt": ph["phrase"],
            "answer": "",
            "extra": {"meaning_cn": ph.get("meaning_cn", ""),
                      "example": ph.get("example", ""),
                      "example_cn": ph.get("example_cn", "")},
            "explanation": "",
            "knowledge_point": "",
            "score": 0,
        })
    paper = {
        "title": f"词汇短语作业 · 雅思答案词 {n_ielts} + 单词本 {n_wb} + 短语讲解 {n_ph}",
        "skill": "vocabulary",
        "topic": "词汇短语练习",
        "goal": "词汇题交卷后自动批改，请自行对照答案验证；短语卡由老师讲解，可一键收藏进短语本。",
        "questions": questions,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已生成词汇短语作业（雅思词 {n_ielts} + 词本词 {n_wb} + 短语 {n_ph}）→ {out}")
    if len(ready) < args.wordbook:
        print(f"⚠ 单词本只有 {len(ready)} 个带中文+词性的词可用（需求 {args.wordbook}），已全部使用")
    if len(bank) < args.ielts:
        print(f"⚠ 雅思词库只有 {len(bank)} 词（需求 {args.ielts}），已全部使用")
    print("   发布：python3 agent/cli.py create " + str(out))
    print("   说明：词汇部分学生自验证（无需批改）；短语部分无需作答，学生自行收藏")


# ---------------------------------------------------------------- 短语本
def cmd_phrase(args):
    if args.phrase_cmd == "list":
        with db.connect() as conn:
            rows = db.phrase_list(conn)
        if not rows:
            print("（短语本为空：词汇短语作业里的短语讲解卡可一键收藏）")
            return
        print(f"共 {len(rows)} 条短语")
        print(f"{'ID':>4}  {'短语':<30} {'释义':<24} 例句")
        print("-" * 100)
        for p in rows:
            print(f"{p['id']:>4}  {p['phrase']:<30} {(p['meaning_cn'] or ''):<24} {(p['example'] or '')[:40]}")
    elif args.phrase_cmd == "add":
        with db.connect() as conn:
            row, created = db.phrase_add(conn, args.phrase,
                                         meaning_cn=args.meaning or "",
                                         example=args.example or "",
                                         example_cn=args.example_cn or "",
                                         source=args.source or "")
        print(f"{'已加入' if created else '已存在'}：{row['phrase']}（#{row['id']}）")
    elif args.phrase_cmd == "delete":
        with db.connect() as conn:
            db.phrase_delete(conn, args.pid)
        print(f"已删除短语 #{args.pid}")


def cmd_profile(args):
    if args.profile_cmd == "get":
        with db.connect() as conn:
            p = db.profile_get(conn)
        print(json.dumps(p, ensure_ascii=False, indent=2))
        if not p:
            print("（画像为空，学生还没在「我的」页设置）")
    elif args.profile_cmd == "set":
        with open(args.json_file, encoding="utf-8") as f:
            payload = json.load(f)
        with db.connect() as conn:
            for k, v in payload.items():
                db.profile_set(conn, k, v)
        print(f"已更新画像：{list(payload.keys())}")


def cmd_kmap(args):
    if args.kmap_cmd == "import":
        with open(args.json_file, encoding="utf-8") as f:
            payload = json.load(f)
        with db.connect() as conn:
            n = db.kmap_import(conn, payload)
        print(f"知识图谱已导入：{n} 个知识点")
    elif args.kmap_cmd == "list":
        with db.connect() as conn:
            stages = db.kmap_list(conn)
            summ = db.kmap_summary(conn)
        if not stages:
            print("图谱为空：`kmap import curriculum/grammar_map.json` 导入")
            return
        print(f"总评：{summ['grade']}（已学 {summ['attempted']}/{summ['total']}，"
              f"已掌握 {summ['mastered']}，薄弱 {summ['weak']}，平均 {summ['avg']} 分）")
        for st in stages:
            print(f"\n◆ 第{st['stage']}阶段 · {st['stage_name']}")
            for p in st["points"]:
                mark = {"mastered": "✓", "weak": "⚠"}.get(p["status"], "·")
                print(f"  {mark} {p['name']:<12} {p['score']:>3} 分"
                      + (f"（{p['attempts']} 次作答）" if p["attempts"] else ""))
    elif args.kmap_cmd == "next":
        cmd_kmap_next(args)


def cmd_kmap_next(args):
    """按图谱 stage/seq 顺序列出尚未掌握的知识点（语法学习顺序的执行抓手）。
    出语法卷前先看这个：优先出最靠前的未掌握点。"""
    with db.connect() as conn:
        stages = db.kmap_list(conn)
    if not stages:
        print("图谱为空：`kmap import curriculum/grammar_map.json` 导入")
        return
    todo = []
    for st in stages:
        for p in st["points"]:
            if p["status"] != "mastered":
                todo.append(p)
    if not todo:
        print("🎉 图谱全部知识点已掌握！后续用周回顾保持。")
        return
    labels = {"weak": "⚠ 薄弱", "learning": "◐ 学习中", "new": "· 未练过"}
    for p in todo[:args.limit]:
        mark = labels.get(p["status"], p["status"])
        extra = f"（{p['attempts']} 次作答）" if p["attempts"] else "（未练过）"
        print(f"第{p['stage']}阶段[{p['stage_name']}] {mark} {p['name']}  {p['score']}分 {extra}")
    if len(todo) > args.limit:
        print(f"（共 {len(todo)} 个未掌握；按图谱顺序学完当前再往后，先不跳级）")


def cmd_delete(args):
    with db.connect() as conn:
        h = db.delete_homework(conn, args.hw_id)
    print(f"已删除试卷《{h['title']}》#{args.hw_id}（含全部提交与批改记录）")


def main(argv=None):
    db.ensure_db()
    p = argparse.ArgumentParser(
        prog="homework-lab",
        description="homework-lab Agent CLI：发布试卷 / 批改 / 错题与知识点管理。")
    p.add_argument("--json", action="store_true", help="输出 JSON（部分命令支持）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="初始化数据库")

    ps = sub.add_parser("setup", help="首次初始化：写 config.json + 部署数据库（网页向导的 CLI 版）")
    ps.add_argument("--db", help="数据库文件路径（默认 <项目>/data/homework.db）")
    ps.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    ps.add_argument("--port", type=int, help="网页端口（默认 8877）")
    ps.add_argument("--api-token", help="AI 服务 API 访问令牌（可选）")
    ps.add_argument("--rules-json", help="教学规则 JSON 文件（题目目标）")
    ps.add_argument("--profile-json", help="学生画像默认值 JSON 文件")

    pcg = sub.add_parser("config", help="查看当前生效配置（数据库路径/端口/教学规则）")
    pcg.add_argument("--json", action="store_true", help="输出完整 JSON")

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

    pl = sub.add_parser("log", help="记录学习路径事件（讲解/验证等 AI 主动事件）")
    pl.add_argument("type", choices=["assign", "submit", "graded", "explain", "verify",
                                     "weekly", "diag", "request", "other"])
    pl.add_argument("--summary", required=True, help="事件摘要")
    pl.add_argument("--kp", help="关联知识点")
    pl.add_argument("--ref", help="关联对象，如 homework:3 / submission:2")

    pt = sub.add_parser("timeline", help="学习路径时间线")
    pt.add_argument("--limit", type=int, default=30)

    pd_ = sub.add_parser("diag", help="学生问题诊断档案")
    pds = pd_.add_subparsers(dest="diag_cmd", required=True)
    pda = pds.add_parser("add", help="记录一条诊断")
    pda.add_argument("--kp", required=True, help="知识点")
    pda.add_argument("--finding", required=True, help="问题描述")
    pda.add_argument("--severity", default="mid", choices=["high", "mid", "low"])
    pda.add_argument("--sub", type=int, help="关联提交 id")
    pda.add_argument("--evidence", help="证据（错题引用等）")
    pdl = pds.add_parser("list", help="列出诊断")
    pdl.add_argument("--open", action="store_true", help="只显示未解决")
    pdr = pds.add_parser("resolve", help="标记诊断已解决")
    pdr.add_argument("diag_id", type=int)
    pdr.add_argument("--note", help="解决说明（如：验证卷满分）")

    pw_ = sub.add_parser("weekly", help="每周随机知识点回顾")
    pws = pw_.add_subparsers(dest="weekly_cmd", required=True)
    pws.add_parser("status", help="查看上次回顾与候选知识点")
    pwr = pws.add_parser("record", help="记录一次周回顾")
    pwr.add_argument("--sampled", required=True, help="抽查的知识点，逗号分隔")
    pwr.add_argument("--wrong", default="", help="出错的知识点，逗号分隔")
    pwr.add_argument("--hw", type=int, help="关联抽查卷 id")
    pwr.add_argument("--note", help="备注")

    pv = sub.add_parser("vocab", help="单词本")
    pvs = pv.add_subparsers(dest="vocab_cmd", required=True)
    pvl = pvs.add_parser("list", help="列出单词")
    pvl.add_argument("--unfilled", action="store_true", help="只显示缺中文/词性的（提醒学生补填）")
    pvl.add_argument("--confirmed", action="store_true", help="只显示学生已确认的")
    pvl.add_argument("--await-detail", action="store_true", help="只显示已确认但 AI 还没补详细的（批改后查）")
    pvl.add_argument("--pool", action="store_true", help="只显示抽查池里的词")
    pvl.add_argument("--json", dest="out_json", help="导出到 JSON 文件")
    pva = pvs.add_parser("add", help="加入单词")
    pva.add_argument("--word", required=True)
    pva.add_argument("--source", default="")
    pvu = pvs.add_parser("update", help="按 JSON 批量更新（学生：meaning_cn/pos；AI：detail）")
    pvu.add_argument("json_file", help='{"updates":[{"word":"...","detail":"词典词性+详细释义..."}]}')
    pvd = pvs.add_parser("delete", help="删除单词")
    pvd.add_argument("vid", type=int)
    pvk = pvs.add_parser("dictation", help="从单词本生成默写卷 JSON（全词本）")
    pvk.add_argument("--limit", type=int, default=10, help="默写词数（默认 10）")
    pvk.add_argument("--random", action="store_true", help="随机抽词（默认按加入先后）")
    pvk.add_argument("--out", default="papers/dictation_words.json", help="输出路径")
    pvc = pvs.add_parser("check", help="从抽查池随机抽词生成抽查卷 JSON")
    pvc.add_argument("--limit", type=int, default=5, help="抽查词数（默认 5，随机抽取）")
    pvc.add_argument("--out", default="papers/vocab_check.json", help="输出路径")
    pvcr = pvs.add_parser("check-result", help="批改后回写抽查池（对→出池，错→留池）")
    pvcr.add_argument("--sub", dest="sub_id", type=int, required=True, help="抽查卷的提交 id")
    pvhw = pvs.add_parser("homework", help="生成「词汇短语作业」卷（雅思答案词+单词本词+短语讲解卡）")
    pvhw.add_argument("--ielts", type=int, default=20, help="雅思听力阅读答案词数（默认 20）")
    pvhw.add_argument("--wordbook", type=int, default=5, help="单词本词汇数（默认 5）")
    pvhw.add_argument("--phrases", type=int, default=5, help="短语讲解卡数（默认 5）")
    pvhw.add_argument("--out", default="papers/vocab_homework.json", help="输出路径")

    pph = sub.add_parser("phrase", help="短语本（AI 老师教、学生收藏）")
    pphs = pph.add_subparsers(dest="phrase_cmd", required=True)
    pphs.add_parser("list", help="列出短语")
    ppha = pphs.add_parser("add", help="加入短语")
    ppha.add_argument("--phrase", required=True)
    ppha.add_argument("--meaning", default="", help="中文释义")
    ppha.add_argument("--example", default="", help="英文例句")
    ppha.add_argument("--example-cn", default="", help="例句中文")
    ppha.add_argument("--source", default="")
    pphd = pphs.add_parser("delete", help="删除短语")
    pphd.add_argument("pid", type=int)

    ppf = sub.add_parser("profile", help="学生画像（学习目标/话题/题型，出题前必读）")
    ppfs = ppf.add_subparsers(dest="profile_cmd", required=True)
    ppfs.add_parser("get", help="读取画像 JSON")
    ppfe = ppfs.add_parser("set", help="按 JSON 更新画像")
    ppfe.add_argument("json_file", help='{"goals":[...],"topics":[...],"question_types":[...]}')

    pk = sub.add_parser("kmap", help="语法知识图谱")
    pks = pk.add_subparsers(dest="kmap_cmd", required=True)
    pki = pks.add_parser("import", help="导入图谱（全量替换）")
    pki.add_argument("json_file", help="curriculum/grammar_map.json")
    pks.add_parser("list", help="图谱 + 掌握度打分")
    pkn = pks.add_parser("next", help="按图谱顺序列出下一个未掌握知识点")
    pkn.add_argument("--limit", type=int, default=3)

    pdel = sub.add_parser("delete", help="删除试卷（级联删除提交与批改）")
    pdel.add_argument("hw_id", type=int)

    args = p.parse_args(argv)
    handlers = {
        "init": cmd_init, "setup": cmd_setup, "config": cmd_config,
        "create": cmd_create, "list": cmd_list, "paper": cmd_paper,
        "pending": cmd_pending, "autograde": cmd_autograde, "grade": cmd_grade,
        "report": cmd_report, "wronglist": cmd_wronglist, "weakpoints": cmd_weakpoints,
        "requests": cmd_requests, "request": cmd_request_done, "archive": cmd_archive,
        "state": cmd_state, "log": cmd_log, "timeline": cmd_timeline,
        "diag": lambda a: cmd_diag_add(a) if a.diag_cmd == "add"
        else cmd_diag_list(a) if a.diag_cmd == "list" else cmd_diag_resolve(a),
        "weekly": lambda a: cmd_weekly_status(a) if a.weekly_cmd == "status"
        else cmd_weekly_record(a),
        "vocab": cmd_vocab, "profile": cmd_profile, "kmap": cmd_kmap,
        "phrase": cmd_phrase,
        "delete": cmd_delete,
    }
    try:
        handlers[args.cmd](args)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
