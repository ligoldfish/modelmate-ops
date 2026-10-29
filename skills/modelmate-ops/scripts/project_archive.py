#!/usr/bin/env python3
"""Bounded code bundles, verified fresh-directory deployment, explicit result exports."""
from __future__ import annotations

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

MANIFEST = '.modelmate-manifest.json'
SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
             'checkpoints', 'outputs', 'results', 'logs', '.private', 'profiles'}
SECRET_NAMES = {'id_rsa', 'id_ed25519', 'password.txt', 'connection.json', '.env'}
SKIP_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.pt', '.pth', '.bin', '.ckpt', '.safetensors',
                 '.zip', '.tar', '.gz', '.pyc', '.jsonl', '.csv', '.tsv', '.parquet', '.arrow', '.npy', '.npz', '.h5', '.hdf5'}


def relative_name(value):
    if '\\' in value or ':' in value or '\x00' in value:
        raise ValueError('Use a relative POSIX path: ' + value)
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or p.as_posix() != value or value == '.':
        raise ValueError('Unsafe or non-canonical relative path: ' + value)
    return p


def secret_name(name):
    base = PurePosixPath(name).name.lower()
    return base in SECRET_NAMES or base.startswith('.env.') or fnmatch.fnmatch(base, 'connection.*.json') or Path(base).suffix in {'.pem', '.key', '.p12', '.pfx'}


def explicit_file(root, name):
    rel = relative_name(name)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlink not permitted: ' + name)
    if not current.is_file() or root not in current.resolve().parents:
        raise ValueError('Expected a regular file within root: ' + name)
    if secret_name(name):
        raise ValueError('Credential-like file excluded: ' + name)
    return current


def hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def pack(root, output, *, file_list=None, kind='code', max_files=2000,
         max_file_bytes=32 * 1024 ** 2, max_total_bytes=128 * 1024 ** 2):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not root.is_dir() or output == root or root in output.parents:
        raise ValueError('Choose an existing source root and an archive outside it')
    if output.exists():
        raise FileExistsError('Refusing to overwrite archive: ' + str(output))
    excluded, excluded_count = [], 0
    def note_excluded(name, reason):
        nonlocal excluded_count
        excluded_count += 1
        if len(excluded) < 100:
            excluded.append({'path': name, 'reason': reason})
    if file_list is not None:
        names = file_list
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError('File list must be a JSON array of relative file paths')
        paths = [explicit_file(root, n) for n in names]
    else:
        paths, pending, scanned = [], [root], 0
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > max_files * 10 + 100:
                        raise ValueError('Directory-entry bound exceeded; choose a narrower source root or explicit file-list')
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if entry.name in SKIP_DIRS and entry.is_dir(follow_symlinks=False):
                        note_excluded(relative, 'generated/environment directory')
                    elif entry.is_symlink():
                        raise ValueError('Symlink not permitted: ' + relative)
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif secret_name(entry.name) or path.suffix.lower() in SKIP_SUFFIXES:
                        note_excluded(relative, 'credential/asset/archive extension')
                    elif entry.is_file(follow_symlinks=False):
                        paths.append(explicit_file(root, relative))
                        if len(paths) > max_files:
                            raise ValueError('Code file-count bound exceeded; narrow the source root')
        paths.sort(key=lambda p: p.relative_to(root).as_posix())
    if not paths or len(paths) > max_files:
        raise ValueError('Empty source or file-count bound exceeded')
    items, seen, total = [], set(), 0
    for path in paths:
        name = path.relative_to(root).as_posix()
        if name == MANIFEST or name.casefold() in seen:
            raise ValueError('Reserved manifest name or duplicate/case-colliding path: ' + name)
        seen.add(name.casefold())
        size = path.stat().st_size
        total += size
        if size > max_file_bytes or total > max_total_bytes:
            raise ValueError('Byte bound exceeded; separate code from large assets/results')
        if kind == 'results' and Path(name).suffix.lower() in {'.pt', '.pth', '.bin', '.ckpt', '.safetensors'}:
            raise ValueError('Model weights do not belong in this analysis export')
        items.append({'path': name, 'bytes': size, 'sha256': hash_file(path)})
    manifest = {'format': 'modelmate-bundle-v1', 'kind': kind,
                'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'file_count': len(items), 'total_bytes': total, 'files': items,
                'excluded_count': excluded_count, 'excluded_paths_first_100': excluded}
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for item in items:
            path = root / item['path']
            # Write the exact bytes whose hash is recorded, not a second unverified read.
            data = path.read_bytes()
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise RuntimeError('Source changed while packaging: ' + item['path'])
            archive.writestr(item['path'], data)
        archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return {'archive': str(output), 'sha256': hash_file(output), 'files': len(items), 'source_bytes': total,
            'status': 'complete', 'selection': 'explicit list' if file_list is not None else 'code filters; review included manifest and exclusions',
            'excluded_count': excluded_count, 'excluded_paths_first_100': excluded}


