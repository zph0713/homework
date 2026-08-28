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
  deleteHomework: (id) => API._req("DELETE", `/api/homeworks/${id}`),
  profile: () => API._get("/api/profile"),
  saveProfile: (p) => API._post("/api/profile", p),
  knowledgeMap: () => API._get("/api/knowledge-map"),
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

const SKILL = { grammar: "语法", vocabulary: "词汇", reading: "阅读", writing: "写作", listening: "听力", mixed: "综合" };
const TYPE = { choice: "单选", fill: "填空", cloze: "语法填空", tfng: "判断 TFNG", writing: "写作", translate: "翻译" };
const SUB_STATUS = { pending: "已交卷 · 待批改", partial: "已交卷 · 批改中", graded: "已批改" };

function fmtDate(s) {
  return (s || "").slice(5, 16);
}
function fmtAnswer(a) {
  if (a == null) return "（未作答）";
  if (typeof a === "object") return JSON.stringify(a);
  return String(a);
}

/* ================================ 路由 ================================ */
function route() {
  const hash = location.hash || "#/";
  const app = $("#app");
  const navName = hash.slice(2).split("/")[0] || "home";
  $$("nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === navName));
  app.innerHTML = '<div class="loading">加载中…</div>';
  const mPaper = hash.match(/^#\/paper\/(\d+)/);
  const mResult = hash.match(/^#\/result\/(\d+)/);
  if (hash === "#/" || hash === "#") return viewHome();
  if (mPaper) return viewPaper(+mPaper[1]);
  if (mResult) return viewResult(+mResult[1]);
  if (hash === "#/review") return viewReview();
  if (hash === "#/kp") return viewKnowledge();
  if (hash === "#/words") return viewWords();
  if (hash === "#/me") return viewMe();
  if (hash === "#/settings") return viewSettings();
  app.innerHTML = '<div class="empty"><div class="big">🔍</div>页面不存在</div>';
}

window.addEventListener("hashchange", route);

/* ================================ 首页 ================================ */
async function viewHome() {
  const app = $("#app");
  let data;
  try { data = await API.state(); }
  catch (e) { return renderError(app, e); }
  const hws = data.homeworks || [];
  const kps = data.knowledge || [];
  const reqs = data.open_requests || [];

  const hwCards = hws.length ? hws.map(hwCard).join("") : empty("📭", "还没有作业，等老师发布吧");
  const kpBlock = kpBlockHTML(kps.slice(0, 8), "掌握度概览", "#/kp");

  app.innerHTML = `
    <div class="home-grid">
      <div>
        <h1 class="page-title">我的作业</h1>
        <p class="page-sub">做完点交卷，老师在后台批改；批改完成后点「查看结果」看讲解。</p>
        ${reqs.length ? `<div class="waiting">⏳ 你已申请重练：${reqs.map((r) => esc(r.knowledge_point)).join("、")}，下次作业会安排</div>` : ""}
        <div class="hw-list">${hwCards}</div>
      </div>
      <aside class="kp-side">
        ${kpBlock}
        <div class="kp-card">
          <h3>学习循环</h3>
          <div style="font-size:13.5px;color:var(--muted);line-height:2">
            ① 做作业 → 交卷<br>② 老师批改 + 讲解<br>③ 针对薄弱点再出题验证<br>④ 每周错题重练<br>⑤ 全对 = 真正掌握 ✓
          </div>
        </div>
      </aside>
    </div>`;
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
          viewHome();
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
  if (!s) {
    statusHTML = '<span class="hw-status">📝 未作答</span>';
    actions = `<a class="btn primary" href="#/paper/${h.id}">开始答题</a>`;
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
    <div class="hw-card">
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
  const passages = new Map(paper.passages.map((p) => [p.id, p]));
  const qs = paper.questions;

  const head = `
    <div class="paper-head">
      <h1>${esc(h.title)}</h1>
      <div class="hw-meta">
        <span class="badge skill">${SKILL[h.skill] || h.skill}</span>
        ${h.topic ? `<span class="badge">${esc(h.topic)}</span>` : ""}
        <span class="badge">${qs.length} 题</span>
      </div>
      ${h.goal ? `<div class="goal">🎯 ${esc(h.goal)}</div>` : ""}
    </div>`;
  const body = qs.map((q, i) => renderQuestion(q, i, passages)).join("");
  app.innerHTML = `${head}${body}${submitBarHTML()}`;
  bindPaperEvents(qs, id);
}

function renderQuestion(q, i, passages) {
  const pi = q.passage_id ? passages.get(q.passage_id) : null;
  const passageHTML = pi
    ? `<div class="q-passage"><div class="p-title">📄 ${esc(pi.title || "阅读材料")}</div><p>${esc(pi.body)}</p></div>`
    : "";
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
  }
  return `
    <div class="q-card" id="qc-${q.id}">
      <div class="q-top"><span class="q-num">${i + 1}.</span>
        <span class="q-type">${TYPE[q.type] || q.type}</span>
        ${q.knowledge_point ? `<span class="badge">${esc(q.knowledge_point)}</span>` : ""}
        ${q.score !== 1 ? `<span class="badge">${q.score} 分</span>` : ""}
      </div>
      ${passageHTML}
      ${main}
    </div>`;
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
  const progress = () => {
    const answers = collectAnswers(qs);
    $("#prog-done").textContent = Object.keys(answers).length;
    $("#prog-total").textContent = qs.length;
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
    const unanswered = qs.filter((q) => !answers[q.id]).map((q, i) => i + 1);
    const doSubmit = async () => {
      const btn = $("#btn-submit");
      btn.disabled = true;
      btn.textContent = "提交中…";
      try {
        const r = await API.submit(hwId, answers);
        const app = $("#app");
        app.innerHTML = `
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

/* ================================ 结果页 ================================ */
async function viewResult(sid) {
  const app = $("#app");
  let d;
  try { d = await API.result(sid); }
  catch (e) { return renderError(app, e); }
  const waiting = d.status !== "graded"
    ? `<div class="waiting">⏳ 本卷还有题目在批改中（当前状态：${SUB_STATUS[d.status] || d.status}）。批改完成后刷新页面即可看到完整结果与讲解。</div>`
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
  app.innerHTML = `${hero}${waiting}${items}<div style="text-align:center;margin-top:18px">
    <a class="btn ghost" href="#/">← 返回首页</a></div>`;
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
  app.innerHTML = `<h1 class="page-title">错题本</h1>
    <p class="page-sub">每次批改后的错题都归档在这里。点「申请重练」会排进下一次针对性练习。</p>
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
    const wrong = wrongs[k.name] || [];
    return `
      <div class="kp-card">
        <div class="kp-row">
          <div class="kp-head">
            <span class="kp-name">${esc(k.name)}</span>
            <span class="kp-pct">${pct}% · ${k.attempts} 次作答 · 对 ${k.correct}</span>
          </div>
          <div class="bar ${pct >= 85 && k.attempts >= 3 ? "ok" : pct < 50 ? "bad" : "warn"}"><i style="width:${pct}%"></i></div>
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
    <p class="page-sub">掌握度 = 累计答对 ÷ 累计作答。满 3 次且 ≥85% 才算「已掌握」。</p>
    <div class="kp-grid">${cards}</div>`;
}

function statusTag(k) {
  if (k.attempts >= 3 && k.mastery >= 0.85) return '<span class="status-tag ok">已掌握 ✓</span>';
  if (k.attempts === 0) return '<span class="status-tag new">未练过</span>';
  if (k.mastery < 0.5) return '<span class="status-tag bad">薄弱 · 需加强</span>';
  return '<span class="status-tag warn">学习中</span>';
}

function kpBlockHTML(kps, title, link) {
  const rows = kps.length ? kps.map((k) => {
    const pct = Math.round((k.mastery || 0) * 100);
    return `
      <div class="kp-row">
        <div class="kp-head"><span class="kp-name">${esc(k.name)}</span><span class="kp-pct">${pct}%</span></div>
        <div class="bar ${pct >= 85 && k.attempts >= 3 ? "ok" : pct < 50 ? "bad" : "warn"}"><i style="width:${pct}%"></i></div>
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
async function viewWords() {
  const app = $("#app");
  let data;
  try { data = await API.vocabulary(); } catch (e) { return renderError(app, e); }
  const words = data.words || [];
  const rows = words.map((w) => `
    <tr>
      <td class="v-word">${esc(w.word)}</td>
      <td class="v-pos">${w.pos ? esc(w.pos) : '<span class="v-empty">待老师补</span>'}</td>
      <td class="v-mean">${w.meaning_cn ? esc(w.meaning_cn) : '<span class="v-empty">待老师补</span>'}</td>
      <td class="v-note"><input type="text" data-note="${w.id}" value="${esc(w.note)}" placeholder="写点备注…"></td>
      <td class="v-date">${fmtDate(w.added_ts)}</td>
      <td><button class="btn ghost small" data-vdel="${w.id}">删除</button></td>
    </tr>`).join("");
  app.innerHTML = `
    <h1 class="page-title">单词本</h1>
    <p class="page-sub">做题时选中不认识的单词即可一键收藏；中文和词性会在老师批改作业时自动补上。</p>
    ${words.length ? `
    <div class="card" style="padding:0;overflow-x:auto">
      <table class="v-table">
        <thead><tr><th>单词</th><th>词性</th><th>中文</th><th>我的备注</th><th>加入时间</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="page-sub" style="margin-top:12px">共 ${words.length} 词${data.unfilled ? `，其中 ${data.unfilled} 词待老师补充释义` : ""}，以后可据词本定制默写</p>`
      : empty("📖", "单词本还空着——做题时选中不认识的单词就能一键收藏")}`;
  $$("[data-note]").forEach((inp) => {
    inp.addEventListener("blur", async () => {
      try {
        await API.vocabPatch(+inp.dataset.note, { note: inp.value.trim() });
        toast("备注已保存 ✓");
      } catch (e) { toast(`❌ ${e.message}`); }
    });
  });
  $$("[data-vdel]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await API.vocabDelete(+b.dataset.vdel);
        toast("已删除 ✓");
        viewWords();
      } catch (e) { toast(`❌ ${e.message}`); }
    }));
}

/* ================================ 我的页 ================================ */
const GOAL_OPTS = ["语法", "雅思词汇", "雅思写作", "阅读", "翻译"];
const TOPIC_OPTS = ["教育", "环保", "科技", "城市", "健康", "工作", "文化", "媒体"];
const QT_OPTS = ["单选", "填空", "语法填空", "TFNG", "写作", "翻译"];

async function viewMe() {
  const app = $("#app");
  let state, kmap;
  try {
    [state, kmap] = await Promise.all([API.state(), API.knowledgeMap()]);
  } catch (e) { return renderError(app, e); }
  const p = state.profile || {};
  const goals = p.goals || [], topics = p.topics || [], qts = p.question_types || [], notes = p.notes || "";

  const chips = (name, opts, chosen) => `
    <div class="chips" data-group="${name}">
      ${opts.map((o) => `<label class="chip ${chosen.includes(o) ? "on" : ""}">
        <input type="checkbox" value="${esc(o)}" ${chosen.includes(o) ? "checked" : ""}>${esc(o)}</label>`).join("")}
    </div>`;

  const summ = kmap.summary || {};
  const mapHTML = (kmap.stages || []).map((st) => `
    <div class="map-stage">
      <div class="map-stage-head">第${st.stage}阶段 · ${esc(st.stage_name)}</div>
      <div class="map-grid">
        ${st.points.map((pt) => `
          <div class="map-point ${pt.status}">
            <div class="map-name">${esc(pt.name)}</div>
            <div class="map-score">${pt.score}<span>分</span></div>
            <div class="bar ${pt.score >= 85 && pt.attempts >= 3 ? "ok" : pt.score === 0 ? "" : pt.score < 50 ? "bad" : "warn"}">
              <i style="width:${pt.score}%"></i>
            </div>
            ${pt.attempts
              ? `<div class="map-meta">${pt.attempts} 次作答${pt.status === "mastered" ? " · 已掌握 ✓" : pt.status === "weak" ? " · 薄弱 ⚠" : ""}</div>`
              : '<div class="map-meta">未练过</div>'}
          </div>`).join("")}
      </div>
    </div>`).join("");

  const recentHTML = (state.recent_graded || []).map((s) => {
    const pct = s.max_score ? Math.round((s.total_score / s.max_score) * 100) : 0;
    return `<div class="recent-row"><span class="recent-title">${esc(s.title)}</span>
      <span class="recent-score">${s.total_score}/${s.max_score}</span>
      <span class="status-tag ${pct >= 85 ? "ok" : pct < 60 ? "bad" : "warn"}">${pct}%</span>
      <span class="recent-date">${fmtDate(s.submitted_at)}</span></div>`;
  }).join("") || '<div style="font-size:13px;color:var(--faint)">还没有已批改的作业</div>';

  app.innerHTML = `
    <h1 class="page-title">我的</h1>
    <p class="page-sub">你的设置会直接告诉 AI 老师出题方向、话题和题型需求；老师仍会根据你的错题与弱点动态调整策略。</p>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">🎯 学习目标与题目需求</h3>
      <div class="field"><label>学习目标（可多选）</label>${chips("goals", GOAL_OPTS, goals)}</div>
      <div class="field"><label>话题偏好（雅思话题）</label>${chips("topics", TOPIC_OPTS, topics)}</div>
      <div class="field"><label>题型需求</label>${chips("qts", QT_OPTS, qts)}</div>
      <div class="field"><label>给老师的备注（自由填写）</label>
        <textarea id="profile-notes" rows="3" placeholder="例如：我希望多练从句；作文请给我模板；词汇想练同义替换……">${esc(notes)}</textarea></div>
      <button class="btn primary" id="btn-save-profile">保存设置</button>
    </div>

    <div class="card" style="margin-bottom:18px">
      <h3 class="card-h">📊 语法知识图谱</h3>
      <div class="map-summary">
        <span class="map-grade">${esc(summ.grade || "暂无数据")}</span>
        <span class="map-stat">已学 ${summ.attempted}/${summ.total} · 已掌握 ${summ.mastered} · 薄弱 ${summ.weak} · 平均 ${summ.avg} 分</span>
      </div>
      ${mapHTML || empty("🧭", "图谱还没导入（老师导入后显示）")}
    </div>

    <div class="card">
      <h3 class="card-h">📈 近期作业正确率</h3>
      ${recentHTML}
    </div>`;

  $("#btn-save-profile").addEventListener("click", async () => {
    const collect = (group) => Array.from($$(`.chips[data-group="${group}"] input:checked`)).map((i) => i.value);
    try {
      await API.saveProfile({
        goals: collect("goals"),
        topics: collect("topics"),
        question_types: collect("qts"),
        notes: $("#profile-notes").value.trim(),
      });
      toast("已保存 ✓ 老师出题时会读取这些设置");
    } catch (e) { toast(`❌ ${e.message}`); }
  });
  $$(".chips input").forEach((inp) => inp.addEventListener("change", () =>
    inp.closest(".chip").classList.toggle("on", inp.checked)));
}

/* ================================ 设置页 ================================ */
async function viewSettings() {
  const app = $("#app");
  let cfg;
  try { cfg = await API.settings(); } catch (e) { return renderError(app, e); }
  const saved = cfg.config || {};
  app.innerHTML = `
    <h1 class="page-title">设置</h1>
    <p class="page-sub">修改后需重启服务生效。数据库路径对网页和 AI 老师同时生效（读同一份 config.json）。</p>

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
      <p class="page-sub">当前运行：${esc(cfg.host)}:${esc(cfg.port)} · 数据库 ${esc(cfg.db_path)}</p>
      <div class="btn-row" style="justify-content:flex-start">
        <button class="btn primary" id="btn-save-set">保存配置</button>
        <button class="btn ghost" id="btn-restart">重启服务</button>
      </div>
    </div>

    <div class="card">
      <h3 class="card-h">🤖 给不同 AI Agent 导入「老师技能」</h3>
      <div class="agent-guide">
        <div class="agent-row"><b>Hermes Agent</b>
          <code>cp skills/homework-lab/SKILL.md ~/.hermes/skills/education/homework-lab/</code>
          重启会话后生效。触发词：出题吧 / 写好了 / 交了。</div>
        <div class="agent-row"><b>Claude Code</b>
          在项目目录运行 <code>claude</code>，根目录 AGENTS.md 自动加载，零配置。</div>
        <div class="agent-row"><b>OpenAI Codex / OpenCode</b>
          在项目目录运行 <code>codex</code> 或 <code>opencode</code>，AGENTS.md 自动加载。</div>
        <div class="agent-row"><b>其他 agent / 自研</b>
          把 <code>AGENTS.md</code> + <code>docs/AGENT_PROTOCOL.md</code> 全文放进 system prompt，赋予 shell 权限即可。</div>
      </div>
    </div>`;

  $("#btn-save-set").addEventListener("click", async () => {
    try {
      await API.saveSettings({
        db_path: $("#set-db").value.trim(),
        host: $("#set-host").value.trim(),
        port: $("#set-port").value.trim(),
      });
      toast("已保存 ✓ 需重启服务生效");
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
}

route();
