"""Generate a bounded Ubuntu 26.04 archive from reviewed, immutable Debian packages."""
import argparse
import datetime as dt
import email.utils
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

SUITE = 'ubuntu-26.04-beta'
ORIGIN = 'Jambor'
BASE = 'https://assets.jojo.dev.br'
ARCHITECTURES = {'linux-x64': 'amd64', 'linux-arm64': 'arm64'}
VALIDITY = dt.timedelta(days=7)
EXPIRY_WARNING = dt.timedelta(hours=48)
KEY_WARNING = dt.timedelta(days=30)
MAX_METADATA_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_ENTRIES = 10000
COMMAND_TIMEOUT_SECONDS = 120
MAX_VERSION_MARKER_BYTES = 64
MAX_CLOCK_SKEW = dt.timedelta(minutes=5)
ELF_HEADER_BYTES = 20
ELF_MACHINE_OFFSET = 18
ELF_MACHINE_BY_ARCHITECTURE = {'amd64': 62, 'arm64': 183}
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
COMMIT = re.compile(r'[0-9a-f]{40}')
SHA256 = re.compile(r'[0-9a-f]{64}')
FINGERPRINT = re.compile(r'[A-F0-9]{40}')
RUNTIME_DEPENDENCIES = (
    'python3:any, libc6 (>= 2.43), libstdc++6, zlib1g, libssl3t64, libicu78, '
    'libvulkan1, libsecret-1-0, libwayland-client0, libwayland-cursor0, libwayland-egl1, '
    'libxkbcommon0, libx11-6, libxext6, libxcursor1, libxi6, libxfixes3, libxrandr2, libxss1')


def run(*arguments, cwd=None, data=None):
    """Keep subprocess diagnostics private: GnuPG stderr can contain identity data."""
    result = subprocess.run(arguments, cwd=cwd, input=data, capture_output=True,
                            timeout=COMMAND_TIMEOUT_SECONDS)
    if result.returncode:
        raise ValueError(f'{Path(arguments[0]).name} failed (exit {result.returncode})')
    return result.stdout


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path, limit):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Expected a bounded regular file')


def read_json(path):
    regular(path, MAX_METADATA_BYTES)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=unique)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def checked_match(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value)


def validate_candidate(candidate, artifacts):
    if (candidate.get('schemaVersion') != 1 or candidate.get('channel') != 'beta'
            or not checked_match(VERSION, candidate.get('version'))
            or any(not checked_match(COMMIT, candidate.get(key)) for key in ('commit', 'coreCommit'))
            or set(candidate.get('installers', {})) != set(ARCHITECTURES)):
        raise ValueError('Invalid Linux candidate identity')
    packages = []
    for rid, arch in ARCHITECTURES.items():
        row = candidate['installers'][rid]
        filename = f'jambor-launcher_{candidate["version"]}_{arch}.deb'
        expected = f'{BASE}/jambor/launcher/beta/{candidate["version"]}/{filename}'
        if (set(row) != {'url', 'size', 'sha256'} or row['url'] != expected
                or type(row['size']) is not int or not 0 < row['size'] <= MAX_PACKAGE_BYTES
                or not checked_match(SHA256, row['sha256'])):
            raise ValueError('Invalid installer identity')
        path = artifacts / filename
        regular(path, MAX_PACKAGE_BYTES)
        if path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise ValueError('Installer bytes changed')
        validate_deb(path, 'jambor-launcher', candidate['version'], arch)
        packages.append(path)
    return packages


def fields(text):
    result = {}
    previous = None
    for line in text.splitlines():
        if line.startswith((' ', '\t')) and previous:
            result[previous] += '\n' + line
        elif line:
            key, separator, value = line.partition(':')
            if not separator or key in result:
                raise ValueError('Invalid or duplicate Debian field')
            result[key] = value.lstrip(' ')
            previous = key
    return result


