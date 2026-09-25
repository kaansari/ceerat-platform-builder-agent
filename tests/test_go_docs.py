import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ceerat_builder.go_docs import GoDocsError, load_go_docs
from ceerat_builder.context_loader import ARCHITECTURE_DOCS, PROMPTS, load_agent_context


@unittest.skipUnless(shutil.which('go'), 'Go toolchain required')
class GoDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.builder = self.workspace / 'ceerat-platform-builder-agent'
        self.builder.mkdir()
        self.module = self.workspace / 'contracts-repo/packages/ceerat-contracts'
        self.module.mkdir(parents=True)
        (self.module / 'go.mod').write_text('module example.test/contracts\n\ngo 1.20\n')
        (self.workspace / 'go.work').write_text('go 1.20\n\nuse ./contracts-repo/packages/ceerat-contracts\n')
        self.package = self.module / 'customer'
        self.package.mkdir()
        self.source = self.package / 'customer.go'
        self.source.write_text('// Package customer manages customer profiles.\npackage customer\n\n// CustomerProfilePatch changes selected fields.\ntype CustomerProfilePatch struct { Phone string }\n')
        for name in ARCHITECTURE_DOCS + PROMPTS:
            p = self.builder / '.ceerat-agent' / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('Stable architecture policy.\n')

    def test_live_symbol_docs_change_without_markdown_refresh(self):
        first = load_go_docs(self.builder, package='example.test/contracts/customer', symbol='CustomerProfilePatch')
        self.assertIn('Phone string', first['packages'][0]['documentation'])
        self.source.write_text(self.source.read_text().replace('Phone string', 'Email string'))
        second = load_go_docs(self.builder, package='example.test/contracts/customer', symbol='CustomerProfilePatch')
        self.assertIn('Email string', second['packages'][0]['documentation'])
        self.assertNotIn('Phone string', second['packages'][0]['documentation'])
        self.assertNotEqual(first['packages'][0]['sha256'], second['packages'][0]['sha256'])
        self.assertIn('/example.test/contracts/customer#CustomerProfilePatch', second['packages'][0]['pkgsite_url'])

    def test_context_contains_current_go_declarations(self):
        context = load_agent_context(self.builder, request='customer profile')
        self.assertIn('CustomerProfilePatch', context.architecture_context)
        self.assertTrue(context.go_documentation['packages'])

    def test_unknown_package_and_invalid_symbol_fail(self):
        for kwargs in [{'package': 'example.test/remote'}, {'package': 'example.test/contracts/customer', 'symbol': '-all'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(GoDocsError):
                load_go_docs(self.builder, **kwargs)

    def test_cli_returns_real_symbol_documentation(self):
        from typer.testing import CliRunner
        from ceerat_builder.main import app
        result = CliRunner().invoke(app, ['go-docs', '--project-root', str(self.builder),
            '--package', 'example.test/contracts/customer', '--symbol', 'CustomerProfilePatch'])
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output)
        self.assertIn('Phone string', payload['packages'][0]['documentation'])

    def test_command_timeout_is_actionable(self):
        import subprocess
        from ceerat_builder.go_docs import _run
        with patch('ceerat_builder.go_docs.subprocess.run', side_effect=subprocess.TimeoutExpired('go', 30)):
            with self.assertRaisesRegex(GoDocsError, 'timed out'):
                _run(['go', 'doc', '.'], self.package, dict(os.environ))

    def test_missing_workspace_is_actionable(self):
        (self.workspace / 'go.work').unlink()
        with self.assertRaisesRegex(GoDocsError, 'go.work'):
            load_go_docs(self.builder)

    def test_missing_go_does_not_fall_back_to_memory(self):
        with patch.dict(os.environ, {'PATH': ''}):
            with self.assertRaisesRegex(GoDocsError, 'Go toolchain'):
                load_go_docs(self.builder)

    def test_private_module_environment_cannot_enable_downloads(self):
        import subprocess
        real_run = subprocess.run
        with patch.dict(os.environ, {'GOPRIVATE': 'example.test/*', 'GONOPROXY': 'example.test/*'}):
            with patch('ceerat_builder.go_docs.subprocess.run', wraps=real_run) as run:
                payload = load_go_docs(self.builder, request='customer')
        self.assertIn('CustomerProfilePatch', payload['packages'][0]['documentation'])
        self.assertTrue(run.call_args_list)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs['env']['GOPROXY'], 'off')
            self.assertEqual(call.kwargs['env']['GONOPROXY'], 'none')
            self.assertEqual(call.kwargs['env']['GOTOOLCHAIN'], 'local')

    def test_truncation_is_visible(self):
        with patch('ceerat_builder.go_docs.MAX_DOC_CHARS', 30):
            result = load_go_docs(self.builder, request='customer')
        self.assertTrue(result['packages'][0]['truncated'])
        self.assertIn('truncated', result['packages'][0]['documentation'])

    def test_non_workspace_module_is_rejected(self):
        (self.workspace / 'go.work').write_text('go 1.20\n')
        with self.assertRaisesRegex(GoDocsError, 'go work use'):
            load_go_docs(self.builder)


if __name__ == '__main__':
    unittest.main()
