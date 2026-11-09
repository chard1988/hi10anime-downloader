import base64
import socket
import unittest
from unittest.mock import patch
import httpcore
from hi10_downloader.browser_proxy import BrowserProxy


class BrowserProxyTests(unittest.TestCase):
    def test_authentication_and_private_destinations_are_denied(self):
        proxy=BrowserProxy()
        try:
            port=proxy.server.server_address[1]
            with socket.create_connection(('127.0.0.1',port),timeout=2) as client:
                client.sendall(b'CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n')
                self.assertIn(b'407',client.recv(1024))
            authorization=proxy.server.authorization
            with patch('hi10_downloader.browser_proxy.public_addresses',side_effect=httpcore.ConnectError('blocked')):
                with socket.create_connection(('127.0.0.1',port),timeout=2) as client:
                    client.sendall(f'CONNECT 127.0.0.1:443 HTTP/1.1\r\nProxy-Authorization: {authorization}\r\n\r\n'.encode())
                    self.assertEqual(client.recv(1024),b'')
        finally:
            proxy.close()
