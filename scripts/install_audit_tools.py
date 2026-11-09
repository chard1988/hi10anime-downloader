"""Install only hash-verified, version-locked official Syft/Grype Linux binaries."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-hashes',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];lock=root/'tools.lock.json';metadata=json.loads(lock.read_text())
    output=root/'.tools';output.mkdir(exist_ok=True)
    for name in ('syft','grype'):
        tool=metadata[name];version=tool['version'].removeprefix('v')
        filename=f'{name}_{version}_linux_amd64.tar.gz'
        base=f'https://github.com/{tool["repository"]}/releases/download/v{version}/'
        expected=tool.get('sha256')
        if args.refresh_hashes:
            with urllib.request.urlopen(base+f'{name}_{version}_checksums.txt',timeout=60) as response:
                checksums=response.read().decode()
            expected=next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip('*')==filename)
            tool['sha256']=expected
        if not expected:
            raise ValueError('Missing reviewed scanner hash. Refresh and review tools.lock.json first.')
        binary=output/name
        archive=output/filename
        if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
            with urllib.request.urlopen(base+filename,timeout=90) as response,archive.open('wb') as target:
                while chunk:=response.read(1024*1024):target.write(chunk)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
            raise ValueError(f'{name} checksum mismatch')
        with tarfile.open(archive) as tar:
            member=tar.getmember(name)
            if not member.isfile():raise ValueError('Invalid scanner archive')
            binary.write_bytes(tar.extractfile(member).read());binary.chmod(0o755)
        print(f'Verified {name} {version}')
    if args.refresh_hashes:lock.write_text(json.dumps(metadata,indent=2)+'\n')


if __name__=='__main__':main()
