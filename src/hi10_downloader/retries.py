"""Bounded retries for transient failures, respecting upstream backoff."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import httpx


def retry_delay(error, attempt):
    """None means stop; never shorten a server's requested wait to our budget."""
    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        if response.status_code not in {408, 429, 500, 502, 503, 504}:
            return None
        value = response.headers.get('Retry-After')
        if value:
            try:
                delay = float(int(value))
            except ValueError:
                try:
                    when = parsedate_to_datetime(value)
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    delay = (when - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = 0
            if delay > 300:
                return None
            return max(0, delay, min(2 ** attempt, 30))
    elif not isinstance(error, (httpx.TransportError,)):
        return None
    return min(2 ** attempt, 30)
