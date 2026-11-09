"""SBOM a local rootless image mount without a container engine API socket."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--inside',action='store_true')
parser.add_argument('--engine',default='podman',help='Podman command, including optional storage flags')
parser.add_argument('--image',default='localhost/hi10-downloader:beta')
parser.add_argument('--output',default='artifacts/sbom.cdx.json')
args=parser.parse_args()
engine=shlex.split(args.engine)
if not args.inside:
    raise SystemExit(subprocess.call([*engine,'unshare',sys.executable,__file__,'--inside','--engine',args.engine,'--image',args.image,'--output',args.output]))
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
mount=subprocess.check_output([*engine,'image','mount',args.image],text=True).strip()
try:
    subprocess.run(['.tools/syft','dir:'+mount,'-o','cyclonedx-json='+args.output],check=True)
finally:
    subprocess.run([*engine,'image','unmount',args.image],check=True)
