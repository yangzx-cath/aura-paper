/* 创作台：列出书库，并接受一个 PDF 上传。 */

const SHELF = document.getElementById("shelf");
const DROP = document.getElementById("drop");
const PICK = document.getElementById("pick");
const FILE = document.getElementById("file");
const NOTE = document.getElementById("note");
const PROGRESS = document.getElementById("progress");
const FILL = document.getElementById("fill");

let busy = false;

const STATUS_LABELS = {
  uploaded: ["已上传", "waiting"],
  running: ["处理中", "running"],
  ready: ["可观看", "ready"],
  failed: ["失败", "failed"],
};

async function load() {
  const reply = await fetch("/api/books");
  if (!reply.ok) {
    note("读取书库失败");
    return;
  }
  const data = await reply.json();
  render(data.books);
}

function render(books) {
  SHELF.replaceChildren();
  if (!books.length) {
    const empty = document.createElement("p");
    empty.className = "shelf-empty";
    empty.textContent = "还没有绘本，先上传一本";
    SHELF.append(empty);
    return;
  }
  for (const book of books) {
    SHELF.append(card(book));
  }
}

function card(book) {
  const article = document.createElement("article");
  article.className = "book";

  const cover = document.createElement("div");
  cover.className = "cover cover--empty";
  const name = document.createElement("span");
  name.className = "cover-name";
  name.textContent = book.title || book.filename;
  cover.append(name);

  const title = document.createElement("h3");
  title.className = "book-title";
  title.textContent = book.title || book.filename;

  const [label, tone] = STATUS_LABELS[book.status] || [book.status, "waiting"];
  const status = document.createElement("p");
  status.className = `status status--${tone}`;
  const dot = document.createElement("span");
  dot.className = "status-dot";
  status.append(dot, document.createTextNode(`${label} · ${book.id}`));

  article.append(cover, title, status);
  return article;
}

function upload(file) {
  if (busy || !file) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    note("只能上传 PDF 文件", "is-error");
    return;
  }

  setBusy(true);
  fill(0);
  note("上传中…", "is-live");

  const form = new FormData();
  form.append("file", file);
  const request = new XMLHttpRequest();
  request.open("POST", "/api/books");

  request.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) {
      return;
    }
    const percent = Math.round((event.loaded / event.total) * 100);
    fill(percent);
    note(`上传中 ${percent}%`, "is-live");
  });

  request.addEventListener("load", () => {
    setBusy(false);
    if (request.status >= 200 && request.status < 300) {
      const book = JSON.parse(request.responseText);
      note(`已上传 ${book.id}`, "is-done");
      load();
      return;
    }
    note(readError(request), "is-error");
  });

  request.addEventListener("error", () => {
    setBusy(false);
    note("上传失败，检查服务是否在运行", "is-error");
  });

  request.send(form);
}

// 上传期间锁住按钮与拖放，避免同一秒内提交两次。
function setBusy(value) {
  busy = value;
  PICK.disabled = value;
  FILE.disabled = value;
  DROP.classList.toggle("is-busy", value);
  PROGRESS.hidden = !value;
  if (!value) {
    fill(0);
  }
}

function fill(percent) {
  FILL.style.width = `${percent}%`;
}

function readError(request) {
  try {
    return JSON.parse(request.responseText).detail || "上传失败";
  } catch (error) {
    return `上传失败 ${request.status}`;
  }
}

function note(text, tone) {
  NOTE.textContent = text;
  NOTE.className = tone ? `drop-note ${tone}` : "drop-note";
}

PICK.addEventListener("click", () => FILE.click());

FILE.addEventListener("change", () => {
  upload(FILE.files[0]);
  FILE.value = "";
});

document.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (!busy) {
    DROP.classList.add("is-over");
  }
});

document.addEventListener("dragleave", (event) => {
  if (!event.relatedTarget) {
    DROP.classList.remove("is-over");
  }
});

document.addEventListener("drop", (event) => {
  event.preventDefault();
  DROP.classList.remove("is-over");
  if (busy) {
    return;
  }
  upload(event.dataTransfer.files[0]);
});

load();
