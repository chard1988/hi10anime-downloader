"""Assemble an allowlisted beta release; never package local runtime state."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from release_metadata import metadata
import tomllib


def main():
    root=Path(__file__).resolve().parents[1]
    version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
    data=metadata(version,sys.argv[1],'chard1988/hi10anime-downloader')
    subprocess.run([sys.executable,str(root/'unraid/package.py')],check=True)
    subprocess.run([sys.executable,str(root/'scripts/check_bundle.py')],cwd=root,check=True)
    report=json.loads((root/'artifacts/beta-validation.json').read_text())
    if report.get('package_version')!=version or report.get('image_version')!=data['version']:
        raise ValueError('Validation evidence does not match this release version.')
    destination=root/'dist/release';destination.mkdir(parents=True,exist_ok=True)
    files={'hi10-unraid.tar.gz':root/'dist/hi10-unraid.tar.gz',
           'hi10-downloader.xml':root/'unraid/hi10-downloader.xml',
           'INSTALL.md':root/'docs/UNRAID_INSTALL.md',
           'sbom.cdx.json':root/'artifacts/sbom.cdx.json',
           'vulnerabilities.json':root/'artifacts/vulnerabilities.json',
           'beta-validation.json':root/'artifacts/beta-validation.json',
           'browser-sandbox.txt':root/'artifacts/browser-sandbox.txt',
           'image-digest.txt':root/'artifacts/image-digest.txt',
           'build-metadata.json':root/'artifacts/build-metadata.json'}
    expected=set(files)|{'hi10-session-export.zip','SHA256SUMS'}
    if any(p.name not in expected for p in destination.iterdir()):
        raise ValueError('Unexpected file in release output directory; inspect it before publishing.')
    for name,source in files.items():shutil.copy2(source,destination/name)
    extension=root/'browser-extension/hi10-session-export'
    with zipfile.ZipFile(destination/'hi10-session-export.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('README.md','manifest.json','exporter.js','popup.js','popup.css','popup.html'):
            archive.write(extension/name,'hi10-session-export/'+name)
    sums=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(destination.iterdir()) if p.name!='SHA256SUMS')
    (destination/'SHA256SUMS').write_text(sums)
    report=json.loads((root/'artifacts/beta-validation.json').read_text())
    notes=(root/'docs/releases'/f'{data["tag"]}.md').read_text()
    counts=report['findings']
    notes+=f'\n## Exact-image validation\n\n- Python tests: {report["python_tests"]} passed.\n- Image scan: {counts.get("Critical",0)} critical, {counts.get("High",0)} high findings.\n- Hardened Chromium sandbox check: {"passed" if report["sandbox_gate_pass"] else "failed; use session import"}.\n- Stable-release gates: not approved.\n\n'
    notes+='Image reference/digest:\n\n```text\n'+(root/'artifacts/image-digest.txt').read_text().strip()+'\n```\n'
    (root/'artifacts/release-notes.md').write_text(notes)
    print(f'Release assets prepared for {data["tag"]}; nothing published by this script.')


if __name__=='__main__':main()
