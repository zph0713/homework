---
name: homework-lab
description: Use when 布置/批改/讲解作业或操作 homework-lab 系统.
version: 2.2.0
author: genos
license: MIT
metadata:
  hermes:
    tags: [education, ielts, sqlite, homework, grading]
    related_skills: []
---

# homework-lab 作业实验室 · 老师角色工作流

## When to Use

- 学生说「出题吧 / 来点练习 / 写好了 / 交了 / 交卷了」或提到作业、试卷、错题、知识点掌握度、单词本默写/抽查
- 需要布置新作业、批改提交、查看待批改队列、记录诊断、做每周回顾时
- 操作或维护 homework-lab 项目（服务启动、数据检查）时

本地试卷学习系统：AI 出卷 → 学生在网页答题交卷 → AI 批改并讲解 → 出变式卷验证 → 错题归档重练。
项目位于 `~/Documents/GitHub/homework-lab`（git 管理，papers/ 入库、data/ 不入库）。
**交互全部对话驱动，不使用定时任务**。讲解在对话框进行；网页只承载作业与成绩。

## 三大终极目标（一切出题决策的总纲）

1. **语法第一优先，按知识图谱顺序学**：图谱 6 阶段 30 知识点（curriculum/grammar_map.json）。每阶段全部「已掌握」才进入下一阶段，不跳级。**掌握标准：作答超过 5 次且正确率 ≥85%**（≤5 次不计分，图谱显示"计分中"）。出语法题前先 `kmap next` 看下一个未掌握点。
2. **错题揪着不放**：只要有错 → 讲解 → 立即出同知识点变式验证卷 → 全对才算过 → 关闭诊断。之后的周回顾抽查再发现错，重新揪。**不放过任何一个没掌握的知识点**。
3. **按学生画像定制**：出题前必读 `profile get`（学生在「我的」页用输入框自由填：目标/话题/题型/备注，逗号分隔）。雅思话题、翻译/阅读/写作需求直接决定题目方向；出题策略随错题与弱点动态调整。

## 前置检查

```bash
cd ~/Documents/GitHub/homework-lab
curl -s http://127.0.0.1:8877/api/state >/dev/null && echo 在线 || echo 离线
# 离线则启动（后台）：python3 server/app.py   # 默认 8877
```

出题前的四个必读（决定方向）：
```bash
python3 agent/cli.py profile get             # 学生画像：目标/话题/题型需求（输入框自由填写）
python3 agent/cli.py kmap next --limit 3     # 图谱顺序中下一个未掌握知识点
python3 agent/cli.py vocab list --await-detail   # 学生已确认、等 AI 补词典详细的词（AI 行动项）
python3 agent/cli.py vocab list --unfilled       # 缺中文/词性的词（提醒学生在网页补填，不是 AI 填）
```

## 交互模式（用户约定）

- **出题**：学生主动说「出题吧 / 来点默写 / 抽查下单词」才出题，不擅自布置。方向按「三大终极目标」。
- **交卷**：学生说「写好了 / 交了」→ 立即批改（下面循环第 1-3 步）。
- **讲解**：批改完在对话框逐题讲解；网页结果页同步显示。
- **周回顾**：每次批改完成后顺手 `weekly status` 检查——到期（≥7 天）就告诉学生并安排抽查卷。

## 标准循环（每次批改）

1. **收作业**：
   ```bash
   python3 agent/cli.py pending          # 待批改详情（学生答案+参考答案）
   python3 agent/cli.py autograde        # 自动批客观题
   ```
2. **批改**（未命中的 fill/cloze 复核 + 全部 writing/translate）：
   ```bash
   python3 agent/cli.py grade <sub_id> --json /tmp/grades.json
   # {"grades":[{"question_id":N,"correct":0.75,"feedback":"..."}],"note":"总评"}
   # correct 语义：0~1 比例！部分正确用 0.5/0.75，禁止写 1.5 这种分值（会被钳制，且会弄乱掌握度）
   ```
   批改原则：未命中填空/cloze 判断是否可接受替代答案（可接受则 correct=1 覆盖）；写作按 rubric 打分，feedback 具体到句子；翻译按忠实度/结构/搭配打分。
3. **讲解 + 记录**（批改后必做）：
   - `python3 agent/cli.py report <sub_id>` → 对话框逐题讲错题（规则 + 错因 + 避免方法）
   - **发现的每个问题写进诊断档案**（跨环境跟踪的关键）：
     ```bash
     python3 agent/cli.py diag add --kp "<知识点>" --finding "<问题描述>" \
       --severity high|mid|low --sub <sub_id> --evidence "<错题引用>"
     ```
   - 讲解事件记入学习路径：`python3 agent/cli.py log explain --summary "..." --kp ... --ref submission:<id>`
   - **单词本查漏**（批改后必做，两件事）：
     ① `vocab list --await-detail` 有词 → AI 写 /tmp/vocab.json，`detail` 字段填**词典词性 + 详细中文释义** → `vocab update /tmp/vocab.json`（中文/词性由学生自己填，AI 只补 detail）
     ② 若本次批改含「词汇-抽查」题目 → `vocab check-result --sub <sub_id>` 回写抽查池
   - 若本次有错 → 立刻出验证卷（第 4 步）
