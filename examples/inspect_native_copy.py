"""Read-only QA-copy comparison; differences never certify runtime acceptance.

Run with an installed Static2Live package. This inspects only manifest-tracked
native resources, reports exact JSON leaf changes, and never edits either tree.
"""
import argparse
import json
from pathlib import Path

from static2live.storage import read_json, safe_resource, sha256


def json_changes(before, after, path='$'):
    if isinstance(before, dict) and isinstance(after, dict):
        changes=[]
        for key in sorted(before.keys() | after.keys()):
            child=f'{path}.{key}'
            if key not in before:changes.append({'path':child,'change':'added','after':after[key]})
            elif key not in after:changes.append({'path':child,'change':'removed','before':before[key]})
            else:changes.extend(json_changes(before[key],after[key],child))
        return changes
    if isinstance(before,list) and isinstance(after,list):
        if len(before)!=len(after):return [{'path':path,'change':'array_length','before':len(before),'after':len(after)}]
        return [change for i,(a,b) in enumerate(zip(before,after)) for change in json_changes(a,b,f'{path}[{i}]')]
    # Booleans must not compare equal to numeric 0/1. Numeric serialization
    # differences remain reported; no approximate equivalence is asserted.
    if (isinstance(before,bool)!=isinstance(after,bool)) or before!=after:
        return [{'path':path,'change':'value','before':before,'after':after}]
    return []


def inspect_copy(source,copy):
    source=Path(source).resolve();copy=Path(copy).resolve()
    manifest_hash=sha256(source/'manifest.json');manifest=read_json(source/'manifest.json')
    if manifest.get('generator')!='static2live' or manifest.get('adapter',{}).get('actual')!='native-scene':
        raise ValueError('Source must be a Static2Live native-scene version')
    identical=[];different=[]
    for relative,digest in sorted(manifest['resources'].items()):
        if not relative.startswith('wallpaper-engine/'):continue
        original=safe_resource(source,relative);target=safe_resource(copy,relative[len('wallpaper-engine/'):])
        if sha256(original)!=digest:raise ValueError('Source resource no longer matches manifest: '+relative)
        if not target.is_file():
            different.append({'resource':relative,'change':'missing'});continue
        actual=sha256(target)
        if actual==digest:identical.append(relative);continue
        entry={'resource':relative,'source_sha256':digest,'copy_sha256':actual}
        if original.suffix=='.json':entry['json_changes']=json_changes(read_json(original),read_json(target))
        different.append(entry)
    if sha256(source/'manifest.json')!=manifest_hash:raise ValueError('Source manifest changed during inspection')
    return {'source':str(source),'copy':str(copy),'source_manifest_sha256':manifest_hash,
        'identical_resources':identical,'different_resources':different,
        'runtime_status':'not_tested','note':'Exact comparison only; editor additions or rounding are not automatically accepted as equivalent'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('copy')
    args=parser.parse_args()
    print(json.dumps(inspect_copy(args.source,args.copy),ensure_ascii=False,indent=2))
