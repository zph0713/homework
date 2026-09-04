#!/usr/bin/env python3
"""雅思四栏目常备巡检（watchdog 输出，供 Hermes cron monitor / 普通 cron 使用）。

目标：雅思专项 4 个子栏目（阅读节选小题 / 英译汉 / 作文中译英 / 口语话题）
每栏时刻保持 ≥1 张「未做」作业卡。学生做完 / 删掉卡片后栏目出现缺口 → 输出缺口行
（输出变化 → 唤醒 AI 老师补齐）；四栏目都齐 → 输出固定 OK 行（输出不变 → 静默）。

用法: python3 scripts/ielts_topup_status.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

NAMES = {"ielts_reading": "阅读节选小题", "ielts_stem": "英译汉（听力/阅读题干）",
         "ielts_essay": "作文中译英", "ielts_speaking": "口语话题"}


def main():
    with db.connect() as conn:
        missing = db.ielts_gaps(conn)
    if missing:
        print("IELTS_TOPUP_NEED|" + ",".join(missing) + "|" +
              ",".join(NAMES[s] for s in missing))
    else:
        print("IELTS_TOPUP_OK|reading,stem,essay,speaking 四栏目都有未做作业")


if __name__ == "__main__":
    main()
