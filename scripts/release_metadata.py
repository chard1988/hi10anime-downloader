"""Validate beta-only release refs and keep Python/container versions aligned."""
import os
from pathlib import Path
import re
import sys
import tomllib


def metadata(version, ref, repository):
    match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)b(\d+)',version)
    if not match:
        raise ValueError('This workflow only publishes explicit Python beta versions; stable publishing is disabled.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Invalid repository name')
    major,minor,patch,beta=match.groups()
    semver=f'{major}.{minor}.{patch}-beta.{beta}'
    tag='v'+semver
    if ref not in {tag,'release/'+semver}:
        raise ValueError('Release ref does not match the package beta version.')
    return {'version':semver,'tag':tag,'image':'ghcr.io/'+repository.lower()}


def main():
    root=Path(__file__).resolve().parents[1]
    version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
    result=metadata(version,sys.argv[1],os.environ.get('GITHUB_REPOSITORY','chard1988/hi10anime-downloader'))
    if f'__version__ = "{version}"' not in (root/'src/hi10_downloader/__init__.py').read_text():
        raise ValueError('Python/application version mismatch')
    if f'ARG VERSION={result["version"]}' not in (root/'Dockerfile').read_text():
        raise ValueError('Container/application version mismatch')
    for key,value in result.items():print(f'{key}={value}')


if __name__=='__main__':main()
