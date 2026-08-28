# 开发路线图（Roadmap）

> 听力与口语为**预留开发计划**：当前开发目标（语法+词汇+写作+翻译闭环）完成后，再单独立项开发。本文档记录预留设计，保证届时可以直接开工、不需要推翻现有结构。

## 阶段 0 · 当前（已交付）

- 六种题型：choice / fill / cloze / tfng / writing / translate
- 语法知识图谱（30 知识点 · 6 阶段）+ 掌握度打分
- 单词本：划词收藏 → 批改时补中文/词性 → 定制默写
- 学生画像（目标/话题/题型）、错题本、周回顾、诊断档案
- 设置页（数据库路径 / IP / 端口）+ AI Agent 技能导入指引

## 阶段 1 · 听力（预留）

**目标**：题目可附带音频，学生听音频作答。

- **数据层**：`questions` 表增加 `audio_url` 列；试卷 JSON 的题目对象增加可选 `audio_url` 字段（file:// 或 http://）
- **前端**：`renderQuestion` 中当 `audio_url` 存在时渲染播放控件（HTML5 `<audio controls>`，可重复听）
- **出题**：agent 用本地 TTS（如 macOS `say`）生成音频 → 放 `data/audio/`（不入 git）→ 在试卷 JSON 引用
- **题型**：复用 choice / fill / cloze（听音答题形态本质不变）
- **批改**：与现有流程完全一致，零改动

## 阶段 2 · 口语（预留）

**目标**：学生对着题目朗读/作答，录音上传，AI 基于转写文本批改。

- **数据层**：`submissions.answers` 中某题的值可存 `{"audio": "<文件引用>", "transcript": "<转写>"}`；`data/audio/` 存录音文件（不入 git）
- **前端**：新增 `speaking` 题型渲染——`navigator.mediaDevices.getUserMedia` + MediaRecorder 录音，上传到预留的 `POST /api/audio`
- **服务器**：预留 `POST /api/audio`（保存音频）与 `GET /api/audio/<id>`（回放）；白名单校验文件大小与扩展名
- **批改**：AI 批改读转写文本 + 可选本地 STT（如 whisper.cpp）；评分维度：发音（转写置信度）、流利度、语法准确性
- **出题**：prompt 给口语任务（描述图表 / 回答观点题），参考雅思口语 Part 1-3 题型

## 阶段 3 · 远期想法（不做承诺）

- 间隔重复算法（SM-2）驱动的单词复习计划
- 听力错题定位（第几秒没听出来）与逐句精听
- 写作自动纠错（拼写/语法高亮）与范文对比
- 多学生支持（当前为单学生设计）

## 设计约束（所有阶段必须遵守）

1. 纯标准库 / 无 npm 构建 / 零第三方运行时依赖（当前架构的原则）
2. 学习数据（音频、录音、DB）永不入 git，只入 `data/`
3. 学生接口永不泄露答案与批改信息（服务器层强制）
4. 新增题型必须先更新本文件、`docs/QUESTION_TYPES.md`、`docs/AGENT_PROTOCOL.md` 三处文档，再改代码
