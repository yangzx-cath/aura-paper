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

const NAME = document.getElementById("name");
const THUMBS = document.getElementById("thumbs");
const STAGES_BOX = document.getElementById("stages");

async function start() {
  const id = new URLSearchParams(location.search).get("id") || "";
  NAME.textContent = id || "未选择绘本";
  await title(id);
  thumbs();
  stages();
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
    STAGES_BOX.append(row(stage));
  }
}

function row(stage) {
  const item = document.createElement("li");
  item.className = "stage";

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

  item.append(main, badge, run);
  return item;
}

start();
