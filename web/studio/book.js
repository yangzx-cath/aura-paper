/* The studio book page. */

const NAME = document.getElementById("name");
const BOOK = document.getElementById("book");
const STAGES = document.getElementById("stages");

const BOOK_ID = new URLSearchParams(location.search).get("id") || "";

async function start() {
  if (!BOOK_ID) {
    NAME.textContent = "未选择绘本";
    return;
  }
  BOOK.textContent = BOOK_ID;
  NAME.textContent = BOOK_ID;

  await readBook();
  await readStages();
}

async function readBook() {
  try {
    const reply = await fetch(`/api/books/${encodeURIComponent(BOOK_ID)}`);
    if (!reply.ok) {
      return;
    }
    const book = await reply.json();
    NAME.textContent = book.label;
  } catch (error) {
    // The id stays in the title when the book cannot be read.
  }
}

async function readStages() {
  const url = `/api/books/${encodeURIComponent(BOOK_ID)}/stages`;
  try {
    const reply = await fetch(url);
    if (!reply.ok) {
      return;
    }
    const body = await reply.json();
    showStages(body.stages);
  } catch (error) {
    // An unreachable server leaves the stage list empty.
  }
}

function showStages(list) {
  const rows = list.map(rowOf);
  STAGES.replaceChildren(...rows);
}

function rowOf(stage) {
  const name = document.createElement("span");
  name.className = "stage-name";
  name.textContent = stage.name;

  const key = document.createElement("span");
  key.className = "stage-key";
  key.textContent = stage.key;

  const row = document.createElement("li");
  row.className = "stage";
  row.dataset.key = stage.key;
  row.append(name, key);
  return row;
}

start();
