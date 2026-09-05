# Agent 接入协议（AGENT_PROTOCOL）

本文档是 **AI / Agent 与 Homework Lab 交互的唯一契约**。任何模型、任何 agent（Claude、GPT、DeepSeek、本地模型、cron 任务……）只要会「写 JSON 文件 + 执行 CLI 命令」，就能完整扮演老师角色，无需理解网页或数据库细节。

## 1. 系统构成

```
┌──────────┐   浏览器答题    ┌──────────────┐   读写   ┌───────────────┐
│  学生端   │ ──────────────▶ │ 本地服务器     │ ◀──────▶ │ SQLite 数据库   │
│ (网页)    │ ◀────────────── │ server/app.py │          │ data/homework.db│
└──────────┘   成绩/讲解      └──────────────┘          └───────────────┘
                                      ▲
                                      │ JSON 文件 + CLI（本协议）
                              ┌───────┴───────┐
                              │  AI / Agent    │
                              │ agent/cli.py   │
                              └───────────────┘
```

- 学生只接触网页；学生视角的接口**永远不返回答案**（`answer` / `explanation` 字段被剥离）
- Agent 只接触 CLI + JSON 文件；批改结果写回数据库，网页自动呈现

## 2. 环境

```bash
cd homework-lab                      # 项目根目录（所有命令在此执行）
export HOMELAB_DB=data/homework.db   # 可选；测试时指向 /tmp/xxx.db
python3 agent/cli.py <子命令> ...
```

CLI 会自动建库，无需手工初始化。

## 3. 老师角色的标准循环

```
第 1 步  cli.py create papers/xxx.json   发布试卷（见 §4 JSON 规范）
第 2 步  （学生在网页答题并交卷）
第 3 步  cli.py pending                   查看待批改提交 → 输出需要 AI 处理的题目
第 4 步  cli.py autograde                 自动批改客观题（可选，建议先跑）
第 5 步  AI 阅读 pending/report 输出 → 写批改 JSON → cli.py grade <sid> --json grades.json
第 6 步  cli.py report <sid>              读取完整结果，在聊天里讲解错题
第 7 步  cli.py weakpoints                看知识点掌握度 → 决定下一份卷的方向
第 8 步  针对薄弱点写新试卷 JSON → create → 回到第 1 步
周期性   cli.py wronglist --json /tmp/wrong.json   导出错题 → 生成变式重练卷
```

## 4. 试卷 JSON 规范

文件放在 `papers/` 下（随 git 版本管理），通过 `cli.py create <文件>` 发布。

```jsonc
{
  "title": "诊断卷 #1 · 时态 / 语态 / 主谓一致",   // 必填
  "skill": "grammar",        // 作业栏目（决定前端归属与统计口径）：
                             //   grammar = 语法作业（老师批改+讲解，计入掌握度/错题本/近期成绩）
                             //   vocabulary = 词汇短语作业（交卷自批改，学生自验证，老师不批改）
                             //   ielts_reading / ielts_listening / ielts_essay / ielts_speaking = 雅思专项训练四栏目
                             //   （ielts_listening=听力精听：精听文稿+真题格式题目，见 docs/QUESTION_TYPES.md；旧 ielts_stem「题干英译汉」已废弃）
                             //   （reading/writing/listening/mixed 为旧值，新卷不要用）
  "topic": "IELTS 写作 Task 1 语境",               // 可选
  "goal": "本次考察目标（显示给学生看）",            // 可选
  "passages": [               // 可选：阅读材料，题里用 passage_ref 引用
    { "ref": "p1", "title": "Bike-sharing", "body": "Many cities ..." }
  ],
  "questions": [ /* 见下 */ ]
}
```

### 题型字段

公共字段：`type`、`prompt`、`explanation`（解析，批改后显示）、`knowledge_point`（知识点标签，**必填**，掌握度统计依赖它）、`score`（默认 1 分）、`extra`（可选，JSON 扩展字段——speaking 存 `{"part": 1|2|3}`，phrase 存 `{"meaning_cn","example","example_cn"}`）。

**① choice 单选（雅思选择题）**

```jsonc
{
  "type": "choice",
  "prompt": "Air pollution in major cities ___ a serious concern ___ the 1990s.",
  "options": ["A. became / since", "B. has become / since", "C. has become / for", "D. became / for"],
  "answer": "B",
  "explanation": "since + 时间点是现在完成时标志……",
  "knowledge_point": "现在完成时"
}
```

- `answer` 是单个大写字母 `A`-`D`；`options` 以「字母 + .」开头

**② fill 填空（单空，prompt 中用 `____` 表示空格）**

```jsonc
{
  "type": "fill",
  "prompt": "By 2050, global sea levels ____ (rise) by more than 30 centimetres.",
  "answer": ["will have risen"],           // 数组 = 多个可接受答案；单答案也可以是字符串
  "explanation": "by + 将来时间点 → 将来完成时……",
  "knowledge_point": "将来完成时"
}
```

- 自动批改时做宽松比较（小写、去标点）；未命中参考答案 → 标记 `needs_review`，由 AI 决定是否为可接受的替代答案

