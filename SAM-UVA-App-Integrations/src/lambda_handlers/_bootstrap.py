"""
_bootstrap — make the ``src`` package importable regardless of CodeUri layout.

The hexagonal code uses absolute imports rooted at ``src`` (e.g.
``from src.core.use_cases.last_connection import lambda_handler``). This works in:

  * the test environment, where ``SAM-UVA-App-Integrations/`` is on ``sys.path``
    and ``src`` is a real package directory; and
  * the legacy shims, which add the SAM root to ``sys.path``.

But the deployed HTTP / event Lambdas use ``CodeUri: src``, so the CONTENTS of
``src`` (``core/``, ``adapters/``, ``lambda_handlers/`` ...) land directly at the
Lambda task root — there is no ``src`` package there. To let the same
``from src....`` imports resolve in that context, this bootstrap registers an
alias module named ``src`` whose ``__path__`` is the Lambda task root, so
``src.core``, ``src.adapters`` etc. resolve to those top-level packages.

Import this module FIRST in every lambda_handlers entrypoint.
"""

import os
import sys
import types


def ensure_src_importable() -> None:
    if "src" in sys.modules:
        return
    # Already importable as a real package? (test / shim context)
    try:
        import src  # noqa: F401
        return
    except ImportError:
        pass

    # Deployed context: this file lives at <root>/lambda_handlers/_bootstrap.py,
    # so <root> is two levels up and holds core/, adapters/, etc.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)

    pkg = types.ModuleType("src")
    pkg.__path__ = [root]  # treat the task root as the `src` package directory
    sys.modules["src"] = pkg


ensure_src_importable()
