#!/usr/bin/env python3
"""定时巡检脚本（watchdog 模式，供任何 cron 体系使用）。

有待批改提交时输出提醒文本；否则输出为空（静默）。
- Hermes cron: no_agent 脚本模式，每 30 分钟跑一次
- 普通 cron:  */30 * * * *  cd /path/to/homework-lab && python3 scripts/check_pending.py | mail ...
用法: python3 scripts/check_pending.py [--json]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402


def main():
    as_json = "--json" in sys.argv
    with db.connect() as conn:
        subs = db.pending_submissions(conn)
    if not subs:
        return  # 静默
    if as_json:
        print(json.dumps({"pending": [{"id": s["id"], "homework": s["homework_title"],
                                       "submitted_at": s["submitted_at"]} for s in subs]},
                         ensure_ascii=False))
    else:
        lines = [f"📥 有 {len(subs)} 份作业待批改："]
        for s in subs:
            lines.append(f"  · 提交 #{s['id']}《{s['homework_title']}》({s['submitted_at']})")
        lines.append("学生交卷了，去批改吧。")
        print("\n".join(lines))


if __name__ == "__main__":
    main()