def unpack(archive_path, destination, max_files=2000, max_file_bytes=32 * 1024 ** 2,
           max_total_bytes=128 * 1024 ** 2):
    archive_path, destination = Path(archive_path).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Deployment destination must be a new directory')
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > max_files + 1:
            raise ValueError('Archive file-count bound exceeded')
        seen = set()
        for info in infos:
            relative_name(info.filename)
            if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ValueError('Only unencrypted regular-file entries are accepted')
            if info.filename.casefold() in seen:
                raise ValueError('Duplicate/case-colliding archive member')
            seen.add(info.filename.casefold())
        if MANIFEST not in archive.namelist() or archive.getinfo(MANIFEST).file_size > 2 * 1024 ** 2:
            raise ValueError('Bundle must have a bounded manifest produced by this tool')
        manifest = json.loads(archive.read(MANIFEST))
        if manifest.get('format') != 'modelmate-bundle-v1' or not isinstance(manifest.get('files'), list):
            raise ValueError('Unsupported bundle manifest')
        rows = manifest['files']
        if len(rows) > max_files or len(rows) + 1 != len(infos):
            raise ValueError('Manifest/member count mismatch')
        declared = set()
        total = 0
        for row in rows:
            name = row['path']
            relative_name(name)
            if name == MANIFEST or name in declared or secret_name(name):
                raise ValueError('Manifest contains duplicate/reserved/credential-like member')
            declared.add(name)
            info = archive.getinfo(name)
            total += info.file_size
            if info.file_size != row['bytes'] or info.file_size > max_file_bytes or total > max_total_bytes:
                raise ValueError('Archive byte bound or declared size mismatch')
            digest = hashlib.sha256()
            with archive.open(info) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != row['sha256']:
                raise ValueError('Member SHA256 mismatch: ' + name)
        if declared | {MANIFEST} != set(archive.namelist()):
            raise ValueError('Unlisted archive members')
        # No user files have been written before all members pass validation.
        destination.mkdir(parents=False, exist_ok=False)
        for row in rows:
            target = destination / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(row['path']) as source, target.open('xb') as out:
                while chunk := source.read(1024 * 1024):
                    out.write(chunk)
            if hash_file(target) != row['sha256']:
                raise RuntimeError('Deployed content hash mismatch')
        (destination / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'destination': str(destination), 'files': len(rows), 'bytes': total, 'status': 'verified'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('pack', 'export'):
        ap = sub.add_parser(name)
        ap.add_argument('--source' if name == 'pack' else '--root', required=True, dest='root', type=Path)
        ap.add_argument('--output', required=True, type=Path)
        ap.add_argument('--file-list', type=Path, required=name == 'export')
        ap.add_argument('--max-files', type=int, default=2000)
        ap.add_argument('--max-file-bytes', type=int, default=32 * 1024 ** 2)
        ap.add_argument('--max-total-bytes', type=int, default=128 * 1024 ** 2)
    ap = sub.add_parser('unpack')
    ap.add_argument('--archive', required=True, type=Path)
    ap.add_argument('--destination', required=True, type=Path)
    ap.add_argument('--max-files', type=int, default=2000)
    ap.add_argument('--max-file-bytes', type=int, default=32 * 1024 ** 2)
    ap.add_argument('--max-total-bytes', type=int, default=128 * 1024 ** 2)
    args = parser.parse_args(argv)
    limits = {n: getattr(args, n) for n in ('max_files', 'max_file_bytes', 'max_total_bytes')}
    if any(value <= 0 for value in limits.values()):
        raise ValueError('All bounds must be positive')
    if args.action == 'unpack':
        result = unpack(args.archive, args.destination, **limits)
    else:
        names = json.loads(args.file_list.read_text(encoding='utf-8-sig')) if args.file_list else None
        result = pack(args.root, args.output, file_list=names,
                      kind='results' if args.action == 'export' else 'code', **limits)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
