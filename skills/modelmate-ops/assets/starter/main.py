#!/usr/bin/env python3
"""A tiny real training example for ModelMate deployment, using only stdlib."""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
CONFIG_KEYS = {'CONFIG', 'config', '--CONFIG', '--config'}
STORAGE_KEYS = {'--checkpoint_url', '--data_url', '--train_url', '--result_url', '--model_url', '--obs_url'}


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_args(argv, environment=None):
    environment = os.environ if environment is None else environment
    config = unquote(environment.get('CONFIG', ''))
    check, prepare_only, ignored = False, False, []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in ('-h', '--help'):
            print('Usage: main.py [--config config.json] [--check | --prepare-only]')
            print('CONFIG/config/--CONFIG/--config support =VALUE and separate VALUE.')
            print('Known platform storage arguments are accepted; unknown options fail.')
            raise SystemExit(0)
        if token in ('--check', '--prepare-only'):
            check = check or token == '--check'
            prepare_only = prepare_only or token == '--prepare-only'
            i += 1
            continue
        key, equal, value = token.partition('=')
        if key not in CONFIG_KEYS and key not in STORAGE_KEYS:
            raise ValueError('Unknown option: ' + token)
        if not equal:
            i += 1
            if i >= len(argv) or argv[i].startswith('--'):
                raise ValueError('Missing value for ' + key)
            value = argv[i]
        if key in CONFIG_KEYS:
            config = unquote(value)
        else:
            ignored.append(key)  # Storage argument values may contain secrets.
        i += 1
    if check and prepare_only:
        raise ValueError('Choose --check or --prepare-only')
    return config or 'config.json', check, prepare_only, ignored


def resolve_path(value):
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def load_config(name, environment=None):
    environment = os.environ if environment is None else environment
    path = resolve_path(name)
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    steps, lr = int(config.get('steps', 200)), float(config.get('learning_rate', 0.2))
    if not 1 <= steps <= 1000 or not math.isfinite(lr) or not 0 < lr <= 0.5:
        raise ValueError('Use 1..1000 steps and a finite learning_rate in (0, 0.5]')
    raw_output = config.get('output_root', 'outputs')
    job_type = environment.get('MANAS_JOB_TYPE', '').lower()
    if job_type and job_type != 'notebook' and not Path(raw_output).expanduser().is_absolute():
        raise ValueError('Formal platform job: set output_root in config.json to a verified writable persistent absolute path')
    return {'config_path': str(path), 'data_file': resolve_path(config.get('data_file', 'data/linear64.jsonl')),
            'output_root': resolve_path(raw_output), 'steps': steps, 'learning_rate': lr,
            'platform_job_type': job_type or None}


def prepare(path):
    rows = [{'id': i, 'x': 2 * i / 63 - 1, 'y': 3 * (2 * i / 63 - 1) - 0.5} for i in range(64)]
    raw = ''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows).encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError('Existing data differs; refusing to overwrite ' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    return rows, digest


def mse(rows, weight, bias):
    return sum((weight * r['x'] + bias - r['y']) ** 2 for r in rows) / len(rows)


def train(config, ignored):
    rows, data_sha = prepare(config['data_file'])
    now = datetime.datetime.now(datetime.timezone.utc)
    run_id = 'starter-' + now.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    output = config['output_root'] / run_id
    output.mkdir(parents=True, exist_ok=False)
    resolved = {k: str(v) if isinstance(v, Path) else v for k, v in config.items()}
    resolved.update(run_id=run_id, python=sys.executable, hostname=socket.gethostname(),
                    output_dir=str(output), ignored_platform_arguments=ignored)
    (output / 'resolved.json').write_text(json.dumps(resolved, indent=2) + '\n', encoding='utf-8')
    print('STARTER_RUN=' + json.dumps(resolved), flush=True)
    start, weight, bias, history = time.perf_counter(), 0.0, 0.0, []
    initial = mse(rows, weight, bias)
    with (output / 'metrics.jsonl').open('x', encoding='utf-8') as log:
        for step in range(1, config['steps'] + 1):
            errors = [(weight * r['x'] + bias - r['y'], r['x']) for r in rows]
            weight -= config['learning_rate'] * 2 * sum(e * x for e, x in errors) / len(rows)
            bias -= config['learning_rate'] * 2 * sum(e for e, x in errors) / len(rows)
            if step == 1 or step % 50 == 0 or step == config['steps']:
                item = {'step': step, 'mse': mse(rows, weight, bias)}
                history.append(item)
                log.write(json.dumps(item) + '\n')
                log.flush()
                print('METRIC=' + json.dumps(item), flush=True)
    result = {'kind': 'modelmate_starter_cpu_training', 'rows': len(rows), 'steps': config['steps'],
              'initial_mse': initial, 'final_mse': mse(rows, weight, bias), 'weight': weight, 'bias': bias,
              'elapsed_seconds': time.perf_counter() - start, 'data_sha256': data_sha,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'platform_job_type': config['platform_job_type'],
              'hostname': socket.gethostname(), 'python': sys.executable, 'history': history}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('COMPLETE=' + str(output / 'result.json'), flush=True)
    return result


def main(argv=None):
    name, check, prepare_only, ignored = parse_args(sys.argv[1:] if argv is None else argv)
    config = load_config(name)
    if check:
        print(json.dumps({'check': 'config_parsed', 'python': sys.executable,
                          **{k: str(v) if isinstance(v, Path) else v for k, v in config.items()},
                          'ignored_platform_arguments': ignored, 'npu_checked': False}))
    elif prepare_only:
        rows, sha = prepare(config['data_file'])
        print(json.dumps({'data_file': str(config['data_file']), 'rows': len(rows), 'sha256': sha}))
    else:
        train(config, ignored)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('STARTER_ERROR=' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
