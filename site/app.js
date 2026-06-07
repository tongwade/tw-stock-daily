"use strict";
const DATA = "data";
const cache = {}, pending = {};
let INDEX = null, curDate = null, curView = "market", curStock = null, wrChart = null;
let curWeek = null, curWeeklyStock = null;

const $ = s => document.querySelector(s);

// 以 <script> 載入資料（file:// 直接雙擊也能用，免伺服器）
window.__DATAREG = (key, data) => {
  cache[key] = data;
  if (pending[key]) { pending[key].forEach(fn => fn(data)); delete pending[key]; }
};
function loadData(key) {
  if (cache[key]) return Promise.resolve(cache[key]);
  return new Promise((resolve, reject) => {
    (pending[key] = pending[key] || []).push(resolve);
    const sc = document.createElement("script");
    // 日期清單 index 會隨每次更新而變，須避開瀏覽器/CDN 快取（max-age=600）才能即時反映新日期；
    // 各單日資料是固定的可正常快取。file:// 開啟時不加查詢字串（本機檔案帶 ?query 可能載不到）。
    const bust = (key === "index" && typeof location !== "undefined" && location.protocol !== "file:") ? `?t=${Date.now()}` : "";
    sc.src = `${DATA}/${key}.js${bust}`;
    sc.onerror = () => { delete pending[key]; reject(new Error("無法載入 " + key)); };
    document.head.appendChild(sc);
  });
}
const fmtInt = n => (n === null || n === undefined || n === "") ? "" : Number(n).toLocaleString("en-US", {maximumFractionDigits: 0});
const fmt1 = n => (n === null || n === undefined || n === "") ? "" : Number(n).toLocaleString("en-US", {maximumFractionDigits: 1});
const fmt2 = n => (n === null || n === undefined || n === "") ? "" : Number(n).toLocaleString("en-US", {maximumFractionDigits: 2});
const num = n => (typeof n === "number") ? n : (parseFloat(String(n).replace(/[,%]/g, "")) || 0);

async function init() {
  INDEX = await loadData("index");
  const sel = $("#dateSel");
  sel.innerHTML = INDEX.dates.map(d => `<option value="${d.date}">${d.label}</option>`).join("");
  curDate = INDEX.dates[0].date;
  sel.onchange = () => {
    curDate = sel.value;
    // 切換日期時保留已選個股；只有當新日期沒有這檔股票時才清空，省得每次都要重點
    const di = INDEX.dates.find(d => d.date === curDate);
    if (!(di && (di.stocks || []).some(s => s.code === curStock))) curStock = null;
    render();
  };
  document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    curView = t.dataset.view;
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    $(`#view-${curView}`).classList.add("active");
    render();
  });
  // 週報下拉選單
  const weekSel = $("#weekSel");
  if (weekSel) {
    if (INDEX.weekly_dates && INDEX.weekly_dates.length) {
      weekSel.innerHTML = INDEX.weekly_dates.map(w =>
        `<option value="${w.wkey}">${w.label}</option>`).join("");
      curWeek = INDEX.weekly_dates[0].wkey;
      weekSel.onchange = () => { curWeek = weekSel.value; curWeeklyStock = null; if (curView === "weekly") renderWeekly(); };
    } else {
      weekSel.innerHTML = '<option value="">（尚無週報資料）</option>';
    }
  }
  render();
}

function render() {
  if (curView === "market") renderMarket();
  else if (curView === "continuation") renderContinuation();
  else if (curView === "release") renderRelease();
  else if (curView === "disposed") renderDisposed();
  else if (curView === "winrate") renderWinrate();
  else if (curView === "stock") renderStock();
  else if (curView === "weekly") renderWeekly();
  // help：靜態內容，已在 index.html，無需渲染
}

/* Grid.js 共用工具 ----------------------------------------------------- */
// 切換日期後若對同一節點重複 render，Grid.js(Preact) 會沿用殘留虛擬 DOM，
// 導致新搜尋框事件接不上；故每次都換上全新容器節點再 render。
function gridInto(box, cols, rows, opts = {}) {
  const fresh = document.createElement("div");
  fresh.id = box.id;
  box.replaceWith(fresh);
  new gridjs.Grid({
    columns: cols, data: rows, sort: true,
    search: opts.search !== false,
    pagination: {limit: opts.limit || 25}, fixedHeader: true,
    language: {search: {placeholder: opts.placeholder || "搜尋代號 / 名稱…"},
      pagination: {previous: "上一頁", next: "下一頁", showing: "顯示", to: "至", of: "共", results: "筆"}},
  }).render(fresh);
}
const pctCell = c => { const v = num(c); return gridjs.html(`<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${fmt2(v)}%</span>`); };
const starCell = c => gridjs.html(`<span class="star">${c || ""}</span>`);

function dayInfo() { return INDEX.dates.find(d => d.date === curDate); }

