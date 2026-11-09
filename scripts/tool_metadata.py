import json
from pathlib import Path
import urllib.request

metadata={}
for name,repo in [('syft','anchore/syft'),('grype','anchore/grype')]:
    with urllib.request.urlopen('https://api.github.com/repos/'+repo+'/releases/latest',timeout=30) as response:
        data=json.load(response)
    metadata[name]={'version':data['tag_name'],'repository':repo}
with urllib.request.urlopen('https://api.github.com/repos/actions/checkout/git/ref/tags/v6',timeout=30) as response:
    metadata['checkout']=json.load(response)['object']
Path('tools.lock.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps(metadata))
