#!/usr/bin/env python3
"""Bounded SSH commands and single-file SFTP with a pinned local profile.

Credentials remain local. No private-key or passphrase bytes are emitted.
The default banner probe uses only the standard library; --host-key and
authenticated modes use Paramiko and cryptography. Existing SSH configs and
system proxy settings are not modified.
"""
from __future__ import annotations

import argparse
import base64
import csv
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import uuid
import warnings

DEFAULT_PROFILE = Path.home() / '.codex' / 'modelmate' / 'connection.json'
MAX_CREDENTIAL_BYTES = 1024 * 1024
MAX_CREDENTIAL_ARCHIVE_BYTES = 32 * 1024 * 1024


def emit(value, stream=None):
    print(json.dumps(value, ensure_ascii=False), file=stream or sys.stdout, flush=True)


def fingerprint(key_bytes):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip('=')


def valid_fingerprint(value):
    if not isinstance(value, str) or not value.startswith('SHA256:'):
        raise ValueError('Host fingerprint must be SHA256:<base64 digest>')
    encoded = value[7:]
    try:
        decoded = base64.b64decode(encoded + '=' * (-len(encoded) % 4), validate=True)
    except ValueError as error:
        raise ValueError('Malformed SHA256 host fingerprint') from error
    if len(decoded) != 32:
        raise ValueError('SHA256 host fingerprint must contain a 32-byte digest')
    return 'SHA256:' + base64.b64encode(decoded).decode().rstrip('=')


def positive(value):
    converted = float(value)
    if converted <= 0:
        raise argparse.ArgumentTypeError('Value must be positive')
    return converted


def positive_int(value):
    converted = int(value)
    if converted <= 0:
        raise argparse.ArgumentTypeError('Value must be a positive integer')
    return converted


def port_number(value):
    converted = int(value)
    if not 1 <= converted <= 65535:
        raise argparse.ArgumentTypeError('Port must be between 1 and 65535')
    return converted


def load_profile(path):
    p = json.loads(Path(path).expanduser().read_text(encoding='utf-8-sig'))
    if not isinstance(p, dict):
        raise ValueError('Local profile must be a JSON object')
    for name in ('host', 'port', 'user', 'host_key_sha256'):
        if not p.get(name):
            raise ValueError('Missing local profile field: ' + name)
    if not 1 <= int(p['port']) <= 65535:
        raise ValueError('Invalid port')
    p['host_key_sha256'] = valid_fingerprint(p['host_key_sha256'])
    return p


def observe_host_key(host, port, timeout):
    paramiko, _ = dependencies()
    transport = paramiko.Transport(socket.create_connection((host, port), timeout))
    try:
        transport.banner_timeout = timeout
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
        return {'host_key_sha256': fingerprint(key.asbytes()),
                'host_key_algorithm': key.get_name(),
                'host_identity': 'observed_only_not_independently_verified'}
    finally:
        transport.close()


def probe(host, port, timeout, host_key=False):
    started = time.monotonic()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        data = b''
        while len(data) < 4096:
            piece = sock.recv(1)
            if not piece:
                break
            data += piece
            if data.endswith(b'\n') and data.splitlines()[-1].startswith(b'SSH-'):
                break
        banner = data.decode('ascii', 'replace').strip()
        result = {'tcp': 'connected', 'ssh_banner': banner,
                  'ssh_protocol_seen': any(x.startswith('SSH-') for x in banner.splitlines()),
                  'elapsed_seconds': round(time.monotonic() - started, 3)}
    if host_key:
        result.update(observe_host_key(host, port, timeout))
    return result


def dependencies():
    # Paramiko 2.x can warn about unrelated legacy cipher classes on import.
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Blowfish has been deprecated.*')
            import paramiko
        from cryptography.hazmat.primitives import serialization
    except ImportError as error:
        requirements = Path(__file__).resolve().parents[1] / 'requirements-ssh.txt'
        raise RuntimeError('SSH dependencies are missing in this local Python. Install locally: '
                           'python -m pip install -r "' + str(requirements) + '"') from error
    return paramiko, serialization


