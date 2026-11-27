/* The shelf on the studio home page. */

const SHELF = document.getElementById("shelf");
const PAGER = document.getElementById("pager");
const PREV = document.getElementById("prev");
const NEXT = document.getElementById("next");
const COUNT = document.getElementById("count");

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

async function start() {
  try {
    const reply = await fetch("/api/books");
    if (!reply.ok) {
      throw new Error(`读取书库失败 ${reply.status}`);
    }
    const data = await reply.json();
    books = data.books;
  } catch (error) {
    empty(String(error.message || error));
    return;
  }
  render();
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

PREV.addEventListener("click", () => {
  page -= 1;
  render();
});

NEXT.addEventListener("click", () => {
  page += 1;
  render();
});

start();
