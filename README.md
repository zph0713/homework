# 📝 Homework Lab · 作业实验室

**本地试卷系统 + 轻量数据库 + Agent 批改循环**——AI 布置作业 → 你在网页上答卷 → AI 从数据库读取批改 → 错题讲解 + 针对性再出题 → 直到彻底掌握。

- **零依赖**：Python 标准库（sqlite3 + http.server）+ 原生 JS，任何机器开箱即用，不用装任何包
- **只在本机**：服务器只绑定 `127.0.0.1`，学习数据（`data/`）不入 git
- **模型无关**：任何 AI / agent（换模型、换工具都行）通过一套 JSON 协议 + CLI 接入，见 [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md)
- **当前学科**：英语（语法 + 雅思词汇短语），学科可扩展

## 快速开始

```bash
cd homework-lab

# 1. 初始化数据库（首次）
python3 agent/cli.py init

# 2. 发布第一份试卷
python3 agent/cli.py create papers/diagnostic_001.json

# 3. 启动本地网页
python3 server/app.py
# → 打开 http://127.0.0.1:8877
```

之后每天的使用方式：
1. 打开 http://127.0.0.1:8877 → 看到待做作业 → 答题 → 交卷
2. 交卷后在聊天里说一声「交了」
3. Agent（老师）执行批改循环 → 网页上出现成绩 + 每道题的点评解析，聊天里同步讲解错题
4. Agent 根据薄弱知识点发布针对性验证卷 → 回到第 1 步
5. 每周 Agent 从错题本导出错题 → 生成变式重练卷

## 学习循环（核心理念）

```
出题(考察知识点) → 答题 → 批改 → 讲解错题 → 出变式题验证 → 全对为止 → 定期错题重练
```

- **题目不在多，在于多轮考察**：每个知识点至少答对 3 次且掌握度 ≥85% 才算「已掌握」
- **错题全部归档**：网页「错题本」页随时可回顾，也可以一键「申请重练」某知识点
- **知识点追踪**：每道题标注知识点，系统自动统计掌握度（薄弱⚠ / 学习中 / 已掌握✓），Agent 据此调整出题方向

## 项目结构

```
homework-lab/
├── agent/
│   ├── db.py               # 数据层：表结构、试卷校验、自动批改、知识点统计
│   └── cli.py              # Agent CLI：发布/批改/错题/知识点管理（模型无关接口）
├── server/
│   ├── app.py              # 本地 HTTP 服务器（标准库，只绑 127.0.0.1）
│   └── static/             # 学生端网页（无框架 SPA）
├── papers/                 # 试卷库（JSON，随 git 版本管理）
├── data/                   # SQLite 学习数据（本地，不入 git）
└── docs/
    ├── AGENT_PROTOCOL.md   # ★ 任何 AI/agent 的接入协议（试卷 JSON 规范 + CLI 参考）
    └── QUESTION_TYPES.md   # 题型规范与出题指南
```

## 批改分层

| 题型 | 自动批改 | AI 批改 | 说明 |
|---|---|---|---|
| 单选 choice | ✅ | — | 对错明确 |
| 判断 TFNG | ✅ | — | 对错明确 |
| 填空 fill | 命中参考答案时 ✅ | 未命中时复核 | AI 判断是否为可接受的替代答案 |
| 语法填空 cloze | 按空格比例给分 ✅ | 未命中空格复核 | 同上 |
| 写作 writing | — | ✅ 必批 | AI 按 rubric 打分 + 写点评 |

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOMELAB_DB` | `data/homework.db` | 数据库路径（测试时指向临时文件） |
| `HOMELAB_PORT` | `8877` | 网页端口 |

## 常见问题

**重启电脑后网页打不开？** 服务器是手动启动的，重新运行：
```bash
cd ~/Documents/GitHub/homework-lab && python3 server/app.py
```

**想换端口？** `HOMELAB_PORT=8899 python3 server/app.py`

**数据会丢吗？** 所有学习数据在 `data/homework.db`（单文件 SQLite）。备份只需复制这一个文件。

## Roadmap

- [ ] 题型扩展：词汇搭配选择、段落匹配、雅思图表题
- [ ] 错题重练支持「同类变式」自动重排
- [ ] 其他学科接入（题目类型与知识点标签体系已是通用的）
- [ ] 定时任务：检测到新交卷自动通知 agent 批改
- [ ] 开机自启（launchd / systemd）