def restrict_new_profile_file(path):
    """Restrict only a newly-created file, without changing parent/system ACLs."""
    if os.name != 'nt':
        path.chmod(0o600)
        return 'posix_mode_0600'
    who = subprocess.run(['whoami.exe', '/user', '/fo', 'csv', '/nh'],
                         capture_output=True, text=True, errors='replace', timeout=10)
    if who.returncode:
        raise RuntimeError('Could not determine current Windows user for profile ACL')
    sid = next((field for row in csv.reader(io.StringIO(who.stdout)) for field in row
                if field.startswith('S-1-') and all(c.isdigit() or c in 'S-' for c in field)), None)
    if not sid:
        raise RuntimeError('Could not parse current Windows user SID for profile ACL')
    result = subprocess.run(['icacls.exe', str(path), '/inheritance:r', '/grant:r',
                             '*' + sid + ':F', '*S-1-5-18:F'],
                            capture_output=True, timeout=10)
    if result.returncode:
        raise RuntimeError('Could not restrict newly-created profile ACL; existing files were not changed')
    return 'windows_acl_current_user_and_system'


def write_private_json(path, value):
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        protection = restrict_new_profile_file(path)
    except BaseException:
        path.unlink(missing_ok=True)  # This function created this exact new file.
        raise
    return protection


def initialize_profile(args):
    if not args.host.strip() or '://' in args.host or any(c.isspace() for c in args.host):
        raise ValueError('--host must be a hostname or IP address, without a URL scheme or spaces')
    if not args.user.strip():
        raise ValueError('--user must be the platform SSH username')
    profile = args.profile.expanduser().absolute()
    receipt_path = profile.with_name(profile.name + '.receipt.json')
    if profile.exists() or profile.is_symlink() or receipt_path.exists() or receipt_path.is_symlink():
        raise FileExistsError('Refusing to overwrite profile or receipt; use a new --profile path')
    if args.identity_file and args.passphrase_member is not None:
        raise ValueError('--passphrase-member applies only to --credentials-archive')
    credential_source = args.credentials_archive or args.identity_file
    credential_source = credential_source.expanduser().resolve()
    if not credential_source.is_file():
        raise FileNotFoundError('Credential source must be an existing local regular file')
    password_file = args.passphrase_file.expanduser().resolve() if args.passphrase_file else None
    if password_file and not password_file.is_file():
        raise FileNotFoundError('Passphrase source must be an existing local regular file')
    if args.passphrase_member is not None and (password_file or args.passphrase_env):
        raise ValueError('Choose archive passphrase member OR an external passphrase source')
    observed = None
    if args.trust_first_use:
        observed = observe_host_key(args.host, args.port, args.connect_timeout)
        pinned = observed['host_key_sha256']
        trust = 'first_use_observed_not_independently_verified'
    else:
        pinned = valid_fingerprint(args.host_key_sha256)
        trust = 'fingerprint_supplied_by_operator'
    data = {'host': args.host, 'port': args.port, 'user': args.user,
            'host_key_sha256': pinned, 'host_key_trust': trust,
            'connect_timeout': args.connect_timeout}
    if args.credentials_archive:
        data.update(credentials_archive=str(credential_source), key_member=args.key_member,
                    passphrase_member=args.passphrase_member if args.passphrase_member is not None
                    else ('' if password_file or args.passphrase_env else 'password.txt'))
    else:
        data['identity_file'] = str(credential_source)
    if password_file:
        data['passphrase_file'] = str(password_file)
    if args.passphrase_env:
        data['passphrase_env'] = args.passphrase_env
    if args.strip_passphrase_newline:
        data['strip_passphrase_newline'] = True
    if args.expected_remote_user:
        data['expected_remote_user'] = args.expected_remote_user
    if args.expected_notebook_hostname:
        data['expected_notebook_hostname'] = args.expected_notebook_hostname
    profile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    protection = write_private_json(profile, data)
    receipt = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'profile': str(profile), 'host': args.host, 'port': args.port,
               'host_key_sha256': pinned, 'trust': trust, 'file_protection': protection,
               'credentials_copied': False, 'authentication_tested': False,
               'profile_sha256': hashlib.sha256(profile.read_bytes()).hexdigest()}
    if observed:
        receipt['host_key_algorithm'] = observed['host_key_algorithm']
    try:
        write_private_json(receipt_path, receipt)
    except BaseException:
        profile.unlink()  # Roll back only the profile created by this invocation.
        raise
    return {'profile': str(profile), 'receipt': str(receipt_path),
            'host_key_sha256': pinned, 'host_key_trust': trust,
            'file_protection': protection, 'authentication_tested': False}


