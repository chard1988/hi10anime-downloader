"""Repeatable large-queue benchmark without live website traffic."""
import json
from pathlib import Path
import re
import tempfile
import time
from hi10_downloader.web import Application


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        app=Application(root/'config',root/'output',password='test')
        app.items=[{'id':str(i),'project_id':'large-project','project':'Large project','filename':f'{i}.mkv','status':'failed','bytes':0,'message':'HTTP 403 Forbidden'} for i in range(50000)]
        app.snapshot(grouped=True)
        started=time.perf_counter()
        for _ in range(100):
            state=app.snapshot(grouped=True,group_pages={'large-project':500})
        elapsed=(time.perf_counter()-started)*10
        size=len(json.dumps(state).encode())
        assert len(state['downloads'])==50
        assert size<100000, size
        assert elapsed<100, elapsed
        rss=int(re.search(r'VmRSS:\s+(\d+)',Path('/proc/self/status').read_text())[1])
        print(json.dumps({'queue_items':50000,'visible_items':50,'payload_bytes':size,'mean_snapshot_ms':round(elapsed,3),'sampled_rss_kib':rss},indent=2))
        app.close(timeout=2)


if __name__=='__main__':main()
