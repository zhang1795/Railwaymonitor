"""Publish a verified immutable runtime copy, separate from Maven's target/."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def stage_artifact(source,release_root):
    source=Path(source);expected=digest(source)
    directory=Path(release_root)/expected;directory.mkdir(parents=True,exist_ok=True)
    destination=directory/source.name
    if destination.exists():
        if digest(destination)!=expected:raise RuntimeError('Existing immutable release was modified')
        return destination
    fd,temp=tempfile.mkstemp(prefix='.stage-',dir=directory);os.close(fd);temp=Path(temp)
    try:
        shutil.copyfile(source,temp)
        if digest(temp)!=expected:raise RuntimeError('Build artifact changed while staging; retry after build completion')
        temp.chmod(0o444)
        try:os.link(temp,destination)  # atomic publish, never overwrite a running release
        except FileExistsError:
            if digest(destination)!=expected:raise RuntimeError('Concurrent immutable release mismatch')
    finally:temp.unlink(missing_ok=True)
    return destination


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    print(stage_artifact(root/'web-springboot/target/railway-monitoring-1.0.0.jar',root/'workspace/runtime/releases/backend'))