def read_credentials(p, serialization, paramiko):
    password = None
    if p.get('credentials_archive'):
        archive = Path(p['credentials_archive']).expanduser()
        if archive.stat().st_size > MAX_CREDENTIAL_ARCHIVE_BYTES:
            raise ValueError('Credential archive exceeds 32 MiB size bound')
        with tarfile.open(archive) as tf:
            members = []
            for member in tf:
                members.append(member)
                if len(members) > 64:
                    raise ValueError('Credential archive has more than 64 members')
            def member_bytes(name):
                matching = [m for m in members if m.name == name]
                if len(matching) != 1 or not matching[0].isfile():
                    raise ValueError('Credential member must be one regular file: ' + name)
                if matching[0].size > MAX_CREDENTIAL_BYTES:
                    raise ValueError('Credential member exceeds size bound')
                with tf.extractfile(matching[0]) as source:
                    return source.read(MAX_CREDENTIAL_BYTES + 1)
            raw = member_bytes(p.get('key_member', 'id_rsa'))
            if p.get('passphrase_member', 'password.txt'):
                password = member_bytes(p.get('passphrase_member', 'password.txt'))
    else:
        key_path = Path(p['identity_file']).expanduser()
        if key_path.stat().st_size > MAX_CREDENTIAL_BYTES:
            raise ValueError('Identity file exceeds size bound')
        raw = key_path.read_bytes()
    if p.get('passphrase_file'):
        pass_path = Path(p['passphrase_file']).expanduser()
        if pass_path.stat().st_size > MAX_CREDENTIAL_BYTES:
            raise ValueError('Passphrase file exceeds size bound')
        password = pass_path.read_bytes()
    elif p.get('passphrase_env'):
        value = os.environ.get(p['passphrase_env'])
        if value is None:
            raise ValueError('Configured passphrase environment variable is not set')
        password = value.encode('utf-8')
    if p.get('strip_passphrase_newline') and password is not None:
        password = password.rstrip(b'\r\n')
    loaders = (serialization.load_ssh_private_key, serialization.load_pem_private_key)
    loaded = None
    for loader in loaders:
        try:
            loaded = loader(raw, password=password)
            break
        except (ValueError, TypeError):
            pass
    if loaded is None:
        raise ValueError('Unable to load key: check format and local passphrase source')
    # Paramiko versions differ in support for encrypted PKCS8. Convert only in RAM.
    for fmt, classes in (
        (serialization.PrivateFormat.TraditionalOpenSSL, ('RSAKey', 'ECDSAKey')),
        (serialization.PrivateFormat.OpenSSH, ('Ed25519Key',)),
    ):
        try:
            memory_pem = loaded.private_bytes(serialization.Encoding.PEM, fmt,
                                              serialization.NoEncryption()).decode('ascii')
        except (ValueError, TypeError):
            continue
        for class_name in classes:
            try:
                return getattr(paramiko, class_name).from_private_key(io.StringIO(memory_pem))
            except (ValueError, paramiko.SSHException):
                pass
    raise ValueError('Unsupported private key algorithm for installed Paramiko')


