# 题型规范与出题指南

八种题型覆盖语法 / 词汇 / 翻译 / 雅思专项训练的主要形态。所有题型统一支持 `explanation`（通用解析）与 `knowledge_point`（知识点标签）。
**带音频的听力题型为预留，尚未实现**（见文末）；但雅思听力精听栏目（ielts_listening）已有**纯文字版**（精听文稿 + 真题格式题目，见「雅思听力精听 / 阅读节选 · 真题格式卷」一节）；口语已实现**纯文字版**（只出题不批改，见 speaking 一节）。

## choice · 单选

**用途**：考察辨析类语法点（时态、主谓一致、冠词、情态、连词）与雅思高频搭配。

**出题要点**：
- 选项 4 个（A-D），以「字母. 」开头
- 干扰项要「错得有道理」：正确答案与易混项成对出现（如 has become/since vs became/for）
- 题干语境用雅思话题（环保、教育、科技、城市生活），顺便积累话题词汇
- 解析写清「为什么对 + 为什么每个干扰项错」

## fill · 填空

**用途**：考察输出型语法（动词变形、被动、词性转换、固定搭配）。

**出题要点**：
- prompt 中用 `____`（4 个以上下划线）表示空格，空格后给提示词，如 `____ (rise)`
- `answer` 用数组列出所有可接受答案（单复数、可省成分都算上）；AI 复核会兜底
- 同义答案拿不准时，用宽一点的描述性提示，宁可让 AI 复核

## cloze · 语法填空

**用途**：雅思听力/阅读 Section 4 风格的综合语法训练（一篇文章练多个点）。

**出题要点**：
- 短文 100~150 词，3~6 个空，用 `__1__` `__2__` 编号
- 空格编号与 answer 键严格一致（校验器会检查）
- 考点搭配：时态 + 非谓语 + 词性 + 连词 + 介词，别只考一种
- `explanation` 按空格编号逐条写（①…… ②……）

## tfng · TRUE / FALSE / NOT GIVEN

**用途**：雅思阅读判断正误题，训练「定位 + 同义替换 + 区分未提及与矛盾」。

**出题要点**：
- 阅读材料 100~150 词，放 `passages` 数组，题里用 `passage_ref` 引用（一篇材料可以配多题）
- 三种答案都要覆盖到，尤其 NOT GIVEN 要多出（这是学生最容易错的）
- FALSE 的题干要「与原文矛盾」（说反了），NOT GIVEN 的题干要「原文根本没提」（新信息）
- 解析必须写清：定位到原文哪句话 + 为什么是 TRUE/FALSE/NOT GIVEN

## writing · 写作

**用途**：雅思 Task 1 / Task 2 的迷你练习（控制篇幅，方便高频批改）。

**出题要点**：
- prompt 里明确：任务描述 + 硬性要求（句数限制、必用结构、词汇）
- `answer.rubric` 写给 AI 的评分要点（学生看不到），批改时按点给分（可用小数）
- 篇幅建议：Task 1 迷你练 ≤3 句；Task 2 段落练 ≤80 词。题目贵在多轮，不贵在长

## translate · 翻译

**用途**：中译英训练（输出型语法 + 话题词汇双重练习），学生画像勾选「翻译」后安排。

**出题要点**：
- prompt 给中文原句 + 明确的翻译要求（必用语法结构 / 话题词汇）
- `answer.rubric` 写给 AI 的评分要点（忠实度、语法结构、词汇搭配），批改时给 0~1 比例分 + 逐句反馈
- 中文原句设计成「逼出目标结构」，如想练现在完成时就给带「自从/已经」的句子

## 默写与抽查（vocabulary）· 单词本专项

**用途**：根据学生单词本定制默写/抽查——看中文释义写英文单词。

**学生→AI 的分工**：学生填中文意思 + 词性（网页多选下拉）→ 点「确认已填」→ AI 在 `detail` 字段补**词典词性 + 详细中文释义**（`vocab list --await-detail` 查待补 → `vocab update` 写入）。

**实现方式**：复用 `fill` 题型 + `skill=vocabulary`。**不要手写默写/抽查卷 JSON**，用 CLI 一键生成：

```bash
# 全词本默写（定制默写训练）
python3 agent/cli.py vocab dictation --limit 10 --out papers/dictation_words.json
# 抽查池随机抽词（词随机出现在作业里混考：可整卷发布，也可把 questions 并入其它卷）
python3 agent/cli.py vocab check --limit 3 --out papers/vocab_check.json
python3 agent/cli.py create papers/xxx.json
```

生成规则：只收录已填中文释义的词（`meaning_cn` 非空；抽查池额外要求已确认），prompt 形如「默写/抽查：可持续的（adj.）____」，`answer=[单词]` 自动判分；同义词变体由 AI 批改时用 `grade` 覆盖兜底。知识点标签：默写用「词汇-默写」，抽查用「词汇-抽查」（抽查卷批改后必须回写池状态）。

