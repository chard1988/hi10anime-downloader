from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import httpx

from hi10_downloader.cli import download_one, save_json
import test_runtime
from hi10_downloader.schema import catalog, schedule


class LimitTests(unittest.TestCase):
    def test_video_is_synced_before_completion_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'episode.mkv'
            synced=[]
            def fail_sync(descriptor):
                synced.append(os.readlink(f'/proc/self/fd/{descriptor}'))
                raise OSError(5, 'fixture disk sync failure')
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'\x1a\x45\xdf\xa3video'))) as client:
                with patch('os.fsync',side_effect=fail_sync),self.assertRaises(OSError):
                    download_one(client,{'url':'https://mirror.invalid/a.mkv'},'https://hi10anime.com',target)
            self.assertEqual(synced,[str(target)+'.part'])
            self.assertFalse(target.exists())
            self.assertFalse(target.with_name(target.name+'.receipt.json').exists())

    def test_download_limits_and_free_space_fail_without_final_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'episode.mkv'
            with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'\x1a\x45\xdf\xa3'+b'a'*30))) as client:
                with patch.dict('os.environ',{'HI10_MAX_FILE_BYTES':'10'}),self.assertRaisesRegex(ValueError,'maximum file size'):
                    download_one(client,{'url':'https://mirror.invalid/a.mkv'},'https://hi10anime.com',target)
                with patch('hi10_downloader.cli.shutil.disk_usage',return_value=type('Space',(),{'free':0})()),self.assertRaisesRegex(ValueError,'free disk space'):
                    download_one(client,{'url':'https://mirror.invalid/a.mkv'},'https://hi10anime.com',target)
            self.assertFalse(target.exists());self.assertFalse(target.with_suffix('.mkv.part').exists())

    def test_future_state_and_nonfinite_schedules_are_rejected(self):
        self.assertFalse(catalog({'schema_version':999,'projects':[]}))
        self.assertFalse(schedule({'starts_at':float('nan')}))
        self.assertFalse(schedule({'starts_at':float('inf')}))


class ReceiptTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def test_completed_receipt_recovers_manifest_after_interrupted_recording(self):
        self.app.queue([self.p['id']]);entry=self.app.items[0]
        from hi10_downloader.cli import file_folder, digest
        folder=file_folder(self.app.output,entry['folder'],entry['file']);folder.mkdir(parents=True)
        target=folder/entry['filename'];target.write_bytes(b'\x1a\x45\xdf\xa3fixture')
        receipt=target.with_name(target.name+'.receipt.json')
        save_json(receipt,{'url':entry['file']['url'],'size':target.stat().st_size,'sha256':digest(target)})
        with patch('hi10_downloader.web.make_client',return_value=httpx.Client()),patch.object(self.app.download_cancel,'wait',return_value=False),patch('hi10_downloader.web.download_one') as download:
            self.app.run_downloads([entry])
        download.assert_not_called()
        self.assertEqual(entry['status'],'complete')
        self.assertFalse(receipt.exists())
        self.assertTrue(self.app.manifest())
