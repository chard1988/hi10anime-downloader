"""Record explicit beta exceptions without suppressing scanner findings or stable gates."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shlex
import subprocess
import tomllib


def evaluate(report,sandbox_code,sandbox_log):
    if not isinstance(report,dict) or not isinstance(report.get('matches'),list):
        raise ValueError('No complete vulnerability report; publication is blocked.')
    counts=Counter(match['vulnerability']['severity'] for match in report['matches'])
    known_sandbox_failure=any(marker in sandbox_log.lower() for marker in
        ('no usable sandbox','sandboxing failed','zygote process exited prematurely'))
    if sandbox_code and not known_sandbox_failure:
        raise ValueError('Unexpected browser failure; publication is blocked. Read browser-sandbox.txt.')
    return {'scan_complete':True,'vulnerability_gate_pass':not (counts['High'] or counts['Critical']),
            'findings':dict(counts),'sandbox_gate_pass':sandbox_code==0,
            'stable_release_approved':False,
            'beta_policy':'Owner authorized a testing prerelease on 2026-11-17 with disclosed scan findings and hardened-browser compatibility limits. No findings are ignored or waived for stable release.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--engine',default='docker');parser.add_argument('--image',default='hi10-release:candidate');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];artifacts=root/'artifacts';artifacts.mkdir(exist_ok=True)
    engine=shlex.split(args.engine)
    package_version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version']
    version_match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)b(\d+)',package_version)
    if not version_match:raise ValueError('Only beta audits may use this release policy.')
    expected_version='.'.join(version_match.groups()[:3])+'-beta.'+version_match[4]
    image=json.loads(subprocess.check_output([*engine,'image','inspect',args.image],text=True))[0]
    if image.get('Config',{}).get('Labels',{}).get('org.opencontainers.image.version')!=expected_version:
        raise RuntimeError('Image version does not match the release source; publication is blocked.')
    sbom=json.loads((artifacts/'sbom.cdx.json').read_text())
    if not any(c.get('name')=='hi10-downloader' and c.get('version')==package_version for c in sbom.get('components',[])):
        raise RuntimeError('SBOM does not contain this application version; publication is blocked.')
    with (artifacts/'browser-sandbox.txt').open('w') as output:
        sandbox=subprocess.run([*engine,'run','--rm','--shm-size=1g','--cap-drop=ALL','--security-opt=no-new-privileges','--entrypoint','python','-v',f'{root}/tests:/tests:ro',args.image,'/tests/browser_sandbox.py'],stdout=output,stderr=subprocess.STDOUT)
    with (artifacts/'vulnerabilities.json').open('w') as output,(artifacts/'scanner-log.txt').open('w') as errors:
        scan=subprocess.run([str(root/'.tools/grype'),'sbom:'+str(artifacts/'sbom.cdx.json'),'--fail-on','high','-o','json'],stdout=output,stderr=errors)
    if scan.returncode not in {0,2}:
        raise RuntimeError('Scanner failed to execute; publication is blocked. Read scanner-log.txt.')
    summary=evaluate(json.loads((artifacts/'vulnerabilities.json').read_text()),sandbox.returncode,(artifacts/'browser-sandbox.txt').read_text())
    if scan.returncode==2 and summary['vulnerability_gate_pass']:
        raise RuntimeError('Unexpected scanner exit status; publication is blocked.')
    tests=(artifacts/'unit-tests.txt').read_text()
    match=re.search(r'Ran (\d+) tests',tests)
    if not match or not re.search(r'^OK$',tests,re.M):
        raise RuntimeError('Missing passing unit test evidence; publication is blocked.')
    summary['python_tests']=int(match[1])
    summary['image_id']=image['Id']
    summary['package_version']=package_version
    summary['image_version']=expected_version
    (artifacts/'beta-validation.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if not summary['vulnerability_gate_pass'] or not summary['sandbox_gate_pass']:
        print('::warning::Testing beta only: security/compatibility gates remain open. See attached reports; no stable/latest tag is published.')


if __name__=='__main__':main()
