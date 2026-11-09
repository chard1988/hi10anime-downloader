from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from hi10_downloader.web import Handler


class DisconnectTests(unittest.TestCase):
    def handler(self, fail_write, exception):
        handler=Handler.__new__(Handler)
        handler.request_version='HTTP/1.1'
        handler.requestline='GET /api/state HTTP/1.1'
        handler.command='GET'
        handler.path='/api/state'
        handler.close_connection=False
        handler.authenticated=lambda:True
        handler.server=SimpleNamespace(app=SimpleNamespace(snapshot=lambda *args:{'downloads':[]}))
        output=BytesIO()
        writes=0
        def write(data):
            nonlocal writes
            writes+=1
            if writes==fail_write:
                raise exception('peer disconnected')
            return output.write(data)
        handler.wfile=SimpleNamespace(write=Mock(side_effect=write))
        handler.send=Mock(wraps=handler.send)
        return handler

    def test_status_disconnect_is_not_retried_as_an_error_response(self):
        for exception in (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,TimeoutError):
            for failed_write in (1,2):
                with self.subTest(error=exception.__name__,write=failed_write):
                    handler=self.handler(failed_write,exception)
                    handler.do_GET()
                    self.assertTrue(handler.close_connection)
                    self.assertEqual(handler.send.call_count,1)
                    self.assertEqual(handler.send.call_args.args[0],200)
                    self.assertEqual(handler.wfile.write.call_count,failed_write)

    def test_request_read_disconnect_closes_connection_quietly(self):
        handler=Handler.__new__(Handler)
        handler.close_connection=False
        with patch('http.server.BaseHTTPRequestHandler.handle',side_effect=ConnectionResetError('peer disconnected')):
            handler.handle()
        self.assertTrue(handler.close_connection)

    def test_successful_response_is_still_written(self):
        handler=self.handler(99,BrokenPipeError)
        self.assertTrue(handler.send(200,{'ok':True}))
        self.assertEqual(handler.wfile.write.call_count,2)
        self.assertFalse(handler.close_connection)

    def test_unrelated_io_errors_are_not_hidden_by_send(self):
        handler=self.handler(1,OSError)
        with self.assertRaises(OSError):
            handler.send(200,{'ok':True})
