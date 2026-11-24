/* 绘本处理页：只渲染阶段与产物，不调用流水线。 */

const STAGES = [
  { key: "ingest", name: "拆页", out: "ingest.json · pages/" },
  { key: "understand", name: "理解", out: "understand.json · figures/" },
  { key: "assets", name: "出图", out: "cast.json · locations.json" },
  { key: "identify", name: "认人", out: "identify.json" },
  { key: "storyboard", name: "分镜", out: "scenes.json · shots.json" },
  { key: "voice", name: "配音", out: "voice.json · voice/" },
  { key: "jobs", name: "镜次", out: "jobs.json · jobs/" },
  { key: "render", name: "出镜", out: "render.json · clips/" },
  { key: "compose", name: "成片", out: "compose.json · shots/film.mp4" },
  { key: "subtitles", name: "字幕", out: "subtitles.json · shots/film-subs.mp4" },
  { key: "show", name: "发布", out: "show.json" },
];

// 书还没有页图，先摆 6 个占位框看版式。
const PLACEHOLDERS = 6;

// 目前只有 ingest 的脚本参数与服务端的约定一致。
const RUNNABLE = new Set(["ingest"]);

const STATE_LABELS = {
  idle: ["未运行", "badge"],
  running: ["运行中", "badge badge--running"],
  done: ["完成", "badge badge--done"],
  failed: ["失败", "badge badge--failed"],
};

let BOOK = "";

const NAME = document.getElementById("name");
const THUMBS = document.getElementById("thumbs");
const STAGES_BOX = document.getElementById("stages");

// 阶段键 → 这一行的徽标、按钮与日志框。
const ROWS = new Map();

async function start() {
  BOOK = new URLSearchParams(location.search).get("id") || "";
  NAME.textContent = BOOK || "未选择绘本";
  await title(BOOK);
  thumbs();
  stages();
  await refresh();
}

// 书名沿用书库的规则：没检测出书名前显示带 .pdf 的文件名。
async function title(id) {
  if (!id) {
    return;
  }
  try {
    const reply = await fetch("/api/books");
    if (!reply.ok) {
      return;
    }
    const data = await reply.json();
    const book = data.books.find((row) => row.id === id);
    if (!book) {
      return;
    }
    NAME.textContent =
      book.title_source === "filename" ? book.filename : book.title;
  } catch (error) {
    // 读不到书库时保留编号，不影响看版式。
  }
}

function thumbs() {
  THUMBS.replaceChildren();
  for (let index = 0; index < PLACEHOLDERS; index += 1) {
    const cell = document.createElement("div");
    cell.className = "thumb";
    cell.textContent = `第 ${index + 1} 页`;
    THUMBS.append(cell);
  }
}

function stages() {
  STAGES_BOX.replaceChildren();
  for (const stage of STAGES) {
    const ui = row(stage);
    ROWS.set(stage.key, ui);
    STAGES_BOX.append(ui.item);
  }
}

// 刷新后从产物和日志把每行的状态拿回来。
async function refresh() {
  if (!BOOK) {
    return;
  }
  try {
    const url = `/api/books/${encodeURIComponent(BOOK)}/stages`;
    const reply = await fetch(url);
    if (!reply.ok) {
      return;
    }
    const data = await reply.json();
    for (const row of data.stages) {
      const ui = ROWS.get(row.stage);
      if (ui) {
        paint(ui, row);
      }
    }
  } catch (error) {
    // 读不到状态时保持未运行，不影响看版式。
  }
}

function paint(ui, row) {
  const [label, className] = STATE_LABELS[row.state] || STATE_LABELS.idle;
  ui.badge.textContent = label;
  ui.badge.className = className;
  ui.run.disabled = !RUNNABLE.has(ui.key);

  // 跑过的阶段留着上一次的输出，先收起来，展开时再读。
  const finished = row.state === "done" || row.state === "failed";
  if (finished && row.log) {
    ui.log.hidden = false;
    ui.log.classList.add("is-closed");
    ui.toggle.textContent = "展开";
    ui.replay = true;
  }
}