**抽查池回写**（抽查卷批改全部完成后执行，幂等）：
```bash
python3 agent/cli.py vocab check-result --sub <提交id>
# 写对 → 出池，网页标绿 🟢；拼错 → 留池，下次抽查再考，直到写对
```

## 雅思听力精听 / 阅读节选 · 真题格式卷（skill=ielts_listening / ielts_reading）

**用途**：听力卷 = **可播放音频**（edge-tts 多音色合成，模拟真人对话/独白）+ 精听文稿 + 真题格式题目；阅读卷 = 节选文章 + 标准题组。两者都以「仿真剑桥真题」格式呈现：题目按考试样式分区（Questions 1–5 / 11–15…）、带题区说明行、表格标准化渲染。**学生直接作答，交卷自动批改**（choice / tfng 即定论；fill / cloze 未命中由老师复核并讲定位句）。

**出题要点**：
- 试卷 `skill`：听力用 `ielts_listening`（前端显示「🎧 听力精听」），阅读用 `ielts_reading`。**不要再出 ielts_stem（题干英译汉栏目已废弃）**
- 材料放 `passages`，每道题都写 `passage_ref` 引用：听力 passage 的 title 写「精听文稿 / 精听对话 · …」，正文 = 完整文稿；阅读 passage = 原文节选
- **听力音频（passage.audio 规格）**：听力卷的 passage 增加合成规格，`cli.py tts` 负责生成：
  ```jsonc
  "audio": { "mode": "tts", "voice": "en-GB-SoniaNeural", "rate": "-4%",
    "segments": [
      { "label": "Tutor · 导师", "voice": "en-GB-RyanNeural", "text": "Right, let's go over..." },
      { "label": "Mia · 学生",   "voice": "en-GB-SoniaNeural", "text": "I wanted something local..." }
    ] }
  ```
  - 独白 = 一段 segments；多人对话 = 每人一段（**每段可指定不同音色**：en-GB 有 Ryan/Sonia/Thomas 等男女老少，可混口音模拟真实考试）；rate 语速默认 `-4%`（对话建议 `-2%`）
  - 出题流程：`create` 发布后跑 `python3 agent/cli.py tts papers/xxx.json --hw <id>` → 合成到 `<数据库同目录>/audio/`（不入 git）、清单回写试卷 JSON 与 DB；已合成文件再跑自动跳过，`--force` 重合成
  - 前端体验：作答页顶部播放器（整段音频 + 0.75/1/1.25× 倍速），**文稿默认折叠**（先听后答）；展开后按说话人着色显示、播放时高亮当前句、**点任意句回听**；结果页文稿默认展开并附音频回放
- **真题题号**：每道题 `extra: {"qno": <考试题号>}`，前端按此显示题号（如 11.、12.）；题区说明行放 `extra.head`（如 `"Questions 11–15\nChoose the correct letter, A, B or C."`），同一题区只写在第一题上，前端会自动去重渲染成题区条
- **表格标准化**：表格完成题用 `cloze` 题型 + `extra.table`（听力表格 / 阅读 summary 表都能用）：
  ```jsonc
  {
    "type": "cloze",
    "passage_ref": "l1",
    "prompt": "Questions 16–20\nComplete the table below.\nWrite NO MORE THAN TWO WORDS for each answer.",
    "passage": "表格文本兜底（必须含 __16__…__20__ 标记，校验器要求与 answer 键一致）",
    "answer": { "16": ["water wheel"], "17": ["steep staircase"] },
    "extra": { "qno": 16, "qno_end": 20,
      "table": { "cols": ["Place", "What you can see or do", "Advice"],
                 "rows": [ ["the watermill", "driven by the great __16__", "…"] ] } }
  }
  ```
  单元格文本里用 `__N__` 标记空格 → 前端渲染真实表格、格内填空；`qno_end` 让题号显示为 16–20；可按 blank 数把 `score` 设为空数（如上例 5 空 → score 5）
- 题量：听力卷 1 个 passage（Section 导览/讲座风格，200~300 词）配 6~11 个小题（单选 3~5 + 表格/笔记完成 5）；阅读卷 1~2 段 passage 配 8~12 题，题型可混：TFNG 组 + 单选组 + summary 完成组
- 解析（`explanation`）写清**定位句**（引用文稿/原文原句）+ 中文讲解；TFNG 的 FALSE 必须「与原文矛盾」、NOT GIVEN 必须「原文没提」；**所有答案词必须在文稿中明确出现一次**，别用同义改写含糊带过（TTS 里也听得到）
- 材料来源：优先原创仿真（准确、可量产、无版权顾虑）；学生贴真实真题原文时照此规范结构化，**保留原文考试题号**
- 交互约定：听力卷作答页顶部提示「先浏览题目 → 播放音频作答」；单选/判断自动批改，填空错漏进老师复核

## speaking · 口语话题（纯文字 · 只出题不批改）

**用途**：雅思口语 Part 1 / Part 2 / Part 3 随机话题训练。**只出题，不要求作答、不做批改**：学生自己开口练、自行判断，点「下一题」逐题过；全部练完点「完成练习」→ 前端记录为已做过（status=done），并展示本卷的**参考表达**供对照优化。

