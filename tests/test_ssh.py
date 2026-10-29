"""Offline behavior tests: no platform, real profiles or user credentials used."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
import errno
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'public_modelmate_ssh', ROOT / 'skills' / 'modelmate-ops' / 'scripts' / 'modelmate_ssh.py')
ssh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ssh)
FP = ssh.fingerprint(b'synthetic server key for offline tests')


def make_init_args(directory, *additional):
    key = directory / 'synthetic-key-reference'
    key.write_text('This is a local test reference, not a private key.', encoding='utf-8')
    return ssh.parser().parse_args([
        '--profile', str(directory / 'connection.json'), 'init',
        '--host', 'notebook.example.invalid', '--port', '31500', '--user', 'ssh-user',
        '--identity-file', str(key), *additional])


class ProfileTests(unittest.TestCase):
    def test_init_requires_an_explicit_trust_choice(self):
        with tempfile.TemporaryDirectory() as d, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                make_init_args(Path(d))
            self.assertEqual(error.exception.code, 2)

    def test_init_creates_profile_and_receipt_without_copying_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            password = directory / 'synthetic-passphrase'
            password.write_text('LOCAL-TEST-SECRET-NEVER-IN-PROFILE', encoding='utf-8')
            args = make_init_args(directory, '--host-key-sha256', FP,
                                  '--passphrase-file', str(password))
            result = ssh.initialize_profile(args)
            profile = args.profile.read_text(encoding='utf-8')
            receipt = json.loads(Path(result['receipt']).read_text(encoding='utf-8'))
            self.assertNotIn(password.read_text(), profile)
            self.assertIn(str(password.resolve()).replace('\\', '\\\\'), profile)
            self.assertEqual(receipt['profile_sha256'], hashlib.sha256(args.profile.read_bytes()).hexdigest())
            self.assertFalse(receipt['authentication_tested'])
            self.assertFalse(receipt['credentials_copied'])
            self.assertEqual(result['host_key_sha256'], FP)
            self.assertEqual(ssh.load_profile(args.profile)['user'], 'ssh-user')

    def test_existing_profile_is_never_replaced_or_probed(self):
        with tempfile.TemporaryDirectory() as d:
            args = make_init_args(Path(d), '--trust-first-use')
            args.profile.write_bytes(b'KEEP-THIS-EXISTING-PROFILE')
            with mock.patch.object(ssh, 'observe_host_key') as observer:
                with self.assertRaises(FileExistsError):
                    ssh.initialize_profile(args)
            observer.assert_not_called()
            self.assertEqual(args.profile.read_bytes(), b'KEEP-THIS-EXISTING-PROFILE')

    def test_first_use_receipt_marks_observation_without_authentication(self):
        with tempfile.TemporaryDirectory() as d:
            args = make_init_args(Path(d), '--trust-first-use')
            with mock.patch.object(ssh, 'observe_host_key', return_value={
                    'host_key_sha256': FP, 'host_key_algorithm': 'ssh-ed25519'}) as observer:
                result = ssh.initialize_profile(args)
            receipt = json.loads(Path(result['receipt']).read_text())
            observer.assert_called_once_with('notebook.example.invalid', 31500, 10)
            self.assertEqual(receipt['trust'], 'first_use_observed_not_independently_verified')
            self.assertFalse(receipt['authentication_tested'])

    def test_failed_file_protection_removes_only_the_new_profile(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'new-profile.json'
            with mock.patch.object(ssh, 'restrict_new_profile_file', side_effect=RuntimeError('ACL unavailable')):
                with self.assertRaises(RuntimeError):
                    ssh.write_private_json(target, {'host': 'example.invalid'})
            self.assertFalse(target.exists())

    def test_invalid_fingerprint_rejected(self):
        for invalid in ['no-pin', 'SHA256:not-valid!', 'SHA256:dGVzdA']:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ssh.valid_fingerprint(invalid)


class CredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paramiko, cls.serialization = ssh.dependencies()
        from cryptography.hazmat.primitives.asymmetric import rsa
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.password = b'synthetic-offline-test-passphrase'
        cls.encrypted = cls.key.private_bytes(
            cls.serialization.Encoding.PEM, cls.serialization.PrivateFormat.PKCS8,
            cls.serialization.BestAvailableEncryption(cls.password))

    def make_archive(self, path, *, duplicate=False, linked=False):
        with tarfile.open(path, 'w') as tf:
            entries = [('id_rsa', self.encrypted), ('password.txt', self.password)]
            if duplicate:
                entries.append(('id_rsa', self.encrypted))
            for name, value in entries:
                member = tarfile.TarInfo(name)
                if linked and name == 'id_rsa':
                    member.type = tarfile.SYMTYPE
                    member.linkname = 'outside-the-archive'
                    tf.addfile(member)
                else:
                    member.size = len(value)
                    tf.addfile(member, io.BytesIO(value))

    def test_encrypted_pkcs8_tar_is_decrypted_only_in_memory(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / 'synthetic.tar'
            self.make_archive(archive)
            before = set(Path(d).iterdir())
            key = ssh.read_credentials({'credentials_archive': str(archive)}, self.serialization, self.paramiko)
            self.assertEqual(set(Path(d).iterdir()), before)
            expected = self.key.public_key().public_bytes(self.serialization.Encoding.OpenSSH,
                                                         self.serialization.PublicFormat.OpenSSH)
            self.assertEqual(key.get_base64(), expected.decode().split()[1])

    def test_duplicate_or_link_credential_members_are_rejected(self):
        for options in [{'duplicate': True}, {'linked': True}]:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as d:
                archive = Path(d) / 'synthetic.tar'
                self.make_archive(archive, **options)
                with self.assertRaises(ValueError):
                    ssh.read_credentials({'credentials_archive': str(archive)}, self.serialization, self.paramiko)

    def test_external_passphrase_and_newline_rule(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            key_file = directory / 'synthetic.pem'
            password_file = directory / 'password'
            key_file.write_bytes(self.encrypted)
            password_file.write_bytes(self.password + b'\n')
            p = {'identity_file': str(key_file), 'passphrase_file': str(password_file)}
            with self.assertRaises(ValueError):
                ssh.read_credentials(p, self.serialization, self.paramiko)
            p['strip_passphrase_newline'] = True
            self.assertEqual(ssh.read_credentials(p, self.serialization, self.paramiko).get_bits(), 2048)

    def test_archive_can_use_external_passphrase_without_password_member(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            archive = directory / 'key-only.tar'
            with tarfile.open(archive, 'w') as tf:
                item = tarfile.TarInfo('key.pem'); item.size = len(self.encrypted)
                tf.addfile(item, io.BytesIO(self.encrypted))
            pass_file = directory / 'password'
            pass_file.write_bytes(self.password)
            p = {'credentials_archive': str(archive), 'key_member': 'key.pem',
                 'passphrase_member': '', 'passphrase_file': str(pass_file)}
            self.assertEqual(ssh.read_credentials(p, self.serialization, self.paramiko).get_bits(), 2048)


class FakeChannel:
    def __init__(self, out=None, err=None, exit_code=0, completed=True):
        self.out = list(out or [])
        self.err = list(err or [])
        self.exit_code = exit_code
        self.completed = completed
        self.closed = False
        self.sent = b''
    def settimeout(self, value): self.timeout = value
    def exec_command(self, command): self.command = command
    def sendall(self, program): self.sent += program
    def shutdown_write(self): self.eof_sent = True
    def recv_ready(self): return bool(self.out)
    def recv_stderr_ready(self): return bool(self.err)
    def recv(self, count): return self.out.pop(0)
    def recv_stderr(self, count): return self.err.pop(0)
    def exit_status_ready(self): return self.completed
    def recv_exit_status(self): return self.exit_code
    def close(self): self.closed = True


class CommandTests(unittest.TestCase):
    def test_utf8_and_shell_metacharacters_are_program_stdin(self):
        channel = FakeChannel([b'out\n'], [b'err\n'], exit_code=7)
        transport = mock.Mock(); transport.open_session.return_value = channel
        program = "printf '%s\\n' '连接 $HOME `literal`'"
        result = ssh.run_channel(transport, program, 10, 1000)
        self.assertEqual(channel.command, 'bash -s')
        self.assertEqual(channel.sent, (program + '\n').encode('utf-8'))
        self.assertTrue(channel.eof_sent)
        self.assertTrue(channel.closed)
        self.assertEqual(result, {'exit_code': 7, 'stdout': 'out\n', 'stderr': 'err\n'})

    def test_timeout_closes_channel_without_claiming_remote_termination(self):
        channel = FakeChannel(completed=False)
        transport = mock.Mock(); transport.open_session.return_value = channel
        with mock.patch.object(ssh.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(TimeoutError, 'termination is not guaranteed'):
                ssh.run_channel(transport, 'sleep 10', 1, 1000)
        self.assertTrue(channel.closed)

    def test_output_bound_closes_channel(self):
        channel = FakeChannel([b'too much output'])
        transport = mock.Mock(); transport.open_session.return_value = channel
        with self.assertRaisesRegex(RuntimeError, 'Output bound'):
            ssh.run_channel(transport, 'example', 10, 3)
        self.assertTrue(channel.closed)

    def test_main_preserves_remote_exit_code_and_normalizes_command_file(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            profile = directory / 'connection.json'
            profile.write_text(json.dumps({'host': 'example.invalid', 'port': 31500,
                                           'user': 'ssh-user', 'host_key_sha256': FP}))
            command = directory / 'program.sh'
            command.write_bytes(b'printf hello\r\nexit 7\r\n')
            transport = mock.Mock()
            with mock.patch.object(ssh, 'connect', return_value=(transport, mock.Mock(), {'user': 'linux-user'})), \
                    mock.patch.object(ssh, 'run_channel', return_value={'exit_code': 7, 'stdout': '', 'stderr': ''}) as run, \
                    redirect_stdout(io.StringIO()):
                code = ssh.main(['--profile', str(profile), 'run', '--command-file', str(command), '--cwd', '/project with space'])
            self.assertEqual(code, 7)
            text = run.call_args.args[1]
            self.assertNotIn('\r', text)
            self.assertIn("cd '/project with space'", text)
            transport.close.assert_called_once()

    def test_host_key_mismatch_stops_before_reading_or_authenticating_key(self):
        transport = mock.Mock()
        transport.get_remote_server_key.return_value.asbytes.return_value = b'actual-server'
        paramiko = mock.Mock(); paramiko.Transport.return_value = transport
        with mock.patch.object(ssh, 'dependencies', return_value=(paramiko, mock.Mock())), \
                mock.patch.object(ssh.socket, 'create_connection'), \
                mock.patch.object(ssh, 'read_credentials') as reader:
            with self.assertRaisesRegex(RuntimeError, 'HOST_KEY_MISMATCH'):
                ssh.connect({'host': 'example.invalid', 'port': 31500, 'user': 'ssh-user', 'host_key_sha256': FP})
        reader.assert_not_called()
        transport.auth_publickey.assert_not_called()
        transport.close.assert_called_once()

    def test_probe_banner_does_not_import_ssh_dependencies(self):
        class BannerSocket:
            data = bytearray(b'SSH-2.0-test-server\r\n')
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def settimeout(self, value): pass
            def recv(self, size):
                result = bytes(self.data[:size]); del self.data[:size]; return result
        with mock.patch.object(ssh.socket, 'create_connection', return_value=BannerSocket()), \
                mock.patch.object(ssh, 'dependencies', side_effect=AssertionError('must not import')):
            self.assertTrue(ssh.probe('example.invalid', 31500, 1)['ssh_protocol_seen'])

    def test_check_preserves_authentication_stage_when_sftp_directory_fails(self):
        with tempfile.TemporaryDirectory() as d:
            profile = Path(d) / 'connection.json'
            profile.write_text(json.dumps({'host': 'example.invalid', 'port': 31500,
                                           'user': 'ssh-user', 'host_key_sha256': FP}))
            transport, paramiko, sf = mock.Mock(), mock.Mock(), mock.Mock()
            paramiko.SFTPClient.from_transport.return_value = sf
            sf.normalize.side_effect = OSError('SFTP directory unavailable')
            output = io.StringIO()
            with mock.patch.object(ssh, 'connect', return_value=(transport, paramiko, {'user': 'linux-user'})), \
                    redirect_stdout(output):
                code = ssh.main(['--profile', str(profile), 'check'])
            self.assertEqual(code, 1)
            result = json.loads(output.getvalue())
            self.assertTrue(result['authenticated'])
            self.assertFalse(result['sftp'])
            self.assertEqual(result['identity']['user'], 'linux-user')
            sf.close.assert_called_once()
            transport.close.assert_called_once()


class UploadBuffer(io.BytesIO):
    def __init__(self, owner, name):
        super().__init__(); self.owner = owner; self.name = name
    def close(self):
        if not self.closed:
            self.owner.files[self.name] = self.getvalue()
        super().close()


class FakeSFTP:
    def __init__(self, files=None):
        self.files = dict(files or {})
        self.opened_writes = []
    def stat(self, name):
        if name not in self.files:
            raise FileNotFoundError(errno.ENOENT, 'not found')
        return SimpleNamespace(st_size=len(self.files[name]))
    def open(self, name, mode):
        if mode == 'rb': return io.BytesIO(self.files[name])
        if name in self.files: raise FileExistsError(name)
        self.opened_writes.append(name)
        return UploadBuffer(self, name)
    def rename(self, source, destination):
        if destination in self.files: raise FileExistsError(destination)
        self.files[destination] = self.files.pop(source)


def transfer_args(action, local, *, sha256=None, limit=4096):
    return SimpleNamespace(action=action, local=str(local), remote='/project/explicit.txt',
                           max_bytes=limit, sha256=sha256)


class TransferTests(unittest.TestCase):
    def test_download_verifies_hash_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / 'result.txt'
            payload = 'UTF8: 结果\n'.encode()
            sf = FakeSFTP({'/project/explicit.txt': payload})
            args = transfer_args('download', local, sha256=hashlib.sha256(payload).hexdigest())
            result = ssh.transfer(sf, args)
            self.assertEqual(local.read_bytes(), payload)
            self.assertEqual(result['bytes'], len(payload))
            with self.assertRaises(FileExistsError): ssh.transfer(sf, args)
            self.assertEqual(local.read_bytes(), payload)

    def test_download_hash_mismatch_never_creates_final_file(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / 'result.txt'
            sf = FakeSFTP({'/project/explicit.txt': b'received'})
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                ssh.transfer(sf, transfer_args('download', local, sha256='0' * 64))
            self.assertFalse(local.exists())
            self.assertEqual(len(list(Path(d).glob('*.part-*'))), 1)

    def test_download_falls_back_safely_on_filesystem_without_hardlinks(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / 'result.txt'
            sf = FakeSFTP({'/project/explicit.txt': b'verified bytes'})
            with mock.patch.object(ssh.os, 'link', side_effect=OSError(errno.ENOTSUP, 'no hardlinks')):
                ssh.transfer(sf, transfer_args('download', local))
            self.assertEqual(local.read_bytes(), b'verified bytes')
            self.assertEqual(list(Path(d).glob('*.part-*')), [])

    def test_upload_roundtrip_hash_and_refusal_to_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / 'source.txt'; local.write_bytes(b'new payload')
            sf = FakeSFTP()
            args = transfer_args('upload', local, sha256=hashlib.sha256(local.read_bytes()).hexdigest())
            result = ssh.transfer(sf, args)
            self.assertEqual(sf.files, {'/project/explicit.txt': b'new payload'})
            self.assertEqual(result['sha256'], args.sha256)
            with self.assertRaises(FileExistsError): ssh.transfer(sf, args)
            self.assertEqual(sf.files['/project/explicit.txt'], b'new payload')

    def test_upload_wrong_source_hash_writes_nothing_remotely(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / 'source.txt'; local.write_bytes(b'new payload')
            sf = FakeSFTP()
            with self.assertRaisesRegex(ValueError, 'nothing was uploaded'):
                ssh.transfer(sf, transfer_args('upload', local, sha256='0' * 64))
            self.assertEqual(sf.files, {})
            self.assertEqual(sf.opened_writes, [])

    def test_oversized_download_is_rejected_before_file_creation(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / 'result.txt'
            with self.assertRaisesRegex(ValueError, 'exceeds'):
                ssh.transfer(FakeSFTP({'/project/explicit.txt': b'12345'}),
                             transfer_args('download', local, limit=4))
            self.assertEqual(list(Path(d).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
