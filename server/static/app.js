/* Homework Lab 前端 —— 无框架单页应用（hash 路由） */
"use strict";

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

const API = {
  async _get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
    return r.json();
  },
  async _post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  },
  state: () => API._get("/api/state"),
  paper: (id) => API._get(`/api/homeworks/${id}`),
  submit: (homework_id, answers) => API._post("/api/submit", { homework_id, answers }),
  result: (sid) => API._get(`/api/submissions/${sid}`),
  review: () => API._get("/api/review"),
  knowledge: () => API._get("/api/knowledge"),
  request: (knowledge_point, note) => API._post("/api/request", { knowledge_point, note: note || "" }),
  vocabulary: () => API._get("/api/vocabulary"),
  vocabAdd: (word, note, source) => API._post("/api/vocabulary", { word, note: note || "", source: source || "" }),
  vocabPatch: (id, fields) => API._req("PATCH", `/api/vocabulary/${id}`, fields),
  vocabDelete: (id) => API._req("DELETE", `/api/vocabulary/${id}`),
  phrases: () => API._get("/api/phrases"),
  phraseAdd: (p) => API._post("/api/phrases", p),
  phraseDelete: (id) => API._req("DELETE", `/api/phrases/${id}`),
  deleteHomework: (id) => API._req("DELETE", `/api/homeworks/${id}`),
  profile: () => API._get("/api/profile"),
  saveProfile: (p) => API._post("/api/profile", p),
  knowledgeMap: () => API._get("/api/knowledge-map"),
  setupStatus: () => API._get("/api/setup-status"),
  setup: (payload) => API._post("/api/setup", payload),
  settings: () => API._get("/api/settings"),
  saveSettings: (cfg) => API._post("/api/settings", cfg),
  restart: () => API._post("/api/restart", {}),
  _req: async (method, url, body) => {
    const r = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  },
};

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

let toastTimer = null;
function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), ms);
}

/* ================================ 主题（设置页切换，localStorage 记忆） ================================ */
function currentTheme() {
  return localStorage.getItem("hwl_theme") === "dark" ? "dark" : "light";
}
function applyTheme(t) {
  t = t === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = t;
  localStorage.setItem("hwl_theme", t);
  $$(".theme-btn").forEach((b) => b.classList.toggle("on-theme", b.dataset.theme === t));
}

const SKILL = {
  grammar: "语法", vocabulary: "词汇", reading: "阅读", writing: "写作", listening: "听力", mixed: "综合",
  ielts_reading: "阅读节选小题", ielts_stem: "题干翻译", ielts_essay: "作文中译英", ielts_speaking: "口语话题",
};
const TYPE = {
  choice: "单选", fill: "填空", cloze: "语法填空", tfng: "判断 TFNG",
  writing: "写作", translate: "翻译", speaking: "口语话题", phrase: "短语讲解",
};
const SUB_STATUS = { pending: "已交卷 · 待批改", partial: "已交卷 · 批改中", graded: "已批改" };

/* 三大作业栏目（与顶部导航一致） */
const LANES = [
  {
    key: "vocabulary", icon: "📚", title: "词汇短语作业",
    desc: "雅思听力阅读答案词 + 单词本词汇随机汉英互译 / 拼写 / 词性；短语由老师讲解展示，可收藏进短语本。",
    note: "交卷即自动批改，自行对照答案验证（老师不批改词汇）",
    skills: ["vocabulary"],
  },
  {
    key: "grammar", icon: "🔧", title: "语法作业",
    desc: "按知识图谱反复攻克语法短板，翻译中发现语法问题并反复纠正；错题本专属于语法作业。",
    skills: ["grammar"],
  },
  {
    key: "ielts", icon: "🎯", title: "雅思专项训练",
    desc: "阅读节选小题 · 听力阅读题干翻译 · 作文长句中译英 · 口语随机话题（文字训练，贴近剑桥真题）。",
    skills: ["ielts_reading", "ielts_stem", "ielts_essay", "ielts_speaking"],
  },
];
const LANE_BY_KEY = Object.fromEntries(LANES.map((l) => [l.key, l]));
const SUB_LANES = {
  "ielts-reading": { icon: "📰", title: "阅读节选小题训练", skills: ["ielts_reading"],
    desc: "剑桥真题风格的阅读节选 + 各类小题（选择 / TFNG / 填空 / 配对）。批改由老师完成并附答案讲解。" },
  "ielts-stem": { icon: "🔤", title: "听力阅读题干翻译练习", skills: ["ielts_stem"],
    desc: "翻译听力 / 阅读的题干（instruction + questions），扫清审题障碍。老师批改译文。" },
  "ielts-essay": { icon: "✒️", title: "作文长句中译英", skills: ["ielts_essay"],
    desc: "大作文各题型模版句 + 小作文图表描述例句的中译英训练。老师纠正语法问题。" },
  "ielts-speaking": { icon: "🎤", title: "口语随机话题", skills: ["ielts_speaking"],
    desc: "Part 1 / Part 2 / Part 3 随机话题（优先当季话题）。只出题不要求作答、不批改，点「下一题」即可。" },
};
/* 子栏目 / 辅助页归属到哪个主栏目（导航高亮用） */
const NAV_PARENT = {
  words: "lane-vocabulary", phrases: "lane-vocabulary", review: "lane-grammar",
  "ielts-reading": "lane-ielts", "ielts-stem": "lane-ielts",
  "ielts-essay": "lane-ielts", "ielts-speaking": "lane-ielts",
};

function laneOf(skill) {
  const lane = LANES.find((l) => l.skills.includes(skill));
  if (lane) return lane.key;
  if (["reading", "listening"].includes(skill)) return "ielts";   // 旧数据兼容
  if (["writing", "mixed"].includes(skill)) return "grammar";     // 旧数据兼容
  return "grammar";
}

function fmtDate(s) {
  return (s || "").slice(5, 16);
}
function fmtAnswer(a) {
  if (a == null) return "（未作答）";
  if (typeof a === "object") return JSON.stringify(a);
  return String(a);
}

