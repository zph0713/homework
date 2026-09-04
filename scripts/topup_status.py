#!/usr/bin/env python3
"""常备作业巡检（watchdog 输出，供 Hermes cron monitor / 普通 cron 使用）。

目标：词汇短语作业（vocabulary）+ 雅思专项四子栏目（阅读节选小题 / 英译汉 /
作文中译英 / 口语话题）每栏时刻保持 ≥1 张「未做」作业卡。学生做完/删掉后栏目
出现缺口 → 输出缺口行（输出变化 → 唤醒 AI 老师补齐）；全部齐 → 输出固定 OK 行
（输出不变 → 静默）。

用法: python3 scripts/topup_status.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

NAMES = {"vocabulary": "词汇短语作业",
         "ielts_reading": "阅读节选小题", "ielts_stem": "英译汉（听力/阅读题干）",
         "ielts_essay": "作文中译英", "ielts_speaking": "口语话题"}


def main():
    with db.connect() as conn:
        missing = db.topup_gaps(conn)
    if missing:
        print("TOPUP_NEED|" + ",".join(missing) + "|" +
              ",".join(NAMES[s] for s in missing))
    else:
        print("TOPUP_OK|vocabulary,ielts_reading,ielts_stem,ielts_essay,"
              "ielts_speaking 常备作业都有未做卡")


if __name__ == "__main__":
    main()
