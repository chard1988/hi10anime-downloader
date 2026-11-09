"""Validate a built image with private throwaway volumes and no account session."""
import argparse
import json
import shlex
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',default='docker');parser.add_argument('--image',default='hi10-downloader:beta');parser.add_argument('--user',help='Optional UID:GID portability check');args=parser.parse_args()
    engine=shlex.split(args.engine)
    def run(*parts,**kw):return subprocess.run([*engine,*parts],check=True,text=True,**kw)
    name='hi10-smoke-'+uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);config=root/'config';output=root/'downloads';config.mkdir();output.mkdir()
        # The container's configured UID needs access; this is private test-only data.
        root.chmod(0o755);config.chmod(0o777);output.chmod(0o777)
        try:
            identity=['--user',args.user,'-e','HOME=/tmp'] if args.user else []
            run('run','-d','--name',name,'--init','--stop-timeout=75','--shm-size=1g','--cap-drop=ALL','--security-opt=no-new-privileges','-p','127.0.0.1::8080','-e','HI10_WEB_PASSWORD=smoke-test-only','-v',f'{config}:/config','-v',f'{output}:/downloads',*identity,args.image,stdout=subprocess.DEVNULL)
            health=run('inspect',name,'--format','{{json .Config.Healthcheck}}',capture_output=True).stdout
            assert '/healthz' in health, 'Image is missing its health check'
            cookie=None
            for cycle in range(2):
                port=run('port',name,'8080',capture_output=True).stdout.strip().split(':')[-1]
                deadline=time.monotonic()+30
                while True:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=1) as response:assert json.load(response)=={'status':'ok'}
                        break
                    except OSError:
                        if time.monotonic()>deadline:raise RuntimeError('Image did not become healthy')
                        time.sleep(.2)
                uid=run('exec',name,'id','-u',capture_output=True).stdout.strip();assert uid==(args.user.split(':')[0] if args.user else '99'),uid
                if cookie:
                    request=urllib.request.Request(f'http://127.0.0.1:{port}/api/diagnostics',headers={'Cookie':cookie})
                    with urllib.request.urlopen(request,timeout=3) as response:assert response.status==200
                request=urllib.request.Request(f'http://127.0.0.1:{port}/api/unlock',data=b'{"password":"smoke-test-only"}',headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=3) as response:
                    assert response.status==200
                    cookie=response.headers['Set-Cookie'].split(';',1)[0]
                run('stop','--time','75',name,stdout=subprocess.DEVNULL)
                code=run('inspect',name,'--format','{{.State.ExitCode}}',capture_output=True).stdout.strip();assert code=='0',code
                if cycle==0:run('start',name,stdout=subprocess.DEVNULL)
            assert (config/'state-format.json').exists()
            print('Container smoke passed: non-root health, authenticated API, clean stop, persistent restart.')
        finally:
            subprocess.run([*engine,'rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


if __name__=='__main__':main()
