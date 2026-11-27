from aura_paper.schema.content import BookContent, language_of


# Build a book from its title and the words of its pages.
def make_book(title, texts):
    pages = [
        {"index": index, "filename": f"p{index:03d}.jpg", "page_text": text}
        for index, text in enumerate(texts)
    ]
    return BookContent.from_dict(
        {
            "id": "demo",
            "source": "",
            "cover": {"title": title},
            "pages": pages,
        }
    )


def test_a_chinese_book_is_zh():
    book = make_book("一起搭积木吧", ["滴答滴答下雨了"])

    assert book.language == "zh"


def test_an_english_book_is_en():
    book = make_book("A Costume Party", ["Thanks for inviting me"])

    assert book.language == "en"


def test_a_book_without_words_is_zh():
    book = make_book("", [])

    assert book.language == "zh"


def test_a_question_is_read_in_its_own_language():
    assert language_of("What is this?") == "en"
    assert language_of("这是什么？") == "zh"
