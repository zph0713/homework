# 📝 Homework Lab · 作业实验室

**本地试卷系统 + 轻量数据库 + AI 批改循环**——AI 布置作业 → 你在网页上答卷 → AI 从数据库读取批改 → 错题讲解 + 针对性再出题 → 直到彻底掌握。

- **零依赖**：Python 标准库（sqlite3 + http.server）+ 原生 JS，任何机器开箱即用，不用装任何包
- **只在本机**：服务器只绑定 `127.0.0.1`，学习数据（`data/`）不入 git
- **模型无关**：任何 AI / agent（换模型、换工具都行）通过一套 JSON 协议 + CLI 接入，见 [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md) 与仓库根目录的 [AGENTS.md](AGENTS.md)
- **当前学科**：英语（语法 + 雅思词汇短语），学科可扩展

---

## 使用说明

### 一键启动（推荐）

```bash
./start.command        # macOS：双击或在终端运行，自动起服务 + 打开浏览器
./start.sh             # Linux / macOS 终端
```

**首次使用**：打开网页后自动进入「本地初始化」向导，只需三步（都有默认值，可后期修改）：

1. **数据库文件位置** —— 学习数据（提交/错题/单词本）存在这一个 SQLite 文件里；输入相对路径会自动转成绝对路径，**网页、AI 老师、命令行读的是同一份 config.json，访问位置天然一致**
2. **端口** —— 默认 8877，改后服务自动重启到新端口
3. **题目目标** —— 教学规则（掌握标准 ≥85%、计分最少作答 5 次、验证卷 3~5 题、周回顾 7 天、诊断卷 ≤15 题、出题优先级）+ 学生画像（目标/话题/题型）

之后随时可在「设置」页修改教学规则与服务配置、「我的」页修改画像。

### 学生端（网页）

```
http://127.0.0.1:8877
```

页面三个入口：

| 页面 | 作用 |
|---|---|
| **作业** | 待做/已做试卷列表，点「开始答题」进入试卷页；批改完成后点「查看结果」看每道题的得分、老师点评和解析 |
| **错题本** | 所有批改过的错题按知识点归档，可一键「申请重练」某个知识点 |
| **知识点** | 每个知识点的掌握度进度条（薄弱⚠ / 学习中 / 已掌握✓），附该知识点错题记录 |

答题 → 交卷（未答题目会弹窗确认）→ 等老师批改 → 结果页看讲解。交卷后在聊天里说一声「交了」，AI 老师开始批改。

### 老师端（AI / Agent 的日常循环）

```bash
cd homework-lab

# 1. 发布新试卷
python3 agent/cli.py create papers/xxx.json

# 2. 学生交卷后：查待批改 → 自动批改
python3 agent/cli.py pending
python3 agent/cli.py autograde

# 3. AI 批改（写作 + 复核填空）后入库
python3 agent/cli.py grade <sub_id> --json /tmp/grades.json

# 4. 读完整结果，在聊天里讲解错题
python3 agent/cli.py report <sub_id>

# 5. 看知识点掌握度，决定下一份卷方向
python3 agent/cli.py weakpoints

# 6. 周期性：导出错题 → 生成变式重练卷
python3 agent/cli.py wronglist --json /tmp/wrong.json

# 7. 处理学生的重练申请
python3 agent/cli.py requests
```

完整命令参考与试卷/批改 JSON 规范见 [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md)。

### 学习循环（核心理念）

```
出题(考察知识点) → 答题 → 批改 → 讲解错题 → 出变式题验证 → 全对为止 → 定期错题重练
                                                              ↓
                                          每周随机知识点抽查（回顾上周所学）→ 出错转入练习目标
```

- **题目不在多，在于多轮考察**：每个知识点至少答对 3 次且掌握度 ≥85% 才算「已掌握」
- **错题全部归档**：错题本随时回顾，可一键申请重练
- **知识点追踪**：每道题标注知识点，系统自动统计掌握度，老师据此调整出题方向
- **对话驱动**：出题、交卷、批改、讲解全部由对话触发，不用定时任务

