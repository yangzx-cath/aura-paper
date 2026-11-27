/* The shelf and the PDF drop box on the studio home page. */

const SHELF = document.getElementById("shelf");
const PAGER = document.getElementById("pager");
const PREV = document.getElementById("prev");
const NEXT = document.getElementById("next");
const COUNT = document.getElementById("count");
const DROP = document.getElementById("drop");
const PICK = document.getElementById("pick");
const FILE = document.getElementById("file");
const NOTE = document.getElementById("note");
const PROGRESS = document.getElementById("progress");
const FILL = document.getElementById("fill");

// Five columns by two rows, the same as the grid in home.css.
const PAGE_SIZE = 10;

const STATUS_LABELS = {
  uploaded: ["已上传", "waiting"],
  running: ["处理中", "running"],
  ready: ["可观看", "ready"],
  failed: ["失败", "failed"],
};

let books = [];
let page = 0;
let busy = false;

// The seconds counter shown while the server stores the PDF.
let ticker = 0;

async function start() {
  try {
    books = await read();
  } catch (error) {
    empty(String(error.message || error));
    return;
  }
  render();
}

async function read() {
  const reply = await fetch("/api/books");
  if (!reply.ok) {
    throw new Error(`读取书库失败 ${reply.status}`);
  }
  const data = await reply.json();
  return data.books;
}

function render() {
  SHELF.replaceChildren();
  if (!books.length) {
    empty("书库里还没有绘本");
    pager(0);
    return;
  }
  const first = page * PAGE_SIZE;
  for (const book of books.slice(first, first + PAGE_SIZE)) {
    SHELF.append(card(book));
  }
  pager(books.length);
}

// One book as the shelf shows it, with a placeholder when it has no cover.
function card(book) {
  const shown = book.title || book.filename;

  const item = document.createElement("article");
  item.className = "book";

  const cover = document.createElement("div");
  cover.className = "cover";
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

  item.append(cover, title, status);
  return item;
}

// The pager follows the book count, and hides while one page is enough.
function pager(total) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  COUNT.textContent = `第 ${page + 1} / ${pages} 页`;
  PAGER.hidden = pages < 2;
  PREV.disabled = page === 0;
  NEXT.disabled = page >= pages - 1;
}

// One centred line, used for an empty shelf and for a failed read.
function empty(text) {
  SHELF.replaceChildren();
  const line = document.createElement("p");
  line.className = "shelf-empty";
  line.textContent = text;
  SHELF.append(line);
}

// Read the shelf again and open the page the newest book landed on.
async function refresh() {
  try {
    books = await read();
  } catch (error) {
    note(String(error.message || error), "is-error");
    return;
  }
  page = Math.floor(Math.max(0, books.length - 1) / PAGE_SIZE);
  render();
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
  // A big PDF takes tens of seconds on the wire, so give up after three
  // minutes and unlock the page.
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
      refresh();
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

// The bytes are through, but the server is still storing the file.
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

// Uploading locks the button and the drop zone, so one file goes at a time.
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

PREV.addEventListener("click", () => {
  page -= 1;
  render();
});

NEXT.addEventListener("click", () => {
  page += 1;
  render();
});

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

start();
