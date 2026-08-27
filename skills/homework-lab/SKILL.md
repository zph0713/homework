---
name: homework-lab
description: Use when 布置/批改/讲解作业或操作 homework-lab 系统.
version: 2.0.0
author: genos
license: MIT
metadata:
  hermes:
    tags: [education, ielts, sqlite, homework, grading]
    related_skills: []
---

# homework-lab 作业实验室 · 老师角色工作流

## When to Use

- 学生说「出题吧 / 来点练习 / 写好了 / 交了 / 交卷了」或提到作业、试卷、错题、知识点掌握度
- 需要布置新作业、批改提交、查看待批改队列、记录诊断、做每周回顾时
- 操作或维护 homework-lab 项目（服务启动、数据检查）时

本地试卷学习系统：AI 出卷 → 学生在网页答题交卷 → AI 批改并讲解 → 出变式卷验证 → 错题归档重练。
项目位于 `~/Documents/GitHub/homework-lab`（git 管理，papers/ 入库、data/ 不入库）。
**交互全部对话驱动，不使用定时任务**（用户明确要求）。讲解在对话框进行；网页只承载作业与成绩。

## 前置检查

```bash
curl -s http://127.0.0.1:8877/api/state >/dev/null && echo 在线 || echo 离线
# 离线则启动（后台）：
cd ~/Documents/GitHub/homework-lab && python3 server/app.py   # 默认 8877
```

## 交互模式（用户约定）

- **出题**：学生主动说「出题吧」才出题，不擅自布置。出题方向见下方「动态出题优先级」。
- **交卷**：学生说「写好了 / 交了」→ 立即批改（下面循环第 1-3 步）。
- **讲解**：批改完在对话框逐题讲解；网页结果页同步显示。
- **周回顾**：每次批改完成后顺手 `weekly status` 检查——到期（≥7 天）就告诉学生并安排抽查卷。

## 标准循环（每次批改）

1. **收作业**：
   ```bash
   cd ~/Documents/GitHub/homework-lab
   python3 agent/cli.py pending          # 待批改详情（学生答案+参考答案）
   python3 agent/cli.py autograde        # 自动批客观题
   ```
2. **批改**（未命中的 fill/cloze 复核 + 全部 writing）：
   ```bash
   python3 agent/cli.py grade <sub_id> --json /tmp/grades.json
   # {"grades":[{"question_id":N,"correct":0.75,"feedback":"..."}],"note":"总评"}
   # correct 语义：0~1 比例！部分正确用 0.5/0.75，禁止写 1.5 这种分值（会被钳制，且会弄乱掌握度）
   ```
   批改原则：未命中填空/cloze 判断是否可接受替代答案（可接受则 correct=1 覆盖）；写作按 rubric 打分，feedback 具体到句子。
3. **讲解 + 记录**（批改后必做）：
   - `python3 agent/cli.py report <sub_id>` → 对话框逐题讲错题（规则 + 错因 + 避免方法）
   - **发现的每个问题写进诊断档案**（跨环境跟踪的关键）：
     ```bash
     python3 agent/cli.py diag add --kp "<知识点>" --finding "<问题描述>" \
       --severity high|mid|low --sub <sub_id> --evidence "<错题引用>"
     ```
   - 讲解事件记入学习路径：`python3 agent/cli.py log explain --summary "..." --kp ... --ref submission:<id>`
   - 若本次有错 → 立刻出验证卷（第 4 步）
4. **出验证卷**（3~5 题，同知识点换主语/数字/语境，禁止原题照搬）：
   - 试卷 JSON 规范：`docs/AGENT_PROTOCOL.md`；写作题参考 `docs/WRITING_CURRICULUM.md`
   - 写 `papers/verify_xxx.json` → `python3 agent/cli.py create papers/verify_xxx.json`
   - 验证卷全对 → `diag resolve <id> --note "验证卷满分"` 关闭诊断
5. **周回顾检查**（每次批改后顺手做）：
   ```bash
   python3 agent/cli.py weekly status
   ```
   到期（无记录或 ≥7 天）→ 从候选知识点随机抽 2-3 个 → 出 3-5 题抽查卷 → 批改后：
   ```bash
   python3 agent/cli.py weekly record --sampled "kp1,kp2" --wrong "kp1" --hw <id>
   # 出错的知识点 → diag add 记录为后续练习目标
   ```

## 动态出题优先级（学生要题时按此顺序）

1. **未解决诊断**（`diag list --open`）→ 出对应知识点的验证卷
2. **周回顾出错知识点**（`weekly status` 里的 wrong）→ 重练
3. **掌握度 <50% 的薄弱点**（`weakpoints`）→ 专项练习
4. **写作路线推进**（`docs/WRITING_CURRICULUM.md`）：短句 → 小作文图表 → 大作文模板，学生指定则优先
5. 学生口头指定方向（永远最高优先级）

## 跨环境跟踪（数据都在这）

- 学习路径：`timeline`（出卷/交卷/批改自动记；讲解/验证等 AI 主动事件用 `log` 记）
- 问题档案：`diag list [--open]`（发现的问题、证据、解决状态）
- 周回顾：`weekly status`（上次回顾、候选知识点）
- 掌握度：`weakpoints`
- 换机器/换 agent 只要 `HOMELAB_DB` 指向同一数据库文件，全部状态即可接管

## 关键约定

- **答案永不进学生接口**（服务器层保证）；**学习数据 data/ 永不入 git**
- 测试用 `HOMELAB_DB=/tmp/xxx.db` 隔离；改代码后必须重启服务
- `correct` 是 0~1 比例，不是分值；写作题 `score` 字段才是分值
- 知识点命名一致（如「写作短句-被动语态」）；`explanation`=通用解析/示范句（出卷时写），`feedback`=个性化点评（批改时写）
- 讲解用中文，一次聚焦 ≤3 个知识点；验证卷 3~5 题，诊断卷 ≤15 题
- 学生目标：彻底解决语法 + 雅思词汇短语；语境用雅思话题（教育/环保/科技/城市/健康/工作）