### 学习路径 / 问题诊断 / 周回顾（跨环境跟踪）

除试卷、提交、错题外，系统还维护三份学习档案，全部在数据库里，换机器、换 AI agent 都能无缝接管：

| 档案 | 内容 | CLI |
|---|---|---|
| **学习路径** learning_log | 时间线：出卷/交卷/批改自动记录，讲解/验证等由老师记录 | `cli.py timeline` / `cli.py log` |
| **问题诊断** diagnoses | 每次批改发现的学生问题：知识点、问题描述、证据、严重度、解决状态 | `cli.py diag add/list/resolve` |
| **周回顾** weekly_reviews | 每周随机抽查记录：抽查了哪些知识点、哪些出错、后续安排 | `cli.py weekly status/record` |

每周回顾机制：距上次回顾 ≥7 天时，从上周学过的知识点中**随机抽 2-3 个**出抽查卷；抽查出错的知识点记入诊断档案，成为后续练习目标——动态跟随学生情况。

### 写作课程路线（雅思）

写作按 [docs/WRITING_CURRICULUM.md](docs/WRITING_CURRICULUM.md) 三阶段推进，从简单开始：

1. **话题短句**：高频语法结构 × 雅思话题，每题写 1-2 句
2. **小作文 Task 1**：line / bar / pie / table / process / map 六类图表模板
3. **大作文 Task 2**：opinion / discussion / advantages-disadvantages / problem-solution / double question 五类题型模板

### 批改分层