/* ================================ 路由 ================================ */
function navKeyFor(hash) {
  const m = hash.match(/^#\/lane\/([a-z-]+)/);
  if (m) return NAV_PARENT[m[1]] || `lane-${m[1]}`;
  const name = hash.slice(2).split("/")[0] || "home";
  return NAV_PARENT[name] || name;
}

function route() {
  const hash = location.hash || "#/";
  const app = $("#app");
  const navKey = navKeyFor(hash);
  document.body.classList.toggle("wide", navKey === "words" || navKey === "phrases");
  $$("nav [data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === navKey));
  app.innerHTML = '<div class="loading">加载中…</div>';
  const mPaper = hash.match(/^#\/paper\/(\d+)/);
  const mResult = hash.match(/^#\/result\/(\d+)/);
  const mLane = hash.match(/^#\/lane\/([a-z-]+)/);
  if (hash === "#/" || hash === "#") return viewHome();
  if (mPaper) return viewPaper(+mPaper[1]);
  if (mResult) return viewResult(+mResult[1]);
  if (mLane) return viewLane(mLane[1]);
  if (hash === "#/review") return viewReview();
  if (hash === "#/kp") return viewKnowledge();
  if (hash === "#/words") return viewWords();
  if (hash === "#/phrases") return viewPhrases();
  if (hash === "#/me") return viewMe();
  if (hash === "#/settings") return viewSettings();
  app.innerHTML = '<div class="empty"><div class="big">🔍</div>页面不存在</div>';
}

window.addEventListener("hashchange", route);

/* ================================ 首页 ================================ */
let HW_FILTER = "all"; // 首页作业筛选：all=全部 | todo=只显示未做

async function viewHome() {
  const app = $("#app");
  let data;
  try { data = await API.state(); }
  catch (e) { return renderError(app, e); }
  const hws = data.homeworks || [];
  const kps = data.knowledge || [];
  const reqs = data.open_requests || [];
  const filterList = (list) => (HW_FILTER === "todo"
    ? list.filter((h) => !h.latest_submission)
    : list);

  const lanesHTML = LANES.map((lane) => {
    const laneHws = hws.filter((h) => lane.skills.includes(h.skill));
    const shown = filterList(laneHws);
    const cards = shown.length
      ? shown.slice(0, 6).map(hwCard).join("")
      : empty("🕐", HW_FILTER === "todo" ? "这一栏没有未做的作业 ✓" : "这一栏还没有作业，等老师发布吧");
    const reqNotice = lane.key === "grammar" && reqs.length
      ? `<div class="waiting" style="margin-bottom:10px">⏳ 你已申请重练：${reqs.map((r) => esc(r.knowledge_point)).join("、")}，下次语法作业会额外增加</div>` : "";
    return `
      <section class="lane">
        <div class="lane-head">
          <h2>${lane.icon} ${lane.title}</h2>
          <a class="lane-more" href="#/lane/${lane.key}">${laneHws.length ? `全部 ${laneHws.length} 张 →` : "进入 →"}</a>
        </div>
        <p class="lane-desc">${lane.desc}</p>
        ${lane.note ? `<p class="lane-note">💡 ${lane.note}</p>` : ""}
        ${reqNotice}
        <div class="hw-list">${cards}</div>
      </section>`;
  }).join("");

  const kpBlock = kpBlockHTML(kps.slice(0, 8), "语法掌握度概览（只统计语法作业）", "#/kp");

  app.innerHTML = `
    <div class="home-head">
      <div>
        <h1 class="page-title">我的作业</h1>
        <p class="page-sub">作业分为三个栏目：词汇短语作业（交卷自动批改、自行验证）、语法作业（老师批改+讲解）、雅思专项训练（文字训练，口语只出题）。<span style="color:var(--faint)">淡蓝=未做 · 淡绿=已写</span></p>
      </div>
      <div class="seg">
        <button class="seg-btn ${HW_FILTER === "all" ? "on" : ""}" data-hwf="all">全部</button>
        <button class="seg-btn ${HW_FILTER === "todo" ? "on" : ""}" data-hwf="todo">未做</button>
      </div>
    </div>
    <div class="lane-grid">${lanesHTML}</div>
    <div class="home-bottom">
      ${kpBlock}
      <div class="kp-card">
        <h3>学习循环</h3>
        <div style="font-size:13.5px;color:var(--muted);line-height:2">
          ① 做作业 → 交卷<br>② 老师批改 + 讲解（语法优先）<br>③ 针对薄弱点再出题验证<br>④ 错题本申请重练 → 下次额外加题<br>⑤ 全对 = 真正掌握 ✓
        </div>
      </div>
    </div>`;
  $$("[data-hwf]").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.hwf === HW_FILTER) return;
      HW_FILTER = b.dataset.hwf;
      viewHome();
      window.scrollTo(0, 0);
    }));
  bindDeleteHomework(hws);
}

/* ================================ 栏目页 ================================ */
async function viewLane(key) {
  const app = $("#app");
  let data;
  try { data = await API.state(); }
  catch (e) { return renderError(app, e); }
  const hws = data.homeworks || [];
  const reqs = data.open_requests || [];
  const meta = LANE_BY_KEY[key] || SUB_LANES[key];
  if (!meta) {
    app.innerHTML = '<div class="empty"><div class="big">🔍</div>栏目不存在</div>';
    return;
  }
  const skills = meta.skills || (LANE_BY_KEY[key] ? LANE_BY_KEY[key].skills : []);
  const laneHws = hws.filter((h) => skills.includes(h.skill));
  const base = LANE_BY_KEY[key];
  const subLaneLinks = key === "ielts" ? `
    <div class="sub-lane-links">
      ${Object.entries(SUB_LANES).map(([k, s]) =>
        `<a class="btn ghost small" href="#/lane/${k}">${s.icon} ${s.title}</a>`).join("")}
    </div>` : "";
  const reqNotice = key === "grammar" && reqs.length
    ? `<div class="waiting">⏳ 你已申请重练：${reqs.map((r) => esc(r.knowledge_point)).join("、")}，下次语法作业会额外增加</div>` : "";
  const cards = laneHws.length ? laneHws.map(hwCard).join("") : empty("🕐", "这一栏还没有作业，等老师发布吧");
  app.innerHTML = `
    <h1 class="page-title">${meta.icon || (base && base.icon)} ${meta.title || (base && base.title)}</h1>
    <p class="page-sub">${meta.desc || (base && base.desc)}</p>
    ${subLaneLinks}
    ${reqNotice}
    <div class="hw-list">${cards}</div>
    <div style="text-align:center;margin-top:18px"><a class="btn ghost" href="#/">← 返回首页</a></div>`;
  bindDeleteHomework(hws);
}

function bindDeleteHomework(hws) {
  $$("[data-del-hw]").forEach((b) =>
    b.addEventListener("click", () => {
      const id = +b.dataset.delHw;
      const h = hws.find((x) => x.id === id);
      showModal(`
        <h3>删除作业卡？</h3>
        <p>《${esc(h ? h.title : `#${id}`)}》及其全部提交、批改记录都会被删除，无法恢复。</p>
        <div class="btn-row">
          <button class="btn ghost" data-act="cancel">取消</button>
          <button class="btn danger" data-act="confirm">确认删除</button>
        </div>`, async (act) => {
        if (act !== "confirm") return;
        try {
          await API.deleteHomework(id);
          toast("已删除 ✓");
          route();
        } catch (e) {
          toast(`❌ ${e.message}`);
        }
      });
    }));
}

function hwCard(h) {
  const s = h.latest_submission;
  let statusHTML, actions;
  const badgeArch = h.status === "archived" ? '<span class="badge archived">已归档</span>' : "";
  if (h.skill === "ielts_speaking") {
    statusHTML = '<span class="hw-status">🎤 口语练习 · 只出题不交卷</span>';
    actions = `<a class="btn primary" href="#/paper/${h.id}">开始练习</a>`;
  } else if (!s) {
    statusHTML = '<span class="hw-status">📝 未作答</span>';
    actions = `<a class="btn primary" href="#/paper/${h.id}">${h.skill === "vocabulary" ? "开始练习" : "开始答题"}</a>`;
  } else if (s.status !== "graded") {
    statusHTML = `<span class="hw-status">⏳ ${SUB_STATUS[s.status] || s.status}（${fmtDate(s.submitted_at)} 提交）</span>`;
    actions = `<a class="btn ghost small" href="#/result/${s.id}">查看进度</a>`;
  } else {
    const pct = s.max_score ? Math.round((s.total_score / s.max_score) * 100) : 0;
    statusHTML = `<span class="hw-status">✅ 得分 <b>${s.total_score}/${s.max_score}</b>（${pct}%）· ${fmtDate(s.submitted_at)}</span>`;
    actions = `<a class="btn primary small" href="#/result/${s.id}">查看结果</a>
               <a class="btn ghost small" href="#/paper/${h.id}">再练一次</a>`;
  }
  return `
    <div class="hw-card ${s ? "done" : "todo"}">
      <div class="hw-head">
        <div>
          <div class="hw-title">${esc(h.title)}</div>
          <div class="hw-meta">
            <span class="badge skill">${SKILL[h.skill] || h.skill}</span>
            ${h.topic ? `<span class="badge">${esc(h.topic)}</span>` : ""}
            <span class="badge">${h.question_count} 题</span>
            <span class="badge">${fmtDate(h.created_at)}</span>
            ${badgeArch}
          </div>
        </div>
        <button class="btn-del" data-del-hw="${h.id}" title="删除这张作业卡">✕</button>
      </div>
      ${h.goal ? `<div class="hw-goal">🎯 ${esc(h.goal)}</div>` : ""}
      <div class="hw-foot"><div>${statusHTML}</div><div class="hw-actions">${actions}</div></div>
    </div>`;
}

/* ================================ 试卷页 ================================ */
async function viewPaper(id) {
  const app = $("#app");
  let paper;
  try { paper = await API.paper(id); }
  catch (e) { return renderError(app, e); }
  const h = paper.homework;
  if (h.skill === "ielts_speaking") return viewSpeaking(paper);
  const passages = new Map(paper.passages.map((p) => [p.id, p]));
  const qs = paper.questions;

  const vocabNote = h.skill === "vocabulary"
    ? `<div class="waiting" style="margin-top:10px">💡 词汇练习：交卷即自动批改，无需等老师。做完点「交卷」后直接在结果页对照答案自行验证。</div>` : "";
  const head = `
    <div class="paper-head">
      <h1>${esc(h.title)}</h1>
      <div class="hw-meta">
        <span class="badge skill">${SKILL[h.skill] || h.skill}</span>
        ${h.topic ? `<span class="badge">${esc(h.topic)}</span>` : ""}
        <span class="badge">${qs.length} 题</span>
      </div>
      ${h.goal ? `<div class="goal">🎯 ${esc(h.goal)}</div>` : ""}
      ${vocabNote}
    </div>`;
  // 阅读材料只在试卷开头展示一次（按题目引用顺序去重），题目卡片不再重复整篇文章
  const used = new Set();
  const passageBlocks = qs
    .map((q) => (q.passage_id ? passages.get(q.passage_id) : null))
    .filter((p) => p && !used.has(p.id) && (used.add(p.id), true))
    .map((p) => `<div class="q-passage"><div class="p-title">📄 ${esc(p.title || "阅读材料")}</div><p>${esc(p.body)}</p></div>`)
    .join("");
  const body = qs.map((q, i) => renderQuestion(q, i)).join("");
  app.innerHTML = `${head}${passageBlocks}${body}${submitBarHTML()}`;
  bindPaperEvents(qs, id);
}

function renderQuestion(q, i) {
  let main = "";
  if (q.type === "choice") {
    main = `<div class="q-prompt">${esc(q.prompt)}</div>
      <div class="q-options">${(q.options || []).map((opt, oi) => {
      const letter = (opt.match(/^([A-D])[.．、)\s]/) || [])[1] || String.fromCharCode(65 + oi);
      return `<label class="q-opt" data-q="${q.id}" data-v="${letter}">
        <input type="radio" name="q${q.id}" value="${letter}"><span>${esc(opt)}</span></label>`;
    }).join("")}</div>`;
  } else if (q.type === "tfng") {
    const opts = [
      ["TRUE", "TRUE · 与原文一致"], ["FALSE", "FALSE · 与原文矛盾"], ["NOT GIVEN", "NOT GIVEN · 未提及"],
    ];
    main = `<div class="q-prompt">${esc(q.prompt)}</div>
      <div class="q-options">${opts.map(([v, label]) => {
      const [big, hint] = label.split("·");
      return `<label class="q-opt" data-q="${q.id}" data-v="${v}">
        <input type="radio" name="q${q.id}" value="${v}"><span>${big}<span class="tfng-hint">${hint}</span></span></label>`;
    }).join("")}</div>`;
  } else if (q.type === "fill") {
    const parts = esc(q.prompt).split(/_{3,}/);
    const input = `<span class="q-fill"><input type="text" data-q="${q.id}" data-blank="1" placeholder="填写答案"></span>`;
    main = `<div class="q-prompt">${parts.join(input)}</div>`;
  } else if (q.type === "cloze") {
    const html = esc(q.passage).replace(/__(\d+)__/g,
      (m, n) => `<span class="q-fill"><input type="text" data-q="${q.id}" data-blank="${n}" size="10"></span>`);
    main = `${q.prompt ? `<div class="q-prompt" style="margin-bottom:8px">${esc(q.prompt)}</div>` : ""}
      <div class="q-cloze-text">${html}</div>`;
  } else if (q.type === "writing" || q.type === "translate") {
    const ph = q.type === "translate" ? "在这里写下你的译文…" : "在这里写下你的作文…";
    main = `<div class="q-prompt">${esc(q.prompt)}</div>
      <div class="q-write"><textarea data-q="${q.id}" placeholder="${ph}"></textarea>
      <div class="wc"><span data-wc="${q.id}">0</span> 词</div></div>`;
  } else if (q.type === "phrase") {
    const ex = q.extra || {};
    main = phraseCardHTML(q.prompt, ex, `homework#${q.homework_id}`);
  } else if (q.type === "speaking") {
    main = `<div class="q-prompt">${esc(q.prompt)}</div>`;
  }
  return `
    <div class="q-card" id="qc-${q.id}">
      <div class="q-top"><span class="q-num">${i + 1}.</span>
        <span class="q-type">${TYPE[q.type] || q.type}</span>
        ${q.knowledge_point ? `<span class="badge">${esc(q.knowledge_point)}</span>` : ""}
        ${q.score !== 1 ? `<span class="badge">${q.score} 分</span>` : ""}
      </div>
      ${main}
    </div>`;
}

/* 短语讲解卡（AI 老师教；学生可一键收藏进短语本） */
function phraseCardHTML(phrase, ex, source) {
  const data = JSON.stringify({ phrase, meaning_cn: ex.meaning_cn || "", example: ex.example || "", example_cn: ex.example_cn || "" })
    .replace(/"/g, "&quot;");
  return `
    <div class="phrase-card">
      <div class="phrase-main">💬 <b>${esc(phrase)}</b></div>
      ${ex.meaning_cn ? `<div class="phrase-meaning">${esc(ex.meaning_cn)}</div>` : ""}
      ${ex.example ? `<div class="phrase-example">${esc(ex.example)}${ex.example_cn ? `（${esc(ex.example_cn)}）` : ""}</div>` : ""}
      <div class="phrase-foot">
        <span class="phrase-tip">👩‍🏫 老师讲解 · 仅供学习，无需作答</span>
        <button class="btn primary small" data-add-phrase="${data}">➕ 加入短语本</button>
      </div>
    </div>`;
}

function bindPhraseButtons(root) {
  $$("[data-add-phrase]", root || document).forEach((b) =>
    b.addEventListener("click", async () => {
      const p = JSON.parse(b.dataset.addPhrase.replace(/&quot;/g, '"'));
      try {
        const r = await API.phraseAdd(Object.assign({}, p, { source: location.hash }));
        toast(r.created ? `「${p.phrase}」已加入短语本 ✓` : `「${p.phrase}」已在短语本中`);
        b.disabled = true;
        b.textContent = "已收藏 ✓";
      } catch (e) {
        toast(`❌ ${e.message}`);
      }
    }));
}

function submitBarHTML() {
  return `
    <div class="submit-bar">
      <div class="submit-inner">
        <div class="submit-progress">已答 <b id="prog-done">0</b> / <span id="prog-total">0</span></div>
        <button class="btn primary" id="btn-submit">交 卷</button>
      </div>
    </div>`;
}

function collectAnswers(qs) {
  const answers = {};
  qs.forEach((q) => {
    if (q.type === "phrase" || q.type === "speaking") return; // 展示型：无作答
    if (q.type === "choice" || q.type === "tfng") {
      const el = $(`input[name="q${q.id}"]:checked`);
      if (el) answers[q.id] = el.value;
    } else if (q.type === "fill") {
      const el = $(`input[data-q="${q.id}"][data-blank="1"]`);
      if (el && el.value.trim()) answers[q.id] = el.value.trim();
    } else if (q.type === "cloze") {
      const obj = {};
      $$(`input[data-q="${q.id}"]`).forEach((inp) => {
        if (inp.value.trim()) obj[inp.dataset.blank] = inp.value.trim();
      });
      if (Object.keys(obj).length) answers[q.id] = obj;
    } else if (q.type === "writing" || q.type === "translate") {
      const el = $(`textarea[data-q="${q.id}"]`);
      if (el && el.value.trim()) answers[q.id] = el.value.trim();
    }
  });
  return answers;
}

function bindPaperEvents(qs, hwId) {
  bindPhraseButtons();
  const answerable = qs.filter((q) => q.type !== "phrase" && q.type !== "speaking");
  const progress = () => {
    const answers = collectAnswers(qs);
    $("#prog-done").textContent = Object.keys(answers).length;
    $("#prog-total").textContent = answerable.length;
    return answers;
  };
  $$(".q-opt input").forEach((inp) => {
    inp.addEventListener("change", () => {
      $$(`.q-opt[data-q="${inp.name.slice(1)}"]`).forEach((l) =>
        l.classList.toggle("selected", l.dataset.v === inp.value));
      progress();
    });
  });
  $$("input[data-blank]").forEach((inp) => inp.addEventListener("input", progress));
  $$("textarea[data-q]").forEach((ta) => {
    ta.addEventListener("input", () => {
      const words = ta.value.trim() ? ta.value.trim().split(/\s+/).length : 0;
      $(`[data-wc="${ta.dataset.q}"]`).textContent = words;
      progress();
    });
  });
  progress();

  $("#btn-submit").addEventListener("click", () => {
    const answers = collectAnswers(qs);
    const unanswered = answerable.filter((q) => !answers[q.id]).map((q) => answerable.indexOf(q) + 1);
    const doSubmit = async () => {
      const btn = $("#btn-submit");
      btn.disabled = true;
      btn.textContent = "提交中…";
      try {
        const r = await API.submit(hwId, answers);
        const app = $("#app");
        app.innerHTML = r.auto_graded ? `
          <div class="card" style="text-align:center;padding:50px 30px">
            <div style="font-size:44px">⚡</div>
            <h1 class="page-title">交卷成功，已自动批改！</h1>
            <p class="page-sub">词汇短语练习由你自行对照答案验证。点「查看结果」看每题的对错与答案；短语讲解卡可收藏进短语本。</p>
            <div style="margin-top:16px;display:flex;gap:10px;justify-content:center">
              <a class="btn primary" href="#/result/${r.submission_id}">查看结果</a>
              <a class="btn ghost" href="#/">返回首页</a>
            </div>
          </div>` : `
          <div class="card" style="text-align:center;padding:50px 30px">
            <div style="font-size:44px">📬</div>
            <h1 class="page-title">交卷成功！</h1>
            <p class="page-sub">老师批改完成后，会在这里显示结果，并在聊天中为你讲解错题。</p>
            <div style="margin-top:16px;display:flex;gap:10px;justify-content:center">
              <a class="btn primary" href="#/result/${r.submission_id}">查看提交</a>
              <a class="btn ghost" href="#/">返回首页</a>
            </div>
          </div>`;
        window.scrollTo(0, 0);
      } catch (e) {
        toast(`❌ 提交失败：${e.message}`);
        btn.disabled = false;
        btn.textContent = "交 卷";
      }
    };
    if (unanswered.length) {
      showModal(`
        <h3>还有 ${unanswered.length} 题未作答</h3>
        <p>确定要交卷吗？未作答的题目会计为错误。</p>
        <div class="uns-list">未作答：第 ${unanswered.join("、")} 题</div>
        <div class="btn-row">
          <button class="btn ghost" data-act="cancel">再检查一下</button>
          <button class="btn primary" data-act="confirm">确认交卷</button>
        </div>`, (act) => { if (act === "confirm") doSubmit(); });
    } else {
      showModal(`
        <h3>确认交卷？</h3>
        <p>共 ${qs.length} 题已全部作答。提交后等待老师批改。</p>
        <div class="btn-row">
          <button class="btn ghost" data-act="cancel">再检查一下</button>
          <button class="btn primary" data-act="confirm">确认交卷</button>
        </div>`, (act) => { if (act === "confirm") doSubmit(); });
    }
  });
}

function showModal(inner, onAction) {
  const mask = document.createElement("div");
  mask.className = "modal-mask";
  mask.innerHTML = `<div class="modal">${inner}</div>`;
  mask.addEventListener("click", (e) => {
    if (e.target === mask) mask.remove();
  });
  mask.querySelectorAll("[data-act]").forEach((b) =>
    b.addEventListener("click", () => { mask.remove(); onAction(b.dataset.act); }));
  document.body.appendChild(mask);
}

/* ================================ 口语随机话题（只出题不交卷） ================================ */
let speakIdx = 0;
let speakQs = [];

function viewSpeaking(paper) {
  const app = $("#app");
  const h = paper.homework;
  speakQs = paper.questions || [];
  speakIdx = 0;
  app.innerHTML = `
    <div class="paper-head">
      <h1>${esc(h.title)}</h1>
      <div class="hw-meta"><span class="badge skill">🎤 口语随机话题</span><span class="badge">${speakQs.length} 题</span></div>
      ${h.goal ? `<div class="goal">🎯 ${esc(h.goal)}</div>` : ""}
      <p class="page-sub" style="margin:10px 0 0;font-size:13px">口语只出题、不要求作答、不做批改：自己开口练（可录音回听），答得如何由你自行判断。看完点「下一题」；Part 2 按真实考试展示题目卡与要求。</p>
    </div>
    <div id="speak-stage"></div>`;
  if (!speakQs.length) {
    $("#speak-stage").innerHTML = empty("🎤", "这份口语卷还没有题目，等老师补充吧");
    return;
  }
  renderSpeakCard();
}

function renderSpeakCard() {
  const q = speakQs[speakIdx];
  const ex = q.extra || {};
  const p = Number(ex.part) || 1;
  const partLabel = { 1: "Part 1 · 日常问答", 2: "Part 2 · 个人陈述", 3: "Part 3 · 深入讨论" }[p] || `Part ${p}`;
  const isPart2 = p === 2;
  const cardHTML = isPart2 ? `
    <div class="speak-cue">
      <div class="cue-top"><span class="q-type">${partLabel}</span><span class="cue-time">⌛ 准备 1 分钟 · 陈述 1-2 分钟</span></div>
      <div class="cue-body">${esc(q.prompt)}</div>
    </div>` : `
    <div class="speak-card">
      <div class="q-top"><span class="q-type">${partLabel}</span></div>
      <div class="q-prompt">${esc(q.prompt)}</div>
    </div>`;
  $("#speak-stage").innerHTML = `
    ${cardHTML}
    <div class="speak-actions">
      <span class="speak-progress">第 ${speakIdx + 1} / ${speakQs.length} 题</span>
      <div>
        <button class="btn ghost" id="btn-prev" ${speakIdx === 0 ? "disabled" : ""}>← 上一题</button>
        <button class="btn primary" id="btn-next">${speakIdx >= speakQs.length - 1 ? "全部练完 ✓" : "下一题 →"}</button>
      </div>
    </div>`;
  $("#btn-next").addEventListener("click", () => {
    if (speakIdx >= speakQs.length - 1) {
      $("#speak-stage").innerHTML = `
        <div class="card" style="text-align:center;padding:40px 30px">
          <div style="font-size:44px">🎉</div>
          <h2>全部话题练完！</h2>
          <p class="page-sub">想再来一轮点「重新开始」；想换话题，等老师发布新的口语卷（老师会优先从你「我的」页填写的当季话题里抽题）。</p>
          <div style="margin-top:12px;display:flex;gap:10px;justify-content:center">
            <button class="btn primary" id="btn-restart">重新开始</button>
            <a class="btn ghost" href="#/">返回首页</a>
          </div>
        </div>`;
      $("#btn-restart").addEventListener("click", () => { speakIdx = 0; renderSpeakCard(); });
      return;
    }
    speakIdx += 1;
    renderSpeakCard();
    window.scrollTo(0, 0);
  });
  const prev = $("#btn-prev");
  if (prev) prev.addEventListener("click", () => {
    if (speakIdx > 0) { speakIdx -= 1; renderSpeakCard(); }
  });
}

/* ================================ 结果页 ================================ */
async function viewResult(sid) {
  const app = $("#app");
  let d;
  try { d = await API.result(sid); }
  catch (e) { return renderError(app, e); }
  const waiting = d.status !== "graded"
    ? `<div class="waiting">⏳ 本卷还有题目在批改中（当前状态：${SUB_STATUS[d.status] || d.status}）。批改完成后刷新页面即可看到完整结果与讲解。</div>`
    : "";
  const vocabNote = d.homework_skill === "vocabulary"
    ? `<div class="waiting">📚 词汇短语练习：以下对错与参考答案供你自行对照验证（不计入语法掌握度）；短语讲解卡可一键收藏进短语本。</div>`
    : "";
  let hero = `
    <div class="score-hero">
      <h1>${esc(d.homework_title)} · 结果</h1>
      <div class="score-row">
        ${d.total_score != null
          ? `<span class="score-big">${d.total_score}/${d.max_score}</span>
             <span class="score-meta">全对 ${d.correct_count}/${d.total_count} · ${fmtDate(d.submitted_at)} 交卷</span>`
          : `<span class="score-meta">已交卷，等待批改（${fmtDate(d.submitted_at)}）</span>`}
      </div>
      ${d.overall_feedback ? `<div class="score-note">💬 ${esc(d.overall_feedback)}</div>` : ""}
    </div>`;
  const items = d.items.map(renderResultItem).join("");
  app.innerHTML = `${hero}${waiting}${vocabNote}${items}<div style="text-align:center;margin-top:18px">
    <a class="btn ghost" href="#/">← 返回首页</a></div>`;
  bindPhraseButtons();
}

function clozePerBlank(it) {
  const user = it.user_answer || {};
  const key = it.correct_answer || {};
  const norm = (s) => String(s == null ? "" : s).trim().toLowerCase();
  return Object.keys(key).map((n) => {
    const accepted = (Array.isArray(key[n]) ? key[n] : [key[n]]).map(norm);
    const ok = accepted.includes(norm(user[n]));
    const ref = Array.isArray(key[n]) ? key[n][0] : key[n];
    return `<div class="${ok ? "ok-t" : "bad-t"}">${n}. ${ok ? "✓" : "✗"} 你的：<b>${esc(user[n] || "（空）")}</b>${ok ? "" : `　参考答案：${esc(ref)}`}</div>`;
  }).join("");
}

function renderResultItem(it) {
  if (it.type === "phrase") {
    // 短语讲解卡：结果页只做展示，无对错
    const ex = it.extra || {};
    return `
    <div class="r-card" style="border-left-color:var(--accent)">
      <div class="q-top"><span class="q-type">${TYPE[it.type] || it.type}</span></div>
      ${phraseCardHTML(it.prompt, ex)}
    </div>`;
  }
  const isText = it.type === "writing" || it.type === "translate";
  const cls = it.correct === 1 ? "ok" : it.correct === 0 ? "bad" : "partial";
  const mark = it.correct === 1 ? "✓ 正确" : it.correct === 0 ? "✗ 错误" : "◐ 部分正确";
  const showKey = it.correct !== 1 && it.correct_answer != null && !isText;
  let answerHTML = "";
  if (isText) {
    const lbl = it.type === "translate" ? "你的译文：" : "你的作文：";
    answerHTML = `<div class="r-answer">${lbl}</div>
      <div class="r-essay">${esc(it.user_answer || "（未作答）")}</div>`;
  } else if (it.type === "cloze") {
    answerHTML = `<div class="cloze-check">${clozePerBlank(it)}</div>`;
  } else {
    answerHTML = `<div class="r-answer">
      <span>你的答案：<b class="mine">${esc(fmtAnswer(it.user_answer))}</b></span>
      ${showKey ? `　|　<span>正确答案：<b class="key">${esc(fmtAnswer(it.correct_answer))}</b></span>` : ""}
    </div>`;
  }
  const feedback = it.feedback
    ? `<div class="r-feedback"><span class="fb-label">👩‍🏫 老师点评：</span>${esc(it.feedback)}</div>` : "";
  const explain = it.correct !== 1 && it.explanation
    ? `<div class="r-explain"><span class="ex-label">📖 解析：</span>${esc(it.explanation)}</div>` : "";
  return `
    <div class="r-card ${cls}">
      <div class="q-top">
        <span class="r-mark ${cls}">${mark}</span>
        ${it.score != null ? `<span class="q-type">得分 ${it.score}/${it.max_score}</span>` : ""}
        <span class="q-type">${TYPE[it.type] || it.type}</span>
        ${it.knowledge_point ? `<span class="badge">${esc(it.knowledge_point)}</span>` : ""}
      </div>
      <div class="q-prompt">${esc(it.prompt)}</div>
      ${it.passage_info ? `<div class="q-passage"><div class="p-title">📄 ${esc(it.passage_info.title)}</div><p>${esc(it.passage_info.body)}</p></div>` : ""}
      ${answerHTML}
      ${feedback}
      ${explain}
    </div>`;
}

/* ================================ 错题本 ================================ */
async function viewReview() {
  const app = $("#app");
  let data;
  try { data = await API.review(); }
  catch (e) { return renderError(app, e); }
  const groups = data.groups || {};
  const names = Object.keys(groups);
  if (!names.length) {
    app.innerHTML = `<h1 class="page-title">错题本</h1>${empty("🎉", "还没有错题，继续保持！")}`;
    return;
  }
  const blocks = names.map((kp) => {
    const items = groups[kp];
    const cards = items.map(wrongCard).join("");
    return `
      <div class="group-block">
        <div class="group-head">
          <h2>📌 ${esc(kp)}</h2><span class="count">${items.length} 道错题</span>
          <button class="btn ghost small" data-request="${esc(kp)}">申请重练这个知识点</button>
        </div>
        ${cards}
      </div>`;
  }).join("");
  app.innerHTML = `<h1 class="page-title">错题本（语法作业专属）</h1>
    <p class="page-sub">每次语法作业批改后的错题都归档在这里（词汇/雅思练习不计入）。点「申请重练」会排进下一次语法作业，作为额外增加的题目。</p>
    ${blocks}`;
  $$("[data-request]").forEach((b) =>
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await API.request(b.dataset.request);
        toast(`已申请重练「${b.dataset.request}」，下次作业会安排 ✓`);
      } catch (e) {
        toast(`❌ ${e.message}`);
        b.disabled = false;
      }
    }));
}

function wrongCard(it) {
  let ansHTML = "";
  if (it.type === "writing" || it.type === "translate") {
    const lbl = it.type === "translate" ? "你的译文：" : "你的作文：";
    ansHTML = `<div class="r-answer"><span>${lbl}</span></div>
      <div class="r-essay">${esc(it.user_answer || "")}</div>`;
  } else if (it.type === "cloze") {
    ansHTML = `<div class="cloze-check">${clozePerBlank(it)}</div>`;
  } else {
    ansHTML = `<div class="r-answer">
      <span>错答：<b class="mine">${esc(fmtAnswer(it.user_answer))}</b></span>
      <span>　|　正解：<b class="key">${esc(fmtAnswer(it.correct_answer))}</b></span></div>`;
  }
  const feedback = it.feedback ? `<div class="r-feedback"><span class="fb-label">👩‍🏫 点评：</span>${esc(it.feedback)}</div>` : "";
  const explain = it.explanation ? `<div class="r-explain"><span class="ex-label">📖 解析：</span>${esc(it.explanation)}</div>` : "";
  return `
    <div class="wrong-card">
      <div class="wrong-meta">
        <span>${esc(it.homework_title)}</span><span>·</span><span>${fmtDate(it.graded_at)}</span>
        <span>·</span><span>${TYPE[it.type] || it.type}</span>
      </div>
      <div class="q-prompt">${esc(it.prompt)}</div>
      ${ansHTML}
      ${feedback}
      ${explain}
    </div>`;
}

/* ================================ 知识点页 ================================ */
async function viewKnowledge() {
  const app = $("#app");
  let data;
  try { data = await API.knowledge(); }
  catch (e) { return renderError(app, e); }
  const kps = data.knowledge || [];
  const wrongs = data.wrongs_by_kp || {};
  if (!kps.length) {
    app.innerHTML = `<h1 class="page-title">知识点掌握度</h1>
      ${empty("🧭", "还没有数据：做完第一份作业并批改后，这里会显示每个知识点的掌握情况")}`;
    return;
  }
  const cards = kps.map((k) => {
    const pct = Math.round((k.mastery || 0) * 100);
    const counted = k.attempts > 5;
    const wrong = wrongs[k.name] || [];
    return `
      <div class="kp-card">
        <div class="kp-row">
          <div class="kp-head">
            <span class="kp-name">${esc(k.name)}</span>
            <span class="kp-pct">${counted ? pct + "%" : "计分中"} · ${k.attempts} 次作答 · 对 ${k.correct}</span>
          </div>
          <div class="bar ${counted ? (k.mastery >= 0.85 ? "ok" : pct < 50 ? "bad" : "warn") : ""}"><i style="width:${counted ? pct : 0}%"></i></div>
          <div style="margin-top:6px">${statusTag(k)}</div>
        </div>
        ${wrong.length ? `
          <details class="wrongs-toggle">
            <summary>错题记录（${wrong.length}）</summary>
            ${wrong.map(wrongCard).join("")}
          </details>` : ""}
      </div>`;
  }).join("");
  app.innerHTML = `<h1 class="page-title">知识点掌握度</h1>
    <p class="page-sub">掌握度 = 累计答对 ÷ 累计作答。作答超过 5 次才开始计分，超过 5 次且 ≥85% 才算「已掌握」。</p>
    <div class="kp-grid">${cards}</div>`;
}

function statusTag(k) {
  if (k.attempts > 5 && k.mastery >= 0.85) return '<span class="status-tag ok">已掌握 ✓</span>';
  if (k.attempts === 0) return '<span class="status-tag new">未练过</span>';
  if (k.attempts > 5 && k.mastery < 0.5) return '<span class="status-tag bad">薄弱 · 需加强</span>';
  return '<span class="status-tag warn">学习中（计分中）</span>';
}

function kpBlockHTML(kps, title, link) {
  const rows = kps.length ? kps.map((k) => {
    const pct = Math.round((k.mastery || 0) * 100);
    const counted = k.attempts > 5;
    return `
      <div class="kp-row">
        <div class="kp-head"><span class="kp-name">${esc(k.name)}</span><span class="kp-pct">${counted ? pct + "%" : "计分中"}</span></div>
        <div class="bar ${counted ? (k.mastery >= 0.85 ? "ok" : pct < 50 ? "bad" : "warn") : ""}"><i style="width:${counted ? pct : 0}%"></i></div>
      </div>`;
  }).join("") : '<div style="font-size:13px;color:var(--faint)">暂无数据</div>';
  return `
    <div class="kp-card">
      <h3>📊 ${title}${link ? ` <a href="${link}" style="float:right;font-weight:400">全部 →</a>` : ""}</h3>
      ${rows}
    </div>`;
}

function empty(icon, text) {
  return `<div class="empty"><div class="big">${icon}</div>${text}</div>`;
}

function renderError(app, e) {
  app.innerHTML = `
    <div class="empty">
      <div class="big">⚠️</div>
      <div>加载失败：${esc(e.message)}</div>
      <div style="margin-top:12px"><a class="btn ghost small" href="#/">返回首页</a></div>
    </div>`;
}

/* ================================ 选中单词 → 单词本 ================================ */
let wordPopEl = null;
function removeWordPop() {
  if (wordPopEl) { wordPopEl.remove(); wordPopEl = null; }
}
document.addEventListener("mousedown", (e) => {
  if (wordPopEl && !wordPopEl.contains(e.target)) removeWordPop();
});
document.addEventListener("scroll", removeWordPop, true);
document.addEventListener("mouseup", () => {
  setTimeout(() => {
    removeWordPop();
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const text = sel.toString().trim();
    if (!text || !/^[A-Za-z][A-Za-z'’\- ]*$/.test(text)) return;
    const node = sel.anchorNode;
    const host = node && node.nodeType === 3 ? node.parentElement : node;
    if (!host || !host.closest(".q-card, .r-card, .wrong-card, .q-passage, .q-cloze-text")) return;
    if (host.closest(".phrase-card, .speak-cue")) return; // 短语/口语卡不走单词本收藏
    const word = text.replace(/[^A-Za-z'’-]/g, " ").trim().split(/\s+/)[0];
    if (!word || word.length < 2 || word.length > 40) return;
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const pop = document.createElement("div");
    pop.className = "word-pop";
    pop.innerHTML = `➕ <b>${esc(word)}</b> 加入单词本`;
    pop.style.left = `${Math.min(window.scrollX + rect.left, window.innerWidth - 190)}px`;
    pop.style.top = `${window.scrollY + rect.bottom + 6}px`;
    pop.addEventListener("mousedown", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      removeWordPop();
      addToWordbook(word);
    });
    document.body.appendChild(pop);
    wordPopEl = pop;
  }, 10);
});

async function addToWordbook(word) {
  try {
    const r = await API.vocabAdd(word, "", location.hash);
    toast(r.created ? `「${word}」已加入单词本 ✓` : `「${word}」已在单词本中`);
  } catch (e) {
    toast(`❌ ${e.message}`);
  }
}

/* ================================ 单词本页 ================================ */
const POS_OPTS = ["n.", "v.", "vt.", "vi.", "adj.", "adv.", "prep.", "conj.", "pron.", "num.", "art.", "aux.", "interj.", "phr."];
let VW_PAGE = 1;   // 单词本当前页
let VW_SIZE = 20;  // 每页词数

function poolTag(w) {
  if (w.in_pool === 0 && w.times_checked) return '<span class="pool-tag ok">🟢 抽查通过 · 已出池</span>';
  if (w.in_pool === 1 && w.last_check_ok === 0) return '<span class="pool-tag bad">🔴 拼错 · 留池重抽</span>';
  if (w.in_pool === 1 && w.confirmed) return '<span class="pool-tag pending">⚪ 在抽查池</span>';
  return '<span class="pool-tag none">—</span>';
}

function wordStatus(w) {
  if (w.confirmed && w.detail) return '<span class="status-tag ok">✓ 已收录</span>';
  if (w.confirmed) return '<span class="status-tag warn">⏳ 待老师补详细</span>';
  return '<span class="status-tag new">✏️ 填写中</span>';
}

async function viewWords() {
  const app = $("#app");
  let data;
  try { data = await API.vocabulary(); } catch (e) { return renderError(app, e); }
  const words = data.words || [];
  const totalPages = Math.max(1, Math.ceil(words.length / VW_SIZE));
  if (VW_PAGE > totalPages) VW_PAGE = totalPages;
  const pageWords = words.slice((VW_PAGE - 1) * VW_SIZE, VW_PAGE * VW_SIZE);
  const rows = pageWords.map((w) => {
    const posText = w.pos.length ? w.pos.join(" / ") : "选择词性…";
    const canConfirm = w.meaning_cn && w.pos.length;
    return `
    <tr>
      <td class="v-word">${esc(w.word)}</td>
      <td class="v-pos">
        <div class="pos-wrap">
          <button class="pos-btn" data-posbtn="${w.id}">${esc(posText)} ▾</button>
          <div class="pos-pop" data-pospop="${w.id}" hidden>
            ${POS_OPTS.map((o) => `<label class="pos-opt">
              <input type="checkbox" value="${o}" data-posc="${w.id}" ${w.pos.includes(o) ? "checked" : ""}>${o}</label>`).join("")}
          </div>
        </div>
      </td>
      <td class="v-mean"><input type="text" data-mean="${w.id}" value="${esc(w.meaning_cn)}" placeholder="你填的中文意思"></td>
      <td class="v-detail">${w.detail ? esc(w.detail) : (w.confirmed
        ? '<span class="v-empty">老师补词典词性 + 详细释义</span>'
        : '<span class="v-empty">—</span>')}</td>
      <td class="v-status">${poolTag(w)}${wordStatus(w)}</td>
      <td class="v-date">${fmtDate(w.added_ts)}</td>
      <td class="v-acts">
        <button class="btn ghost small" data-confirm="${w.id}" ${canConfirm ? "" : "disabled"} title="确认你已填好中文和词性，老师就会补详细释义">确认已填</button>
        <button class="btn ghost small" data-vdel="${w.id}">删除</button>
      </td>
    </tr>`;
  }).join("");
  const unfilled = words.filter((w) => !w.meaning_cn || !w.pos.length).length;
  const awaitDetail = words.filter((w) => w.confirmed && !w.detail).length;
  const pager = words.length > VW_SIZE ? `
    <div class="pager">
      <button class="btn ghost small" data-pg="prev" ${VW_PAGE <= 1 ? "disabled" : ""}>← 上一页</button>
      <span class="pager-info">第 ${VW_PAGE} / ${totalPages} 页</span>
      <button class="btn ghost small" data-pg="next" ${VW_PAGE >= totalPages ? "disabled" : ""}>下一页 →</button>
      <span class="pager-size">每页
        <select id="pg-size">${[10, 20, 50].map((n) => `<option value="${n}" ${VW_SIZE === n ? "selected" : ""}>${n}</option>`).join("")}</select>
        词</span>
    </div>` : "";
  app.innerHTML = `
    <h1 class="page-title">单词本</h1>
    <p class="page-sub">做题时选中不认识的单词即可一键收藏。你来填中文和词性（词性可多选），点「确认已填」后老师补词典词性与详细释义；之后单词会随机出现在作业里抽查——写对出池（绿色），拼错继续留池。</p>
    ${words.length ? `
    <div class="v-wrap">
      <table class="v-table">
        <thead><tr><th>单词</th><th>词性（你选，可多选）</th><th>中文意思（你填）</th><th>详细（老师补）</th><th>状态</th><th>加入时间</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    ${pager}
    <p class="page-sub" style="margin-top:12px">共 ${words.length} 词${unfilled ? `，其中 ${unfilled} 词待你补填中文/词性` : ""}${awaitDetail ? `，${awaitDetail} 词已确认、等老师补详细` : ""}</p>`
      : empty("📖", "单词本还空着——做题时选中不认识的单词就能一键收藏")}`;

  $$("[data-pg]").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.disabled) return;
      VW_PAGE += b.dataset.pg === "next" ? 1 : -1;
      viewWords();
      window.scrollTo(0, 0);
    }));
  const sizeSel = $("#pg-size");
  if (sizeSel) sizeSel.addEventListener("change", () => {
    VW_SIZE = +sizeSel.value;
    VW_PAGE = 1;
    viewWords();
  });

  $$("[data-mean]").forEach((inp) => {
    inp.addEventListener("blur", async () => {
      try {
        await API.vocabPatch(+inp.dataset.mean, { meaning_cn: inp.value.trim() });
        refreshConfirm(+inp.dataset.mean);
        toast("中文意思已保存 ✓");
      } catch (e) { toast(`❌ ${e.message}`); }
    });
  });
  $$("[data-posbtn]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const pop = $(`[data-pospop="${btn.dataset.posbtn}"]`);
      const willShow = pop.hidden;
      $$("[data-pospop]").forEach((p) => (p.hidden = true));
      if (willShow) openPosPop(btn, pop);
    });
  });
  $$("[data-posc]").forEach((c) => {
    c.addEventListener("change", async () => {
      const id = +c.dataset.posc;
      const chosen = $$(`[data-posc="${id}"]:checked`).map((i) => i.value);
      const btn = $(`[data-posbtn="${id}"]`);
      try {
        await API.vocabPatch(id, { pos: chosen });
        btn.textContent = (chosen.length ? chosen.join(" / ") : "选择词性…") + " ▾";
        refreshConfirm(id);
        toast("词性已保存 ✓");
      } catch (e) { toast(`❌ ${e.message}`); }
    });
  });
  $$("[data-confirm]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await API.vocabPatch(+b.dataset.confirm, { confirmed: 1 });
        toast("已确认 ✓ 老师批改时会补词典词性与详细释义");
        viewWords();
      } catch (e) { toast(`❌ ${e.message}`); }
    }));
  $$("[data-vdel]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await API.vocabDelete(+b.dataset.vdel);
        toast("已删除 ✓");
        viewWords();
      } catch (e) { toast(`❌ ${e.message}`); }
    }));
}

