/* The studio book page. */

const NAME = document.getElementById("name");
const BOOK = document.getElementById("book");

const BOOK_ID = new URLSearchParams(location.search).get("id") || "";

async function start() {
  if (!BOOK_ID) {
    NAME.textContent = "未选择绘本";
    return;
  }
  BOOK.textContent = BOOK_ID;
  NAME.textContent = BOOK_ID;

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

start();
