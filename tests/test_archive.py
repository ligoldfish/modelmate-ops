import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

MODULE = Path(__file__).resolve().parents[1] / 'skills/modelmate-ops/scripts/project_archive.py'
spec = importlib.util.spec_from_file_location('mm_archive', MODULE)
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'main.py').write_text('print("hello")\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_code_roundtrip_excludes_assets_and_secrets(self):
        (self.source / 'data').mkdir()
        (self.source / 'data/train.jsonl').write_text('{"x":1}')
        (self.source / '.env').write_text('synthetic-not-a-real-secret')
        path = self.root / 'code.zip'
        result = archive.pack(self.source, path)
        self.assertEqual(result['files'], 1)
        dest = self.root / 'deployed'
        archive.unpack(path, dest)
        self.assertEqual((dest / 'main.py').read_bytes(), (self.source / 'main.py').read_bytes())
        self.assertFalse((dest / '.env').exists())

    def test_models_and_datasets_source_packages_are_preserved(self):
        for folder in ('models', 'datasets', 'data'):
            (self.source / folder).mkdir()
            (self.source / folder / '__init__.py').write_text('VALUE = 42\n')
        p = self.root / 'packages.zip'
        result = archive.pack(self.source, p)
        self.assertEqual(result['files'], 4)
        target = self.root / 'packages'
        archive.unpack(p, target)
        for folder in ('models', 'datasets', 'data'):
            self.assertTrue((target / folder / '__init__.py').is_file())

    def test_export_uses_explicit_files_without_walk(self):
        (self.source / 'outputs').mkdir()
        (self.source / 'outputs/result.json').write_text('{"passed":true}')
        with mock.patch.object(archive.os, 'scandir', side_effect=AssertionError('must not scan')):
            result = archive.pack(self.source, self.root / 'results.zip',
                                  file_list=['outputs/result.json'], kind='results')
        self.assertEqual(result['files'], 1)

    def test_traversal_rejected_before_destination_created(self):
        p = self.root / 'malicious.zip'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('../outside.py', 'bad')
        target = self.root / 'fresh'
        with self.assertRaises(ValueError):
            archive.unpack(p, target)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / 'outside.py').exists())

    def test_tamper_rejected_before_destination_created(self):
        p = self.root / 'valid.zip'
        archive.pack(self.source, p)
        q = self.root / 'tampered.zip'
        with zipfile.ZipFile(p) as src, zipfile.ZipFile(q, 'w') as dst:
            for name in src.namelist():
                dst.writestr(name, b'corrupt' if name == 'main.py' else src.read(name))
        with self.assertRaises(ValueError):
            archive.unpack(q, self.root / 'fresh')
        self.assertFalse((self.root / 'fresh').exists())

    def test_refuses_overwrite_and_size_excess(self):
        p = self.root / 'code.zip'
        archive.pack(self.source, p)
        with self.assertRaises(FileExistsError):
            archive.pack(self.source, p)
        with self.assertRaises(ValueError):
            archive.pack(self.source, self.root / 'small.zip', max_file_bytes=1)
        target = self.root / 'existing'
        target.mkdir()
        with self.assertRaises(FileExistsError):
            archive.unpack(p, target)

    def test_explicit_secret_and_duplicate_are_rejected(self):
        (self.source / 'password.txt').write_text('synthetic')
        with self.assertRaises(ValueError):
            archive.pack(self.source, self.root / 'no.zip', file_list=['password.txt'])
        with self.assertRaises(ValueError):
            archive.pack(self.source, self.root / 'dupe.zip', file_list=['main.py', 'main.py'])


if __name__ == '__main__':
    unittest.main()
