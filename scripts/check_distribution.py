"""Offline source/metadata gate; it does not claim CA approval."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
for name in ('LICENSE','SECURITY.md','CHANGELOG.md','CONTRIBUTING.md','requirements.lock','ca_profile.xml','assets/icon.svg'):
    assert (root/name).is_file(),name
profile=ET.parse(root/'ca_profile.xml').getroot()
assert profile.findtext('Profile','').strip()
template=ET.parse(root/'unraid/hi10-downloader.xml').getroot()
assert template.findtext('Privileged')=='false'
assert 'MIT License' in (root/'LICENSE').read_text()
assert '--require-hashes' in (root/'Dockerfile').read_text()
assert '@sha256:' in (root/'Dockerfile').read_text()
for file in (root/'.github/workflows').glob('*.yml'):
    for match in re.finditer(r'uses:\s*([^\s]+)',file.read_text()):
        assert re.search(r'@[a-f0-9]{40}$',match[1]),match[1]
print('Offline distribution checks passed. Live repository/image/support URLs and CA Scan remain external gates.')