/* ---------- 大盤放量訊號 ---------- */
async function renderMarket() {
  const box = $("#marketGrid");
  box.innerHTML = `<div class="loading">載入中…</div>`;
  let m;
  try { m = await loadData(`${curDate}/market`); }
  catch (e) { box.innerHTML = `<div class="loading">本日無大盤資料</div>`; $("#marketCards").innerHTML = ""; return; }
  const sig = m.signals || [];
  const s3 = sig.filter(r => (r["訊號強度"] || "").length >= 3).length;
  const up5 = sig.filter(r => num(r["漲跌幅%"]) >= 5).length;
  const mchg = sig.length ? sig[0]["大盤漲跌%"] : null;
  $("#marketCards").innerHTML = [
    ["放量檔數", fmtInt(sig.length)],
    ["★★★ 強烈", fmtInt(s3)],
    ["漲幅 ≥5%", fmtInt(up5)],
    ["大盤漲跌%", (mchg != null ? (num(mchg) >= 0 ? "+" : "") + fmt2(mchg) + "%" : "—")],
  ].map(c => `<div class="card"><div class="k">${c[0]}</div><div class="v">${c[1]}</div></div>`).join("");

  const cols = [
    {name: "代號", width: "78px"},
    {name: "名稱", width: "96px"},
    {name: "市場", width: "82px"},
    {name: "類型", width: "82px"},
    {name: "強度", width: "84px", formatter: c => gridjs.html(`<span class="star">${c || ""}</span>`)},
    {name: "當日量(張)", width: "110px", formatter: c => fmtInt(c)},
    {name: "漲跌幅%", width: "100px", formatter: c => { const v = num(c); return gridjs.html(`<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${fmt2(v)}%</span>`); }},
    {name: "收盤", width: "84px", formatter: c => fmt2(c)},
    {name: "量價關係", width: "124px"},
    {name: "×MA5", width: "86px", formatter: c => fmt1(c)},
    {name: "×MA20", width: "92px", formatter: c => fmt1(c)},
    {name: "訊號說明", width: "260px"},
  ];
  const rows = sig.map(r => [
    String(r["代號"] ?? ""), r["股票名稱"] ?? "", r["市場"] ?? "", r["訊號類型"] ?? "",
    r["訊號強度"] ?? "", num(r["當日量(張)"]), num(r["漲跌幅%"]), num(r["收盤價"]),
    r["量價關係"] ?? "", num(r["較MA5倍"]), num(r["較MA20倍"]), r["訊號說明"] ?? "",
  ]);
  // 用全新的容器節點重繪：Grid.js(Preact) 會沿用容器殘留的虛擬 DOM 樹，
  // 直接對同一節點重複 render 會讓新搜尋框的事件接不上（切換日期後搜尋失效）。
  const fresh = document.createElement("div");
  fresh.id = box.id;
  box.replaceWith(fresh);
  new gridjs.Grid({
    columns: cols, data: rows, search: true, sort: true,
    pagination: {limit: 25}, fixedHeader: true,
    language: {search: {placeholder: "搜尋代號 / 名稱…"}, pagination: {previous: "上一頁", next: "下一頁", showing: "顯示", to: "至", of: "共", results: "筆"}},
  }).render(fresh);
}

/* ---------- 量能延續追蹤 ---------- */
async function renderContinuation() {
  const box = $("#contGrid");
  box.innerHTML = `<div class="loading">載入中…</div>`;
  let m;
  try { m = await loadData(`${curDate}/market`); }
  catch (e) { box.innerHTML = `<div class="loading">本日無資料</div>`; $("#contCards").innerHTML = ""; return; }
  const rs = m.continuation || [];
  if (!rs.length) { box.innerHTML = `<div class="loading">本日無量能延續追蹤資料</div>`; $("#contCards").innerHTML = ""; return; }
  const strong = rs.filter(r => String(r["延續類型"] || "").includes("強力")).length;
  $("#contCards").innerHTML = [
    ["延續檔數", fmtInt(rs.length)],
    ["強力延續", fmtInt(strong)],
  ].map(c => `<div class="card"><div class="k">${c[0]}</div><div class="v">${c[1]}</div></div>`).join("");
  const cols = [
    {name: "代號", width: "76px"},
    {name: "名稱", width: "92px"},
    {name: "市場", width: "74px"},
    {name: "延續類型", width: "124px"},
    {name: "放量日期", width: "108px"},
    {name: "放量量(張)", width: "104px", formatter: c => fmtInt(c)},
    {name: "放量收盤", width: "92px", formatter: c => fmt2(c)},
    {name: "次日量(張)", width: "104px", formatter: c => fmtInt(c)},
    {name: "次日量/放量", width: "112px", formatter: c => fmt2(c)},
    {name: "次日收盤", width: "92px", formatter: c => fmt2(c)},
    {name: "次日漲跌幅%", width: "118px", formatter: pctCell},
    {name: "累計漲幅%", width: "108px", formatter: pctCell},
    {name: "原始星等", width: "92px", formatter: starCell},
  ];
  const rows = rs.map(r => [
    String(r["代號"] ?? ""), r["股票名稱"] ?? "", r["市場"] ?? "", r["延續類型"] ?? "",
    r["放量日期"] ?? "", num(r["放量量(張)"]), num(r["放量收盤"]), num(r["次日量(張)"]),
    num(r["次日量/放量"]), num(r["次日收盤"]), num(r["次日漲跌幅%"]), num(r["累計漲幅%"]), r["原始星等"] ?? "",
  ]);
  gridInto(box, cols, rows);
}

