"""Public descriptor exports coexist with implementation imports, in fresh interpreters."""

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("first_import", [
    "import lm15",
    "from lm15.providers.xai import XaiLM",
    "from lm15.login import providers as descriptors",
])
def test_descriptor_exports_and_import_order(first_import):
    result = subprocess.run(
        [sys.executable, "-c", first_import + "\n" + textwrap.dedent("""
            import importlib
            import sys
            import types
            import lm15
            from lm15 import providers
            from lm15.providers import XaiLM, AnthropicLM, AsyncXaiLM
            from lm15.providers.xai import XaiLM as ImplementationXaiLM

            if 'lm15.login' not in sys.modules:
                # Merely using the package and public classes must stay lazy.
                assert not any(n.startswith('lm15.login.') for n in sys.modules)
            elif 'descriptors' not in globals():
                raise AssertionError('implementation imports loaded login')

            assert providers is importlib.import_module('lm15.providers')
            assert XaiLM is ImplementationXaiLM is lm15.XaiLM
            assert AnthropicLM is lm15.AnthropicLM
            assert AsyncXaiLM is lm15.AsyncXaiLM
            from lm15 import login_providers
            from lm15.login import providers as descriptors
            assert login_providers is descriptors
            assert login_providers.meta.id == 'meta'
            assert login_providers.xai.id == 'xai'
            assert login_providers.openai_codex.id == 'openai-codex'
            for name in dir(descriptors):
                assert getattr(login_providers, name) is getattr(descriptors, name)
            for name in ('xai', 'openai_codex', 'anthropic', 'gemini', 'openai'):
                assert isinstance(getattr(providers, name), types.ModuleType)
                assert getattr(descriptors, name).id == name.replace('_', '-')

            # Re-importing implementations after descriptor access changes nothing.
            import lm15.providers.xai
            from lm15.providers.xai import XaiLM as AfterXaiLM
            from lm15.providers import XaiLM as AfterPublicXaiLM
            assert AfterXaiLM is AfterPublicXaiLM is XaiLM
            assert lm15.providers.xai is importlib.import_module('lm15.providers.xai')
            assert lm15.login_providers is login_providers
            for name in ('not_a_provider', '_private'):
                try:
                    getattr(login_providers, name)
                except AttributeError:
                    pass
                else:
                    raise AssertionError(name)
        """)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
