---
name: homework-lab
description: Use when 布置/批改/讲解作业或操作 homework-lab 系统.
version: 1.0.0
author: genos
license: MIT
metadata:
  hermes:
    tags: [education, ielts, sqlite, homework, grading]
    related_skills: []
---

# homework-lab 作业实验室 · 老师角色工作流

## When to Use

- 用户说「交了」/「交卷了」或提到作业、试卷、错题、知识点掌握度时
- 需要布置新作业、批改提交、查看 pending 队列、生成重练卷时
- 操作或维护 homework-lab 项目（服务启动、数据检查）时

本地试卷学习系统：AI 出卷 → 学生在网页答题交卷 → AI 批改并讲解 → 出变式卷验证 → 错题归档重练。
项目位于 `~/Documents/GitHub/homework-lab`（git 管理，papers/ 入库、data/ 不入库）。
**讲解在对话框进行**（本技能承载流程；网页只承载作业与成绩）。

## 前置检查

```bash
# 服务是否在跑
curl -s http://127.0.0.1:8877/api/state >/dev/null && echo 在线 || echo 离线
# 离线则启动（后台）：
cd ~/Documents/GitHub/homework-lab && python3 server/app.py   # 默认 8877
```

## 标准循环（每次执行）

1. **收作业**：学生交卷后在聊天说「交了」→ 查待批改：
   ```bash
   cd ~/Documents/GitHub/homework-lab
   python3 agent/cli.py pending          # 输出需要 AI 处理的题目详情（含学生答案+参考答案）
   python3 agent/cli.py autograde        # 先自动批客观题（choice/tfng + 命中的 fill/cloze）
   ```
2. **批改**：pending 里剩下的（未命中的 fill/cloze + 全部 writing）写批改 JSON → 入库：
   ```bash
   python3 agent/cli.py grade <sub_id> --json /tmp/grades.json
   # grades.json: {"grades":[{"question_id":5,"correct":0,"feedback":"..."}],"note":"总体点评"}
   # correct: 1 对 | 0 错 | 0..1 部分正确；question_id 从 pending/report 输出读取，勿自编
   ```
   批改原则：未命中的填空/cloze 判断是否为可接受替代答案（是则 correct=1 覆盖自动判错）；写作按 rubric 打分并写具体改进建议。
3. **对话框讲解**：`python3 agent/cli.py report <sub_id>` 读完整结果 → 在聊天里逐题讲解错题：规则 + 本题错因 + 怎么避免。讲完立刻进入第 4 步。
4. **出验证卷**（3~5 题，考同知识点，换主语/数字/语境，禁止原题照搬）：
   - 试卷 JSON 规范：`docs/AGENT_PROTOCOL.md`（题型：choice/fill/cloze/tfng/writing）
   - 写到 `papers/` 下（如 `verify_xxx.json`）→ `python3 agent/cli.py create papers/verify_xxx.json`
   - 试卷必填 `knowledge_point`（命名要前后一致）与 `explanation`（通用解析）
5. **追踪**：`python3 agent/cli.py weakpoints` 看掌握度（≥3 次且 ≥85% = 已掌握✓，之后降频）；`python3 agent/cli.py requests` 查学生的重练申请（处理后 `request done <id>`）。
6. **每周重练**：`python3 agent/cli.py wronglist --json /tmp/wrong.json` 导出错题 → 按知识点生成变式卷 → 发布。
7. **收尾**：改动提交 git（试卷 JSON 与代码都提交）。

## 关键约定

- **答案永不进学生接口**：`paper_for_student` 剥离 answer/explanation（服务器层保证）
- **数据安全**：测试用 `HOMELAB_DB=/tmp/xxx.db` 隔离，别污染 `data/homework.db`；改代码后必须重启服务才生效
- **UI 冒烟**：发布后可用浏览器工具打开 http://127.0.0.1:8877 检查渲染（注意：该工具视口矮、不会自动滚动，点击视口外元素前先 `scrollIntoView`）
- **知识点命名一致**：如统一「现在完成时」；新增知识点会自动出现在掌握度表
- **解析 vs 点评**：`explanation`=题目自带通用解析（出卷时写）；`feedback`=AI 针对该学生这次错答的个性化点评（批改时写）

## 用户偏好

- 讲解用中文；一次讲解聚焦 ≤3 个知识点，讲完即出验证卷
- 题目贵在多轮不贵在多：验证卷 3~5 题，诊断卷 ≤15 题
- 学生目标：彻底解决语法问题 + 雅思词汇短语；题型语境全部用雅思话题（教育/环保/科技/城市/健康/工作）
