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

    def test_certificate_verification_is_permanent_not_a_transient_connection_error(self):
        import ssl
        error=httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch")
        for attempt in range(3):self.assertIsNone(retry_delay(error,attempt))
        wrapped=httpx.ConnectError('TLS connection failed')
        wrapped.__cause__=ssl.SSLCertVerificationError(1,'certificate verify failed')
        self.assertIsNone(retry_delay(wrapped,0))
        cycle=httpx.ConnectError('Connection reset by peer')
        cycle.__context__=cycle
        self.assertEqual(retry_delay(cycle,1),2)
        self.assertEqual(retry_delay(httpx.ConnectError('Connection reset by peer'),1),2)
