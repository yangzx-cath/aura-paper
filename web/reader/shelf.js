/* 阅读端书架：列出书库，点书暂时没有反应。 */

const SHELF = document.getElementById("shelf");
const PAGER = document.getElementById("pager");
const PREV = document.getElementById("prev");
const NEXT = document.getElementById("next");
const COUNT = document.getElementById("count");

// 一页 5 列 × 2 行，与 shelf.css 的 grid 模板一致。
const PAGE_SIZE = 10;

let books = [];
let page = 0;

const STATUS_LABELS = {
  uploaded: ["已上传", "waiting"],
  running: ["处理中", "running"],
  ready: ["可观看", "ready"],
  failed: ["失败", "failed"],
};

async function load() {
  const reply = await fetch("/api/books");
  if (!reply.ok) {
    SHELF.replaceChildren(message("读取书库失败"));
    return;
  }
  const data = await reply.json();
  books = data.books;
  page = 0;
  render();
}

function render() {
  SHELF.replaceChildren();
  if (!books.length) {
    SHELF.append(message("绘本书架还空着"));
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

// 只做展示，不用链接：阅读页还没有做出来。
function card(book) {
  const shown = labelOf(book);
  const article = document.createElement("article");
  article.className = "book";

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

function message(text) {
  const line = document.createElement("p");
  line.className = "shelf-empty";
  line.textContent = text;
  return line;
}

PREV.addEventListener("click", () => {
  page -= 1;
  render();
});

NEXT.addEventListener("click", () => {
  page += 1;
  render();
});

load();
