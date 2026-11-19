import importlib.util,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('stage_detector',Path(__file__).resolve().parents[1]/'stage_detector.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class DetectorReleaseTests(unittest.TestCase):
    def test_rebuild_keeps_the_running_source_release_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();(source/'ui.py').write_text('version=1');(source/'track_events.py').write_text('v=1')
            first=module.stage_source_tree(source,root/'releases');(source/'ui.py').write_text('version=2')
            second=module.stage_source_tree(source,root/'releases')
            self.assertNotEqual(first,second);self.assertEqual((first/'ui.py').read_text(),'version=1');self.assertEqual((second/'ui.py').read_text(),'version=2')
    def test_corrupted_published_source_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();(source/'ui.py').write_text('version=1');(source/'track_events.py').write_text('v=1')
            release=module.stage_source_tree(source,root/'releases');(release/'ui.py').chmod(0o644);(release/'ui.py').write_text('tampered')
            with self.assertRaises(RuntimeError):module.stage_source_tree(source,root/'releases')

if __name__=='__main__':unittest.main()
