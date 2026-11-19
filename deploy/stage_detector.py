"""Publish a content-addressed detector source/config release; weights stay explicit."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

def stage_source_tree(source,release_root,required=('ui.py','track_events.py')):
    source=Path(source).resolve();release_root=Path(release_root);release_root.mkdir(parents=True,exist_ok=True)
    files={}
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source)
        if any(part.startswith('.') or part in ('__pycache__','tests') for part in relative.parts):continue
        if not path.is_file() or (path.suffix not in ('.py','.yaml','.yml') and path.name!='requirements.txt'):continue
        if source not in path.resolve().parents:raise RuntimeError('Detector source link escapes project')
        files[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    if any(name not in files for name in required):raise RuntimeError('Incomplete runtime source')
    manifest=json.dumps(files,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(manifest.encode()).hexdigest();destination=release_root/digest
    def verify():
        if (destination/'manifest.json').read_text()!=manifest:raise RuntimeError('Detector release manifest changed')
        for name,expected in files.items():
            if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Detector release modified')
    if destination.exists():verify();return destination
    temp=Path(tempfile.mkdtemp(prefix='.detector-',dir=release_root))
    try:
        for name,expected in files.items():
            content=(source/name).read_bytes()
            if hashlib.sha256(content).hexdigest()!=expected:raise RuntimeError('Detector source changed while staging')
            path=temp/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content);path.chmod(0o444)
        (temp/'manifest.json').write_text(manifest);(temp/'manifest.json').chmod(0o444)
        try:os.rename(temp,destination)
        except FileExistsError:verify()
        for directory in sorted([p for p in destination.rglob('*') if p.is_dir()],reverse=True):directory.chmod(0o555)
        destination.chmod(0o555)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return destination

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    print(stage_source_tree(root/'RailwayDetector',root/'workspace/runtime/releases/detector'))