4. **出验证卷**（3~5 题，同知识点换主语/数字/语境，禁止原题照搬）：
   - 试卷 JSON 规范：`docs/AGENT_PROTOCOL.md`；题型指南：`docs/QUESTION_TYPES.md`；写作题参考 `docs/WRITING_CURRICULUM.md`
   - 写 `papers/verify_xxx.json` → `python3 agent/cli.py create papers/verify_xxx.json`
   - 验证卷全对 → `diag resolve <id> --note "验证卷满分"` 关闭诊断；仍有错 → 继续讲 + 再出变式卷，直到全对
5. **周回顾检查**（每次批改后顺手做）：
   ```bash
   python3 agent/cli.py weekly status
   ```
   到期（无记录或 ≥7 天）→ 从候选知识点随机抽 2-3 个 → 出 3-5 题抽查卷 → 批改后：
   ```bash
   python3 agent/cli.py weekly record --sampled "kp1,kp2" --wrong "kp1" --hw <id>
   # 出错的知识点 → diag add 记录 → 回到目标 2 的揪错循环
   ```

## 出题决策顺序（学生要题时按此顺序）

1. 学生口头指定方向（永远最高优先级，如「出默写」「练翻译」「抽查单词」）
2. **未解决诊断**（`diag list --open`）→ 出对应知识点的验证卷（目标 2）
3. **图谱顺序下一个未掌握点**（`kmap next`）→ 语法卷主攻它（目标 1）
4. 周回顾出错知识点（`weekly status` 里的 wrong）→ 重练
5. 掌握度 <50% 的薄弱点（`weakpoints`）→ 专项练习
6. 写作路线推进（`docs/WRITING_CURRICULUM.md`）或画像勾选的翻译/阅读训练（目标 3）
7. 学生要求默写 → `vocab dictation --limit 10` 生成默写卷（无需手写 JSON）

## 单词本 / 抽查池（学生参与的新流程）

**分工**：学生填中文意思 + 词性（网页多选下拉）→ 点「确认已填」→ AI 补 `detail`（词典词性+详细释义）→ 单词进入抽查池。

- 抽查卷生成（随机抽池中词，可整卷发布或把 questions 并入任何作业混考）：
  ```bash
  python3 agent/cli.py vocab check --limit 3 --out papers/vocab_check.json
  ```
- **批改全部完成后**回写池状态（必须做）：
  ```bash
  python3 agent/cli.py vocab check-result --sub <sub_id>
  # 对 → 出池（绿色标记）；拼错 → 留池，下次抽查再考，直到写对
  ```
- 全词本默写（区别于抽查）：`vocab dictation --limit 10`
- 常用查看：`vocab list`（全量）/ `--pool`（池中词）/ `--await-detail`（待 AI 补详细）/ `--unfilled`（待学生补填）

## 前端能力速查（出题时对齐前端，勿超纲）

- 题型：choice / fill / cloze / tfng / writing / translate；默写=fill+skill=vocabulary+知识点「词汇-默写」；抽查=fill+知识点「词汇-抽查」（用 CLI 生成，勿手写）。**listening/speaking 未实现，不要出**（预留见 docs/ROADMAP.md）
- 学生在网页可：划词加入单词本、单词本页填中文/词性（多选下拉）并确认、错题本申请重练、删除作业卡（有确认弹窗）、「我的」页用输入框改画像、设置页改库路径/端口
- 知识图谱：作答超过 5 次才按正确率计分，≥85% 且超过 5 次 = 已掌握
- 出题能力不匹配前端时先查 `docs/QUESTION_TYPES.md`，别让 AI 自定义新题型

## 跨环境跟踪（数据都在这）

- 学习路径：`timeline`（出卷/交卷/批改自动记；讲解/验证等 AI 主动事件用 `log` 记）
- 问题档案：`diag list [--open]`（发现的问题、证据、解决状态）
- 周回顾：`weekly status`（上次回顾、候选知识点）
- 掌握度：`weakpoints` / 图谱：`kmap list` / `kmap next`
- 学生画像：`profile get`；单词本：`vocab list [--pool|--await-detail|--unfilled|--confirmed]`
- 换机器/换 agent 只要 `HOMELAB_DB` 指向同一数据库文件，全部状态即可接管

## 关键约定

- **答案永不进学生接口**（服务器层保证）；**学习数据 data/ 永不入 git**
- 测试用 `HOMELAB_DB=/tmp/xxx.db` 隔离；改代码后必须重启服务
- `correct` 是 0~1 比例，不是分值；写作题 `score` 字段才是分值
- 知识点命名一致（如「写作短句-被动语态」）；`explanation`=通用解析/示范句（出卷时写），`feedback`=个性化点评（批改时写）
- 讲解用中文，一次聚焦 ≤3 个知识点；验证卷 3~5 题，诊断卷 ≤15 题
- 学生目标：彻底解决语法 + 雅思词汇短语；语境用雅思话题（教育/环保/科技/城市/健康/工作）
- 删除试卷前确认（`delete <id>` 级联删除全部提交记录，不可恢复）
