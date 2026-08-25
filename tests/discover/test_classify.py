from offprint.discover.classify import should_queue


def test_yyyy_mm_kept() -> None:
    assert should_queue("https://example.com/2020/06/slug")


def test_category_skipped() -> None:
    assert not should_queue("https://example.com/category/foo")


def test_feedback_kept_feed_skipped() -> None:
    assert should_queue("https://example.com/feedback/my-post")
    assert not should_queue("https://example.com/feed/atom")


def test_home_skipped_unless_only_home() -> None:
    assert not should_queue("https://example.com/")
    assert should_queue("https://example.com/", only_home=True)


def test_urls_file_skips_deny_list() -> None:
    assert should_queue("https://example.com/tag/foo", apply_deny_list=False)


def test_searching_not_denied() -> None:
    assert should_queue("https://example.com/searching")


def test_blog_page_2_queued() -> None:
    assert should_queue("https://example.com/blog/page/2")
    assert not should_queue("https://example.com/page/2")
