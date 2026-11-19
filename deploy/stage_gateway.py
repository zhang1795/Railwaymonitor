"""The preview gateway and its decoder must both run from immutable releases."""
from pathlib import Path
from stage_detector import stage_source_tree

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    print(stage_source_tree(root/'web-flask',root/'workspace/runtime/releases/gateway',required=('app.py',)))
