from datetime import date, datetime, timezone

import app.core.time as business_time


def test_business_today_uses_asia_kolkata_date(monkeypatch):
    class FrozenDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 1, 1, 19, 0, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(business_time, "datetime", FrozenDateTime)

    assert business_time.business_today() == date(2026, 1, 2)