def run_channel(transport, text, timeout, max_output):
    if timeout <= 0 or max_output <= 0:
        raise ValueError('Command timeout and output bound must be positive')
    if '\x00' in text:
        raise ValueError('Command contains NUL')
    # Pass the program through stdin. Some ModelMate gateways reinterpret exec
    # quoting, including POSIX shlex.quote's embedded single-quote sequence.
    # A constant exec request avoids that parser and keeps UTF-8 bytes intact.
    program = (text + '\n').encode('utf-8')
    if len(program) > 1024 * 1024:
        raise ValueError('Command script exceeds 1 MiB; upload a bounded script explicitly')
    started = time.monotonic()
    channel = transport.open_session(timeout=min(timeout, 15))
    stdout, stderr = bytearray(), bytearray()
    try:
        channel.settimeout(min(timeout, 15))
        channel.exec_command('bash -s')
        channel.sendall(program)
        channel.shutdown_write()
        while True:
            for ready, recv, dest in ((channel.recv_ready, channel.recv, stdout),
                                      (channel.recv_stderr_ready, channel.recv_stderr, stderr)):
                while ready():
                    if time.monotonic() - started > timeout:
                        raise TimeoutError('Local wait timed out; remote process termination is not guaranteed')
                    dest.extend(recv(32768))
                    if len(stdout) + len(stderr) > max_output:
                        raise RuntimeError('Output bound exceeded; narrow command or use an explicit remote file')
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            if time.monotonic() - started > timeout:
                raise TimeoutError('Local wait timed out; remote process termination is not guaranteed')
            time.sleep(0.02)
        return {'exit_code': channel.recv_exit_status(),
                'stdout': stdout.decode('utf-8', 'replace'),
                'stderr': stderr.decode('utf-8', 'replace')}
    finally:
        channel.close()


def connect(p):
    paramiko, serialization = dependencies()
    timeout = float(p.get('connect_timeout', 10))
    if timeout <= 0:
        raise ValueError('Connect timeout must be positive')
    transport = paramiko.Transport(socket.create_connection((p['host'], int(p['port'])), timeout))
    try:
        transport.banner_timeout = timeout
        transport.auth_timeout = timeout
        transport.start_client(timeout=timeout)
        observed = fingerprint(transport.get_remote_server_key().asbytes())
        if observed != p['host_key_sha256']:
            raise RuntimeError('HOST_KEY_MISMATCH: stop and verify current platform endpoint; observed ' + observed)
        key = read_credentials(p, serialization, paramiko)
        transport.auth_publickey(p['user'], key)
        if not transport.is_authenticated():
            raise RuntimeError('Authentication incomplete')
        transport.set_keepalive(30)
        identity = run_channel(transport, 'id -un; hostname; pwd', 15, 65536)
        parts = identity['stdout'].strip().splitlines()
        if identity['exit_code'] != 0 or len(parts) < 3:
            raise RuntimeError('Remote identity probe did not return user, host and directory')
        user, hostname, directory = parts[:3]
        if p.get('expected_remote_user') and user != p['expected_remote_user']:
            raise RuntimeError('REMOTE_USER_MISMATCH: got ' + user)
        if p.get('expected_notebook_hostname') and hostname != p['expected_notebook_hostname']:
            raise RuntimeError('NOTEBOOK_IDENTITY_CHANGED: got ' + hostname + '; verify instance before updating profile')
        return transport, paramiko, {'user': user, 'hostname': hostname, 'directory': directory,
                                     'host_key_sha256': observed}
    except BaseException:
        transport.close()
        raise


def sftp_exists(sf, name):
    try:
        sf.stat(name)
        return True
    except OSError as error:
        if error.errno == 2:
            return False
        raise


