import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'skills/modelmate-ops/assets/starter'
spec = importlib.util.spec_from_file_location('mm_starter', SOURCE / 'main.py')
starter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(starter)


class StarterTests(unittest.TestCase):
    def test_actual_argv_forms_and_override(self):
        for key in ('CONFIG', 'config', '--CONFIG', '--config'):
            for args in ([key + '="config.json"'], [key, '"config.json"']):
                with self.subTest(args=args):
                    self.assertEqual(starter.parse_args(['--checkpoint_url=""', '--data_url', '', *args], {})[0], 'config.json')
        self.assertEqual(starter.parse_args(['--config='], {'CONFIG': 'old.json'})[0], 'config.json')
        self.assertEqual(starter.parse_args(['--config=a.json', '--CONFIG=b.json'], {})[0], 'b.json')
        with self.assertRaises(ValueError):
            starter.parse_args(['--confg=bad'], {})

    def test_formal_job_rejects_ephemeral_default(self):
        with self.assertRaises(ValueError):
            starter.load_config('config.json', {'MANAS_JOB_TYPE': 'training'})

    def test_independent_training_runs_and_data_identity(self):
        with tempfile.TemporaryDirectory() as name:
            project = Path(name) / 'demo'
            shutil.copytree(SOURCE, project, ignore=shutil.ignore_patterns('__pycache__'))
            env = dict(os.environ)
            env.pop('CONFIG', None)
            env.pop('MANAS_JOB_TYPE', None)
            for _ in range(2):
                result = subprocess.run([sys.executable, str(project / 'main.py'), '--checkpoint_url=""', '--CONFIG="config.json"'],
                                        capture_output=True, text=True, encoding='utf-8', env=env, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
            outputs = list((project / 'outputs').glob('*/result.json'))
            self.assertEqual(len(outputs), 2)
            report = json.loads(outputs[0].read_text())
            self.assertEqual(report['rows'], 64)
            self.assertLess(report['final_mse'], 1e-12)
            self.assertAlmostEqual(report['weight'], 3)
            self.assertAlmostEqual(report['bias'], -0.5)
            (project / 'data/linear64.jsonl').write_text('unexpected data')
            result = subprocess.run([sys.executable, str(project / 'main.py')], capture_output=True,
                                    text=True, env=env, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((project / 'data/linear64.jsonl').read_text(), 'unexpected data')


if __name__ == '__main__':
    unittest.main()
