import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/check_public_release.py'
spec = importlib.util.spec_from_file_location('mm_public_check', MODULE)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublicReleaseTests(unittest.TestCase):
    def make_root(self, name):
        root = Path(name)
        skill = root / 'skills/modelmate-ops/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: modelmate-ops\ndescription: public example\n---\n', encoding='utf-8')
        return root

    def test_private_directory_not_read_and_code_is_not_a_link(self):
        with tempfile.TemporaryDirectory() as name:
            root = self.make_root(name)
            (root / '.private').mkdir()
            (root / '.private/connection.json').write_text('synthetic private config')
            (root / 'README.md').write_text("```powershell\n$x = [int](Read-Host 'port')\n```\n", encoding='utf-8')
            result = checker.check(root)
            self.assertTrue(result['passed'], result['errors'])
            self.assertEqual(result['files_checked'], 2)

    def test_public_endpoint_and_missing_link_are_detected(self):
        with tempfile.TemporaryDirectory() as name:
            root = self.make_root(name)
            address = '.'.join(map(str, (10, 23, 45, 67)))
            (root / 'README.md').write_text(address + '\n[missing](notthere.md)\n', encoding='utf-8')
            result = checker.check(root)
            self.assertFalse(result['passed'])
            self.assertEqual(len(result['errors']), 2)


if __name__ == '__main__':
    unittest.main()
