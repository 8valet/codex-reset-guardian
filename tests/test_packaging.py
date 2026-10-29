import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_public_files_and_installers_exist(self):
        for rel in [
            'README.md',
            'SECURITY.md',
            'CONTRIBUTING.md',
            'LICENSE',
            'CHANGELOG.md',
            'config.example.toml',
            'scripts/install-linux.sh',
            'scripts/install-macos.sh',
            'scripts/install-windows.ps1',
        ]:
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_platform_installers_run_user_scoped_daemon(self):
        linux = (ROOT / 'scripts/install-linux.sh').read_text()
        mac = (ROOT / 'scripts/install-macos.sh').read_text()
        win = (ROOT / 'scripts/install-windows.ps1').read_text()

        self.assertIn('systemctl --user', linux)
        self.assertNotIn('sudo ', linux)
        self.assertIn('codex=$(command -v codex)', linux)
        self.assertIn('CODEX_RESET_GUARDIAN_CODEX', linux)

        self.assertIn('LaunchAgents', mac)
        self.assertIn('reset-guardian', mac)
        self.assertIn('guardian=$(command -v reset-guardian)', mac)
        self.assertIn('codex=$(command -v codex)', mac)
        self.assertIn('<string>$guardian_xml</string>', mac)
        self.assertIn('CODEX_RESET_GUARDIAN_CODEX', mac)
        self.assertNotIn('<string>/usr/bin/env</string>', mac)

        self.assertIn('ONLOGON', win.upper())
        self.assertIn('reset-guardian', win)
        self.assertIn('Get-Command codex', win)
        self.assertIn('CODEX_RESET_GUARDIAN_CODEX', win)

    def test_tracked_public_tree_has_no_private_environment_markers(self):
        private_patterns = [
            re.compile(r'\b192\.168\.\d{1,3}\.\d{1,3}\b'),
            re.compile(r'\b100\.(?:6[4-9]|[78]\d|9\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b'),
            re.compile(r'RateLimitResetCredit_[A-Za-z0-9]{12,}'),
            re.compile(r'azizos[-_](?:mobile|agent)', re.IGNORECASE),
        ]
        for path in ROOT.rglob('*'):
            if not path.is_file() or '.git' in path.parts or '__pycache__' in path.parts:
                continue
            if path == Path(__file__).resolve() or path.suffix in {'.pyc', '.db'}:
                continue
            text = path.read_text(errors='ignore')
            for pattern in private_patterns:
                self.assertIsNone(pattern.search(text), f'{pattern.pattern} matched {path}')

    def test_example_config_uses_env_indirection_for_secrets(self):
        text = (ROOT / 'config.example.toml').read_text()
        for name in ['NTFY_TOKEN', 'GOTIFY_TOKEN', 'TELEGRAM_BOT_TOKEN', 'DISCORD_WEBHOOK_URL']:
            self.assertIn('env:' + name, text)


class CiMetadataTests(unittest.TestCase):
    def test_ci_covers_linux_windows_macos_and_supported_python_versions(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertIn('ubuntu-latest', workflow)
        self.assertIn('windows-latest', workflow)
        self.assertIn('macos-latest', workflow)
        for version in ('3.11', '3.12', '3.13', '3.14'):
            self.assertIn(f'"{version}"', workflow)
        self.assertIn('unittest discover -s tests', workflow)
        self.assertIn('compileall', workflow)
        self.assertIn('pip install ".[desktop]"', workflow)
        self.assertIn('DesktopNotifierSync', workflow)
        self.assertIn('bash -n scripts/install-linux.sh scripts/install-macos.sh', workflow)
        self.assertIn('ParseFile', workflow)

    def test_project_metadata_points_to_public_repository(self):
        text = (ROOT / 'pyproject.toml').read_text()
        self.assertIn('https://github.com/8valet/codex-reset-guardian', text)
        self.assertIn('version = "0.1.0"', text)
        self.assertIn('keywords', text)

    def test_public_version_is_consistent(self):
        expected = '0.1.0'
        self.assertIn(f'__version__ = "{expected}"', (ROOT / 'src/codex_reset_guardian/__init__.py').read_text())
        self.assertIn(f'"version": "{expected}"', (ROOT / 'src/codex_reset_guardian/appserver.py').read_text())
        self.assertIn(f'codex-reset-guardian/{expected}', (ROOT / 'src/codex_reset_guardian/notifications.py').read_text())
        self.assertIn(f'## {expected} -', (ROOT / 'CHANGELOG.md').read_text())

    def test_release_workflow_builds_tagged_version(self):
        workflow = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('tags:', workflow)
        self.assertIn('"v*"', workflow)
        self.assertIn('python -m build', workflow)
        self.assertIn('gh release create', workflow)
        self.assertIn('GITHUB_REF_NAME', workflow)
        self.assertIn('tomllib.loads', workflow)
        self.assertNotIn('re.search', workflow)