/* ================================ 短语本页 ================================ */
async function viewPhrases() {
  const app = $("#app");
  let data;
  try { data = await API.phrases(); } catch (e) { return renderError(app, e); }
  const rows = data.phrases || [];
  const table = rows.length ? `
    <div class="v-wrap">
      <table class="v-table phrase-table">
        <thead><tr><th>短语</th><th>释义（老师教）</th><th>例句</th><th>来源</th><th>加入时间</th><th></th></tr></thead>
        <tbody>${rows.map((p) => `
          <tr>
            <td class="v-word">${esc(p.phrase)}</td>
            <td class="v-mean">${esc(p.meaning_cn) || "—"}</td>
            <td class="v-detail">${esc(p.example) || ""}${p.example_cn ? `<div style="color:var(--faint);font-size:12.5px">${esc(p.example_cn)}</div>` : ""}</td>
            <td class="v-date">${esc(p.source) || "—"}</td>
            <td class="v-date">${fmtDate(p.added_ts)}</td>
            <td class="v-acts"><button class="btn ghost small" data-pdel="${p.id}">删除</button></td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>` : empty("💬", "短语本还空着——词汇短语作业里的「短语讲解卡」点一下就能收藏");

  app.innerHTML = `
    <h1 class="page-title">短语本</h1>
    <p class="page-sub">短语只由 AI 老师教：词汇短语作业里会随机展示 5 个常用口语 / 作文表达（带释义和例句），点「加入短语本」即可收藏到这里反复学习。</p>
    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">➕ 手动添加</h3>
      <div class="field"><label>短语</label><input type="text" id="ph-phrase" placeholder="例如：take ... into account"></div>
      <div class="field-row">
        <div class="field" style="flex:1"><label>释义（中文）</label><input type="text" id="ph-meaning" placeholder="把…考虑在内"></div>
        <div class="field" style="flex:1"><label>例句（英文）</label><input type="text" id="ph-example" placeholder="We must take safety into account."></div>
      </div>
      <button class="btn primary" id="btn-add-phrase">加入短语本</button>
    </div>
    ${table}
    ${rows.length ? `<p class="page-sub" style="margin-top:12px">共 ${rows.length} 条短语</p>` : ""}`;

  $("#btn-add-phrase").addEventListener("click", async () => {
    const phrase = $("#ph-phrase").value.trim();
    if (!phrase) return toast("请先填写短语");
    try {
      const r = await API.phraseAdd({
        phrase, meaning_cn: $("#ph-meaning").value.trim(),
        example: $("#ph-example").value.trim(), example_cn: "",
        source: "手动添加",
      });
      toast(r.created ? "已加入短语本 ✓" : "该短语已存在");
      viewPhrases();
    } catch (e) { toast(`❌ ${e.message}`); }
  });
  $$("[data-pdel]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await API.phraseDelete(+b.dataset.pdel);
        toast("已删除 ✓");
        viewPhrases();
      } catch (e) { toast(`❌ ${e.message}`); }
    }));
}

document.addEventListener("click", (e) => {
  // 点词性按钮或勾选框：交给各自的处理器；点其他任何地方（含浮层空白处）都关闭
  if (e.target.closest("[data-posbtn]") || e.target.closest("[data-posc]")) return;
  $$("[data-pospop]").forEach((p) => (p.hidden = true));
});
document.addEventListener("scroll", () => {
  $$("[data-pospop]").forEach((p) => (p.hidden = true));
}, true);

function openPosPop(btn, pop) {
  /* 用 fixed 定位到按钮下方，避免被表格滚动容器裁剪；放不下就向上弹出。 */
  pop.hidden = false;
  const r = btn.getBoundingClientRect();
  const h = pop.offsetHeight;
  pop.style.position = "fixed";
  pop.style.left = `${Math.min(Math.max(8, r.left), window.innerWidth - pop.offsetWidth - 8)}px`;
  const openUp = r.bottom + 6 + h > window.innerHeight - 8;
  pop.style.top = `${openUp ? Math.max(8, r.top - h - 6) : r.bottom + 6}px`;
}

function refreshConfirm(id) {
  const btn = $(`[data-confirm="${id}"]`);
  if (!btn) return;
  const inp = $(`[data-mean="${id}"]`);
  const posCount = $$(`[data-posc="${id}"]:checked`).length;
  btn.disabled = !(inp && inp.value.trim()) || !posCount;
}

/* ================================ 我的页 ================================ */
const GOAL_DEFAULT = ["语法", "雅思词汇", "雅思写作", "阅读", "翻译"];
const TOPIC_DEFAULT = ["教育", "环保", "科技", "城市", "健康", "工作", "文化", "媒体"];
const QT_DEFAULT = ["单选", "填空", "语法填空", "TFNG", "写作", "翻译"];
const SPLIT_RE = /[,，、;；\s]+/;

function parseInput(v) {
  return String(v || "").split(SPLIT_RE).map((s) => s.trim()).filter(Boolean);
}

async function viewMe() {
  const app = $("#app");
  let state, kmap;
  try {
    [state, kmap] = await Promise.all([API.state(), API.knowledgeMap()]);
  } catch (e) { return renderError(app, e); }
  const p = state.profile || {};
  const goals = p.goals && p.goals.length ? p.goals : GOAL_DEFAULT;
  const topics = p.topics && p.topics.length ? p.topics : TOPIC_DEFAULT;
  const qts = p.question_types && p.question_types.length ? p.question_types : QT_DEFAULT;
  const notes = p.notes || "";
  const gReq = p.grammar_requirement || "";
  const vReq = p.vocabulary_requirement || "";
  const iReq = p.ielts_requirement || "";
  const p1Topics = p.ielts_part1_topics || [];
  const p2Topics = p.ielts_part2_topics || [];

  const field = (id, label, val, ph) => `
    <div class="field"><label>${label}</label>
      <input type="text" id="${id}" value="${esc(Array.isArray(val) ? val.join("，") : val)}" placeholder="${esc(ph)}"></div>`;

  const summ = kmap.summary || {};
  const mapHTML = (kmap.stages || []).map((st) => `
    <div class="map-stage">
      <div class="map-stage-head">第${st.stage}阶段 · ${esc(st.stage_name)}</div>
      <div class="map-grid">
        ${st.points.map((pt) => {
          const barCls = pt.counted
            ? (pt.status === "mastered" ? "ok" : pt.status === "weak" ? "bad" : "warn")
            : "";
          return `
          <div class="map-point ${pt.counted ? pt.status : ""}">
            <div class="map-name">${esc(pt.name)}</div>
            <div class="map-score">${pt.score}<span>分</span></div>
            <div class="bar ${barCls}"><i style="width:${pt.counted ? pt.score : 0}%"></i></div>
            ${pt.attempts
              ? `<div class="map-meta">${pt.attempts} 次作答${pt.counted
                  ? (pt.status === "mastered" ? " · 已掌握 ✓" : pt.status === "weak" ? " · 薄弱 ⚠" : "")
                  : " · 计分中（超过 5 次才计分）"}</div>`
              : '<div class="map-meta">未练过</div>'}
          </div>`;
        }).join("")}
      </div>
    </div>`).join("");

  const recentHTML = (state.recent_graded || []).map((s) => {
    const pct = s.max_score ? Math.round((s.total_score / s.max_score) * 100) : 0;
    return `<div class="recent-row"><span class="recent-title">${esc(s.title)}</span>
      <span class="recent-score">${s.total_score}/${s.max_score}</span>
      <span class="status-tag ${pct >= 85 ? "ok" : pct < 60 ? "bad" : "warn"}">${pct}%</span>
      <span class="recent-date">${fmtDate(s.submitted_at)}</span></div>`;
  }).join("") || '<div style="font-size:13px;color:var(--faint)">还没有已批改的语法作业</div>';

  app.innerHTML = `
    <h1 class="page-title">我的</h1>
    <p class="page-sub">用输入框自由填写（逗号分隔即可，默认已包含常用选项）；你的设置会直接告诉 AI 老师出题方向、话题和题型需求，老师仍会根据你的错题与弱点动态调整策略。</p>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">🎯 学习目标与题目需求</h3>
      ${field("pf-goals", "学习目标（逗号分隔）", goals, "例如：语法，雅思词汇，翻译")}
      ${field("pf-topics", "话题偏好（雅思话题）", topics, "例如：教育，环保，科技")}
      ${field("pf-qts", "题型需求（逗号分隔）", qts, "例如：单选，填空，翻译")}
      <div class="field"><label>给老师的备注（自由填写）</label>
        <textarea id="profile-notes" rows="3" placeholder="例如：我希望多练从句；作文请给我模板；词汇想练同义替换……">${esc(notes)}</textarea></div>
    </div>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">📝 各作业类型的要求（一句话，出题时老师按此定风格与目标）</h3>
      <div class="field"><label>语法作业要求</label>
        <textarea id="pf-greq" rows="2" placeholder="例如：按知识图谱反复攻克语法短板，翻译中发现语法问题并纠正，错题揪着不放直到掌握。">${esc(gReq)}</textarea></div>
      <div class="field"><label>词汇短语作业要求</label>
        <textarea id="pf-vreq" rows="2" placeholder="例如：雅思答案词+单词本词汇随机汉英互译/拼写/词性，短语由老师讲解展示。">${esc(vReq)}</textarea></div>
      <div class="field"><label>雅思专项训练要求</label>
        <textarea id="pf-ireq" rows="2" placeholder="例如：贴近剑桥雅思真题：阅读节选小题、题干翻译、作文长句中译英、口语随机话题。">${esc(iReq)}</textarea></div>
    </div>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">🎤 口语当季话题（Part 1 / Part 2）</h3>
      <p class="page-sub" style="font-size:13px;margin-bottom:10px">老师出随机口语话题时<strong>优先从当季话题里选</strong>，也会少量随机追问或在同一话题下多问几题；Part 3 由老师自行出题（口语只出题、不要求作答、不批改）。</p>
      ${field("pf-p1", "Part 1 当季话题（逗号分隔）", p1Topics, "例如：工作或学习，家乡，天气，空闲时间")}
      ${field("pf-p2", "Part 2 当季话题（逗号分隔）", p2Topics, "例如：描述一个你钦佩的人，一次难忘的旅行，一个安静的地方")}
    </div>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">📊 语法知识图谱</h3>
      <div class="map-summary">
        <span class="map-grade">${esc(summ.grade || "暂无数据")}</span>
        <span class="map-stat">已学 ${summ.attempted}/${summ.total} · 已掌握 ${summ.mastered} · 薄弱 ${summ.weak}${summ.counting ? ` · 计分中 ${summ.counting}` : ""} · 平均 ${summ.avg} 分</span>
      </div>
      <details class="map-fold">
        <summary>展开 / 收起图谱（只统计语法作业 · 作答超过 5 次才开始计分）</summary>
        ${mapHTML || empty("🧭", "图谱还没导入（老师导入后显示）")}
      </details>
    </div>

    <div class="card">
      <h3 class="card-h">📈 近期语法作业正确率（只统计语法作业）</h3>
      ${recentHTML}
      <div style="text-align:right;margin-top:14px">
        <button class="btn primary" id="btn-save-profile">保存全部设置</button>
      </div>
    </div>`;

  $("#btn-save-profile").addEventListener("click", async () => {
    try {
      await API.saveProfile({
        goals: parseInput($("#pf-goals").value),
        topics: parseInput($("#pf-topics").value),
        question_types: parseInput($("#pf-qts").value),
        notes: $("#profile-notes").value.trim(),
        grammar_requirement: $("#pf-greq").value.trim(),
        vocabulary_requirement: $("#pf-vreq").value.trim(),
        ielts_requirement: $("#pf-ireq").value.trim(),
        ielts_part1_topics: parseInput($("#pf-p1").value),
        ielts_part2_topics: parseInput($("#pf-p2").value),
      });
      toast("已保存 ✓ 老师出题时会读取这些设置");
    } catch (e) { toast(`❌ ${e.message}`); }
  });
}

/* ================================ 设置页 ================================ */
const RULE_DEFAULTS = {
  mastery_threshold: 85, mastery_min_attempts: 5,
  verify_min_questions: 3, verify_max_questions: 5,
  weekly_interval_days: 7, diag_max_questions: 15,
  question_priority: "student_request,open_diag,kmap_next,weekly_wrong,weakpoints,writing_curriculum,vocab_dictation",
};

async function viewSettings() {
  const app = $("#app");
  let cfg;
  try { cfg = await API.settings(); } catch (e) { return renderError(app, e); }
  const saved = cfg.config || {};
  const rules = Object.assign({}, RULE_DEFAULTS, saved.rules || {});
  app.innerHTML = `
    <h1 class="page-title">设置</h1>
    <p class="page-sub">修改后需重启服务生效。数据库路径对网页和 AI 老师同时生效（读同一份 config.json）。</p>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">🎨 主题外观</h3>
      <p class="page-sub" style="margin-bottom:12px">切换亮色 / 暗色主题：立即生效并自动保存在本浏览器（无需重启服务，只影响你的浏览器显示）。</p>
      <div class="theme-row">
        <button class="btn ghost theme-btn" data-theme="light">☀️ 亮色背景</button>
        <button class="btn ghost theme-btn" data-theme="dark">🌙 黑色背景</button>
      </div>
    </div>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">⚙️ 服务配置</h3>
      <div class="field"><label>数据库文件路径</label>
        <input type="text" id="set-db" value="${esc(saved.db_path || cfg.db_path)}" placeholder="默认 data/homework.db"></div>
      <div class="field-row">
        <div class="field" style="flex:1"><label>监听地址</label>
          <input type="text" id="set-host" value="${esc(saved.host || cfg.host)}" placeholder="127.0.0.1"></div>
        <div class="field" style="flex:0 0 140px"><label>端口</label>
          <input type="number" id="set-port" value="${esc(saved.port || cfg.port)}" placeholder="8877"></div>
      </div>
      <div class="field"><label>AI 服务访问令牌（可选，设置后 /api/agent/* 需带 Authorization: Bearer &lt;令牌&gt;）</label>
        <input type="text" id="set-token" value="${esc(saved.api_token || "")}" placeholder="留空 = 仅本机可访问"></div>
      <p class="page-sub">当前运行：${esc(cfg.host)}:${esc(cfg.port)} · 数据库 ${esc(cfg.db_path)}</p>
      <div class="btn-row" style="justify-content:flex-start">
        <button class="btn primary" id="btn-save-set">保存配置</button>
        <button class="btn ghost" id="btn-restart">重启服务</button>
      </div>
    </div>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">🎯 题目目标（教学规则）</h3>
      <p class="page-sub">AI 老师出题前读取这些规则决定方向与题量。修改后立即生效，无需重启。学生画像（目标/话题/题型）在「我的」页修改。</p>
      <div class="field-row">
        <div class="field"><label>掌握标准（正确率 %）</label>
          <input type="number" id="set-mastery" value="${esc(rules.mastery_threshold)}" min="50" max="100"></div>
        <div class="field"><label>计分最少作答次数</label>
          <input type="number" id="set-attempts" value="${esc(rules.mastery_min_attempts)}" min="1" max="20"></div>
        <div class="field"><label>验证卷最少题数</label>
          <input type="number" id="set-vmin" value="${esc(rules.verify_min_questions)}" min="1" max="10"></div>
        <div class="field"><label>验证卷最多题数</label>
          <input type="number" id="set-vmax" value="${esc(rules.verify_max_questions)}" min="1" max="10"></div>
      </div>
      <div class="field-row">
        <div class="field"><label>周回顾间隔（天）</label>
          <input type="number" id="set-weekly" value="${esc(rules.weekly_interval_days)}" min="1" max="60"></div>
        <div class="field"><label>诊断卷题数上限</label>
          <input type="number" id="set-diag" value="${esc(rules.diag_max_questions)}" min="5" max="30"></div>
      </div>
      <div class="field"><label>出题优先级（逗号分隔）</label>
        <input type="text" id="set-priority" value="${esc(rules.question_priority || "")}"></div>
      <div class="btn-row" style="justify-content:flex-start">
        <button class="btn primary" id="btn-save-rules">保存题目目标</button>
      </div>
    </div>

    <div class="card">
      <h3 class="card-h">🤖 给不同 AI 老师导入「老师技能」</h3>
      <div class="agent-guide">
        <div class="agent-row"><b>Hermes Agent / Claude Code / Codex 等本地 agent</b>
          <code>cp skills/homework-lab/SKILL.md ~/.hermes/skills/education/homework-lab/</code>
          能跑命令的 agent 直接执行 <code>python3 agent/cli.py &lt;命令&gt;</code>；触发词：出题吧 / 写好了 / 交了。</div>
        <div class="agent-row"><b>在线 AI 服务（ChatGPT 自定义 GPT / 豆包 / Kimi / Dify / n8n）</b>
          把 <code>skills/homework-lab/SKILL.md</code> 导入该服务（自定义指令/知识库），它通过
          <code>http://127.0.0.1:${esc(cfg.port)}/api/agent/*</code> 调用本服务读写数据库（出题/批改/单词本/题目目标）。
          完整协议见 <code>docs/HTTP_API.md</code>。AI 服务不在本机时：监听地址改 0.0.0.0 + 设置令牌，或 SSH 隧道。</div>
        <div class="agent-row"><b>Claude Code</b>
          在项目目录运行 <code>claude</code>，根目录 AGENTS.md 自动加载，零配置。</div>
        <div class="agent-row"><b>OpenAI Codex / OpenCode</b>
          在项目目录运行 <code>codex</code> 或 <code>opencode</code>，AGENTS.md 自动加载。</div>
        <div class="agent-row"><b>其他 agent / 自研</b>
          把 <code>AGENTS.md</code> + <code>docs/AGENT_PROTOCOL.md</code> + <code>docs/HTTP_API.md</code> 全文放进 system prompt，赋予 shell 或 HTTP 能力即可。</div>
      </div>
    </div>`;

  $("#btn-save-set").addEventListener("click", async () => {
    try {
      const r = await API.saveSettings({
        db_path: $("#set-db").value.trim(),
        host: $("#set-host").value.trim(),
        port: $("#set-port").value.trim(),
        api_token: $("#set-token").value.trim(),
      });
      toast(r.message || "已保存");
      if (r.restart_required) setTimeout(() => location.reload(), 1500);
    } catch (e) { toast(`❌ ${e.message}`); }
  });
  $("#btn-save-rules").addEventListener("click", async () => {
    try {
      const r = await API.saveSettings({
        rules: {
          mastery_threshold: +$("#set-mastery").value || 85,
          mastery_min_attempts: +$("#set-attempts").value || 5,
          verify_min_questions: +$("#set-vmin").value || 3,
          verify_max_questions: +$("#set-vmax").value || 5,
          weekly_interval_days: +$("#set-weekly").value || 7,
          diag_max_questions: +$("#set-diag").value || 15,
          question_priority: $("#set-priority").value.trim(),
        },
      });
      toast(r.message || "已保存 ✓");
    } catch (e) { toast(`❌ ${e.message}`); }
  });
  $("#btn-restart").addEventListener("click", () => {
    showModal(`
      <h3>重启服务？</h3>
      <p>服务约 1 秒后自动重启并应用新配置，页面稍后自动刷新，学习数据不受影响。</p>
      <div class="btn-row">
        <button class="btn ghost" data-act="cancel">取消</button>
        <button class="btn primary" data-act="confirm">确认重启</button>
      </div>`, async (act) => {
      if (act !== "confirm") return;
      try {
        await API.restart();
        toast("正在重启…");
        setTimeout(() => { location.reload(); }, 2500);
      } catch (e) { toast(`❌ ${e.message}`); }
    });
  });
  applyTheme(currentTheme());
  $$(".theme-btn").forEach((b) =>
    b.addEventListener("click", () => {
      applyTheme(b.dataset.theme);
      toast(b.dataset.theme === "dark" ? "已切换暗色主题 🌙" : "已切换亮色主题 ☀️");
    }));
}

/* ================================ 首次初始化向导 ================================ */
function splitList(v) {
  return String(v || "").split(/[,，]/).map((s) => s.trim()).filter(Boolean);
}
function joinList(arr) {
  return (arr || []).join("，");
}

async function boot() {
  applyTheme(currentTheme()); // 主题在路由前应用，避免闪白
  let status;
  try {
    status = await API.setupStatus();
  } catch (e) {
    return renderError($("#app"), e);
  }
  if (status && !status.initialized) {
    renderSetup(status);
    return;
  }
  route();
}

function renderSetup(status) {
  const app = $("#app");
  const cfg = status.config || {};
  const d = status.defaults || {};
  const rules = Object.assign({}, d.rules, cfg.rules || {});
  const profile = Object.assign({}, d.profile, cfg.profile || {});
  const dbPreset = [
    { label: "默认（项目内）", path: d.db_path },
    { label: "文稿目录", path: "~/Documents/homework-lab-data/homework.db" },
  ].map((p) => `<button type="button" class="btn ghost mini" data-db="${esc(p.path)}">${esc(p.label)}</button>`).join("");

  app.innerHTML = `
    <div class="setup-wrap">
      <h1 class="page-title">🎓 Homework Lab · 本地初始化</h1>
      <p class="page-sub">首次使用需要完成三步配置。所有设置都有默认值，之后随时可在「设置」页修改。</p>

      <div class="card" style="margin-bottom:18px">
        <h3 class="card-h">📁 1. 数据库文件位置</h3>
        <p class="page-sub">学习数据（试卷提交、错题、单词本）都存在这一个 SQLite 文件里。网页、AI 老师、命令行读取的是<strong>同一份 config.json</strong>，路径天然一致。输入相对路径会自动转为项目下的绝对路径。</p>
        <div class="field"><label>数据库文件路径</label>
          <input type="text" id="wz-db" value="${esc(cfg.db_path || d.db_path)}" placeholder="${esc(d.db_path)}">
          <div class="btn-row" style="justify-content:flex-start">${dbPreset}</div>
        </div>
        <p class="page-sub">${status.db_exists ? "⚠️ 该位置已存在数据库文件 → 部署时直接使用，不会覆盖任何数据。" : "🆕 该位置还没有数据库 → 部署时自动创建目录和全部数据表。"}</p>
      </div>

      <div class="card" style="margin-bottom:18px">
        <h3 class="card-h">🌐 2. 端口设置</h3>
        <div class="field" style="flex:0 0 140px"><label>网页端口</label>
          <input type="number" id="wz-port" value="${esc(cfg.port || d.port || 8877)}" min="1" max="65535" placeholder="8877">
        </div>
        <p class="page-sub">默认 8877。修改后服务会自动重启到新端口，页面自动跳转。</p>
      </div>

      <div class="card" style="margin-bottom:18px">
        <h3 class="card-h">🎯 3. 题目目标</h3>
        <p class="page-sub">AI 老师出题前会读取这些目标来决定方向与题量，均可后期修改。</p>
        <div class="field-row">
          <div class="field"><label>掌握标准（正确率 %）</label>
            <input type="number" id="wz-mastery" value="${esc(rules.mastery_threshold)}" min="50" max="100"></div>
          <div class="field"><label>计分最少作答次数</label>
            <input type="number" id="wz-attempts" value="${esc(rules.mastery_min_attempts)}" min="1" max="20"></div>
        </div>
        <div class="field-row">
          <div class="field"><label>验证卷最少题数</label>
            <input type="number" id="wz-vmin" value="${esc(rules.verify_min_questions)}" min="1" max="10"></div>
          <div class="field"><label>验证卷最多题数</label>
            <input type="number" id="wz-vmax" value="${esc(rules.verify_max_questions)}" min="1" max="10"></div>
          <div class="field"><label>周回顾间隔（天）</label>
            <input type="number" id="wz-weekly" value="${esc(rules.weekly_interval_days)}" min="1" max="60"></div>
          <div class="field"><label>诊断卷题数上限</label>
            <input type="number" id="wz-diag" value="${esc(rules.diag_max_questions)}" min="5" max="30"></div>
        </div>
        <div class="field"><label>出题优先级（逗号分隔，依次生效）</label>
          <input type="text" id="wz-priority" value="${esc(rules.question_priority || "")}">
          <p class="page-sub">选项：student_request（学生指定方向）/ open_diag（未解决诊断）/ kmap_next（图谱下一未掌握点）/ weekly_wrong（周回顾错题）/ weakpoints（薄弱点）/ writing_curriculum（写作路线）/ vocab_dictation（默写抽查）</p>
        </div>
        <div class="field"><label>学习目标（逗号分隔）</label>
          <input type="text" id="wz-goals" value="${esc(joinList(profile.goals))}" placeholder="彻底解决英语语法问题，雅思词汇短语积累"></div>
        <div class="field-row">
          <div class="field"><label>话题（逗号分隔）</label>
            <input type="text" id="wz-topics" value="${esc(joinList(profile.topics))}" placeholder="教育，环保，科技，城市，健康，工作"></div>
          <div class="field"><label>题型偏好（逗号分隔，留空=不限）</label>
            <input type="text" id="wz-qtypes" value="${esc(joinList(profile.question_types))}" placeholder="choice，fill，writing…"></div>
        </div>
        <div class="field"><label>备注</label>
          <input type="text" id="wz-notes" value="${esc(profile.notes || "")}" placeholder="给 AI 老师的补充说明（可选）"></div>
      </div>

      <div class="card" style="margin-bottom:18px">
        <h3 class="card-h">🤖 4. AI 老师接入（可选）</h3>
        <p class="page-sub">默认只允许本机访问。如果要在局域网内让 AI 服务（ChatGPT 自定义 GPT / Dify / n8n 等）直接调用本服务，可以设置一个访问令牌（留空则不校验）。</p>
        <div class="field"><label>AI 服务访问令牌（可选）</label>
          <input type="text" id="wz-token" placeholder="留空 = 仅本机可访问"></div>
      </div>

      <div class="btn-row" style="justify-content:center;margin:26px 0">
        <button class="btn primary big" id="btn-deploy">🚀 部署并开始使用</button>
      </div>
      <p class="page-sub" style="text-align:center" id="wz-msg"></p>
    </div>`;

  $$(".btn[data-db]").forEach((b) => b.addEventListener("click", () => {
    $("#wz-db").value = b.dataset.db;
  }));

  $("#btn-deploy").addEventListener("click", async () => {
    const btn = $("#btn-deploy");
    btn.disabled = true;
    btn.textContent = "部署中…";
    try {
      const r = await API.setup({
        db_path: $("#wz-db").value.trim(),
        port: $("#wz-port").value.trim(),
        api_token: $("#wz-token").value.trim(),
        rules: {
          mastery_threshold: +$("#wz-mastery").value || 85,
          mastery_min_attempts: +$("#wz-attempts").value || 5,
          verify_min_questions: +$("#wz-vmin").value || 3,
          verify_max_questions: +$("#wz-vmax").value || 5,
          weekly_interval_days: +$("#wz-weekly").value || 7,
          diag_max_questions: +$("#wz-diag").value || 15,
          question_priority: $("#wz-priority").value.trim(),
        },
        profile: {
          goals: splitList($("#wz-goals").value),
          topics: splitList($("#wz-topics").value),
          question_types: splitList($("#wz-qtypes").value),
          notes: $("#wz-notes").value.trim(),
        },
      });
      $("#wz-msg").textContent = "✅ " + r.message + `（数据库：${r.db_path}）`;
      if (r.restart_required) {
        $("#wz-msg").textContent += " 正在重启，请稍候…";
        setTimeout(() => { location.href = `http://${r.host}:${r.port}/`; }, 2500);
      } else {
        setTimeout(() => location.reload(), 1200);
      }
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "🚀 部署并开始使用";
      $("#wz-msg").textContent = "❌ " + e.message;
    }
  });
}

boot();
