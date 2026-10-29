import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/install_skill.py'
spec = importlib.util.spec_from_file_location('mm_install', MODULE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_replacement_preserves_previous_and_other_files(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source, target, backups = root / 'source', root / 'skills/modelmate-ops', root / 'backups'
            source.mkdir()
            (source / 'SKILL.md').write_text('new source', encoding='utf-8')
            target.mkdir(parents=True)
            (target / 'SKILL.md').write_text('old source', encoding='utf-8')
            private = root / 'connection.json'
            private.write_text('synthetic profile', encoding='utf-8')
            receipt = installer.install(source, target, backups)
            self.assertEqual((target / 'SKILL.md').read_text(), 'new source')
            self.assertEqual((Path(receipt['previous_installation_backup']) / 'SKILL.md').read_text(), 'old source')
            self.assertEqual(private.read_text(), 'synthetic profile')

    def test_self_install_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'SKILL.md').write_text('source')
            with self.assertRaises(ValueError):
                installer.install(root, root / 'nested', root / 'backups')


if __name__ == '__main__':
    unittest.main()
