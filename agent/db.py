"""homework-lab 数据层：SQLite 表结构 + 试卷/提交/批改/知识点核心逻辑。

纯标准库实现（sqlite3 + json），零第三方依赖。
数据库路径可用环境变量 HOMELAB_DB 覆盖，默认 <项目根>/data/homework.db。

批改分层：
  - 客观题（choice / tfng）：自动批改即可定对错，无需 AI 复核。
  - 半主观题（fill / cloze）：答案命中参考答案则自动判对；未命中时标记
    needs_review，由 AI 判断是否为可接受的替代答案。
  - 主观题（writing）：必须 AI 批改，无自动判定。
"""
import json
import os
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "homework.db"

QUESTION_TYPES = {"choice", "fill", "cloze", "tfng", "writing", "translate"}
OBJECTIVE_TYPES = {"choice", "tfng"}      # 自动批改即可定论
REVIEW_TYPES = {"fill", "cloze"}         # 未命中参考答案时需 AI 复核
MANUAL_TYPES = {"writing", "translate"}  # 必须 AI 批改

SCHEMA = """
CREATE TABLE IF NOT EXISTS homeworks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL,
  skill       TEXT NOT NULL DEFAULT 'mixed',   -- grammar|vocabulary|reading|writing|mixed
  topic       TEXT NOT NULL DEFAULT '',
  goal        TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'published', -- draft|published|archived
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS passages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  homework_id INTEGER NOT NULL REFERENCES homeworks(id) ON DELETE CASCADE,
  title       TEXT NOT NULL DEFAULT '',
  body        TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS questions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  homework_id    INTEGER NOT NULL REFERENCES homeworks(id) ON DELETE CASCADE,
  passage_id     INTEGER REFERENCES passages(id) ON DELETE CASCADE,
  type           TEXT NOT NULL,                 -- choice|fill|cloze|tfng|writing
  prompt         TEXT NOT NULL,
  passage        TEXT,                          -- cloze 专用：含 __1__ __2__ 空格的短文
  options        TEXT,                          -- JSON 数组（choice）
  answer         TEXT NOT NULL,                 -- JSON：
                                                --   choice -> "B"
                                                --   fill   -> ["答案1","答案2"]
                                                --   cloze  -> {"1": ["...", "..."], "2": "..."}
                                                --   tfng   -> "TRUE"|"FALSE"|"NOT GIVEN"
                                                --   writing-> {"rubric": "评分要点"}
  explanation    TEXT NOT NULL DEFAULT '',
  knowledge_point TEXT NOT NULL DEFAULT '',
  score          REAL NOT NULL DEFAULT 1,
  sort_order     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS submissions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  homework_id      INTEGER NOT NULL REFERENCES homeworks(id) ON DELETE CASCADE,
  answers          TEXT NOT NULL,               -- JSON {qid: answer}
  submitted_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  status           TEXT NOT NULL DEFAULT 'pending', -- pending|partial|graded
  total_score      REAL,
  max_score        REAL,
  correct_count    INTEGER,
  total_count      INTEGER,
  overall_feedback TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS grades (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  question_id   INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  user_answer   TEXT,                          -- JSON 快照
  correct       REAL,                          -- 1 | 0 | 0..1 部分正确
  score         REAL,
  feedback      TEXT NOT NULL DEFAULT '',
  graded_by     TEXT NOT NULL DEFAULT 'ai',    -- auto|ai
  needs_review  INTEGER NOT NULL DEFAULT 0,    -- 1 = 需要 AI 复核（半主观题未命中参考答案）
  graded_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE(submission_id, question_id)
);
CREATE TABLE IF NOT EXISTS knowledge_points (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL UNIQUE,
  attempts   INTEGER NOT NULL DEFAULT 0,
  correct    REAL NOT NULL DEFAULT 0,          -- 累计正确次数（部分正确按小数累计）
  mastery    REAL NOT NULL DEFAULT 0,          -- correct / attempts
  status     TEXT NOT NULL DEFAULT 'new',      -- new|weak|learning|mastered
  updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS requests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  knowledge_point TEXT NOT NULL,
  note            TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'open', -- open|done
  created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS learning_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  event_type      TEXT NOT NULL,          -- assign|submit|graded|explain|verify|weekly|diag|request|other
  summary         TEXT NOT NULL DEFAULT '',
  knowledge_point TEXT NOT NULL DEFAULT '',
  ref_type        TEXT NOT NULL DEFAULT '',    -- homework|submission|diagnosis|weekly|''
  ref_id          INTEGER,
  detail          TEXT NOT NULL DEFAULT ''     -- JSON 扩展
);
CREATE TABLE IF NOT EXISTS diagnoses (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  created_ts      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  knowledge_point TEXT NOT NULL,
  finding         TEXT NOT NULL,          -- 问题描述（诊断结论）
  severity        TEXT NOT NULL DEFAULT 'mid', -- high|mid|low
  evidence        TEXT NOT NULL DEFAULT '',    -- 证据：错题/提交引用
  submission_id   INTEGER,
  status          TEXT NOT NULL DEFAULT 'open', -- open|resolved
  resolved_ts     TEXT,
  resolve_note    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS weekly_reviews (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  reviewed_ts TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  sampled     TEXT NOT NULL DEFAULT '[]',   -- JSON 数组：抽查的知识点
  wrong       TEXT NOT NULL DEFAULT '[]',   -- JSON 数组：抽查出错的知识点
  homework_id INTEGER,                      -- 关联的抽查卷
  note        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS vocabulary (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  word           TEXT NOT NULL UNIQUE,
  meaning_cn     TEXT NOT NULL DEFAULT '',      -- 学生自填的中文意思
  pos            TEXT NOT NULL DEFAULT '[]',    -- JSON 数组：学生多选词性（n./v./adj.…）
  detail         TEXT NOT NULL DEFAULT '',      -- AI 补：词典词性 + 详细中文释义
  confirmed      INTEGER NOT NULL DEFAULT 0,    -- 学生确认已填 meaning_cn + pos
  in_pool        INTEGER NOT NULL DEFAULT 1,    -- 抽查池：1=在池 0=已过关出池
  times_checked  INTEGER NOT NULL DEFAULT 0,    -- 被抽查次数
  last_check_ok  INTEGER,                       -- 最近一次抽查结果：1=对 0=错
  last_checked_ts TEXT,
  last_check_sub INTEGER,                       -- 最近一次抽查的提交 id（防重复回写）
  source         TEXT NOT NULL DEFAULT '',      -- 来源，如 homework#2
  added_ts       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_ts     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS student_profile (
  key        TEXT PRIMARY KEY,             -- goals|topics|question_types|notes
  value      TEXT NOT NULL DEFAULT '[]',   -- JSON
  updated_ts TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS knowledge_map (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL UNIQUE,
  stage      INTEGER NOT NULL,
  stage_name TEXT NOT NULL DEFAULT '',
  seq        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_log_ts ON learning_log(ts);
CREATE INDEX IF NOT EXISTS idx_diag_kp ON diagnoses(knowledge_point);
CREATE INDEX IF NOT EXISTS idx_q_hw   ON questions(homework_id);
CREATE INDEX IF NOT EXISTS idx_sub_hw ON submissions(homework_id);
CREATE INDEX IF NOT EXISTS idx_gr_sub ON grades(submission_id);
"""