**出题要点**：
- 试卷 `skill` 必须为 `ielts_speaking`（前端识别后进入口语流程页，无交卷栏，只有完成记录）
- 每道题：`type=speaking`，`prompt`=题目文本，`answer` 留空 `""`，`extra={"part": 1|2|3, "suggestions": [...]}`，`score=0`
- **`extra.suggestions`：每题配 6~10 条该话题的地道表达**（词/短语/短句 + 中文），`[{ "en": "...", "zh": "..." }]`——按话题给足可直接替换的素材：如 hometown 给衣食住行短句（street food / within walking distance / public transport...）、Part 2 地点卡给场景描述句（breathtaking / soak up the atmosphere...）；练完点「完成」后按话题逐卡展示，可收藏进短语本
- **Part 2 尽量模拟真实考试**：prompt 用多行文本写「Describe ... / You should say: - 要点1 - 要点2 ... and explain ...」，前端会渲染成真题风格的题目卡（含「准备 1 分钟 · 陈述 1-2 分钟」提示）
- **话题来源优先级**：① 学生「我的」页填写的 Part 1 / Part 2 当季话题（`profile get` 的 `ielts_part1_topics` / `ielts_part2_topics`）② 少量随机追问或在同一话题下多问几题 ③ Part 3 由老师自行出题（基于 Part 2 话题延伸）
- 一份口语卷建议 6~12 题（Part 1 若干 + Part 2 一题 + Part 3 追问若干）
- 贴近剑桥真题：Part 1 日常问答（hometown / work or study / weather / leisure...），Part 2 人物 / 地点 / 事件 / 物品 / 活动类卡片题

**实现说明**：口语卷练完只记「完成」（submission status=`done`），无批改、不计入任何统计；`knowledge_point` 写「口语Part1」等仅作标注。

## phrase · 短语讲解卡（AI 老师教 · 学生收藏）

**用途**：常用口语 / 作文表达的教学展示。**短语只由 AI 老师教**，学生不答题，一键收藏进短语本。

**出题要点**：
- `type=phrase`，`prompt`=短语本体（如 `take ... into account`），`answer` 留空 `""`，`score=0`
- `extra={"meaning_cn": "中文释义", "example": "英文例句", "example_cn": "例句中文"}` —— 前端渲染成讲解卡（短语 + 释义 + 例句 + 「加入短语本」按钮）
- 短语库：`curriculum/phrase_bank.json`（60 条口语/作文高频表达，带释义与例句），词汇短语作业生成器会随机抽 5 条；也可手写自己的短语卡
- 学生收藏后进入「短语本」页（`phrases` 表）；`phrase list` 可查看

## 词汇短语作业（skill=vocabulary · 学生自验证）

**用途**：雅思听力/阅读答案词 + 单词本词汇的随机汉英互译 / 拼写 / 词性练习。**交卷即自动批改，学生自行对照答案验证，老师不参与批改**（区别于默写/抽查流程）。

**生成方式**（不要手写 JSON，用 CLI）：

```bash
python3 agent/cli.py vocab homework --ielts 20 --wordbook 5 --phrases 5 --out papers/vocab_homework.json
python3 agent/cli.py create papers/vocab_homework.json
```

生成规则：
- 20 个雅思听力/阅读答案词（`curriculum/ielts_answer_words.json`，300 词库）+ 5 个单词本中带中文+词性的词
- 每个词随机出 4 种题型之一：拼写（首字母提示）/ 汉译英（fill）/ 英译汉（choice 4 选 1）/ 词性（choice 4 选 1）
- 5 条短语讲解卡（type=phrase，来自 `curriculum/phrase_bank.json`）
- 知识点留空（不计入语法掌握度）；学生交卷后服务器自动批改定稿

## 预留题型：listening（音频，未实现）

> ⚠️ 注意区分：**听力精听栏目（ielts_listening）是纯文字版**（精听文稿 + 题目，见上节），已在用；
> 本节说的 listening 是**带音频播放**的形态，当前开发目标**不包含听力音频**，以下仅为预留设计，
> agent 出题时不要生成带音频的题目，也不要声称有音频可听。

- **listening（预留）**：question JSON 增加可选字段 `audio_url`（音频地址，支持 file:// 本地路径或 http）；前端播放按钮 + 可重复听；答题形态复用 choice/fill/cloze。
- 服务器 API 已预留 `/api/audio` 命名空间；开发计划详见 `docs/ROADMAP.md`，当前阶段不动。

## 通用出题纪律

1. `knowledge_point` 必填且命名一致（详见 AGENT_PROTOCOL §7）
2. 每份卷子聚焦 1~3 个知识点；验证卷 3~5 题，诊断卷 ≤15 题
3. 题干语境全部用雅思话题（教育/环保/科技/城市/健康/工作），语法练习同时积累话题词汇
4. 解析默认用中文，讲清规则 + 回到本题
5. 重练卷必须出变式题（换主语/换数字/换语境），禁止原题照搬
6. 学生画像勾选的题型（「我的」页）优先出；画像里没勾的题型不主动出