| 题型 | 自动批改 | AI 批改 | 说明 |
|---|---|---|---|
| 单选 choice | ✅ | — | 对错明确 |
| 判断 TFNG | ✅ | — | 对错明确 |
| 填空 fill | 命中参考答案时 ✅ | 未命中时复核 | AI 判断是否为可接受的替代答案 |
| 语法填空 cloze | 按空格比例给分 ✅ | 未命中空格复核 | 同上 |
| 写作 writing | — | ✅ 必批 | AI 按 rubric 打分 + 写点评 |

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOMELAB_DB` | config.json 的 db_path | 数据库路径（测试时指向临时文件；优先级最高） |
| `HOMELAB_PORT` | config.json 的 port | 网页端口 |
| `HOMELAB_CONFIG` | `<项目>/config.json` | 配置文件路径（测试隔离用） |

### 数据与备份

- 所有学习数据在 `data/homework.db`（单文件 SQLite），备份只需复制这一个文件
- 试卷内容在 `papers/*.json`，随 git 版本管理
- 迁移到新机器：复制整个目录 → `./start.command` → 网页上把数据库路径指到旧库即可接管全部历史数据（或直接复制 config.json + data/）

---

## 与不同 AI Agent 的配合

### 接入原理

老师角色需要的能力：**执行 shell 命令 / 读写 JSON**（本地 agent）或 **发 HTTP 请求**（在线 AI 服务）。系统对 agent 的接口有两条：

1. `agent/cli.py` —— 所有操作走这一个命令行工具（本地 agent 用）
2. `docs/HTTP_API.md` 的 `/api/agent/*` —— 同一能力的 JSON HTTP 接口（在线 AI 服务用；**出题/批改/单词本/题目目标检查全覆盖**）
3. `docs/AGENT_PROTOCOL.md` —— 试卷与批改的 JSON 规范（唯一契约，两条接口共用）

任何模型、任何 agent 框架都能无缝接入，换模型时**学生端、数据库、历史数据全部不变**。

### AGENTS.md —— 仓库自带的教师角色指令

仓库根目录的 [AGENTS.md](AGENTS.md) 写了完整的教师角色设定：职责、批改循环、纪律约定。支持该标准的 agent 工具在**项目目录下启动时会自动加载**它，无需任何手工配置：

| Agent 工具 | 接入方式 |
|---|---|
| **Claude Code** | 在项目目录运行 `claude`，AGENTS.md 自动加载；或一次性任务 `claude -p "按 AGENTS.md 检查待批改作业"` |
| **OpenAI Codex** | 在项目目录运行 `codex`，AGENTS.md 自动加载 |
| **OpenCode** | 在项目目录运行 `opencode`，AGENTS.md 自动加载 |
| **Cursor / Windsurf** | 打开项目目录即可，AGENTS.md 会被读取 |
| **Hermes Agent** | 用下方「Hermes Skill 配置」的 skill（本仓库自带） |
| **在线 AI 服务（ChatGPT 自定义 GPT / 豆包 / Kimi / Dify / n8n）** | 把 `skills/homework-lab/SKILL.md` 导入该服务（自定义指令/知识库），它通过 `http://127.0.0.1:<端口>/api/agent/*` 调用本服务，协议见 `docs/HTTP_API.md`；AI 服务不在本机时：监听地址改 0.0.0.0 + 设置访问令牌，或 SSH 隧道 |
| **任意 API / 自研 agent** | 把 `AGENTS.md` + `docs/AGENT_PROTOCOL.md`（+ `docs/HTTP_API.md`）全文塞进 system prompt，赋予 shell 或 HTTP 能力即可 |

### 各 agent 的角色分工（以多 agent 协作为例）

```
学生交卷 ──▶ 任意一个「值班」agent 执行：pending → autograde → grade
                │
                ▼
         另一个 agent 读 report → 在聊天里讲解错题
                │
                ▼
         任意 agent 按 weakpoints 出变式卷 → create 发布
```

因为状态全部落在数据库和 git 里，agent 之间不需要直接通信，谁接手都能从 `pending` / `weakpoints` 拿到全部上下文。

### 触发方式

- **对话触发（默认）**：学生在聊天里说「出题吧」→ 老师出题；说「写好了 / 交了」→ 老师批改讲解。**交互全部对话驱动，不使用定时任务**（本用户明确偏好）
- 仓库自带 `scripts/check_pending.py`（有待批改提交时输出提醒，否则静默），供**其他部署场景**选择使用；本用户不用

---

## Hermes Skill 配置

本仓库自带 Hermes 技能文件：[skills/homework-lab/SKILL.md](skills/homework-lab/SKILL.md)。它把「布置 → 批改 → 讲解 → 验证 → 重练」的完整循环写成可直接加载的技能。

### 安装

Hermes 技能目录有两种布局，二选一：

```bash
# A. 单 profile 布局（默认）
mkdir -p ~/.hermes/skills/education/homework-lab
cp skills/homework-lab/SKILL.md ~/.hermes/skills/education/homework-lab/SKILL.md

# B. 多 profile 布局（如 profile 名为 genos）
mkdir -p ~/.hermes/profiles/genos/skills/education/homework-lab
cp skills/homework-lab/SKILL.md ~/.hermes/profiles/genos/skills/education/homework-lab/SKILL.md

# 想随时同步仓库更新，用软链更省事：
ln -s "$(pwd)/skills/homework-lab" ~/.hermes/skills/education/homework-lab
```

重启 Hermes 会话后生效。

### 技能触发条件

- 学生说「交了」「交卷了」，或提到作业、试卷、错题、知识点掌握度
- 需要布置新作业、批改提交、查看待批改队列、生成重练卷
- 操作或维护本系统（启动服务、检查数据）

### 技能内容概要

| 环节 | 技能里的动作 |
|---|---|
| 出题 | 学生要求才出，方向按「动态出题优先级」（未解决诊断 → 周回顾错题 → 薄弱点 → 写作路线） |
| 收作业 | `pending` → `autograde` |
| 批改 | 写批改 JSON → `grade <sub_id> --json ...` |
| 讲解 | `report <sub_id>` → 对话框逐题讲解 |
| 记录 | 问题写入 `diag add`；讲解/验证事件写入 `log` |
| 验证 | 按薄弱点出 3~5 题变式卷 → `create`；全对后 `diag resolve` |
| 周回顾 | 每次批改后顺手 `weekly status`，到期随机抽查 + `weekly record` |

### 定时任务说明（本用户不使用）

本用户偏好**纯对话驱动**，不配置定时任务。`scripts/check_pending.py` 保留供其他部署场景（如家长盯作业、批量学生场景）参考。

---

## 项目结构

```
homework-lab/
├── AGENTS.md              # ★ 教师角色指令（Claude Code / Codex / OpenCode 等自动加载）
├── start.command / start.sh   # 一键启动：起服务 + 打开浏览器
├── config.json            # 本地配置（初始化页/设置页写入，不入 git）：数据库路径/端口/题目目标
├── agent/
│   ├── db.py              # 数据层：表结构、试卷校验、自动批改、知识点统计、初始化部署
│   ├── cli.py             # Agent CLI：发布/批改/错题/知识点管理（模型无关接口）
│   └── settings.py        # 配置模块：默认值 + config.json 读写（网页/CLI/API 共用）
├── server/
│   ├── app.py             # 本地 HTTP 服务器（标准库，默认只绑 127.0.0.1）
│   ├── agent_api.py       # AI 服务接入 API（/api/agent/*，协议见 docs/HTTP_API.md）
│   └── static/            # 学生端网页（无框架 SPA，含首次初始化向导）
├── papers/                # 试卷库（JSON，随 git 版本管理）
├── scripts/
│   └── check_pending.py   # 定时巡检脚本（待批改提醒，供 cron 使用）
├── skills/
│   └── homework-lab/
│       └── SKILL.md       # ★ AI 老师技能（本地 agent 用 CLI，在线服务用 HTTP API）
├── data/                  # SQLite 学习数据（本地，不入 git）
└── docs/
    ├── AGENT_PROTOCOL.md  # ★ 任何 AI/agent 的接入协议（试卷 JSON 规范 + CLI 参考）
    ├── HTTP_API.md        # ★ 在线 AI 服务的 HTTP 接入协议（/api/agent/*）
    ├── QUESTION_TYPES.md  # 题型规范与出题指南
    └── WRITING_CURRICULUM.md  # 雅思写作课程路线（短句 → 图表 → 大作文）
```

## 快速开始

```bash
git clone git@github.com:zph0713/homework.git
cd homework

# 1. 一键启动（自动起服务 + 打开浏览器）→ 网页上完成首次初始化（数据库路径/端口/题目目标）
./start.command        # macOS；Linux 用 ./start.sh

# 或者手动：
python3 server/app.py  # → 打开 http://127.0.0.1:8877 完成初始化

# 2. 发布第一份试卷（AI 老师）
python3 agent/cli.py create papers/diagnostic_001.json

# 3. （可选）接入你的 AI 老师：本地 agent 装 skill / 在线 AI 服务导入 skill + HTTP API
```

## 常见问题

**重启电脑后网页打不开？** 服务器是手动启动的，重新运行：
```bash
cd ~/Documents/GitHub/homework-lab && python3 server/app.py
```

**想换端口？** `HOMELAB_PORT=8899 python3 server/app.py`

**换 agent / 换模型会丢数据吗？** 不会。数据在 `data/homework.db`，接口只有 CLI + JSON，agent 之间互不依赖。

**学生能看到答案吗？** 不能。发给网页的试卷数据在服务器层强制剥离答案与解析，批改后答案才出现在结果页。

## Roadmap

- [ ] 题型扩展：词汇搭配选择、段落匹配、雅思图表题
- [ ] 错题重练支持「同类变式」自动重排
- [ ] 其他学科接入（题目类型与知识点标签体系已是通用的）
- [ ] 定时任务：检测到新交卷自动通知 agent 批改
- [ ] 开机自启（launchd / systemd）