# ---------------------------------------------------------------- 连接与初始化
def get_db_path() -> Path:
    """数据库路径：HOMELAB_DB 环境变量 > config.json 的 db_path > 默认 data/homework.db。
    这样设置页改的路径对 CLI 与服务器同时生效。"""
    env = os.environ.get("HOMELAB_DB")
    if env:
        return Path(env).expanduser()
    try:
        cfg = json.loads((PROJECT_ROOT / "config.json").read_text(encoding="utf-8"))
        p = (cfg or {}).get("db_path")
        if p:
            return Path(str(p)).expanduser()
    except (OSError, ValueError):
        pass
    return DEFAULT_DB


def connect(path=None):
    p = Path(path) if path else get_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn):
    """旧库 → 新结构的小步迁移（幂等）。"""
    try:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(vocabulary)")]
    except sqlite3.OperationalError:
        return  # 新库：表由 SCHEMA 直接建成新结构
    if not cols:
        return
    if "note" in cols and "detail" not in cols:
        conn.execute("ALTER TABLE vocabulary RENAME COLUMN note TO detail")
    for name, ddl in (
        ("confirmed", "INTEGER NOT NULL DEFAULT 0"),
        ("in_pool", "INTEGER NOT NULL DEFAULT 1"),
        ("times_checked", "INTEGER NOT NULL DEFAULT 0"),
        ("last_check_ok", "INTEGER"),
        ("last_checked_ts", "TEXT"),
        ("last_check_sub", "INTEGER"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE vocabulary ADD COLUMN {name} {ddl}")
    # 旧 pos 是纯文本（如 "adj."）→ 转成 JSON 数组
    for r in conn.execute("SELECT id, pos FROM vocabulary WHERE pos != '' AND pos NOT LIKE '[%'"):
        conn.execute("UPDATE vocabulary SET pos=? WHERE id=?",
                     (json.dumps([r["pos"]]), r["id"]))


def init_db(path=None):
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        # 掌握度状态依赖 kp_status 规则，规则改版后旧数据要重算（幂等，代价低）
        try:
            recompute_knowledge_points(conn)
        except sqlite3.OperationalError:
            pass  # 新库还没有 grades/questions 时跳过
    return Path(path) if path else get_db_path()


def ensure_db():
    """启动时确保库存在且表结构最新：SCHEMA 全部 IF NOT EXISTS，幂等，可安全反复执行。"""
    init_db()


# ---------------------------------------------------------------- 答案归一化
def norm(s) -> str:
    """小写、去标点、压缩空白，用于宽松比较。"""
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return " ".join(s.split())


def choice_letter(ans) -> str:
    m = re.search(r"[A-D]", (ans or "").upper())
    return m.group(0) if m else ""


TFNG_MAP = {
    "true": "TRUE", "t": "TRUE", "yes": "TRUE", "y": "TRUE", "对": "TRUE", "正确": "TRUE", "一致": "TRUE",
    "false": "FALSE", "f": "FALSE", "no": "FALSE", "n": "FALSE", "错": "FALSE", "错误": "FALSE", "矛盾": "FALSE",
    "not given": "NOT GIVEN", "ng": "NOT GIVEN", "未提及": "NOT GIVEN", "未给出": "NOT GIVEN", "没提": "NOT GIVEN",
}


def tfng_canonical(ans):
    return TFNG_MAP.get(norm(ans))


def _as_list(ans):
    """把 answer 统一成可接受答案列表。"""
    return [ans] if isinstance(ans, str) else (list(ans) if isinstance(ans, (list, tuple)) else [])


def check_answer(qtype, answer_spec, user_ans):
    """返回 (correct, needs_review)。
    correct: 1 / 0 / 0..1（cloze 按空格比例）；needs_review: 是否需 AI 复核。
    """
    if qtype == "choice":
        u, c = choice_letter(user_ans), choice_letter(answer_spec)
        return (1.0, False) if u == c else (0.0, False)
    if qtype == "tfng":
        u = tfng_canonical(user_ans)
        c = tfng_canonical(answer_spec)
        if u is None:
            return (0.0, True)  # 无法识别的答案，交给 AI
        return (1.0, False) if u == c else (0.0, False)
    if qtype == "fill":
        accepted = [norm(a) for a in _as_list(answer_spec)]
        if norm(user_ans) in accepted:
            return (1.0, False)
        return (0.0, True)  # 未命中 → AI 判断是否为可接受替代答案
    if qtype == "cloze":
        spec = answer_spec if isinstance(answer_spec, dict) else {}
        user = user_ans if isinstance(user_ans, dict) else {}
        total = len(spec) or 1
        hit, review = 0, False
        for key, acc_spec in spec.items():
            accepted = [norm(a) for a in _as_list(acc_spec)]
            u = norm(user.get(str(key), ""))
            if u in accepted:
                hit += 1
            elif u == "":
                review = True  # 留空，也可能判错，但统一交 AI 复核
            else:
                review = True
        return (hit / total, review)
    if qtype == "writing" or qtype == "translate":
        return (None, True)  # 必须 AI 批改
    return (None, True)


# ---------------------------------------------------------------- 试卷校验
def validate_paper(data):
    """校验试卷 JSON，问题用中文报错，便于 agent 修正。"""
    errors = []
    if not isinstance(data, dict):
        raise ValueError("试卷 JSON 必须是对象")
    if not data.get("title"):
        errors.append("缺少 title")
    qs = data.get("questions")
    if not isinstance(qs, list) or not qs:
        errors.append("questions 必须是非空数组")
    else:
        for i, q in enumerate(qs, 1):
            t = q.get("type")
            if t not in QUESTION_TYPES:
                errors.append(f"第{i}题: 未知题型 {t!r}（可选 {sorted(QUESTION_TYPES)}）")
                continue
            if not q.get("prompt"):
                errors.append(f"第{i}题({t}): 缺少 prompt")
            ans = q.get("answer")
            if ans is None or ans == "":
                errors.append(f"第{i}题({t}): 缺少 answer")
                continue
            if t == "choice":
                if not isinstance(ans, str) or not re.fullmatch(r"[A-D]", ans.strip().upper()):
                    errors.append(f"第{i}题(choice): answer 应为 A-D 单字母")
                opts = q.get("options")
                if not isinstance(opts, list) or len(opts) < 2:
                    errors.append(f"第{i}题(choice): options 应为选项数组")
            elif t == "fill":
                acc = _as_list(ans)
                if not acc:
                    errors.append(f"第{i}题(fill): answer 应为字符串或非空数组（多个可接受答案用数组）")
            elif t == "cloze":
                if not q.get("prompt") and not q.get("passage"):
                    errors.append(f"第{i}题(cloze): 需要 prompt（引导语）或 passage（短文）")
                if not isinstance(ans, dict) or not ans:
                    errors.append(f'第{i}题(cloze): answer 应为 {{"1": "答案", ...}} 对象')
                elif not q.get("passage"):
                    errors.append(f"第{i}题(cloze): 需要 passage 字段（含 __1__ 空格标记）")
                else:
                    marks = set(re.findall(r"__(\d+)__", q["passage"]))
                    keys = {str(k) for k in ans.keys()}
                    if marks != keys:
                        errors.append(f"第{i}题(cloze): passage 空格 {sorted(marks)} 与 answer 键 {sorted(keys)} 不一致")
            elif t == "tfng":
                if tfng_canonical(ans) is None:
                    errors.append(f"第{i}题(tfng): answer 应为 TRUE / FALSE / NOT GIVEN")
            elif t == "writing" or t == "translate":
                pass  # answer 放评分要点对象
    # passages 引用校验
    passages = data.get("passages") or []
    if not isinstance(passages, list):
        errors.append("passages 应为数组")
    refs = {p.get("ref") for p in passages}
    for i, q in enumerate(qs, 1):
        pref = q.get("passage_ref")
        if pref and pref not in refs:
            errors.append(f"第{i}题: passage_ref {pref!r} 在 passages 中不存在")
    if errors:
        raise ValueError("试卷校验失败：\n" + "\n".join("  - " + e for e in errors))
    return data


def create_paper(conn, data, status="published"):
    validate_paper(data)
    cur = conn.execute(
        "INSERT INTO homeworks (title, skill, topic, goal, status) VALUES (?,?,?,?,?)",
        (data["title"], data.get("skill", "mixed"), data.get("topic", ""),
         data.get("goal", ""), status),
    )
    hw_id = cur.lastrowid
    ref_to_pid = {}
    for i, p in enumerate(data.get("passages") or []):
        cur = conn.execute(
            "INSERT INTO passages (homework_id, title, body, sort_order) VALUES (?,?,?,?)",
            (hw_id, p.get("title", ""), p.get("body", ""), i),
        )
        if p.get("ref"):
            ref_to_pid[p["ref"]] = cur.lastrowid
    for i, q in enumerate(data["questions"]):
        conn.execute(
            """INSERT INTO questions
               (homework_id, passage_id, type, prompt, passage, options, answer,
                explanation, knowledge_point, score, sort_order)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (hw_id,
             ref_to_pid.get(q.get("passage_ref")),
             q["type"], q["prompt"], q.get("passage"),
             json.dumps(q["options"], ensure_ascii=False) if q.get("options") is not None else None,
             json.dumps(q["answer"], ensure_ascii=False),
             q.get("explanation", ""), q.get("knowledge_point", ""),
             float(q.get("score", 1)), i),
        )
    add_log(conn, "assign",
            summary=f"发布《{data['title']}》（{len(data['questions'])} 题，skill={data.get('skill', 'mixed')}）",
            ref_type="homework", ref_id=hw_id)
    return hw_id


# ---------------------------------------------------------------- 自动批改
def autograde_submission(conn, sub_id):
    """自动批改一个提交的客观题/半主观题命中项，返回摘要 dict。"""
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        raise ValueError(f"提交 #{sub_id} 不存在")
    answers = json.loads(sub["answers"])
    qs = conn.execute(
        "SELECT * FROM questions WHERE homework_id=? ORDER BY sort_order, id",
        (sub["homework_id"],),
    ).fetchall()
    graded, need_review = [], []
    for q in qs:
        if q["type"] in MANUAL_TYPES:
            continue  # 主观题留给 AI
        user = answers.get(str(q["id"]))
        if user is None or user == "":
            continue  # 未作答，留给 AI 决定是否计 0
        spec = json.loads(q["answer"])
        correct, review = check_answer(q["type"], spec, user)
        conn.execute(
            """INSERT INTO grades (submission_id, question_id, user_answer, correct, score,
                                   graded_by, needs_review)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(submission_id, question_id)
               DO UPDATE SET user_answer=excluded.user_answer, correct=excluded.correct,
                             score=excluded.score, graded_by='auto',
                             needs_review=excluded.needs_review,
                             graded_at=datetime('now','localtime')""",
            (sub_id, q["id"], json.dumps(user, ensure_ascii=False),
             correct, (correct or 0.0) * q["score"], "auto", 1 if review else 0),
        )
        (need_review if review else graded).append(q["id"])
    finalize_if_ready(conn, sub_id)
    return {"submission_id": sub_id, "auto_graded": graded, "needs_review": need_review}


# ---------------------------------------------------------------- AI 批改
def apply_grades(conn, sub_id, grades, note=None):
    """写入 AI 批改结果。grades: [{"question_id", "correct", "feedback", "score"?}]
    correct 语义：0~1 比例（部分正确用 0.75 等小数），传入分值会被钳制。"""
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        raise ValueError(f"提交 #{sub_id} 不存在")
    qids = {r["id"] for r in conn.execute(
        "SELECT id FROM questions WHERE homework_id=?", (sub["homework_id"],))}
    answers = json.loads(sub["answers"])
    applied = []
    for g in grades:
        qid = int(g["question_id"])
        if qid not in qids:
            raise ValueError(f"批改条目引用了不属于该试卷的题 {qid}")
        q = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
        correct = min(1.0, max(0.0, float(g["correct"])))
        score = float(g.get("score", correct * q["score"]))
        conn.execute(
            """INSERT INTO grades (submission_id, question_id, user_answer, correct, score,
                                   feedback, graded_by, needs_review)
               VALUES (?,?,?,?,?,?,?,0)
               ON CONFLICT(submission_id, question_id)
               DO UPDATE SET correct=excluded.correct, score=excluded.score,
                             feedback=excluded.feedback, graded_by='ai',
                             needs_review=0,
                             graded_at=datetime('now','localtime')""",
            (sub_id, qid, json.dumps(answers.get(str(qid)), ensure_ascii=False),
             correct, score, g.get("feedback", ""), "ai"),
        )
        applied.append(qid)
    if note:
        conn.execute("UPDATE submissions SET overall_feedback=? WHERE id=?", (note, sub_id))
    if sub["status"] == "graded":
        # 已批改提交的修正批改：重算总分与知识点（不重复记 graded 日志）
        _recalc_totals(conn, sub_id)
        recompute_knowledge_points(conn)
    else:
        finalize_if_ready(conn, sub_id)
    return applied


def _recalc_totals(conn, sub_id):
    qs = conn.execute(
        "SELECT id, score FROM questions WHERE homework_id="
        "(SELECT homework_id FROM submissions WHERE id=?)", (sub_id,)).fetchall()
    grades = {r["question_id"]: r for r in conn.execute(
        "SELECT * FROM grades WHERE submission_id=?", (sub_id,))}
    total = sum(g["score"] or 0 for g in grades.values())
    max_score = sum(q["score"] for q in qs)
    correct_count = sum(1 for g in grades.values() if g["correct"] == 1.0)
    conn.execute(
        "UPDATE submissions SET total_score=?, max_score=?, correct_count=?, total_count=? WHERE id=?",
        (total, max_score, correct_count, len(qs), sub_id),
    )
    return total, max_score, correct_count, len(qs)


def finalize_if_ready(conn, sub_id):
    """若所有题都已有 grade 且无 needs_review，则把提交置为 graded 并重算统计/知识点。
    已 graded 的提交直接返回（幂等，避免重复记日志）。"""
    cur_status = conn.execute("SELECT status FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not cur_status or cur_status["status"] == "graded":
        return
    qs = conn.execute(
        "SELECT id, score FROM questions WHERE homework_id="
        "(SELECT homework_id FROM submissions WHERE id=?)", (sub_id,)).fetchall()
    if not qs:
        return
    grades = {r["question_id"]: r for r in conn.execute(
        "SELECT * FROM grades WHERE submission_id=?", (sub_id,))}
    missing = [q["id"] for q in qs if q["id"] not in grades or grades[q["id"]]["needs_review"]]
    if missing:
        conn.execute("UPDATE submissions SET status='partial' WHERE id=?", (sub_id,))
        return
    total, max_score, correct_count, nq = _recalc_totals(conn, sub_id)
    conn.execute("UPDATE submissions SET status='graded' WHERE id=?", (sub_id,))
    recompute_knowledge_points(conn)
    hw = conn.execute("SELECT title FROM homeworks WHERE id="
                      "(SELECT homework_id FROM submissions WHERE id=?)", (sub_id,)).fetchone()
    add_log(conn, "graded",
            summary=f"批改完成《{hw['title']}》提交 #{sub_id}：得分 {total:g}/{max_score:g}，全对 {correct_count}/{nq}",
            ref_type="submission", ref_id=sub_id)


def recompute_knowledge_points(conn):
    """从所有已批改提交的 grades 重建知识点掌握度表（幂等，杜绝重复累计）。"""
    rows = conn.execute(
        """SELECT q.knowledge_point AS kp, g.correct
           FROM grades g JOIN questions q ON q.id = g.question_id
           JOIN submissions s ON s.id = g.submission_id
           WHERE s.status='graded' AND q.knowledge_point != ''""").fetchall()
    agg = {}
    for r in rows:
        kp = r["kp"]
        d = agg.setdefault(kp, [0, 0.0])
        d[0] += 1
        d[1] += r["correct"] or 0.0
    conn.execute("DELETE FROM knowledge_points")
    for kp, (attempts, correct) in sorted(agg.items()):
        mastery = correct / attempts if attempts else 0.0
        status = kp_status(attempts, mastery)
        conn.execute(
            "INSERT INTO knowledge_points (name, attempts, correct, mastery, status) VALUES (?,?,?,?,?)",
            (kp, attempts, correct, mastery, status),
        )


def kp_status(attempts, mastery):
    if attempts == 0:
        return "new"
    if attempts > 5 and mastery >= 0.85:
        return "mastered"
    if attempts > 5 and mastery < 0.5:
        return "weak"
    return "learning"


# ---------------------------------------------------------------- 查询
def list_homeworks(conn):
    rows = conn.execute(
        "SELECT * FROM homeworks WHERE status != 'draft' ORDER BY id DESC").fetchall()
    out = []
    for h in rows:
        qc = conn.execute("SELECT COUNT(*) c FROM questions WHERE homework_id=?", (h["id"],)).fetchone()["c"]
        sub = conn.execute(
            "SELECT id, status, total_score, max_score, correct_count, total_count, submitted_at "
            "FROM submissions WHERE homework_id=? ORDER BY id DESC LIMIT 1", (h["id"],)).fetchone()
        out.append({
            "id": h["id"], "title": h["title"], "skill": h["skill"], "topic": h["topic"],
            "goal": h["goal"], "status": h["status"], "created_at": h["created_at"],
            "question_count": qc,
            "latest_submission": dict(sub) if sub else None,
        })
    return out


def paper_full(conn, hw_id):
    h = conn.execute("SELECT * FROM homeworks WHERE id=?", (hw_id,)).fetchone()
    if not h:
        return None
    ps = conn.execute("SELECT * FROM passages WHERE homework_id=? ORDER BY sort_order, id",
                      (hw_id,)).fetchall()
    qs = conn.execute("SELECT * FROM questions WHERE homework_id=? ORDER BY sort_order, id",
                      (hw_id,)).fetchall()
    return {"homework": dict(h), "passages": [dict(p) for p in ps],
            "questions": [dict(q) for q in qs]}


def paper_for_student(conn, hw_id):
    """给学生看的试卷：剔除 answer / explanation 等批改信息。"""
    full = paper_full(conn, hw_id)
    if not full:
        return None
    qs = []
    for q in full["questions"]:
        q = {k: v for k, v in q.items() if k not in ("answer", "explanation")}
        if isinstance(q.get("options"), str):
            q["options"] = json.loads(q["options"])
        qs.append(q)
    return {"homework": full["homework"], "passages": full["passages"], "questions": qs}


def submission_detail(conn, sub_id):
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        return None
    h = conn.execute("SELECT id, title, skill, topic FROM homeworks WHERE id=?",
                     (sub["homework_id"],)).fetchone()
    qs = conn.execute("SELECT * FROM questions WHERE homework_id=? ORDER BY sort_order, id",
                      (sub["homework_id"],)).fetchall()
    gs = {r["question_id"]: r for r in conn.execute(
        "SELECT * FROM grades WHERE submission_id=?", (sub_id,))}
    answers = json.loads(sub["answers"])
    items = []
    for q in qs:
        g = gs.get(q["id"])
        passage = None
        if q["passage_id"]:
            p = conn.execute("SELECT title, body FROM passages WHERE id=?", (q["passage_id"],)).fetchone()
            passage = dict(p) if p else None
        items.append({
            "question_id": q["id"], "type": q["type"], "prompt": q["prompt"],
            "passage": q["passage"], "options": json.loads(q["options"]) if q["options"] else None,
            "passage_info": passage,
            "user_answer": answers.get(str(q["id"])),
            "correct_answer": json.loads(q["answer"]) if q["answer"] else None,
            "explanation": q["explanation"], "knowledge_point": q["knowledge_point"],
            "max_score": q["score"],
            "correct": g["correct"] if g else None,
            "score": g["score"] if g else None,
            "feedback": g["feedback"] if g else "",
            "graded_by": g["graded_by"] if g else None,
            "needs_review": g["needs_review"] if g else None,
        })
    return {
        "id": sub["id"], "homework_id": sub["homework_id"], "homework_title": h["title"],
        "submitted_at": sub["submitted_at"], "status": sub["status"],
        "total_score": sub["total_score"], "max_score": sub["max_score"],
        "correct_count": sub["correct_count"], "total_count": sub["total_count"],
        "overall_feedback": sub["overall_feedback"], "items": items,
    }


def pending_submissions(conn):
    """所有待 AI 处理的提交，含需要复核的题目详情。"""
    subs = conn.execute(
        "SELECT * FROM submissions WHERE status IN ('pending','partial') ORDER BY id").fetchall()
    out = []
    for sub in subs:
        h = conn.execute("SELECT title FROM homeworks WHERE id=?", (sub["homework_id"],)).fetchone()
        answers = json.loads(sub["answers"])
        graded_ids = {r["question_id"] for r in conn.execute(
            "SELECT question_id FROM grades WHERE submission_id=?", (sub["id"],))}
        qs = conn.execute(
            "SELECT * FROM questions WHERE homework_id=? ORDER BY sort_order, id",
            (sub["homework_id"],)).fetchall()
        todo = []
        for q in qs:
            g = conn.execute(
                "SELECT * FROM grades WHERE submission_id=? AND question_id=?",
                (sub["id"], q["id"])).fetchone()
            if q["type"] in MANUAL_TYPES and q["id"] not in graded_ids:
                todo.append(q)  # 主观题未批
            elif g and g["needs_review"]:
                todo.append(q)  # 半主观题待复核
        out.append({
            "id": sub["id"], "homework_id": sub["homework_id"],
            "homework_title": h["title"] if h else "?",
            "submitted_at": sub["submitted_at"], "status": sub["status"],
            "answers": answers,
            "todo_questions": [{
                "id": q["id"], "type": q["type"], "prompt": q["prompt"],
                "passage": q["passage"],
                "options": json.loads(q["options"]) if q["options"] else None,
                "answer_spec": json.loads(q["answer"]),
                "user_answer": answers.get(str(q["id"])),
                "knowledge_point": q["knowledge_point"], "score": q["score"],
            } for q in todo],
        })
    return out


def wrong_items(conn, kp=None, limit=200):
    """错题集合（correct < 1 的已批改题目）。"""
    sql = """SELECT g.id AS grade_id, g.user_answer, g.correct, g.feedback, g.graded_at,
                    q.id AS question_id, q.type, q.prompt, q.passage, q.options,
                    q.answer, q.explanation, q.knowledge_point,
                    h.id AS homework_id, h.title AS homework_title
             FROM grades g
             JOIN questions q ON q.id = g.question_id
             JOIN submissions s ON s.id = g.submission_id
             JOIN homeworks h ON h.id = q.homework_id
             WHERE s.status='graded' AND g.correct < 1"""
    params = []
    if kp:
        sql += " AND q.knowledge_point = ?"
        params.append(kp)
    sql += " ORDER BY g.graded_at DESC, g.id DESC LIMIT ?"
    params.append(limit)
    out = []
    for r in conn.execute(sql, params):
        out.append({
            "grade_id": r["grade_id"], "question_id": r["question_id"], "type": r["type"],
            "prompt": r["prompt"], "passage": r["passage"],
            "options": json.loads(r["options"]) if r["options"] else None,
            "user_answer": json.loads(r["user_answer"]) if r["user_answer"] else None,
            "correct_answer": json.loads(r["answer"]),
            "explanation": r["explanation"], "feedback": r["feedback"],
            "knowledge_point": r["knowledge_point"],
            "homework_id": r["homework_id"], "homework_title": r["homework_title"],
            "graded_at": r["graded_at"], "partial": r["correct"],
        })
    return out


def knowledge_table(conn):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM knowledge_points ORDER BY attempts DESC, mastery ASC")]


def add_request(conn, knowledge_point, note=""):
    cur = conn.execute(
        "INSERT INTO requests (knowledge_point, note) VALUES (?,?)", (knowledge_point, note))
    return cur.lastrowid


def list_requests(conn, only_open=True):
    sql = "SELECT * FROM requests"
    if only_open:
        sql += " WHERE status='open'"
    sql += " ORDER BY id DESC"
    return [dict(r) for r in conn.execute(sql)]


def set_request_status(conn, req_id, status):
    conn.execute("UPDATE requests SET status=? WHERE id=?", (status, req_id))


def set_homework_status(conn, hw_id, status):
    conn.execute("UPDATE homeworks SET status=? WHERE id=?", (status, hw_id))


def state_snapshot(conn):
    """首页/总览数据。"""
    diag = conn.execute("SELECT COUNT(*) c FROM diagnoses WHERE status='open'").fetchone()["c"]
    wk = conn.execute("SELECT MAX(reviewed_ts) t FROM weekly_reviews").fetchone()["t"]
    recent = conn.execute(
        """SELECT s.id, s.total_score, s.max_score, s.correct_count, s.total_count,
                  s.submitted_at, h.title
           FROM submissions s JOIN homeworks h ON h.id = s.homework_id
           WHERE s.status='graded' ORDER BY s.id DESC LIMIT 5""").fetchall()
    return {
        "homeworks": list_homeworks(conn),
        "knowledge": knowledge_table(conn),
        "open_requests": list_requests(conn),
        "open_diagnoses": diag,
        "last_weekly_review": wk,
        "recent_graded": [dict(r) for r in recent],
        "profile": profile_get(conn),
    }


# ---------------------------------------------------------------- 学习路径 / 诊断 / 周回顾
def add_log(conn, event_type, summary="", knowledge_point="", ref_type="", ref_id=None, detail=None):
    cur = conn.execute(
        """INSERT INTO learning_log (event_type, summary, knowledge_point, ref_type, ref_id, detail)
           VALUES (?,?,?,?,?,?)""",
        (event_type, summary, knowledge_point, ref_type, ref_id,
         json.dumps(detail, ensure_ascii=False) if detail is not None else ""),
    )
    return cur.lastrowid


def list_logs(conn, limit=30, event_type=None):
    sql = "SELECT * FROM learning_log"
    params = []
    if event_type:
        sql += " WHERE event_type=?"
        params.append(event_type)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def add_diagnosis(conn, knowledge_point, finding, severity="mid", evidence="", submission_id=None):
    cur = conn.execute(
        """INSERT INTO diagnoses (knowledge_point, finding, severity, evidence, submission_id)
           VALUES (?,?,?,?,?)""",
        (knowledge_point, finding, severity, evidence, submission_id),
    )
    did = cur.lastrowid
    add_log(conn, "diag", summary=f"诊断「{knowledge_point}」：{finding[:60]}",
            knowledge_point=knowledge_point, ref_type="diagnosis", ref_id=did)
    return did


def list_diagnoses(conn, only_open=False):
    sql = "SELECT * FROM diagnoses"
    if only_open:
        sql += " WHERE status='open'"
    sql += " ORDER BY id DESC"
    return [dict(r) for r in conn.execute(sql)]


def resolve_diagnosis(conn, diag_id, note=""):
    conn.execute(
        """UPDATE diagnoses SET status='resolved', resolved_ts=datetime('now','localtime'),
           resolve_note=? WHERE id=?""",
        (note, diag_id),
    )
    row = conn.execute("SELECT * FROM diagnoses WHERE id=?", (diag_id,)).fetchone()
    add_log(conn, "diag", summary=f"诊断 #{diag_id}「{row['knowledge_point']}」已解决"
                                  + (f"（{note[:40]}）" if note else ""),
            knowledge_point=row["knowledge_point"], ref_type="diagnosis", ref_id=diag_id)


def add_weekly_review(conn, sampled, wrong, homework_id=None, note=""):
    cur = conn.execute(
        """INSERT INTO weekly_reviews (sampled, wrong, homework_id, note) VALUES (?,?,?,?)""",
        (json.dumps(sampled, ensure_ascii=False), json.dumps(wrong, ensure_ascii=False),
         homework_id, note),
    )
    wid = cur.lastrowid
    add_log(conn, "weekly",
            summary=f"周回顾 #{wid}：抽查 {sampled}" + (f"，出错 {wrong}" if wrong else "，全部通过 ✓"),
            ref_type="weekly", ref_id=wid)
    return wid


def last_weekly_review(conn):
    return conn.execute("SELECT * FROM weekly_reviews ORDER BY id DESC LIMIT 1").fetchone()


def weekly_candidates(conn):
    """周回顾候选知识点：近期学习记录出现过的 + 掌握度表里的，按近期优先。"""
    seen, result = set(), []
    for r in conn.execute("SELECT knowledge_point FROM learning_log WHERE knowledge_point != '' ORDER BY id DESC"):
        if r["knowledge_point"] not in seen:
            seen.add(r["knowledge_point"])
            result.append(r["knowledge_point"])
    for r in conn.execute("SELECT name FROM knowledge_points WHERE attempts > 0 ORDER BY attempts DESC"):
        if r["name"] not in seen:
            result.append(r["name"])
    return result


# ---------------------------------------------------------------- 单词本
def _parse_pos(raw):
    """pos 列存 JSON 数组；兼容旧纯文本。"""
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]
    except (ValueError, TypeError):
        return [str(raw)]


def vocab_add(conn, word, detail="", source=""):
    """加入单词本。已存在则返回既有行（created=False），不重复插入。"""
    word = (word or "").strip()
    if not word:
        raise ValueError("单词不能为空")
    cur = conn.execute(
        "INSERT OR IGNORE INTO vocabulary (word, detail, source) VALUES (?,?,?)",
        (word, detail, source),
    )
    created = cur.rowcount > 0
    row = conn.execute("SELECT * FROM vocabulary WHERE word=?", (word,)).fetchone()
    return dict(row), created


def vocab_list(conn, **filters):
    """列出单词（pos 解析为数组）。filters: unfilled_only / confirmed_only /
    await_detail / pool_only。"""
    sql = "SELECT * FROM vocabulary WHERE 1=1"
    if filters.get("unfilled_only"):
        sql += " AND (meaning_cn='' OR pos='[]' OR pos='')"
    if filters.get("confirmed_only"):
        sql += " AND confirmed=1"
    if filters.get("await_detail"):
        sql += " AND confirmed=1 AND detail=''"
    if filters.get("pool_only"):
        sql += " AND in_pool=1 AND meaning_cn!='' AND confirmed=1"
    sql += " ORDER BY added_ts DESC, id DESC"
    out = []
    for r in conn.execute(sql):
        d = dict(r)
        d["pos"] = _parse_pos(r["pos"])
        out.append(d)
    return out


def vocab_update(conn, updates):
    """更新单词字段：meaning_cn（学生）/ pos（学生，数组）/ detail（AI 词典信息）/ confirmed。
    updates: [{"word" 或 "id": ..., "meaning_cn": ..., "pos": [...], "detail": ..., "confirmed": 1}]"""
    updated = []
    for u in updates:
        word = (u.get("word") or "").strip()
        if "id" in u and u["id"] is not None:
            row = conn.execute("SELECT * FROM vocabulary WHERE id=?", (int(u["id"]),)).fetchone()
        else:
            row = conn.execute("SELECT * FROM vocabulary WHERE word=?", (word,)).fetchone()
        if not row:
            continue
        meaning = u.get("meaning_cn", row["meaning_cn"])
        pos = u.get("pos", _parse_pos(row["pos"]))
        pos_json = json.dumps(pos, ensure_ascii=False) if isinstance(pos, (list, tuple)) else str(pos)
        detail = u.get("detail", row["detail"])
        confirmed = int(u.get("confirmed", row["confirmed"]))
        conn.execute(
            """UPDATE vocabulary SET meaning_cn=?, pos=?, detail=?, confirmed=?,
               updated_ts=datetime('now','localtime') WHERE id=?""",
            (meaning or "", pos_json, detail or "", confirmed, row["id"]),
        )
        updated.append(row["id"])
    return updated


def vocab_delete(conn, vid):
    conn.execute("DELETE FROM vocabulary WHERE id=?", (vid,))


def vocab_check_candidates(conn):
    """抽查池候选：已确认且填了中文的词。"""
    return vocab_list(conn, pool_only=True)


def vocab_apply_check(conn, sub_id):
    """批改后回写抽查池：抽对的词标记绿色并出池（in_pool=0），拼错的留在池里。
    返回 {"correct": [...], "wrong": [...]}。"""
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        raise ValueError(f"提交 #{sub_id} 不存在")
    qs = conn.execute("SELECT * FROM questions WHERE homework_id=?", (sub["homework_id"],)).fetchall()
    grades = {r["question_id"]: r for r in conn.execute(
        "SELECT * FROM grades WHERE submission_id=?", (sub_id,))}
    correct, wrong = [], []
    for q in qs:
        if q["knowledge_point"] != "词汇-抽查":
            continue
        g = grades.get(q["id"])
        if not g or g["correct"] is None:
            continue
        spec = json.loads(q["answer"])
        word = _as_list(spec)[0] if spec else ""
        if not word:
            continue
        ok = g["correct"] == 1.0
        conn.execute(
            """UPDATE vocabulary SET in_pool=?, last_check_ok=?, times_checked=times_checked+1,
               last_checked_ts=datetime('now','localtime'), last_check_sub=?
               WHERE word=? AND (last_check_sub IS NULL OR last_check_sub != ?)""",
            (0 if ok else 1, 1 if ok else 0, sub_id, word, sub_id),
        )
        (correct if ok else wrong).append(word)
    return {"correct": correct, "wrong": wrong}


# ---------------------------------------------------------------- 学生画像
def profile_get(conn):
    out = {}
    for r in conn.execute("SELECT key, value, updated_ts FROM student_profile"):
        try:
            out[r["key"]] = json.loads(r["value"])
        except ValueError:
            out[r["key"]] = r["value"]
        out[r["key"] + "_ts"] = r["updated_ts"]
    return out


def profile_set(conn, key, value):
    conn.execute(
        """INSERT INTO student_profile (key, value, updated_ts) VALUES (?,?,datetime('now','localtime'))
           ON CONFLICT(key) DO UPDATE SET value=excluded.value,
           updated_ts=datetime('now','localtime')""",
        (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value),
    )


# ---------------------------------------------------------------- 知识图谱
def kmap_import(conn, payload):
    """payload: {"stages":[{"stage":1,"stage_name":"基础词法","points":["名词",...]}, ...]}
    全量替换 knowledge_map 表。"""
    stages = payload.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("kmap JSON 需要 stages 数组")
    conn.execute("DELETE FROM knowledge_map")
    seq = 0
    for st in stages:
        stage = int(st.get("stage", 0))
        stage_name = st.get("stage_name", f"第{stage}阶段")
        for p in st.get("points", []):
            seq += 1
            conn.execute(
                "INSERT INTO knowledge_map (name, stage, stage_name, seq) VALUES (?,?,?,?)",
                (p, stage, stage_name, seq),
            )
    return seq


def kmap_list(conn):
    """知识图谱 + 掌握度合并：作答超过 5 次才开始按正确率计分，否则 0 分（统计中）。"""
    kps = {r["name"]: r for r in conn.execute("SELECT * FROM knowledge_points")}
    rows = [dict(r) for r in conn.execute("SELECT * FROM knowledge_map ORDER BY stage, seq")]
    stages = {}
    for r in rows:
        k = kps.get(r["name"])
        attempts = k["attempts"] if k else 0
        counted = attempts > 5
        r["mastery"] = k["mastery"] if k else 0.0
        r["attempts"] = attempts
        r["correct"] = k["correct"] if k else 0.0
        r["score"] = round((k["mastery"] if k else 0.0) * 100) if counted else 0
        r["counted"] = counted
        r["status"] = k["status"] if k else "new"
        st = stages.setdefault(r["stage"], {"stage": r["stage"], "stage_name": r["stage_name"], "points": []})
        st["points"].append(r)
    return [stages[k] for k in sorted(stages)]


def kmap_summary(conn):
    """图谱总评：已学/已掌握/薄弱/计分中/平均分（平均只算已开始计分的点）。"""
    rows = kmap_list(conn)
    pts = [p for s in rows for p in s["points"]]
    total = len(pts)
    attempted = sum(1 for p in pts if p["attempts"] > 0)
    mastered = sum(1 for p in pts if p["status"] == "mastered")
    weak = sum(1 for p in pts if p["status"] == "weak")
    counted = [p for p in pts if p["counted"]]
    avg = round(sum(p["score"] for p in counted) / len(counted)) if counted else 0
    if total == 0:
        grade = "还没有知识点数据"
    elif avg >= 85:
        grade = "优秀：整体掌握扎实"
    elif avg >= 60:
        grade = "良好：主干已掌握，薄弱点待清零"
    elif avg >= 30:
        grade = "起步：按图谱顺序逐步推进"
    else:
        grade = "刚起步：从第一阶段开始学习"
    return {"total": total, "attempted": attempted, "mastered": mastered, "weak": weak,
            "counting": total - len(counted), "avg": avg, "grade": grade}


# ---------------------------------------------------------------- 删除试卷
def delete_homework(conn, hw_id):
    h = conn.execute("SELECT * FROM homeworks WHERE id=?", (hw_id,)).fetchone()
    if not h:
        raise ValueError(f"试卷 #{hw_id} 不存在")
    conn.execute("DELETE FROM homeworks WHERE id=?", (hw_id,))  # 级联删除 questions/submissions/grades
    add_log(conn, "other", summary=f"删除试卷《{h['title']}》（#{hw_id}）及其全部提交记录")
    return dict(h)
