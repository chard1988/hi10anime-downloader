from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

import httpx
from hi10_downloader.network import client
from hi10_downloader.storage import save_json
from hi10_downloader.web import Application
from hi10_downloader.lifecycle import ServiceLocks
from hi10_downloader.cli import download


class CrashRedirectTests(unittest.TestCase):
    def test_redirect_cannot_escape_explicit_network_exception(self):
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302);self.send_header('Location','http://127.0.0.2/private');self.end_headers()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.dict(os.environ,{'HI10_ALLOWED_NETWORKS':'127.0.0.1/32'}):
                with client() as connection,self.assertRaisesRegex(httpx.ConnectError,'non-public'):
                    connection.get(f'http://127.0.0.1:{server.server_port}/')
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_sigkill_during_commit_recovers_before_service_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'config';output=root/'output';config.mkdir();output.mkdir()
            save_json(config/'library.json',{'projects':[],'default_quality':0})
            save_json(config/'downloads.json',[])
            code='''from pathlib import Path
from hi10_downloader.storage import save_json
import sys,time
root=Path(sys.argv[1]);a=root/'library.json';b=root/'downloads.json'
save_json(root/'pending-transaction.json',{'version':2,'writes':{str(a):{'op':'write','data':{'projects':[],'default_quality':720}},str(b):{'op':'write','data':[]}}})
save_json(a,{'projects':[],'default_quality':720})
print('ready',flush=True)
time.sleep(60)
'''
            process=subprocess.Popen([sys.executable,'-c',code,str(config)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(),'ready')
                process.send_signal(signal.SIGKILL);process.communicate(timeout=3)
                restored=Application(config,output,password='test')
                self.assertEqual(restored.catalog['default_quality'],720)
                self.assertEqual(restored.items,[])
                self.assertFalse((config/'pending-transaction.json').exists())
            finally:
                if process.poll() is None:process.kill();process.communicate()

    def test_cli_rejects_service_owned_data_before_reading_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with ServiceLocks(root/'config',root/'output'):
                args=type('Args',(),{'state':root/'config/session.json','output':root/'output'})()
                with self.assertRaisesRegex(ValueError,'Another Hi10 service'):
                    download(args)