/* ---------- 出關股追蹤 ---------- */
async function renderRelease() {
  const box = $("#relGrid");
  box.innerHTML = `<div class="loading">載入中…</div>`;
  let m;
  try { m = await loadData(`${curDate}/market`); }
  catch (e) { box.innerHTML = `<div class="loading">本日無資料</div>`; return; }
  const rs = m.release || [];
  if (!rs.length) { box.innerHTML = `<div class="loading">本日無出關股追蹤資料</div>`; return; }
  const cols = [
    {name: "代號", width: "76px"},
    {name: "名稱", width: "100px"},
    {name: "市場", width: "74px"},
    {name: "出關類型", width: "120px"},
    {name: "處置天數", width: "92px", formatter: c => fmtInt(c)},
    {name: "處置前收盤", width: "100px", formatter: c => fmt2(c)},
    {name: "出關量(張)", width: "104px", formatter: c => fmtInt(c)},
    {name: "出關量/處置前", width: "120px", formatter: c => fmt2(c)},
    {name: "出關收盤", width: "92px", formatter: c => fmt2(c)},
    {name: "出關漲跌幅%", width: "118px", formatter: pctCell},
    {name: "較處置前變化%", width: "126px", formatter: pctCell},
    {name: "強度", width: "120px", formatter: starCell},
    {name: "期間漲跌幅%", width: "118px", formatter: pctCell},
    {name: "最大單日漲%", width: "118px", formatter: pctCell},
    {name: "最大單日跌%", width: "118px", formatter: pctCell},
    {name: "訊號說明", width: "300px"},
    {name: "特殊標記", width: "180px"},
    {name: "備註", width: "180px"},
  ];
  const rows = rs.map(r => [
    String(r["代號"] ?? ""), r["股票名稱"] ?? "", r["市場"] ?? "", r["出關類型"] ?? "",
    num(r["處置天數"]), num(r["處置前收盤"]), num(r["出關量(張)"]), num(r["出關量/處置前"]),
    num(r["出關收盤"]), num(r["出關漲跌幅%"]), num(r["較處置前價格變化%"]), r["訊號強度"] ?? "",
    num(r["期間漲跌幅%"]), num(r["最大單日漲%"]), num(r["最大單日跌%"]),
    r["訊號說明"] ?? "", r["特殊標記"] ?? "", r["備註"] ?? "",
  ]);
  gridInto(box, cols, rows, {limit: 20});
}

/* ---------- 處置股清單 ---------- */
async function renderDisposed() {
  const box = $("#dispGrid");
  box.innerHTML = `<div class="loading">載入中…</div>`;
  let m;
  try { m = await loadData(`${curDate}/market`); }
  catch (e) { box.innerHTML = `<div class="loading">本日無資料</div>`; return; }
  const rs = m.disposed || [];
  if (!rs.length) { box.innerHTML = `<div class="loading">本日無處置股清單資料</div>`; return; }
  const cols = [
    {name: "代號", width: "90px"},
    {name: "名稱", width: "140px"},
    {name: "市場", width: "90px"},
    {name: "處置起日", width: "130px"},
    {name: "處置迄日", width: "130px"},
    {name: "處置原因", width: "200px"},
  ];
  const rows = rs.map(r => [
    String(r["代號"] ?? ""), r["股票名稱"] ?? "", r["市場"] ?? "",
    r["處置起日"] ?? "", r["處置迄日"] ?? "", r["處置原因"] ?? "",
  ]);
  gridInto(box, cols, rows);
}