**③ cloze 语法填空（短文多空，`__1__` `__2__` 标记空格）**

```jsonc
{
  "type": "cloze",
  "passage": "Over the past decade, the way people work __1__ (change) dramatically.",
  "answer": {
    "1": ["has changed"],                  // 每空一个答案或答案数组
    "2": ["working", "to work"]
  },
  "explanation": "①…… ②……（按空编号写全）",
  "knowledge_point": "综合语法"
}
```

- 空格编号必须与 `answer` 的键一一对应（校验器会检查）
- 自动批改按空格比例给分（如 5 空对 3 → 0.6），有未命中空格的题目整体标记 `needs_review`

**④ tfng 判断（雅思 TRUE / FALSE / NOT GIVEN）**

```jsonc
{
  "type": "tfng",
  "passage_ref": "p1",                     // 引用 passages 里的阅读材料
  "prompt": "Vélib' was the first bike-sharing scheme in the world.",
  "answer": "NOT GIVEN",
  "explanation": "原文没有说\"世界上第一个\"……",
  "knowledge_point": "TFNG 判断"
}
```

- `answer` 只允许 `TRUE` / `FALSE` / `NOT GIVEN`

**⑤ writing 写作（必须 AI 批改）**

```jsonc
{
  "type": "writing",
  "prompt": "用不超过 3 句话描述以下趋势……\n要求：①时态 ②趋势词汇 ③while 对比",
  "answer": { "rubric": "评分要点：①…… ②…… ③……" },   // rubric 只给 AI 看
  "knowledge_point": "写作 Task 1 趋势描述",
  "score": 3
}
```

- 不会自动批改；AI 给 `correct`（1 / 0 / 0.5 等小数）和详细 `feedback`

**⑥ speaking 口语话题（只出题不批改 · 试卷 skill=ielts_speaking）**

```jsonc
{
  "type": "speaking",
  "prompt": "Describe a memorable trip you have taken.\n\nYou should say:\n- where you went\n- who you went with\n- what you did there\n\nand explain why this trip was memorable for you.",
  "answer": "",
  "extra": {
    "part": 2,
    "suggestions": [
      { "en": "It was a real eye-opener for me.", "zh": "那次旅行真让我大开眼界" },
      { "en": "It left a lasting impression on me.", "zh": "它给我留下了深刻的印象" }
    ]
  },
  "knowledge_point": "口语Part2",
  "score": 0
}
```

- `answer` 留空；`extra.part` 为 1/2/3；Part 2 的 prompt 用多行写「Describe ... / You should say: ... and explain ...」，前端渲染成真题风格题目卡
- **`extra.suggestions`（推荐每题配 6~10 条）**：该话题的地道词汇/短语/短句 + 中文，练完点「完成练习」后前端按话题展示，供学生对照优化后续回答；可直接收藏进短语本
- 口语卷的提交仅作「完成记录」（status=done），没有批改、不计入任何统计；话题优先取学生「我的」页的当季话题（`profile get`）

**⑦ phrase 短语讲解卡（AI 老师教 · 学生收藏）**

```jsonc
{
  "type": "phrase",
  "prompt": "take ... into account",
  "answer": "",
  "extra": { "meaning_cn": "把…考虑在内", "example": "We must take safety into account.", "example_cn": "我们必须把安全考虑在内。" },
  "knowledge_point": "",
  "score": 0
}
```

- 只展示不答题；学生点「加入短语本」收藏（`phrases` 表）；词汇短语作业生成器会自动从 `curriculum/phrase_bank.json` 抽 5 条

### 校验

`create` 时自动校验全部字段，错误以中文列出（题号 + 原因）。校验不过不会入库。

## 5. 批改 JSON 规范（`cli.py grade` 的输入）

```jsonc
{
  "grades": [
    {
      "question_id": 5,
      "correct": 0,                        // ★ 0~1 比例！1 对 | 0 错 | 0.5/0.75 部分正确
      "feedback": "by + 将来时间点必须用 will have done，不是 will do。回顾：将来完成时 = will have + 过去分词。"
    },
    {
      "question_id": 12,
      "correct": 0.75,
      "feedback": "趋势词汇用对了，但第二句串用了现在时……"
    }
  ],
  "note": "总体点评：时态基础不错，主谓一致要重点练。"   // 可选，显示在成绩页顶部
}
```

- `question_id` 从 `pending` / `report` 输出中读取，**不要自己编**
- **`correct` 是 0~1 的比例，不是分值**：一道 3 分的写作题得 2.25 分要写 `0.75` 而不是 `2.25`（写分值会被钳制为 1，并弄乱掌握度统计）。分值在 `score` 字段，默认 = correct × 题目分值
- 覆盖已有自动批改是允许的（AI 判断替代答案可接受时）
- 写完后提交自动置为 `graded`（前提：所有题都有 grade 且无 needs_review），并自动重算知识点统计；对已 graded 提交的修正批改会自动重算总分与掌握度

## 6. CLI 参考

