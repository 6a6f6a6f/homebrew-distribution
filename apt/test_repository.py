"""Real dpkg, GnuPG and APT tests, using disposable keys and no host package changes."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import repository as repo


@unittest.skipUnless(all(shutil.which(tool) for tool in ('dpkg-deb', 'apt-ftparchive', 'gpg', 'apt-get')),
                     'Run on Ubuntu with apt-utils and gnupg')
class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.home = cls.root / 'gnupg'
        cls.home.mkdir(mode=0o700)
        cls.environment = patch.dict(os.environ, GNUPGHOME=str(cls.home))
        cls.environment.start()
        repo.run('gpg', '--batch', '--passphrase', '', '--quick-generate-key',
                 'Disposable APT Test <apt@example.invalid>', 'ed25519', 'cert', '1y')
        listing = repo.run('gpg', '--with-colons', '--list-keys').decode()
        cls.fingerprint = next(row.split(':')[9] for row in listing.splitlines() if row.startswith('fpr:'))
        repo.run('gpg', '--batch', '--passphrase', '', '--quick-add-key', cls.fingerprint,
                 'ed25519', 'sign', '1y')
        listing = repo.run('gpg', '--with-colons', '--list-keys').decode()
        cls.subkey = [row.split(':')[9] for row in listing.splitlines() if row.startswith('fpr:')][-1]
        cls.public = cls.root / 'public.asc'
        cls.public.write_bytes(repo.run('gpg', '--armor', '--export', cls.fingerprint))
        cls.artifacts = cls.root / 'artifacts'
        cls.artifacts.mkdir()
        candidate = dict(schemaVersion=1, channel='beta', version='1.0.0', commit='a' * 40,
                         coreCommit='b' * 40, installers={})
        for rid, arch in repo.ARCHITECTURES.items():
            package = cls.make_deb(arch)
            candidate['installers'][rid] = dict(
                url=f'{repo.BASE}/jambor/launcher/beta/1.0.0/{package.name}',
                size=package.stat().st_size, sha256=repo.digest(package))
        cls.candidate = cls.root / 'candidate.json'
        repo.write_json(cls.candidate, candidate)

    @classmethod
    def tearDownClass(cls):
        repo.run('gpgconf', '--kill', 'gpg-agent')
        cls.environment.stop()
        cls.temporary.cleanup()

    @classmethod
    def make_deb(cls, architecture):
        root = cls.root / architecture
        payload = root / 'usr/lib/jambor-launcher'
        payload.mkdir(parents=True)
        for name in ('Jambor', 'Jambor.Updater'):
            data = bytearray(64)
            data[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<HH', data, 16, 3, {'amd64': 62, 'arm64': 183}[architecture])
            (payload / name).write_bytes(data)
            (payload / name).chmod(0o755)
        (payload / 'release-version.txt').write_text('1.0.0\n')
        for name in ('usr/bin/jambor', 'usr/share/applications/dev.jojo.jambor.desktop',
                     'usr/share/icons/hicolor/256x256/apps/dev.jojo.jambor.png'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture; never executed\n')
        (root / 'DEBIAN').mkdir()
        (root / 'DEBIAN/control').write_text(
            f'Package: jambor-launcher\nVersion: 1.0.0\nArchitecture: {architecture}\n'
            f'Depends: {repo.RUNTIME_DEPENDENCIES}\nRecommends: mesa-vulkan-drivers\n'
            'Maintainer: Test <apt@example.invalid>\nDescription: Test only\n')
        for entry in (root, *root.rglob('*')):
            entry.chmod(0o755 if entry.is_dir() or entry.name in ('Jambor', 'Jambor.Updater', 'jambor') else 0o644)
        path = cls.artifacts / f'jambor-launcher_1.0.0_{architecture}.deb'
        repo.run('dpkg-deb', '--root-owner-group', '--build', str(root), str(path))
        return path

    def generate(self, output, now=None):
        repo.generate(self.candidate, self.artifacts, self.public, '1.0.0', 'c' * 40,
                      output, now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0))
        return output / 'dists' / repo.SUITE / 'InRelease'

    def apt(self, root, repository, success, key=None):
        root.mkdir()
        (root / 'lists/partial').mkdir(parents=True)
        (root / 'archives/partial').mkdir(parents=True)
        source = root / 'sources.list'
        source.write_text(f'deb [arch=amd64,arm64 signed-by={key or self.public} by-hash=force] file:{repository} {repo.SUITE} main\n')
        command = ['apt-get', '-o', f'Dir::Etc::sourcelist={source}', '-o', 'Dir::Etc::sourceparts=-',
                   '-o', f'Dir::State::lists={root / "lists"}', '-o', f'Dir::Cache::archives={root / "archives"}',
                   '-o', 'APT::Get::List-Cleanup=0', '-o', 'APT::Update::Error-Mode=any',
                   '-o', f'APT::Sandbox::User={__import__("getpass").getuser()}', 'update']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return command[:-1]

    def test_real_apt_signatures_freshness_and_hashes(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            output = root / 'repo'
            inrelease = self.generate(output)
            repo.sign(output, self.public, self.fingerprint, self.subkey)
            command = self.apt(root / 'valid', output, True)
            package = output / 'pool/main/j/jambor-launcher/jambor-launcher_1.0.0_amd64.deb'
            original_package = package.read_bytes()
            package.write_bytes(b'corrupt package')
            download = subprocess.run(command + ['download', 'jambor-launcher:amd64=1.0.0'],
                                      cwd=root, capture_output=True, text=True)
            self.assertNotEqual(download.returncode, 0, download.stdout + download.stderr)
            self.assertIn('Hash Sum mismatch', download.stdout + download.stderr)
            package.write_bytes(original_package)
            original = inrelease.read_bytes()
            inrelease.write_bytes(original.replace(b'Jambor Beta', b'Jambor Evil'))
            self.apt(root / 'tampered-signature', output, False)
            inrelease.write_bytes(original)
            for path in (output / 'dists').rglob('Packages*'):
                path.write_bytes(b'tampered index')
            for path in (output / 'dists').rglob('by-hash/SHA256/*'):
                path.write_bytes(b'tampered index')
            self.apt(root / 'tampered-index', output, False)
            expired = root / 'expired-repo'
            self.generate(expired, dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=8))
            repo.run('gpg', '--batch', '--local-user', self.subkey + '!', '--output',
                     str(expired / 'dists' / repo.SUITE / 'InRelease'), '--clearsign',
                     str(expired / 'dists' / repo.SUITE / 'Release'))
            self.apt(root / 'expired', expired, False)

    def test_rotation_installs_next_subkey_before_switching_signer(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            output = root / 'repo'
            self.generate(output)
            # The old certificate intentionally has no knowledge of the next subkey.
            repo.run('gpg', '--batch', '--passphrase', '', '--quick-add-key', self.fingerprint,
                     'ed25519', 'sign', '1y')
            listing = repo.run('gpg', '--with-colons', '--list-keys').decode()
            next_subkey = [row.split(':')[9] for row in listing.splitlines() if row.startswith('fpr:')][-1]
            next_public = root / 'next.asc'
            next_public.write_bytes(repo.run('gpg', '--armor', '--export', self.fingerprint))
            next_deb = root / 'jambor-archive-keyring_1.1.0_all.deb'
            repo.keyring_package(next_public, '1.1.0', next_deb)
            repo.run('dpkg-deb', '--extract', str(next_deb), str(root / 'installed'))
            installed = root / 'installed/usr/share/keyrings/jambor-archive-keyring.gpg'
            repo.sign(output, next_public, self.fingerprint, self.subkey)
            self.apt(root / 'overlap-old', output, True)
            self.apt(root / 'overlap-new', output, True, installed)
            repo.sign(output, next_public, self.fingerprint, next_subkey)
            self.apt(root / 'missed-transition', output, False)
            self.apt(root / 'rotated', output, True, installed)

    def test_deterministic_generation_and_candidate_rejection(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            self.generate(root / 'a', now)
            self.generate(root / 'b', now)
            files = lambda folder: {str(p.relative_to(folder)): repo.digest(p)
                                    for p in folder.rglob('*') if p.is_file()}
            self.assertEqual(files(root / 'a'), files(root / 'b'))
            candidate = repo.read_json(self.candidate)
            candidate['installers']['linux-arm64']['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'bytes changed'):
                repo.validate_candidate(candidate, self.artifacts)
            candidate['version'] = '../escape'
            with self.assertRaises(ValueError):
                repo.validate_candidate(candidate, self.artifacts)
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                repo.validate_deb(self.artifacts / 'jambor-launcher_1.0.0_amd64.deb',
                                  'jambor-launcher', '1.0.0', 'arm64')


if __name__ == '__main__':
    unittest.main()
