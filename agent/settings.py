"""homework-lab 配置模块 —— 网页、CLI、AI 服务接口共用的唯一配置真相源。

配置文件：<项目根>/config.json（可用环境变量 HOMELAB_CONFIG 覆盖，测试隔离用）。
配置优先级：环境变量（HOMELAB_DB / HOMELAB_HOST / HOMELAB_PORT）> config.json > 内置默认值。

config.json 结构：
{
  "db_path": "/abs/path/homework.db",   # 数据库文件路径（网页与 CLI 读同一份）
  "host": "127.0.0.1",                  # 监听地址
  "port": 8877,                         # 网页端口
  "api_token": "",                      # 可选：AI 服务 API 的访问令牌（局域网开放时建议设置）
  "rules": {                            # 教学规则（题目目标的一部分，出题决策用）
    "mastery_threshold": 85,            # 掌握标准：正确率 %
    "mastery_min_attempts": 5,          # 计分最少作答次数
    "verify_min_questions": 3,          # 验证卷最少题数
    "verify_max_questions": 5,          # 验证卷最多题数
    "weekly_interval_days": 7,          # 周回顾间隔天数
    "diag_max_questions": 15,           # 诊断卷题数上限
    "question_priority": "..."          # 出题决策顺序（逗号分隔）
  },
  "profile": {                          # 学生画像默认值（首次部署时写入数据库）
    "goals": [...], "topics": [...], "question_types": [...], "notes": ""
  }
}
"""
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "data" / "homework.db"

# 教学规则默认值 —— 与 skills/homework-lab/SKILL.md 保持一致，可在初始化页/设置页修改
DEFAULT_RULES = {
    "mastery_threshold": 85,          # 掌握标准：作答超过 min_attempts 次且正确率 ≥ 此值 = 已掌握
    "mastery_min_attempts": 5,        # 少于该次数不计分（图谱显示"计分中"）
    "verify_min_questions": 3,        # 验证卷 3~5 题
    "verify_max_questions": 5,
    "weekly_interval_days": 7,        # 周回顾间隔
    "diag_max_questions": 15,         # 诊断卷题数上限
    "question_priority": "student_request,open_diag,kmap_next,weekly_wrong,weakpoints,writing_curriculum,vocab_dictation",
}

# 学生画像默认值（首次部署种子数据）
DEFAULT_PROFILE = {
    "goals": ["彻底解决英语语法问题", "雅思词汇短语积累"],
    "topics": ["教育", "环保", "科技", "城市", "健康", "工作"],
    "question_types": [],
    "notes": "",
}

DEFAULT_CONFIG = {
    "db_path": str(DEFAULT_DB),
    "host": "127.0.0.1",
    "port": 8877,
    "api_token": "",
    "rules": DEFAULT_RULES,
    "profile": DEFAULT_PROFILE,
}

# 教学规则键的中文名（前端/文档展示用）
RULE_LABELS = {
    "mastery_threshold": "掌握标准（正确率 %）",
    "mastery_min_attempts": "计分最少作答次数",
    "verify_min_questions": "验证卷最少题数",
    "verify_max_questions": "验证卷最多题数",
    "weekly_interval_days": "周回顾间隔（天）",
    "diag_max_questions": "诊断卷题数上限",
}


def config_file() -> Path:
    env = os.environ.get("HOMELAB_CONFIG")
    return Path(env).expanduser() if env else (PROJECT_ROOT / "config.json")


def load_config() -> dict:
    """读取 config.json；不存在或损坏时返回 {}（调用方用 defaults 兜底）。"""
    try:
        return json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict):
    config_file().parent.mkdir(parents=True, exist_ok=True)
    config_file().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def effective_config() -> dict:
    """config.json 与默认值合并后的完整配置（未显式配置的键取默认值）。"""
    cfg = dict(DEFAULT_CONFIG)
    saved = load_config()
    for k in ("db_path", "host", "port", "api_token"):
        if k in saved and saved[k] not in (None, ""):
            cfg[k] = saved[k]
    rules = dict(DEFAULT_RULES)
    rules.update(saved.get("rules") or {})
    cfg["rules"] = rules
    profile = dict(DEFAULT_PROFILE)
    profile.update(saved.get("profile") or {})
    cfg["profile"] = profile
    return cfg


def get_db_path() -> Path:
    """数据库路径：HOMELAB_DB 环境变量 > config.json 的 db_path > 默认 data/homework.db。"""
    env = os.environ.get("HOMELAB_DB")
    if env:
        return Path(env).expanduser()
    p = load_config().get("db_path")
    if p:
        return Path(str(p)).expanduser()
    return DEFAULT_DB


def get_rules() -> dict:
    """教学规则（默认值与 config.json 合并）。"""
    return effective_config()["rules"]


def is_initialized() -> bool:
    """是否已完成页面初始化：config.json 存在即为已初始化。"""
    return config_file().is_file()
