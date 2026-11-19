"""Read the existing trusted deployment weight; no inference or network services."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
os.environ['YOLOV5_CONFIG_DIR'] = str(ROOT / 'workspace/runtime/config/yolov5')
os.environ['MPLCONFIGDIR'] = '/tmp/railway-audit-matplotlib'
sys.path.insert(0, str(ROOT / 'RailwayDetector'))
from models.experimental import attempt_load

if __name__ == '__main__':
    weights = ROOT / 'RailwayDetector/models/best1030.pt'
    model = attempt_load(str(weights), map_location='cpu')
    counts = Counter(type(module).__module__ + '.' + type(module).__name__
                     for module in model.modules())
    print(json.dumps({
        'weight_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
        'parameters_after_fusion': sum(p.numel() for p in model.parameters()),
        'strides': model.stride.tolist(), 'class_names': model.names,
        'module_counts_after_fusion': dict(counts),
        'contains_mobilevit_named_module': any('mobilevit' in name.lower() for name in counts),
    }, ensure_ascii=False, indent=2))
