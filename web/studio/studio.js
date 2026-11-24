/* 创作台：列出书库，并接受一个 PDF 上传。 */

const SHELF = document.getElementById("shelf");
const DROP = document.getElementById("drop");
const PICK = document.getElementById("pick");
const FILE = document.getElementById("file");
const NOTE = document.getElementById("note");
const PROGRESS = document.getElementById("progress");
const FILL = document.getElementById("fill");
const PAGER = document.getElementById("pager");
const PREV = document.getElementById("prev");
const NEXT = document.getElementById("next");
const COUNT = document.getElementById("count");

// 一页 5 列 × 2 行，与 shelf.css 的 grid 模板一致。
const PAGE_SIZE = 10;

let books = [];
let page = 0;
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
  books = data.books;
  page = 0;
  render();
}

function render() {
  SHELF.replaceChildren();
  SHELF.scrollTop = 0;
  if (!books.length) {
    const empty = document.createElement("p");
    empty.className = "shelf-empty";
    empty.textContent = "还没有绘本，先上传一本";
    SHELF.append(empty);
    updatePager();
    return;
  }
  const start = page * PAGE_SIZE;
  const shown = books.slice(start, start + PAGE_SIZE);
  for (const book of shown) {
    SHELF.append(card(book));
  }
  updatePager();
}

// 页码与翻页按钮跟着书目数量走，只有一页时整条收起。
function updatePager() {
  const pages = Math.max(1, Math.ceil(books.length / PAGE_SIZE));
  COUNT.textContent = `第 ${page + 1} / ${pages} 页`;
  PAGER.hidden = pages < 2;
  PREV.disabled = page === 0;
  NEXT.disabled = page >= pages - 1;
}

function card(book) {
  const shown = labelOf(book);
  const article = document.createElement("a");
  article.className = "book";
  article.href = `book.html?id=${encodeURIComponent(book.id)}`;

  const cover = document.createElement("div");
  cover.className = "cover cover--empty";
  const name = document.createElement("span");
  name.className = "cover-name";
  name.textContent = shown;
  cover.append(name);

  const title = document.createElement("h3");
  title.className = "book-title";
  title.textContent = shown;

  const [label, tone] = STATUS_LABELS[book.status] || [book.status, "waiting"];
  const status = document.createElement("p");
  status.className = `status status--${tone}`;
  const dot = document.createElement("span");
  dot.className = "status-dot";
  status.append(dot, document.createTextNode(`${label} · ${book.id}`));

  article.append(cover, title, status);
  return article;
}

// 还没检测出书名时留 .pdf 后缀，一眼看出这是上传的文件。
function labelOf(book) {
  if (book.title_source === "filename") {
    return book.filename || book.title;
  }
  return book.title || book.filename;
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
  // 大文件在网络里要几十秒才走完，超时后必须把界面解锁。
  request.timeout = 180000;

  request.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) {
      return;
    }
    const percent = Math.round((event.loaded / event.total) * 100);
    fill(percent);
    if (percent >= 100) {
      wait();
      return;
    }
    note(`上传中 ${percent}%`, "is-live");
  });

  request.addEventListener("load", () => {
    stopWait();
    setBusy(false);
    if (request.status >= 200 && request.status < 300) {
      const book = JSON.parse(request.responseText);
      note(`已上传 ${book.filename}`, "is-done");
      books.push(book);
      page = Math.floor((books.length - 1) / PAGE_SIZE);
      render();
      return;
    }
    note(readError(request), "is-error");
  });

  request.addEventListener("error", () => {
    stopWait();
    setBusy(false);
    note("上传失败，检查服务是否在运行", "is-error");
  });

  request.addEventListener("timeout", () => {
    stopWait();
    setBusy(false);
    note("上传超时，请重试", "is-error");
  });

  request.send(form);
}

// 进度走满后数据还在网络里，用秒数说明页面没有卡死。
let ticker = 0;

function wait() {
  let seconds = 0;
  clearInterval(ticker);
  note("正在存入书库… 0s", "is-live");
  ticker = setInterval(() => {
    seconds += 1;
    note(`正在存入书库… ${seconds}s`, "is-live");
  }, 1000);
}

function stopWait() {
  clearInterval(ticker);
  ticker = 0;
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

PREV.addEventListener("click", () => {
  page -= 1;
  render();
});

NEXT.addEventListener("click", () => {
  page += 1;
  render();
});

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
