#!/usr/bin/env python3
"""Check public content, self-contained links, and accidental private material."""
from pathlib import Path
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'.git', '.venv', '__pycache__', '.pytest_cache', 'build', 'dist',
           '.private', '_local', 'profiles', 'outputs', 'results', 'logs'}
RFC1918 = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.json', '.yaml', '.yml', '.sh'}
PRIVATE_FILENAMES = {'connection.json', 'password.txt', 'id_rsa', 'id_ed25519', '.env'}


def check(root=ROOT):
    root = Path(root).resolve()
    errors, count, links = [], 0, 0
    if (root / '.git').exists() and shutil.which('git'):
        result = subprocess.run(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                                capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError('Cannot enumerate public Git files')
        paths = [root / value.decode('utf-8') for value in result.stdout.split(b'\0') if value]
    else:
        paths = []
        for directory, dirs, names in os.walk(root):
            dirs[:] = [n for n in dirs if n not in IGNORED]
            paths.extend(Path(directory) / n for n in names)
    for path in paths:
        relative = path.relative_to(root)
        if not path.is_file():
            continue
        count += 1
        if path.name.lower() in PRIVATE_FILENAMES or path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.zip', '.tar', '.gz'}:
            errors.append(f'{relative}: private/generated artifact must not be in public source')
        if path.suffix not in TEXT_SUFFIXES and path.name not in {'LICENSE', '.gitignore', '.gitattributes'}:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeError:
            errors.append(f'{relative}: invalid UTF-8')
            continue
        if '\ufffd' in text:
            errors.append(f'{relative}: replacement character suggests corrupted encoding')
        for match in re.finditer(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', text):
            try:
                address = ipaddress.ip_address(match.group())
            except ValueError:
                continue
            if any(address in network for network in RFC1918):
                # This checker defines the reserved networks, not a real endpoint.
                if path.resolve() == Path(__file__).resolve():
                    continue
                errors.append(f'{relative}: private-network address; use an explicit user-supplied field')
        if re.search(r'\b[A-Za-z]:[\\/](?![/\\])', text):
            errors.append(f'{relative}: machine-specific local path')
        if re.search(r'-----BEGIN (?:OPENSSH |ENCRYPTED |RSA |EC )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}', text):
            errors.append(f'{relative}: embedded private key')
        if re.search(r'(?i)(?:authorization|x-auth-token|x-access-token)["\x27]?\s*[:=]\s*["\x27](?:Bearer\s+)?[A-Za-z0-9._+/=-]{24,}', text):
            errors.append(f'{relative}: possible embedded authentication value')
        if path.suffix == '.md':
            prose = re.sub(r'(?ms)^```[^\n]*\n.*?^```[^\n]*$', '', text)
            prose = re.sub(r'`[^`\n]*`', '', prose)
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', prose):
                if target.startswith(('https://', 'http://', '#', 'mailto:')):
                    continue
                if target.startswith(('/', 'file:')) or re.match(r'^[A-Za-z]:', target):
                    errors.append(f'{relative}: non-portable link {target}')
                    continue
                links += 1
                if not (path.parent / target.split('#')[0]).exists():
                    errors.append(f'{relative}: missing link {target}')
    skill = root / 'skills/modelmate-ops/SKILL.md'
    if not skill.is_file():
        errors.append('Missing skill entrypoint')
    else:
        text = skill.read_text(encoding='utf-8')
        if not text.startswith('---\n') or not re.search(r'^name: modelmate-ops$', text, re.M) or not re.search(r'^description:', text, re.M):
            errors.append('Invalid skill metadata')
    return {'passed': not errors, 'files_checked': count, 'relative_links_checked': links, 'errors': errors,
            'scope': 'public source selection; not a proof that every possible secret is absent'}


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