def validate_deb(path, package, version, architecture):
    regular(path, MAX_PACKAGE_BYTES)
    control = None
    required = ({'usr/lib/jambor-launcher/Jambor', 'usr/lib/jambor-launcher/Jambor.Updater',
                 'usr/lib/jambor-launcher/release-version.txt', 'usr/bin/jambor',
                 'usr/share/applications/dev.jojo.jambor.desktop',
                 'usr/share/icons/hicolor/256x256/apps/dev.jojo.jambor.png'}
                if package == 'jambor-launcher' else {'usr/share/keyrings/jambor-archive-keyring.gpg'})
    directories = {str(parent) for name in required for parent in PurePosixPath(name).parents}
    for option in ('--ctrl-tarfile', '--fsys-tarfile'):
        # Stream decompression to enforce the expanded bound before allocating/extracting.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(['dpkg-deb', option, str(path)], stdout=subprocess.PIPE, stderr=errors)
            try:
                seen, found, total = set(), set(), 0
                with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
                    for member in archive:
                        name = member.name.removeprefix('./').rstrip('/')
                        parts = PurePosixPath(name).parts
                        total += member.size
                        if (name in seen or len(seen) >= MAX_ENTRIES or total > MAX_EXPANDED_BYTES
                                or member.name.startswith('/') or '..' in parts
                                or (name not in ('', '.') and str(PurePosixPath(name)) != name)
                                or member.uid != 0 or member.gid != 0 or member.mode & 0o7022
                                or not (member.isfile() or member.isdir())):
                            raise ValueError('Unsafe Debian archive entry')
                        seen.add(name)
                        if not member.isfile():
                            if (option == '--fsys-tarfile' and name not in ('', '.') and name not in directories
                                    and not (package == 'jambor-launcher' and name.startswith('usr/lib/jambor-launcher/'))):
                                raise ValueError('Unexpected installed directory')
                            continue
                        if option == '--ctrl-tarfile':
                            if name not in ('control', 'md5sums'):
                                raise ValueError('Maintainer scripts and conffiles are forbidden')
                            if name == 'control':
                                if member.size > MAX_METADATA_BYTES:
                                    raise ValueError('Debian control exceeds metadata bound')
                                control = fields(archive.extractfile(member).read().decode())
                        elif (name not in required and not
                              (package == 'jambor-launcher' and name.startswith('usr/lib/jambor-launcher/'))):
                            raise ValueError('Unexpected installed path')
                        if option == '--fsys-tarfile':
                            found.add(name)
                            if name == 'usr/bin/jambor' and not member.mode & 0o111:
                                raise ValueError('Bootstrap must be executable')
                            if name.endswith('/release-version.txt'):
                                if member.size > MAX_VERSION_MARKER_BYTES or archive.extractfile(member).read().strip() != version.encode():
                                    raise ValueError('Payload version mismatch')
                            if name in ('usr/lib/jambor-launcher/Jambor', 'usr/lib/jambor-launcher/Jambor.Updater'):
                                header = archive.extractfile(member).read(ELF_HEADER_BYTES)
                                machine = ELF_MACHINE_BY_ARCHITECTURE[architecture]
                                if (len(header) != ELF_HEADER_BYTES or header[:7] != b'\x7fELF\x02\x01\x01'
                                        or int.from_bytes(header[ELF_MACHINE_OFFSET:ELF_HEADER_BYTES], 'little') != machine
                                        or not member.mode & 0o111):
                                    raise ValueError('Invalid executable architecture or mode')
                if option == '--fsys-tarfile' and not required <= found:
                    raise ValueError('Incomplete Debian payload')
                if process.wait(timeout=COMMAND_TIMEOUT_SECONDS):
                    raise ValueError('Cannot read Debian archive')
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                process.wait()
        if option == '--ctrl-tarfile':
            if control is None or any(control.get(key) != value for key, value in
                    (('Package', package), ('Version', version), ('Architecture', architecture))):
                raise ValueError('Debian package identity mismatch')
            if package == 'jambor-launcher' and (control.get('Depends') != RUNTIME_DEPENDENCIES
                                               or control.get('Recommends') != 'mesa-vulkan-drivers'):
                raise ValueError('Unreviewed launcher dependencies')
            if any(key in control for key in ('Pre-Depends', 'Conflicts', 'Breaks', 'Replaces', 'Provides', 'Essential')):
                raise ValueError('Unexpected package relationship')


def keyring_package(public_key, version, destination):
    if not checked_match(VERSION, version):
        raise ValueError('Invalid keyring version')
    regular(public_key, MAX_METADATA_BYTES)
    if not public_key.read_bytes().startswith(b'-----BEGIN PGP PUBLIC KEY BLOCK-----'):
        raise ValueError('An armored public certificate is required')
    packets = run('gpg', '--batch', '--list-packets', str(public_key))
    if b':secret key packet:' in packets or b':secret sub key packet:' in packets:
        raise ValueError('Private key packets must never enter the archive')
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        target = root / 'usr/share/keyrings/jambor-archive-keyring.gpg'
        target.parent.mkdir(parents=True)
        target.write_bytes(run('gpg', '--batch', '--dearmor', data=public_key.read_bytes()))
        control = root / 'DEBIAN/control'
        control.parent.mkdir()
        control.write_text(f'Package: jambor-archive-keyring\nVersion: {version}\nArchitecture: all\n'
                           'Maintainer: Jojo <6a6f6a6f@users.noreply.github.com>\n'
                           'Section: misc\nPriority: optional\n'
                           'Description: Archive trust keys for the Jambor APT repository\n')
        for path in (root, *root.rglob('*')):
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.utime(path, (0, 0))
        run('env', 'SOURCE_DATE_EPOCH=0', 'dpkg-deb', '--root-owner-group', '--build', str(root), str(destination))
    validate_deb(destination, 'jambor-archive-keyring', version, 'all')


