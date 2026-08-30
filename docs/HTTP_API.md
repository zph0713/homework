# Homework Lab · AI 服务接入协议（HTTP API）

> 适用对象：**不能跑本地命令、只能发 HTTP 请求的在线 AI 服务**（ChatGPT 自定义 GPT / 豆包 / Kimi / Dify / n8n 等）。
> 能跑命令的本地 agent（Hermes / Claude Code / Codex / OpenCode）直接用 `agent/cli.py`，见 `AGENT_PROTOCOL.md`。
> 本文档 + `skills/homework-lab/SKILL.md` 一起导入 AI 服务后，AI 即可通过对话完成出题、批改、单词本与题目目标检查。

## 1. 基本约定

| 项 | 值 |
|---|---|
| Base URL | `http://127.0.0.1:<端口>/api/agent`（端口默认 8877，初始化时可改） |
| 请求格式 | JSON（`Content-Type: application/json`） |
| 响应格式 | JSON；错误为 `{"error": "..."}` + 4xx/5xx |
| 鉴权 | 若设置页配置了「AI 服务访问令牌」，每次请求必须带 `Authorization: Bearer <令牌>`（或 `X-API-Token: <令牌>`） |
| 访问范围 | 默认只绑 127.0.0.1（本机）。AI 服务不在本机时：把监听地址改为 0.0.0.0 并设置令牌，或 SSH 隧道转发 |

**教师工作流对应的调用顺序**（每步都有独立端点）：

```
出题前:  GET  /goals                    ← 题目目标：教学规则 + 画像 + 图谱下一未掌握点
出题:    POST /papers                   ← 提交试卷 JSON（规范见 docs/AGENT_PROTOCOL.md）
收作业:  GET  /pending  → POST /autograde
批改:    POST /grade                    ← 写 AI 批改结果（fill/cloze 复核 + writing/translate）
讲解:    GET  /submissions/<id>         ← 拿完整结果逐题讲解
记录:    POST /diag · POST /log · POST /weekly
单词本:  GET  /vocab · POST /vocab-detail · POST /vocab-check-result
```

## 2. 端点速查

### 题目目标（出题前必读）

**GET `/api/agent/goals`** — 一次拿齐出题决策所需全部信息：

```jsonc
{
  "rules": {                        // 教学规则（初始化页/设置页可改）
    "mastery_threshold": 85,        // 掌握标准：正确率 ≥85%
    "mastery_min_attempts": 5,      // 作答超过 5 次才计分
    "verify_min_questions": 3,      // 验证卷 3~5 题
    "verify_max_questions": 5,
    "weekly_interval_days": 7,      // 周回顾间隔
    "diag_max_questions": 15,       // 诊断卷题数上限
    "question_priority": "student_request,open_diag,kmap_next,..."  // 出题优先级顺序
  },
  "profile": { "goals": [...], "topics": [...], "question_types": [...], "notes": "..." },
  "kmap_next": [{ "stage": 1, "stage_name": "...", "name": "现在完成时", "status": "new", "score": 0 }],
  "open_diagnoses": [...],
  "weakpoints": [...],
  "weekly": { "last_review": {...} | null, "candidates": [...] },
  "priority_legend": { "student_request": "学生口头指定方向（永远最高优先级）", ... }
}
```

### 出题

**POST `/api/agent/papers`** — 发布试卷：

```json
{ "paper": { "title": "验证卷 · 现在完成时", "skill": "grammar", "topic": "教育",
             "questions": [ { "type": "fill", "prompt": "...", "answer": ["..."],
                              "knowledge_point": "现在完成时", "explanation": "..." } ] },
  "status": "published" }
```
响应：`{"homework_id": 13, "question_count": 5, "title": "..."}`。校验失败返回 400 + 中文错误清单。
题型与字段规范：`docs/AGENT_PROTOCOL.md`；出题纪律：`skills/homework-lab/SKILL.md`（题量克制、知识点必填、变式不照搬）。

**GET `/api/agent/papers`** — 试卷列表（含最新提交状态）。**GET `/api/agent/papers/<id>`** — 含答案的完整试卷（仅供 AI，别外泄）。

### 收作业与批改

**GET `/api/agent/pending`** — 待 AI 处理的提交（含学生答案 + 参考答案 + 知识点）。

**POST `/api/agent/autograde`** — 自动批客观题，body：`{"submission_id": 5}`（省略则处理全部待批改）。
响应列出每份提交的自动批改数、需 AI 复核数、新状态。