/* ---------- 勝率回測 ---------- */
async function renderWinrate() {
  const box = $("#wrTables");
  box.innerHTML = `<div class="loading">載入中…</div>`;
  let m;
  try { m = await loadData(`${curDate}/market`); }
  catch (e) { box.innerHTML = `<div class="loading">本日無資料</div>`; return; }
  const wr = m.winrate || [];
  // 圖表：星等分組的 D+5 / D+10 / D+15 勝率
  const star = wr.filter(r => r["分類"] === "星等");
  const labels = star.map(r => r["分組"]);
  const ds = [["D+5", "D+5_勝率%", "#4da3ff"], ["D+10", "D+10_勝率%", "#ffcb3d"], ["D+15", "D+15_勝率%", "#39c46e"]]
    .map(([lab, key, col]) => ({label: lab, data: star.map(r => num(r[key])), backgroundColor: col}));
  if (wrChart) wrChart.destroy();
  wrChart = new Chart($("#wrChart"), {
    type: "bar",
    data: {labels, datasets: ds},
    options: {responsive: true, plugins: {legend: {labels: {color: "#e6edf3"}}, title: {display: true, text: "各星等勝率 (%)", color: "#8b9bb0"}},
      scales: {x: {ticks: {color: "#e6edf3"}, grid: {color: "#2c3a4f"}}, y: {ticks: {color: "#8b9bb0"}, grid: {color: "#2c3a4f"}}}},
  });
  // 分組表格
  const groups = {};
  wr.forEach(r => { (groups[r["分類"]] ||= []).push(r); });
  let html = "";
  for (const [cat, recs] of Object.entries(groups)) {
    html += `<h3>${cat}</h3><table class="simple"><thead><tr>
      <th>分組</th><th>樣本數</th><th>D+5 勝率</th><th>D+5 均報酬</th><th>D+10 勝率</th><th>D+10 均報酬</th><th>D+15 勝率</th><th>D+15 均報酬</th>
      </tr></thead><tbody>`;
    recs.forEach(r => {
      const pct = (v, suf = "%") => v === null || v === undefined || v === "" ? "" : fmt1(v) + suf;
      const ret = v => { const n = num(v); return `<span class="${n >= 0 ? "up" : "down"}">${n >= 0 ? "+" : ""}${fmt2(n)}%</span>`; };
      html += `<tr><td>${r["分組"] ?? ""}</td><td>${fmtInt(r["樣本數"])}</td>
        <td>${pct(r["D+5_勝率%"])}</td><td>${ret(r["D+5_均報酬%"])}</td>
        <td>${pct(r["D+10_勝率%"])}</td><td>${ret(r["D+10_均報酬%"])}</td>
        <td>${pct(r["D+15_勝率%"])}</td><td>${ret(r["D+15_均報酬%"])}</td></tr>`;
    });
    html += `</tbody></table>`;
  }
  box.innerHTML = html || `<div class="loading">本日無勝率回測資料</div>`;
}

/* ---------- 個股分析 ---------- */
function renderStock() {
  const di = dayInfo();
  const list = $("#stockList");
  list.innerHTML = (di.stocks || []).map(s =>
    `<div class="stockchip${s.code === curStock ? " active" : ""}" data-code="${s.code}">${s.code} ${s.name || ""}</div>`).join("");
  list.querySelectorAll(".stockchip").forEach(c => c.onclick = () => { curStock = c.dataset.code; renderStock(); });
  if (!curStock) { $("#stockBody").innerHTML = `<div class="loading">請選擇上方個股</div>`; return; }
  loadStock(curStock);
}

async function loadStock(code) {
  const body = $("#stockBody");
  body.innerHTML = `<div class="loading">載入 ${code} …</div>`;
  let d;
  try { d = await loadData(`${curDate}/${code}`); }
  catch (e) { body.innerHTML = `<div class="loading">本日無 ${code} 資料</div>`; return; }
  let html = "";

  // 技術分析(K線)圖：本站 Excel 無逐日 OHLC，改連到 Yahoo 股市技術分析頁
  const sInfo = (dayInfo().stocks || []).find(s => s.code === code) || {};
  const yhSuffix = sInfo.mkt === "TWO" ? "TWO" : "TW";
  const yhUrl = `https://tw.stock.yahoo.com/quote/${code}.${yhSuffix}/technical-analysis`;
  html += `<div class="yahoo-link"><a href="${yhUrl}" target="_blank" rel="noopener noreferrer">` +
    `📈 在 Yahoo 股市看技術分析圖（K 線）→</a>` +
    `<span class="yahoo-note">含日/週/月 K 線、均線與成交量，於 Yahoo 站外開啟</span></div>`;

  // 技術圖表：用 buy_top/sell_top/broker_detail 由 Chart.js 即時繪製（不再使用 PNG）
  if ((d.buy_top && d.buy_top.length) || (d.sell_top && d.sell_top.length)) {
    html += `<h3>技術圖表</h3><div class="broker-charts">` +
      [1, 2, 3, 4, 5, 6].map(i => `<div class="chartbox"><canvas id="bc${i}" height="150"></canvas></div>`).join("") + `</div>`;
  }

  // 買賣前20
  const topTable = (recs, title) => {
    if (!recs || !recs.length) return "";
    let t = `<table class="simple"><thead><tr><th>券商</th><th>買量(張)</th><th>買均價</th><th>賣量(張)</th><th>賣均價</th><th>買賣超(張)</th></tr></thead><tbody>`;
    recs.forEach(r => {
      const diff = num(r["buy_sell_diff"]);
      t += `<tr><td>${r["券商"] ?? ""}</td><td>${fmtInt(r["buy_total_qty"])}</td><td>${fmt2(r["buy_avg_price"])}</td>
        <td>${fmtInt(r["sell_total_qty"])}</td><td>${fmt2(r["sell_avg_price"])}</td>
        <td class="${diff >= 0 ? "up" : "down"}">${diff >= 0 ? "+" : ""}${fmtInt(diff)}</td></tr>`;
    });
    return `<h3>${title}</h3>` + t + `</tbody></table>`;
  };
  html += `<div class="two-col"><div>${topTable(d.buy_top, "買超前 20 大券商")}</div><div>${topTable(d.sell_top, "賣超前 20 大券商")}</div></div>`;

  // 各價位成交量
  if (d.price_volume && d.price_volume.length) {
    html += `<h3>各價位成交量分布</h3><div class="chartbox"><canvas id="pvChart" height="90"></canvas></div>`;
  }

  // 券商明細
  if (d.broker_detail && d.broker_detail.length) {
    html += `<h3>券商分點明細（共 ${fmtInt(d.broker_detail.length)} 筆，可搜尋券商）</h3><div id="detailGrid"></div>`;
  }
  body.innerHTML = html;

  // 價量圖
  if (d.price_volume && d.price_volume.length) {
    new Chart($("#pvChart"), {
      type: "bar",
      data: {labels: d.price_volume.map(r => fmt2(r["股價"])),
        datasets: [{label: "成交量(股)", data: d.price_volume.map(r => num(r["買進股數"])), backgroundColor: "#4da3ff"}]},
      options: {responsive: true, plugins: {legend: {labels: {color: "#e6edf3"}}},
        scales: {x: {ticks: {color: "#8b9bb0"}, grid: {color: "#2c3a4f"}}, y: {ticks: {color: "#8b9bb0"}, grid: {color: "#2c3a4f"}}}},
    });
  }

  // 技術圖表（Chart.js）
  renderBrokerCharts(d);

  // 明細表
  if (d.broker_detail && d.broker_detail.length) {
    const rows = d.broker_detail.map(r => [
      fmt2(r["股價"]), r["券商"] ?? "", num(r["買進股數"]), num(r["賣出股數"]),
      r["買進占比"] != null ? fmt2(r["買進占比"]) + "%" : "", r["賣出占比"] != null ? fmt2(r["賣出占比"]) + "%" : "",
    ]);
    new gridjs.Grid({
      columns: [{name: "股價"}, {name: "券商"}, {name: "買進股數", formatter: c => fmtInt(c)}, {name: "賣出股數", formatter: c => fmtInt(c)}, {name: "買進占比"}, {name: "賣出占比"}],
      data: rows, search: true, sort: true, pagination: {limit: 20}, fixedHeader: true,
      language: {search: {placeholder: "搜尋券商…"}, pagination: {previous: "上一頁", next: "下一頁", showing: "顯示", to: "至", of: "共", results: "筆"}},
    }).render($("#detailGrid"));
  }
}

