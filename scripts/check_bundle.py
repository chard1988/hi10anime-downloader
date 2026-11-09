"""Verify source-bundle integrity and absence of private runtime files."""
import hashlib
from pathlib import PurePosixPath
import tarfile

with tarfile.open('dist/hi10-unraid.tar.gz') as archive:
    members=archive.getmembers()
    assert sum(m.size for m in members)<20*1024**2
    for member in members:
        path=PurePosixPath(member.name)
        assert member.isfile() and path.parts[0]=='hi10-unraid' and '..' not in path.parts
        assert not any(part in {'.hi10','downloads','appdata','.venv','.tools','.git'} for part in path.parts)
        assert not path.name.endswith(('.bak','.corrupt','.pyc'))
        assert path.name not in {'session.json','downloads.json','web-password.json','.env'}
    lines=archive.extractfile('hi10-unraid/SHA256SUMS').read().decode().splitlines()
    for line in lines:
        digest,name=line.split('  ',1)
        assert hashlib.sha256(archive.extractfile('hi10-unraid/'+name).read()).hexdigest()==digest
print('Source bundle checksums, paths and runtime-state exclusions verified.')
