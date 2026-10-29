#!/usr/bin/env python3
"""Install the bundled skill locally, preserving an existing installation."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import uuid


def install(source, destination, backup_root):
    source, destination, backup_root = [Path(p).expanduser().resolve() for p in (source, destination, backup_root)]
    if not (source / 'SKILL.md').is_file():
        raise ValueError('Source must be a skill folder with SKILL.md')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate directories')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Refusing to replace a symlink installation')
    temporary = destination.parent / ('.modelmate-install-' + uuid.uuid4().hex)
    shutil.copytree(source, temporary, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    backup = None
    if destination.exists():
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = backup_root / (destination.name + '-' + stamp + '-' + uuid.uuid4().hex[:8])
        # Renaming keeps the original intact; an unsupported cross-device move
        # fails before replacing it, rather than copying and deleting recursively.
        destination.rename(backup)
    try:
        temporary.rename(destination)
    except BaseException:
        if backup is not None and not destination.exists():
            backup.rename(destination)
        raise
    return {'installed': str(destination), 'previous_installation_backup': str(backup) if backup else None,
            'private_connection_profile': 'unchanged'}


def main():
    base = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1] / 'skills' / 'modelmate-ops')
    parser.add_argument('--destination', type=Path, default=base / 'skills' / 'modelmate-ops')
    parser.add_argument('--backup-root', type=Path, default=base / 'skill-backups')
    args = parser.parse_args()
    print(json.dumps(install(args.source, args.destination, args.backup_root), ensure_ascii=False))


if __name__ == '__main__':
    main()