/* ---------- 技術圖表（Chart.js 版・POC）----------
   6 張券商圖全部用 buy_top / sell_top / broker_detail 即時畫，不需要 PNG。 */
let brokerCharts = [];
function renderBrokerCharts(d) {
  if (typeof Chart === "undefined") return;
  brokerCharts.forEach(c => { try { c.destroy(); } catch (e) {} });
  brokerCharts = [];
  const C = {text: "#e6edf3", muted: "#8b9bb0", grid: "#2c3a4f", up: "#ff5d5d", down: "#39c46e",
    upA: "rgba(255,93,93,.55)", downA: "rgba(57,196,110,.55)", line: "#e6edf3"};
  const mk = (id, cfg) => { const el = $("#" + id); if (el) brokerCharts.push(new Chart(el, cfg)); };
  const xAxis = {ticks: {color: C.muted, maxRotation: 90, minRotation: 55, font: {size: 10}}, grid: {color: C.grid}};
  const dualOpts = title => ({
    responsive: true, interaction: {mode: "index", intersect: false},
    plugins: {legend: {labels: {color: C.text, boxWidth: 12, font: {size: 11}}}, title: {display: true, text: title, color: C.muted}},
    scales: {x: xAxis,
      y: {position: "left", ticks: {color: C.muted}, grid: {color: C.grid}, title: {display: true, text: "股數(張)", color: C.muted}},
      y1: {position: "right", ticks: {color: C.muted}, grid: {drawOnChartArea: false}, title: {display: true, text: "均價", color: C.muted}}},
  });
  const netOpts = title => ({
    responsive: true,
    plugins: {legend: {display: false}, title: {display: true, text: title, color: C.muted}},
    scales: {x: xAxis, y: {ticks: {color: C.muted}, grid: {color: C.grid}, title: {display: true, text: "買賣超(張)", color: C.muted}}},
  });
  const bar = (label, data, color, extra) => Object.assign({type: "bar", label, data, backgroundColor: color, yAxisID: "y", order: 2}, extra || {});
  // 均價線：金色加粗、order 較小 → 畫在長條最上層，避免被柱子蓋住
  const line = (label, data) => ({type: "line", label, data, borderColor: "#ffcb3d", backgroundColor: "#ffcb3d",
    borderWidth: 2.5, yAxisID: "y1", tension: 0, pointRadius: 2, pointBackgroundColor: "#ffcb3d", order: 1});
  const bt = d.buy_top || [], st = d.sell_top || [];

  if (bt.length) mk("bc1", {data: {labels: bt.map(r => r["券商"]),
    datasets: [bar("買進股數(張)", bt.map(r => num(r["buy_total_qty"])), C.up), line("均價", bt.map(r => num(r["buy_avg_price"])))]},
    options: dualOpts("買進股數前20名與均價")});
  if (st.length) mk("bc2", {data: {labels: st.map(r => r["券商"]),
    datasets: [bar("賣出股數(張)", st.map(r => num(r["sell_total_qty"])), C.down), line("均價", st.map(r => num(r["sell_avg_price"])))]},
    options: dualOpts("賣出股數前20名與均價")});
  if (bt.length) mk("bc3", {data: {labels: bt.map(r => r["券商"]),
    datasets: [bar("買進股數(張)", bt.map(r => num(r["buy_total_qty"])), C.upA), bar("賣出股數(張)", bt.map(r => num(r["sell_total_qty"])), C.downA), line("均價", bt.map(r => num(r["buy_avg_price"])))]},
    options: dualOpts("買進前20名：買量 vs 賣量")});
  if (st.length) mk("bc4", {data: {labels: st.map(r => r["券商"]),
    datasets: [bar("賣出股數(張)", st.map(r => num(r["sell_total_qty"])), C.downA), bar("買進股數(張)", st.map(r => num(r["buy_total_qty"])), C.upA), line("均價", st.map(r => num(r["sell_avg_price"])))]},
    options: dualOpts("賣出前20名：賣量 vs 買量")});

  // 買超 / 賣超：用 broker_detail 依券商加總淨買（股）→ 張，再取前/後 20
  const net = {};
  (d.broker_detail || []).forEach(r => { const b = r["券商"] || ""; net[b] = (net[b] || 0) + (num(r["買進股數"]) - num(r["賣出股數"])); });
  const arr = Object.entries(net).map(([b, v]) => [b.replace(/^[0-9A-Za-z]{3,4}/, "").trim() || b, v / 1000]);
  const buyTop = [...arr].sort((a, b) => b[1] - a[1]).slice(0, 20);
  const sellTop = [...arr].sort((a, b) => a[1] - b[1]).slice(0, 20);
  if (buyTop.length) mk("bc5", {type: "bar", data: {labels: buyTop.map(x => x[0]),
    datasets: [{label: "買超(張)", data: buyTop.map(x => x[1]), backgroundColor: C.up}]}, options: netOpts("買超前20名")});
  if (sellTop.length) mk("bc6", {type: "bar", data: {labels: sellTop.map(x => x[0]),
    datasets: [{label: "賣超(張)", data: sellTop.map(x => x[1]), backgroundColor: C.down}]}, options: netOpts("賣超前20名")});
}

