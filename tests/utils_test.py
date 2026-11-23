from datetime import datetime, timezone

from aura_paper.utils import now_iso


def test_now_iso_is_utc():
    value = now_iso()
    parsed = datetime.fromisoformat(value)

    assert parsed.tzinfo == timezone.utc
    assert parsed.microsecond == 0
