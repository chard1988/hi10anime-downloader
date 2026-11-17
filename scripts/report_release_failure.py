"""Expose safe fixture/build failure summaries as GitHub check annotations."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]/'artifacts'
for name in ('build-log.txt','unit-tests.txt','browser-ui.txt','browser-extension.txt','lifecycle-99.txt','lifecycle-1000.txt','beta-audit-log.txt','scanner-log.txt','release-preflight.txt','package-preflight.txt'):
    path=root/name
    if path.is_file():
        text='\n'.join(path.read_text(errors='replace').splitlines()[-20:])[-6000:]
        if text:
            text=text.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            print(f'::error title=Release diagnostic {name}::{text}')