/* ========== 週報分析 ========================================= */
function weekInfo() {
  return (INDEX.weekly_dates || []).find(w => w.wkey === curWeek);
}

function renderWeekly() {
  const wi = weekInfo();
  const list = $("#weeklyStockList");
  if (!wi || !wi.stocks || !wi.stocks.length) {
    list.innerHTML = "";
    $("#weeklyBody").innerHTML = '<div class="loading">本週無資料</div>';
    return;
  }
  list.innerHTML = wi.stocks.map(s =>
    `<div class="stockchip${s.code === curWeeklyStock ? " active" : ""}" data-code="${s.code}">${s.code} ${s.name || ""}</div>`
  ).join("");
  list.querySelectorAll(".stockchip").forEach(c => c.onclick = () => {
    curWeeklyStock = c.dataset.code; renderWeekly();
  });
  if (!curWeeklyStock) {
    $("#weeklyBody").innerHTML = '<div class="loading">請選擇上方個股</div>';
    return;
  }
  loadWeeklyStock(curWeeklyStock);
}

async function loadWeeklyStock(code) {
  const body = $("#weeklyBody");
  body.innerHTML = `<div class="loading">載入 ${code} …</div>`;
  const wi = weekInfo();
  const sInfo = (wi.stocks || []).find(s => s.code === code) || {};
  const yhSuffix = sInfo.mkt === "TWO" ? "TWO" : "TW";
  const yhUrl = `https://tw.stock.yahoo.com/quote/${code}.${yhSuffix}/technical-analysis`;

  // 同時載入週報主檔 + 大量與均價
  let dw, dv;
  try { dw = await loadData(`weekly/${curWeek}/${code}`); }
  catch (e) { body.innerHTML = `<div class="loading">無法載入 ${code} 週報資料</div>`; return; }
  try { dv = await loadData(`weekly/${curWeek}/${code}_vol`); } catch (e) { dv = null; }

  let html = "";

  // Yahoo 連結
  html += `<div class="yahoo-link"><a href="${yhUrl}" target="_blank" rel="noopener noreferrer">` +
    `📈 在 Yahoo 股市看技術分析圖（K 線）→</a>` +
    `<span class="yahoo-note">週期間 K 線請在 Yahoo 站外切換</span></div>`;

  // 技術圖表（與日報相同，用 buy_top/sell_top 即時繪製）
  if ((dw.buy_top && dw.buy_top.length) || (dw.sell_top && dw.sell_top.length)) {
    html += `<h3>技術圖表（週）</h3><div class="broker-charts">` +
      [1,2,3,4,5,6].map(i => `<div class="chartbox"><canvas id="wbc${i}" height="150"></canvas></div>`).join("") +
      `</div>`;
  }

  // 買賣前20表格
  const topTable = (recs, title) => {
    if (!recs || !recs.length) return "";
    let t = `<table class="simple"><thead><tr><th>券商</th><th>買量(張)</th><th>買均價</th><th>賣量(張)</th><th>賣均價</th><th>買賣超(張)</th></tr></thead><tbody>`;
    recs.forEach(r => {
      const diff = num(r["buy_sell_diff"]);
      t += `<tr><td>${r["券商"] ?? ""}</td><td>${fmtInt(r["buy_total_qty"])}</td><td>${fmt2(r["buy_avg_price"])}</td>` +
        `<td>${fmtInt(r["sell_total_qty"])}</td><td>${fmt2(r["sell_avg_price"])}</td>` +
        `<td class="${diff >= 0 ? "up" : "down"}">${diff >= 0 ? "+" : ""}${fmtInt(diff)}</td></tr>`;
    });
    return `<h3>${title}</h3>` + t + `</tbody></table>`;
  };
  html += `<div class="two-col"><div>${topTable(dw.buy_top, "買超前 20 大券商（週）")}</div>` +
    `<div>${topTable(dw.sell_top, "賣超前 20 大券商（週）")}</div></div>`;

  // 大量與均價：每日摘要表
  if (dv && dv.daily_summary && dv.daily_summary.length) {
    html += `<h3>每日大量摘要</h3>
    <div style="overflow-x:auto">
    <table class="simple"><thead><tr>
      <th>日期</th><th>大量股價</th><th>買進股數</th><th>賣出股數</th>
      <th>買進家數</th><th>賣出家數</th><th>最高買進</th><th>最高賣出</th><th>收盤價</th>
      <th>前10買量</th><th>前10買均價</th><th>前10賣量</th><th>前10賣均價</th>
    </tr></thead><tbody>`;
    dv.daily_summary.forEach(r => {
      html += `<tr>
        <td>${r.date ?? ""}</td><td>${fmt2(r.price)}</td>
        <td>${fmtInt(r.buy_qty)}</td><td>${fmtInt(r.sell_qty)}</td>
        <td>${fmtInt(r.buy_cnt)}</td><td>${fmtInt(r.sell_cnt)}</td>
        <td>${fmtInt(r.max_buy_qty)}</td><td>${fmtInt(r.max_sell_qty)}</td>
        <td>${fmt2(r.close)}</td>
        <td>${fmtInt(r.top10_buy_qty)}</td><td>${fmt2(r.top10_buy_avg)}</td>
        <td>${fmtInt(r.top10_sell_qty)}</td><td>${fmt2(r.top10_sell_avg)}</td>
      </tr>`;
    });
    html += `</tbody></table></div>`;

    // 每日前10明細圖表（一天一個 canvas）
    if (dv.top10_detail && dv.top10_detail.length) {
      html += `<h3>每日前10券商買賣明細</h3><div class="broker-charts">` +
        dv.top10_detail.map(day =>
          `<div class="chartbox"><canvas id="vol_${day.date}" height="160"></canvas></div>`
        ).join("") + `</div>`;
    }
  }

  body.innerHTML = html;

  // 繪製週報技術圖表（同 renderBrokerCharts，改用 wbc 前綴）
  renderBrokerChartsWeekly(dw);

  // 繪製大量與均價每日前10圖表
  if (dv && dv.top10_detail) {
    dv.top10_detail.forEach(day => {
      const el = document.getElementById(`vol_${day.date}`);
      if (!el || !day.brokers.length) return;
      const labels = day.brokers.map((_, i) => `#${i + 1}`);
      new Chart(el, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {label: "買量(張)", data: day.brokers.map(b => num(b.buy_qty)), backgroundColor: "rgba(255,93,93,.7)", yAxisID: "y"},
            {label: "賣量(張)", data: day.brokers.map(b => num(b.sell_qty)), backgroundColor: "rgba(57,196,110,.7)", yAxisID: "y"},
            {label: "買均價", data: day.brokers.map(b => num(b.buy_avg)), type: "line", borderColor: "#ffcb3d", backgroundColor: "#ffcb3d", borderWidth: 2, yAxisID: "y1", tension: 0, pointRadius: 2, order: 1},
          ]
        },
        options: {
          responsive: true,
          interaction: {mode: "index", intersect: false},
          plugins: {
            legend: {labels: {color: "#e6edf3", boxWidth: 12, font: {size: 11}}},
            title: {display: true, text: `${day.date} 前10券商買賣`, color: "#8b9bb0"},
          },
          scales: {
            x: {ticks: {color: "#8b9bb0"}, grid: {color: "#2c3a4f"}},
            y: {position: "left", ticks: {color: "#8b9bb0"}, grid: {color: "#2c3a4f"}, title: {display: true, text: "股數(張)", color: "#8b9bb0"}},
            y1: {position: "right", ticks: {color: "#8b9bb0"}, grid: {drawOnChartArea: false}, title: {display: true, text: "均價", color: "#8b9bb0"}},
          },
        },
      });
    });
  }
}

