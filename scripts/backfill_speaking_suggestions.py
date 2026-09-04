#!/usr/bin/env python3
"""把 papers/ielts_speaking_001.json 的 extra.suggestions 回写进已发布的卷 #22（保留原 part）。

只动 questions.extra（展示数据），不动提交/批改记录。用法: python3 scripts/backfill_speaking_suggestions.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

HW_ID = 22
SRC = Path(__file__).resolve().parent.parent / "papers/ielts_speaking_001.json"


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    assert data["skill"] == "ielts_speaking"
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, extra, sort_order FROM questions WHERE homework_id=? ORDER BY sort_order, id",
            (HW_ID,)).fetchall()
        if len(rows) != len(data["questions"]):
            print(f"⚠️ 题数不一致：DB {len(rows)} vs JSON {len(data['questions'])}，中止")
            sys.exit(1)
        for row, q in zip(rows, data["questions"]):
            extra = json.loads(row["extra"]) if row["extra"] else {}
            extra["suggestions"] = q["extra"]["suggestions"]
            conn.execute("UPDATE questions SET extra=? WHERE id=?",
                         (json.dumps(extra, ensure_ascii=False), row["id"]))
            print(f"  · Q{row['id']} extra.suggestions = {len(extra['suggestions'])} 条")
        print(f"✅ 已回写《雅思口语 #1》(hw #{HW_ID}) 全部 {len(rows)} 题")


if __name__ == "__main__":
    main()