**POST `/api/agent/grade`** — 写入 AI 批改结果：

```json
{ "submission_id": 5,
  "grades": [ { "question_id": 12, "correct": 0.75, "feedback": "时态正确，但搭配不当…" } ],
  "note": "总评：…" }
```
`correct` 是 **0~1 比例**（部分正确用 0.5/0.75），写作题另可用 `score` 分值。响应含总分与状态。

**GET `/api/agent/submissions/<id>`** — 某次提交完整结果（逐题得分 + feedback + explanation），用于讲解。

### 单词本

**GET `/api/agent/vocab?filter=all|pool|await-detail|unfilled|confirmed`**
- `await-detail`：学生已确认、等 AI 补词典详情的词（批改后必查）
- `pool`：抽查池中的词；`unfilled`：缺中文/词性的词（提醒学生补填）

**POST `/api/agent/vocab-detail`** — AI 补词典信息（只补 detail，中文/词性由学生自己填）：

```json
{ "updates": [ { "word": "complaints", "detail": "n.（复数）投诉，抱怨。搭配 make a complaint about…" } ] }
```

**POST `/api/agent/vocab-check-result`** — 抽查卷批改后回写抽查池：`{"submission_id": 5}`。
响应：`{"correct": [...], "wrong": [...]}`（对→出池，错→留池）。

### 诊断 / 学习路径 / 周回顾 / 重练请求

**POST `/api/agent/diag`** — `{"action": "add", "knowledge_point": "...", "finding": "...", "severity": "high|mid|low", "evidence": "...", "submission_id": 5}` 或 `{"action": "resolve", "diag_id": 3, "note": "验证卷满分"}`。
**GET `/api/agent/diag?open=1`** — 未解决诊断列表。

**POST `/api/agent/log`** — 记录讲解/验证等事件：`{"event_type": "explain", "summary": "...", "knowledge_point": "...", "ref_type": "submission", "ref_id": 5}`。
**GET `/api/agent/timeline`** — 学习路径时间线。

**POST `/api/agent/weekly`** — `{"action": "record", "sampled": "kp1,kp2", "wrong": "kp1", "homework_id": 10}`。
**GET `/api/agent/weekly`** — 周回顾状态（是否到期 + 候选知识点）。

**GET `/api/agent/requests`** — 学生重练申请；**POST `/api/agent/requests`** — `{"action": "done", "id": 3}` 标记已处理。

### 其他查询

| 端点 | 内容 |
|---|---|
| GET `/api/agent/state` | 总览：试卷、知识点、画像、待办 |
| GET `/api/agent/weakpoints` | 知识点掌握度表 |
| GET `/api/agent/kmap?next=1` | 图谱下一个未掌握点（不带参数=全图谱+总评） |
| GET `/api/agent/profile` | 学生画像 |
| POST `/api/agent/profile` | 更新画像：`{"goals": [...], "topics": [...], "question_types": [...], "notes": "..."}` |
| GET `/api/agent/wronglist` | 错题集合（出变式题用） |
| POST `/api/agent/exec` | 兜底：执行 CLI 子命令，`{"args": ["vocab", "dictation", "--limit", "10"]}`（结构化端点未覆盖时用） |

## 3. 接入示例（AI 服务的工具/动作配置）

以 ChatGPT 自定义 GPT Actions 为例，OpenAPI 片段：

```yaml
openapi: 3.0.0
info: { title: Homework Lab, version: "1.0" }
servers:
  - url: http://127.0.0.1:8877/api/agent
paths:
  /goals:
    get:
      summary: 题目目标（教学规则+画像+图谱下一未掌握点），出题前必调
      responses: { "200": { description: OK } }
  /papers:
    post:
      summary: 发布试卷
      requestBody:
        content: { application/json: { schema: { type: object } } }
      responses: { "200": { description: OK } }
  /pending:
    get:
      summary: 待批改提交
      responses: { "200": { description: OK } }
  /grade:
    post:
      summary: 写入 AI 批改结果
      requestBody:
        content: { application/json: { schema: { type: object } } }
      responses: { "200": { description: OK } }
  /vocab:
    get:
      summary: 单词本（?filter=await-detail 等）
      responses: { "200": { description: OK } }
```

Dify / n8n 等工具化平台：把每个端点配成一个 HTTP 工具/节点，工具描述抄上面的「用途」即可。
