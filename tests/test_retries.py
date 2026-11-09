from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import unittest
import httpx
from hi10_downloader.retries import retry_delay


def failure(status, **headers):
    response=httpx.Response(status,headers=headers,request=httpx.Request('GET','https://mirror.invalid/file'))
    return httpx.HTTPStatusError('private',request=response.request,response=response)


class RetryTests(unittest.TestCase):
    def test_permanent_and_filesystem_errors_do_not_retry(self):
        self.assertIsNone(retry_delay(failure(403),0))
        self.assertIsNone(retry_delay(OSError(28,'full'),0))
        self.assertIsNone(retry_delay(ValueError('invalid file'),0))

    def test_transient_backoff_and_retry_after(self):
        self.assertEqual(retry_delay(httpx.ConnectTimeout('timeout'),2),4)
        self.assertEqual(retry_delay(failure(429,**{'Retry-After':'20'}),0),20)
        self.assertIsNone(retry_delay(failure(503,**{'Retry-After':'900'}),0))
        when=format_datetime(datetime.now(timezone.utc)+timedelta(seconds=60))
        self.assertGreater(retry_delay(failure(503,**{'Retry-After':when}),0),58)
        self.assertEqual(retry_delay(failure(500,**{'Retry-After':'invalid'}),1),2)
