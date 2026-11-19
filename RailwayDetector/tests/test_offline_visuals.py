"""Optional rendering assets must not block a cold detector process."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class OfflineVisualTests(unittest.TestCase):
    def test_empty_font_cache_import_and_fallback_never_download(self):
        with tempfile.TemporaryDirectory() as folder:
            env=os.environ.copy()
            for name,child in (('YOLOV5_CONFIG_DIR','yolo'),('MPLCONFIGDIR','matplotlib'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache')):
                env[name]=str(Path(folder)/child)
            script="""
from unittest.mock import patch
with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')), patch('torch.hub.download_url_to_file',side_effect=AssertionError('font download forbidden')):
    import utils.plots as plots
    font=plots.check_pil_font(font='intentionally-absent-font.ttf',size=12)
    assert font is not None
    assert font.getmask('offline').size[0]>0
"""
            result=subprocess.run([sys.executable,'-c',script],cwd=str(Path(__file__).resolve().parents[1]),
                                  env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr[-2500:])
