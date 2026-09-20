"""Hash-verified durable dashboard snapshots and isolated update sources."""
import hashlib
import json
import shutil
from pathlib import Path
from collector import DataError, atomic_json

def snapshot_source(root,asof):
    version=read_snapshot(root,asof).get('source_id')
    if version and (len(version)!=32 or any(c not in '0123456789abcdef' for c in version)):raise DataError('Invalid source identity')
    base=Path(root)/'snapshots'/asof
    return base/version if version else base

def publish_snapshot(root,payload,source):
    import uuid
    root,source=Path(root),Path(source);payload=dict(payload);asof=payload['asof'];version=uuid.uuid4().hex;target=root/'snapshots'/asof/version
    paths=['quality/latest_run.json','quality/history_run.json',f'raw/selected/{asof}.csv',f'raw/curve/{asof}.csv']
    history=json.loads((source/'quality/history_run.json').read_text(encoding='utf-8'))
    for entry in history['prepared']:
        safe=entry['ts_code'].replace('.','_')
        paths.extend([f'processed/history/{safe}.csv',f'processed/history/{safe}.rolls.csv',f'processed/pair_history/{safe}.csv'])
    for relative in paths:
        src=source/relative;dst=target/relative;dst.parent.mkdir(parents=True,exist_ok=True)
        if src.exists() and src.resolve()!=dst.resolve():
            shutil.copy2(src,dst)
            if hashlib.sha256(src.read_bytes()).digest()!=hashlib.sha256(dst.read_bytes()).digest():raise DataError('Snapshot copy hash mismatch')
    for relative in ['supplemental/fundamentals.csv','raw/reference/quote_units.json']:
        src=source/relative;dst=target/relative
        if src.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    payload['source_id']=version
    payload['data_hash']=hashlib.sha256(json.dumps(dict(asof=asof,history=history,phase_settings=payload['phase_settings'],records=payload['records'],decisions=payload.get('decisions')),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    checksum=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    atomic_json(dict(payload=payload,sha256=checksum),root/f'processed/dashboard/{asof}.bundle.json')
    return payload

def read_snapshot(root,asof):
    bundle=Path(root)/f'processed/dashboard/{asof}.bundle.json'
    if bundle.exists():
        value=json.loads(bundle.read_text(encoding='utf-8'))
        if hashlib.sha256(json.dumps(value['payload'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=value['sha256']:raise DataError('Dashboard snapshot hash mismatch')
        return value['payload']
    path=Path(root)/f'processed/dashboard/{asof}.json';receipt=path.with_suffix('.receipt.json')
    if not path.exists() or not receipt.exists():raise DataError('Requested dashboard snapshot unavailable')
    metadata=json.loads(receipt.read_text(encoding='utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:raise DataError('Dashboard snapshot hash mismatch')
    return json.loads(path.read_text(encoding='utf-8'))

def list_snapshots(root):
    values=[]
    directory=Path(root)/'processed/dashboard'
    for path in [directory/f'{day}.json' for day in {p.name[:8] for pattern in ['????????.json','????????.bundle.json'] for p in directory.glob(pattern)}]:
        try:
            payload=read_snapshot(root,path.stem);values.append(dict(asof=path.stem,universe=len(payload['curves']),data_hash=payload['data_hash']))
        except (DataError,OSError,ValueError):continue
    return sorted(values,key=lambda entry:entry['asof'],reverse=True)