function row(stage) {
  const item = document.createElement("li");
  item.className = "stage";

  const line = document.createElement("div");
  line.className = "stage-line";

  const main = document.createElement("div");
  main.className = "stage-main";
  const name = document.createElement("p");
  name.className = "stage-name";
  name.append(document.createTextNode(stage.name));
  const key = document.createElement("span");
  key.className = "stage-key";
  key.textContent = stage.key;
  name.append(key);
  const out = document.createElement("p");
  out.className = "stage-out";
  out.textContent = stage.out;
  main.append(name, out);

  const badge = document.createElement("span");
  badge.className = "badge";
  badge.textContent = "未运行";

  const run = document.createElement("button");
  run.className = "run";
  run.type = "button";
  run.textContent = "运行";

  const log = document.createElement("div");
  log.className = "log";
  log.hidden = true;

  const bar = document.createElement("div");
  bar.className = "log-bar";
  const title = document.createElement("span");
  title.className = "log-title";
  title.textContent = "输出";
  const toggle = document.createElement("button");
  toggle.className = "log-toggle";
  toggle.type = "button";
  toggle.textContent = "收起";
  bar.append(title, toggle);

  const text = document.createElement("pre");
  text.className = "log-text";
  log.append(bar, text);

  const ui = {
    item,
    key: stage.key,
    badge,
    run,
    log,
    text,
    toggle,
    replay: false,
  };

  toggle.addEventListener("click", () => toggleLog(ui));

  if (!BOOK) {
    run.disabled = true;
    run.title = "先选择一本绘本";
  } else if (!RUNNABLE.has(stage.key)) {
    run.disabled = true;
    run.title = "这个阶段还没接入";
  } else {
    run.addEventListener("click", () => startStage(stage, ui));
  }

  line.append(main, badge, run);
  item.append(line, log);
  return ui;
}

// 收起的框第一次展开时，把上一次的输出读回来。
async function toggleLog(ui) {
  if (ui.replay) {
    ui.replay = false;
    const url = `/api/books/${encodeURIComponent(BOOK)}/stages/${ui.key}/log`;
    try {
      const reply = await fetch(url);
      if (reply.ok) {
        const data = await reply.json();
        ui.text.textContent = data.text;
      }
    } catch (error) {
      // 读不到就留空白，不影响开关。
    }
  }
  const closed = ui.log.classList.toggle("is-closed");
  ui.toggle.textContent = closed ? "展开" : "收起";
}

async function startStage(stage, ui) {
  ui.run.disabled = true;
  ui.log.hidden = false;
  ui.log.classList.remove("is-closed");
  ui.toggle.textContent = "收起";
  ui.replay = false;
  ui.text.textContent = "";
  ui.badge.className = "badge badge--running";
  ui.badge.textContent = "运行中";

  const url = `/api/books/${encodeURIComponent(BOOK)}/stages/${stage.key}/run`;
  try {
    const reply = await fetch(url, { method: "POST" });
    if (reply.status === 409) {
      // 上一次还在跑，直接接上它的输出。
      follow(stage, ui);
      return;
    }
    if (!reply.ok) {
      const data = await reply.json().catch(() => ({}));
      throw new Error(data.detail || `启动失败 ${reply.status}`);
    }
  } catch (error) {
    ui.badge.className = "badge badge--failed";
    ui.badge.textContent = "失败";
    ui.text.textContent = String(error.message || error);
    ui.run.disabled = false;
    return;
  }

  follow(stage, ui);
}

// 脚本每写一行就打印一行，最后一行是退出码。
function follow(stage, ui) {
  const url = `/api/books/${encodeURIComponent(BOOK)}/stages/${stage.key}/events`;
  const source = new EventSource(url);

  source.onmessage = (event) => {
    const line = JSON.parse(event.data);
    ui.text.textContent += `${line}\n`;
    ui.text.scrollTop = ui.text.scrollHeight;
    if (!line.startsWith("退出码")) {
      return;
    }
    source.close();
    const ok = line === "退出码 0";
    ui.badge.className = ok ? "badge badge--done" : "badge badge--failed";
    ui.badge.textContent = ok ? "完成" : "失败";
    ui.run.disabled = false;
  };

  source.onerror = () => {
    source.close();
    if (ui.run.disabled) {
      ui.badge.className = "badge badge--failed";
      ui.badge.textContent = "中断";
      ui.run.disabled = false;
    }
  };
}

start();