/* 週報技術圖表（同 renderBrokerCharts，canvas id 用 wbc 前綴）*/
let weeklyBrokerCharts = [];
function renderBrokerChartsWeekly(d) {
  if (typeof Chart === "undefined") return;
  weeklyBrokerCharts.forEach(c => { try { c.destroy(); } catch (e) {} });
  weeklyBrokerCharts = [];
  const C = {text:"#e6edf3",muted:"#8b9bb0",grid:"#2c3a4f",up:"#ff5d5d",down:"#39c46e",
    upA:"rgba(255,93,93,.55)",downA:"rgba(57,196,110,.55)"};
  const mk = (id, cfg) => { const el = document.getElementById(id); if (el) weeklyBrokerCharts.push(new Chart(el, cfg)); };
  const xAxis = {ticks:{color:C.muted,maxRotation:90,minRotation:55,font:{size:10}},grid:{color:C.grid}};
  const dualOpts = title => ({
    responsive:true, interaction:{mode:"index",intersect:false},
    plugins:{legend:{labels:{color:C.text,boxWidth:12,font:{size:11}}},title:{display:true,text:title,color:C.muted}},
    scales:{x:xAxis,
      y:{position:"left",ticks:{color:C.muted},grid:{color:C.grid},title:{display:true,text:"股數(張)",color:C.muted}},
      y1:{position:"right",ticks:{color:C.muted},grid:{drawOnChartArea:false},title:{display:true,text:"均價",color:C.muted}}},
  });
  const netOpts = title => ({
    responsive:true,
    plugins:{legend:{display:false},title:{display:true,text:title,color:C.muted}},
    scales:{x:xAxis,y:{ticks:{color:C.muted},grid:{color:C.grid},title:{display:true,text:"買賣超(張)",color:C.muted}}},
  });
  const bar = (label, data, color, extra) => Object.assign({type:"bar",label,data,backgroundColor:color,yAxisID:"y",order:2}, extra||{});
  const line = (label, data) => ({type:"line",label,data,borderColor:"#ffcb3d",backgroundColor:"#ffcb3d",
    borderWidth:2.5,yAxisID:"y1",tension:0,pointRadius:2,pointBackgroundColor:"#ffcb3d",order:1});
  const bt = d.buy_top || [], st = d.sell_top || [];
  if (bt.length) mk("wbc1",{data:{labels:bt.map(r=>r["券商"]),datasets:[bar("買進股數(張)",bt.map(r=>num(r["buy_total_qty"])),C.up),line("均價",bt.map(r=>num(r["buy_avg_price"])))]},options:dualOpts("買進股數前20名與均價（週）")});
  if (st.length) mk("wbc2",{data:{labels:st.map(r=>r["券商"]),datasets:[bar("賣出股數(張)",st.map(r=>num(r["sell_total_qty"])),C.down),line("均價",st.map(r=>num(r["sell_avg_price"])))]},options:dualOpts("賣出股數前20名與均價（週）")});
  if (bt.length) mk("wbc3",{data:{labels:bt.map(r=>r["券商"]),datasets:[bar("買進股數(張)",bt.map(r=>num(r["buy_total_qty"])),C.upA),bar("賣出股數(張)",bt.map(r=>num(r["sell_total_qty"])),C.downA),line("均價",bt.map(r=>num(r["buy_avg_price"])))]},options:dualOpts("買進前20名：買量 vs 賣量（週）")});
  if (st.length) mk("wbc4",{data:{labels:st.map(r=>r["券商"]),datasets:[bar("賣出股數(張)",st.map(r=>num(r["sell_total_qty"])),C.downA),bar("買進股數(張)",st.map(r=>num(r["buy_total_qty"])),C.upA),line("均價",st.map(r=>num(r["sell_avg_price"])))]},options:dualOpts("賣出前20名：賣量 vs 買量（週）")});
  // 週報無 broker_detail；改用買進/賣出前20 的 buy_sell_diff（本來就是「張」）估算週買賣超
  const net = {};
  [...bt, ...st].forEach(r => { const b = r["券商"] || ""; if (b) net[b] = num(r["buy_sell_diff"]); });
  const arr = Object.entries(net);
  const buyTop=[...arr].sort((a,b)=>b[1]-a[1]).slice(0,20);
  const sellTop=[...arr].sort((a,b)=>a[1]-b[1]).slice(0,20);
  if (buyTop.length) mk("wbc5",{type:"bar",data:{labels:buyTop.map(x=>x[0]),datasets:[{label:"買超(張)",data:buyTop.map(x=>x[1]),backgroundColor:C.up}]},options:netOpts("買超前20名（週）")});
  if (sellTop.length) mk("wbc6",{type:"bar",data:{labels:sellTop.map(x=>x[0]),datasets:[{label:"賣超(張)",data:sellTop.map(x=>x[1]),backgroundColor:C.down}]},options:netOpts("賣超前20名（週）")});
  // 防呆：移除沒有畫出圖的空白 chartbox（例如某檔只有買方或只有賣方資料時）
  const drawn = new Set(weeklyBrokerCharts.map(c => c.canvas && c.canvas.id));
  ["wbc1","wbc2","wbc3","wbc4","wbc5","wbc6"].forEach(id => {
    if (!drawn.has(id)) { const el = document.getElementById(id); if (el && el.parentElement) el.parentElement.remove(); }
  });
}

init().catch(e => { document.querySelector("main").innerHTML = `<div class="loading">載入失敗：${e.message}<br>請確認 data 資料夾與 index.html 在一起</div>`; });