def verify(inrelease, public_key, fingerprint, now=None, allow_expired=False):
    regular(inrelease, MAX_METADATA_BYTES)
    if not checked_match(FINGERPRINT, fingerprint):
        raise ValueError('Invalid signing fingerprint')
    now = now or dt.datetime.now(dt.timezone.utc)
    with tempfile.TemporaryDirectory() as scratch:
        home = Path(scratch)
        keyring = home / 'trusted.gpg'
        keyring.write_bytes(run('gpg', '--batch', '--dearmor', data=public_key.read_bytes()))
        status = run('gpgv', '--homedir', str(home), '--keyring', str(keyring),
                     '--status-fd', '1', str(inrelease)).decode()
        if not any(line.startswith('[GNUPG:] VALIDSIG ') and line.split()[-1] == fingerprint
                   for line in status.splitlines()):
            raise ValueError('Unexpected archive signer')
        content = run('gpg', '--batch', '--homedir', str(home), '--no-default-keyring',
                      '--keyring', str(keyring), '--decrypt', str(inrelease)).decode()
    release = fields(content)
    issued = email.utils.parsedate_to_datetime(release['Date'])
    expiry = email.utils.parsedate_to_datetime(release['Valid-Until'])
    if (issued > now + MAX_CLOCK_SKEW or expiry <= issued or expiry - issued > VALIDITY
            or (not allow_expired and expiry <= now)
            or release.get('Suite') != SUITE or release.get('Origin') != ORIGIN
            or release.get('Architectures') != 'amd64 arm64' or release.get('Components') != 'main'
            or release.get('Acquire-By-Hash') != 'yes'):
        raise ValueError('Invalid or expired archive metadata')
    return release


def generate(candidate_path, artifacts, public_key, keyring_version, generator_commit, output, now):
    if not checked_match(COMMIT, generator_commit) or now.tzinfo is None:
        raise ValueError('Generator revision and timezone are required')
    candidate = read_json(candidate_path)
    packages = validate_candidate(candidate, artifacts)
    output.mkdir(parents=True, exist_ok=False)
    pool = output / 'pool/main/j/jambor-launcher'
    pool.mkdir(parents=True)
    for package in packages:
        shutil.copyfile(package, pool / package.name)
    keypool = output / 'pool/main/j/jambor-archive-keyring'
    keypool.mkdir(parents=True)
    keydeb = keypool / f'jambor-archive-keyring_{keyring_version}_all.deb'
    keyring_package(public_key, keyring_version, keydeb)
    keys = output / 'keys'
    keys.mkdir()
    shutil.copyfile(public_key, keys / 'jambor-archive-keyring.asc')
    state = dict(schemaVersion=1, candidate=candidate, generatorCommit=generator_commit,
                 keyringVersion=keyring_version, keyringSha256=digest(keydeb), publicKeySha256=digest(public_key))
    state_path = output / 'state.json'
    write_json(state_path, state)
    state_hash = digest(state_path)
    snapshot = output / 'snapshots' / state_hash
    snapshot.mkdir(parents=True)
    state_path.rename(snapshot / 'state.json')
    shutil.copyfile(public_key, snapshot / 'archive-key.asc')
    distribution = output / 'dists' / SUITE
    for arch in ARCHITECTURES.values():
        index = distribution / 'main' / f'binary-{arch}'
        index.mkdir(parents=True)
        data = run('apt-ftparchive', '-a', arch, 'packages', 'pool', cwd=output)
        for name, content in (('Packages', data), ('Packages.gz', gzip.compress(data, mtime=0))):
            path = index / name
            path.write_bytes(content)
            by_hash = index / 'by-hash/SHA256' / digest(path)
            by_hash.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, by_hash)
    options = {'Origin': ORIGIN, 'Label': 'Jambor Beta', 'Suite': SUITE, 'Codename': SUITE,
               'Architectures': 'amd64 arm64', 'Components': 'main', 'Acquire-By-Hash': 'yes',
               'Date': email.utils.format_datetime(now, usegmt=True)}
    arguments = [argument for key, value in options.items()
                 for argument in ('-o', f'APT::FTPArchive::Release::{key}={value}')]
    data = run('apt-ftparchive', *arguments, '-o', 'APT::FTPArchive::Release::MD5=false',
               '-o', 'APT::FTPArchive::Release::SHA1=false', 'release', '.', cwd=distribution)
    expiry = email.utils.format_datetime(now + VALIDITY, usegmt=True)
    (distribution / 'Release').write_bytes(data +
        f'Valid-Until: {expiry}\nX-Jambor-State-SHA256: {state_hash}\n'.encode())
    return state


def sign(output, public_key, fingerprint, signing_subkey):
    if not checked_match(FINGERPRINT, signing_subkey) or not checked_match(FINGERPRINT, fingerprint):
        raise ValueError('Explicit primary and signing subkey fingerprints required')
    directory = output / 'dists' / SUITE
    destination = directory / 'InRelease'
    run('gpg', '--batch', '--yes', '--pinentry-mode', 'error', '--digest-algo', 'SHA256',
        '--local-user', signing_subkey + '!', '--output', str(destination),
        '--clearsign', str(directory / 'Release'))
    verify(destination, public_key, fingerprint)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--keyring-version', required=True)
    parser.add_argument('--generator-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--date', required=True, help='UTC ISO 8601 generation time')
    args = parser.parse_args()
    generate(args.candidate, args.artifacts, args.public_key, args.keyring_version,
             args.generator_commit, args.output, dt.datetime.fromisoformat(args.date))


if __name__ == '__main__':
    main()