| 命令 | 用途 |
|---|---|
| `init` | 初始化数据库 |
| `create <paper.json> [--status draft]` | 发布试卷（默认 published，学生立即可见） |
| `list` | 试卷列表 + 最新提交状态 |
| `paper <hw_id>` | 查看试卷（含答案，agent 专用） |
| `pending` | 待批改提交 + 需要 AI 处理的题目详情 |
| `autograde [<sub_id>]` | 自动批改（默认处理全部待批改提交） |
| `grade <sub_id> --json grades.json [--note ...]` | 写入 AI 批改 |
| `report <sub_id>` | 某次提交完整结果（讲解用） |
| `wronglist [--kp X] [--limit N] [--json out.json]` | 导出错题（出变式题用） |
| `weakpoints` | 知识点掌握度表 |
| `requests` | 学员的重练申请（`request done <id>` 关闭） |
| `archive <hw_id> [--unarchive]` | 归档/恢复试卷（归档后首页仍可见但标注） |
| `state` | 总览 JSON（首页数据 / 供定时任务轮询） |
| `log <type> --summary ... [--kp X] [--ref homework:N]` | 记录学习路径事件（讲解 explain / 验证卷 verify 等） |
| `timeline [--limit N]` | 学习路径时间线（出卷/交卷/批改自动记录） |
| `diag add --kp X --finding ... [--severity h\|m\|l] [--sub N]` | 记录学生问题诊断（批改发现的问题必须记录） |
| `diag list [--open]` / `diag resolve <id>` | 诊断档案查询 / 验证卷全对后标记解决 |
| `weekly status` | 周回顾状态：距上次回顾天数 + 候选知识点 |
| `weekly record --sampled a,b --wrong b [--hw N]` | 记录一次周回顾（出错知识点转入诊断） |
| `vocab list [--unfilled\|--confirmed\|--await-detail\|--pool] [--json out.json]` | 单词本查询（学生填中文/词性，AI 补 detail） |
| `vocab add --word X [--source S]` / `vocab delete <vid>` | 加入 / 删除单词 |
| `vocab update updates.json` | 批量更新：学生 `meaning_cn`/`pos`（数组）；AI `detail`（词典词性+详细释义） |
| `vocab dictation --limit N [--random] [--out F]` | 全词本默写卷生成（fill + 知识点「词汇-默写」） |
| `vocab check --limit N [--out F]` | 抽查池随机抽词生成抽查卷（知识点「词汇-抽查」，可并入其它卷混考） |
| `vocab check-result --sub <id>` | 抽查卷批改完成后回写池：对→出池（绿），错→留池重抽（幂等） |
| `vocab homework [--ielts 20 --wordbook 5 --phrases 5] [--out F]` | 生成「词汇短语作业」卷：雅思答案词+单词本词（随机拼写/汉英互译/词性）+短语讲解卡（skill=vocabulary，交卷自批改） |
| `phrase list` / `phrase add --phrase X [--meaning M --example E]` / `phrase delete <id>` | 短语本管理（AI 老师教的短语，学生从作业卡收藏） |
| `kmap import <json>` / `kmap list` / `kmap next [--limit N]` | 知识图谱导入 / 打分总览 / 下一个未掌握点 |

## 7. 纪律与约定

1. **试卷必填 `knowledge_point`**，否则知识点统计会漏题；同一个知识点名称要前后一致（如统一写「现在完成时」而不是一会儿「完成时」一会儿「present perfect」）。
2. **答案绝不进学生接口**：这是服务器层的硬约定，agent 无需处理。
3. **题量克制**：验证卷 3~5 题为宜；诊断卷不超过 15 题。题目贵在多轮，不贵在多。
4. **解析与点评分离**：`explanation` 是题目自带的通用解析（写卷时定稿）；`feedback` 是 AI 针对**这个学生这一次的错答**的个性化点评（批改时写）。两者都会显示给学生。
5. **出变式题**：错题重练不要原题照搬（学生会背答案），要换数字/换主语/换语境，考同一个知识点。
6. **掌握标准**：作答超过 5 次且 mastery ≥ 85% → `mastered`，之后降低该知识点的出题频率；≤5 次不计分（图谱显示"计分中"）。
7. **统计口径（三栏目重构后）**：语法知识图谱 / 掌握度概览 / 近期正确率 / 错题本**只统计 skill=grammar 的作业**。词汇短语作业交卷即自动批改、学生自验证，老师不批改；雅思阅读节选小题批改要附答案讲解，作文长句中译英批改要纠正语法；口语卷只出题不批改。
8. **试卷 JSON 进 git（papers/），学习数据（data/）永远不进 git**。

## 8. 接入新模型的检查清单

- [ ] 能执行 `python3 agent/cli.py`（任何能跑 shell 的环境）
- [ ] 能读 `pending` 输出 → 产出 §5 的批改 JSON
- [ ] 能读 `weakpoints` → 决定出题方向 → 按 §4 写试卷 JSON
- [ ] 讲解在聊天里进行，不依赖本系统（本系统只承载作业与数据）
