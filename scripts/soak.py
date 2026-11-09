"""Configurable local soak; no account access, downloads, or claims about NAS hardware."""
import argparse
import json
from pathlib import Path
import resource
import tempfile
import time
import re
from hi10_downloader.web import Application


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=60);args=parser.parse_args()
    if args.seconds<1:raise ValueError('Choose a positive duration')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);app=Application(root/'config',root/'output',password='test')
        app.items=[{'id':str(i),'project_id':str(i//1000),'project':f'Project {i//1000}','filename':str(i)+'.mkv','status':'failed' if i%3 else 'complete','bytes':0} for i in range(50000)]
        def rss():
            return int(re.search(r'VmRSS:\s+(\d+)',Path('/proc/self/status').read_text())[1])
        baseline=rss();maximum=baseline
        start=time.monotonic();iterations=0;max_payload=0
        while time.monotonic()-start<args.seconds:
            state=app.snapshot(grouped=True,download_page=iterations%10)
            group=state['download_groups'][0]
            state=app.snapshot(grouped=True,download_page=iterations%10,group_pages={group['id']:iterations%20})
            payload=len(json.dumps(state));max_payload=max(max_payload,payload)
            assert len(state['downloads'])<=50 and payload<100000
            maximum=max(maximum,rss())
            assert maximum-baseline<65536, (baseline,maximum)
            iterations+=1
            time.sleep(.05)
        print(json.dumps({'seconds':args.seconds,'iterations':iterations,'max_payload_bytes':max_payload,'baseline_rss_kib':baseline,'max_sampled_rss_kib':maximum,'growth_kib':maximum-baseline}))


if __name__=='__main__':main()
