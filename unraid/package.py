"""Build the source-only unRAID bundle without private runtime data."""
import hashlib
from pathlib import Path
import shutil
import tarfile


def main():
    root = Path(__file__).resolve().parents[1]
    bundle = root / 'dist' / 'hi10-unraid'
    bundle.mkdir(parents=True, exist_ok=True)
    sources = {
        'Dockerfile': root / 'Dockerfile',
        'README.md': root / 'README.md',
        'pyproject.toml': root / 'pyproject.toml',
        'requirements.lock': root / 'requirements.lock',
        'requirements.in': root / 'requirements.in',
        'LICENSE': root / 'LICENSE',
        '.dockerignore': root / '.dockerignore',
        'compose.yaml': root / 'compose.yaml',
        'THIRD_PARTY_NOTICES.md': root / 'THIRD_PARTY_NOTICES.md',
        'SECURITY.md': root / 'SECURITY.md',
        'docs/ADMIN_GUIDE.md': root / 'docs/ADMIN_GUIDE.md',
        'docs/RELEASE_GUIDE.md': root / 'docs/RELEASE_GUIDE.md',
        'docs/HARDENING_PROGRESS.md': root / 'docs/HARDENING_PROGRESS.md',
        'docs/VALIDATION_REPORT.md': root / 'docs/VALIDATION_REPORT.md',
        '.env.example': root / '.env.example',
        'install.sh': root / 'unraid/install.sh',
        'INSTALL.txt': root / 'unraid/INSTALL.txt',
        'hi10-downloader.xml': root / 'unraid/hi10-downloader.xml',
    }
    sources.update({str(path.relative_to(root)): path for path in (root / 'src').rglob('*')
                    if path.is_file() and (path.suffix == '.py' or 'static' in path.parts)
                    and '__pycache__' not in path.parts})
    for name, source in sources.items():
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    checksums = ''.join(f'{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n'
                        for name in sorted(sources))
    (bundle / 'SHA256SUMS').write_text(checksums)
    archive = root / 'dist/hi10-unraid.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for name in sorted([*sources, 'SHA256SUMS']):
            tar.add(bundle / name, arcname=f'hi10-unraid/{name}', recursive=False)
    print(f'{archive} ({archive.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