def transfer(sf, args):
    limit = args.max_bytes
    if limit <= 0:
        raise ValueError('Transfer byte bound must be positive')
    digest = hashlib.sha256()
    total = 0
    if args.action == 'download':
        local = Path(args.local).expanduser().resolve()
        if local.exists():
            raise FileExistsError('Refusing to overwrite local file')
        size = sf.stat(args.remote).st_size
        if size > limit:
            raise ValueError('Remote file exceeds --max-bytes')
        part = local.with_name(local.name + '.part-' + uuid.uuid4().hex[:12])
        # Parent must be an explicit existing destination.
        with sf.open(args.remote, 'rb') as source, part.open('xb') as target:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise ValueError('Transfer exceeded byte bound; partial file retained')
                target.write(block)
                digest.update(block)
        if args.sha256 and digest.hexdigest().lower() != args.sha256.lower():
            raise ValueError('SHA256 mismatch; partial file retained: ' + str(part))
        # link fails atomically if the requested final name already exists.
        try:
            os.link(part, local)
            part.unlink()
        except OSError as error:
            if isinstance(error, FileExistsError) or local.exists():
                raise FileExistsError('Refusing to overwrite local file; verified partial retained at ' + str(part)) from error
            # Filesystems such as FAT do not support hard links. Exclusive
            # creation preserves the no-overwrite promise on that fallback.
            created = False
            try:
                with local.open('xb') as target:
                    created = True
                    with part.open('rb') as source:
                        shutil.copyfileobj(source, target, 1024 * 1024)
                part.unlink()
            except BaseException:
                if created:
                    local.unlink(missing_ok=True)
                raise
    else:
        local = Path(args.local).expanduser().resolve()
        if not local.is_file() or local.stat().st_size > limit:
            raise ValueError('Upload requires a regular file within --max-bytes')
        if sftp_exists(sf, args.remote):
            raise FileExistsError('Refusing to overwrite remote file')
        if args.sha256:
            expected = hashlib.sha256()
            with local.open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    expected.update(block)
            if expected.hexdigest().lower() != args.sha256.lower():
                raise ValueError('Source SHA256 mismatch; nothing was uploaded')
        temporary = args.remote + '.part-' + uuid.uuid4().hex[:12]
        with local.open('rb') as source, sf.open(temporary, 'wx') as target:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise ValueError('Upload exceeded byte bound; temporary file retained')
                digest.update(block)
                target.write(block)
        check = hashlib.sha256()
        checked = 0
        with sf.open(temporary, 'rb') as source:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                checked += len(block)
                if checked > limit:
                    raise ValueError('Uploaded verification exceeds byte bound; temporary retained')
                check.update(block)
        if check.hexdigest() != digest.hexdigest():
            raise ValueError('Uploaded content hash mismatch; temporary retained')
        if args.sha256 and digest.hexdigest().lower() != args.sha256.lower():
            raise ValueError('Source SHA256 mismatch; temporary retained')
        # SFTP standard rename must fail when the target exists. Do not use posix_rename.
        sf.rename(temporary, args.remote)
    return {'action': args.action, 'local': str(local), 'remote': args.remote,
            'bytes': total, 'sha256': digest.hexdigest()}


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    sub = ap.add_subparsers(dest='action', required=True)
    ip = sub.add_parser('init', help='Create a new local profile and trust receipt; never overwrite')
    ip.add_argument('--host', required=True)
    ip.add_argument('--port', type=port_number, required=True)
    ip.add_argument('--user', required=True, help='SSH username from the platform connection information')
    credential = ip.add_mutually_exclusive_group(required=True)
    credential.add_argument('--credentials-archive', type=Path)
    credential.add_argument('--identity-file', type=Path)
    trust = ip.add_mutually_exclusive_group(required=True)
    trust.add_argument('--host-key-sha256', help='Previously verified SHA256 host fingerprint')
    trust.add_argument('--trust-first-use', action='store_true', help='Explicitly pin the first observed server key; does not independently verify identity')
    ip.add_argument('--key-member', default='id_rsa')
    ip.add_argument('--passphrase-member', help='Archive passphrase member, default password.txt; empty string means none')
    password = ip.add_mutually_exclusive_group()
    password.add_argument('--passphrase-file', type=Path)
    password.add_argument('--passphrase-env', help='Name of a local environment variable; never the passphrase itself')
    ip.add_argument('--strip-passphrase-newline', action='store_true')
    ip.add_argument('--expected-remote-user')
    ip.add_argument('--expected-notebook-hostname')
    ip.add_argument('--connect-timeout', type=positive, default=10)
    pp = sub.add_parser('probe', help='TCP and SSH banner only; no credential use')
    pp.add_argument('--host')
    pp.add_argument('--port', type=port_number)
    pp.add_argument('--timeout', type=positive, default=8)
    pp.add_argument('--host-key', action='store_true', help='Observe server public fingerprint without authentication; does not establish trust')
    sub.add_parser('check', help='Verify pinned host, authentication, Notebook identity and SFTP')
    rp = sub.add_parser('run', help='One bounded remote shell command; stdout/stderr in JSON')
    source = rp.add_mutually_exclusive_group(required=True)
    source.add_argument('--command')
    source.add_argument('--command-file', type=Path)
    rp.add_argument('--cwd')
    rp.add_argument('--timeout', type=positive, default=30)
    rp.add_argument('--max-output', type=positive_int, default=4 * 1024 * 1024)
    for name in ('upload', 'download'):
        tp = sub.add_parser(name, help='Transfer one explicit file; never overwrite')
        tp.add_argument('--local', required=True)
        tp.add_argument('--remote', required=True)
        tp.add_argument('--max-bytes', type=positive_int, default=2 * 1024 ** 3)
        tp.add_argument('--sha256')
        tp.add_argument('--timeout', type=positive, default=30, help='SFTP inactivity timeout')
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == 'init':
        emit(initialize_profile(args))
        return 0
    if args.action == 'probe':
        if bool(args.host) != bool(args.port):
            raise ValueError('Provide --host and --port together')
        p = load_profile(args.profile) if not args.host else {}
        emit(probe(args.host or p['host'], args.port or p['port'], args.timeout, args.host_key))
        return 0
    p = load_profile(args.profile)
    transport, paramiko, identity = connect(p)
    try:
        if args.action == 'run':
            text = args.command if args.command is not None else args.command_file.read_text(encoding='utf-8-sig')
            text = text.replace('\r\n', '\n')
            if args.cwd:
                if not args.cwd.startswith('/'):
                    raise ValueError('--cwd must be an absolute remote Linux path')
                text = 'cd ' + shlex.quote(args.cwd) + ' && {\n' + text + '\n}'
            result = run_channel(transport, text, args.timeout, args.max_output)
            emit({'identity': identity, **result})
            return result['exit_code'] if 0 <= result['exit_code'] <= 255 else 1
        try:
            sf = paramiko.SFTPClient.from_transport(transport)
        except Exception as error:
            if args.action == 'check':
                emit({'authenticated': True, 'identity': identity, 'sftp': False,
                      'error_type': type(error).__name__, 'error': str(error)})
                return 1
            raise
        try:
            sf.get_channel().settimeout(getattr(args, 'timeout', 15))
            if args.action == 'check':
                emit({'authenticated': True, 'identity': identity, 'sftp': True,
                      'sftp_directory': sf.normalize('.')})
            else:
                emit({'identity': identity, **transfer(sf, args)})
        except Exception as error:
            if args.action == 'check':
                emit({'authenticated': True, 'identity': identity, 'sftp': False,
                      'error_type': type(error).__name__, 'error': str(error)})
                return 1
            raise
        finally:
            sf.close()
        return 0
    finally:
        transport.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        emit({'error_type': type(error).__name__, 'error': str(error)}, sys.stderr)
        raise SystemExit(1)
