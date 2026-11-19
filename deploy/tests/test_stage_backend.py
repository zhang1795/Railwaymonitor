import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('stage_backend',Path(__file__).resolve().parents[1]/'stage_backend.py')
stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)


class ImmutableBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'backend.jar';self.source.write_bytes(b'version one')
        self.releases=self.root/'releases'

    def test_rebuild_does_not_modify_previous_runtime_release(self):
        old=stage.stage_artifact(self.source,self.releases)
        self.source.write_bytes(b'version two')
        new=stage.stage_artifact(self.source,self.releases)
        self.assertNotEqual(old,new);self.assertEqual(old.read_bytes(),b'version one');self.assertEqual(new.read_bytes(),b'version two')

    def test_repeated_stage_preserves_existing_inode(self):
        old=stage.stage_artifact(self.source,self.releases);inode=old.stat().st_ino
        self.assertEqual(stage.stage_artifact(self.source,self.releases).stat().st_ino,inode)

    def test_corrupt_runtime_release_is_not_silently_replaced(self):
        old=stage.stage_artifact(self.source,self.releases);old.chmod(0o600);old.write_bytes(b'corrupted')
        with self.assertRaisesRegex(RuntimeError,'modified'):stage.stage_artifact(self.source,self.releases)
        self.assertEqual(old.read_bytes(),b'corrupted')

    def test_copy_race_does_not_publish_partial_build(self):
        copy=shutil.copyfile
        def change(source,destination):
            source.write_bytes(b'changed during build');return copy(source,destination)
        with patch.object(stage.shutil,'copyfile',side_effect=change):
            with self.assertRaisesRegex(RuntimeError,'changed while staging'):stage.stage_artifact(self.source,self.releases)
        self.assertEqual(list(self.releases.glob('**/backend.jar')),[])
