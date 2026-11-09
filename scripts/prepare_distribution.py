"""Generate candidate metadata locally; never publish or submit anything."""
import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repository',required=True,help='GitHub owner/repository');parser.add_argument('--support',required=True);args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repository):raise ValueError('Use owner/repository')
    if not args.support.startswith('https://'):raise ValueError('Support URL must use HTTPS')
    root=Path(__file__).resolve().parents[1];out=root/'artifacts/distribution';out.mkdir(parents=True,exist_ok=True)
    tree=ET.parse(root/'unraid/hi10-downloader.xml');container=tree.getroot()
    values={'Repository':f'ghcr.io/{args.repository.lower()}:beta','Project':f'https://github.com/{args.repository}','Support':args.support,'TemplateURL':f'https://raw.githubusercontent.com/{args.repository}/main/unraid/hi10-downloader.xml','Icon':f'https://raw.githubusercontent.com/{args.repository}/main/assets/icon.svg','License':'MIT','Beta':'true','TailscaleStateDir':'/config/.tailscale_state'}
    for key,value in values.items():
        element=container.find(key)
        if element is None:element=ET.SubElement(container,key)
        element.text=value
    ET.indent(tree);tree.write(out/'hi10-downloader.xml',encoding='utf-8',xml_declaration=True)
    profile=ET.parse(root/'ca_profile.xml');node=profile.getroot()
    for key,value in {'WebPage':values['Project'],'Forum':args.support,'Icon':values['Icon']}.items():ET.SubElement(node,key).text=value
    ET.indent(profile);profile.write(out/'ca_profile.xml',encoding='utf-8',xml_declaration=True)
    print('Candidate metadata written locally; verify real URLs/images and run CA validation before submission.')


if __name__=='__main__':main()
