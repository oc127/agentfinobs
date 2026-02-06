"""
SSL verification patch.

On normal VPS environments, this module does nothing.
It only activates if SSL certificate issues are detected
(e.g., running in certain sandboxed/cloud environments).

Import this module BEFORE any other imports that use requests/httpx.
"""

import os
import ssl
import urllib3

# Only apply SSL patches if explicitly enabled via environment variable
# or if running in a known problematic environment
_FORCE_SSL_PATCH = os.getenv("FORCE_SSL_PATCH", "false").lower() in ("true", "1", "yes")


def _test_ssl_connectivity() -> bool:
    """Test if SSL connections to Polymarket work normally."""
    if _FORCE_SSL_PATCH:
        return False  # Force patch
    try:
        import requests
        resp = requests.get(
            "https://clob.polymarket.com/time",
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


_SSL_OK = _test_ssl_connectivity()

if not _SSL_OK:
    # SSL is broken, apply patches
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    import requests
    _original_send = requests.Session.send

    def _patched_send(self, request, **kwargs):
        kwargs['verify'] = False
        return _original_send(self, request, **kwargs)

    requests.Session.send = _patched_send

    try:
        import httpx
        _original_httpx_client_init = httpx.Client.__init__

        def _patched_httpx_init(self, *args, **kwargs):
            kwargs['verify'] = False
            _original_httpx_client_init(self, *args, **kwargs)

        httpx.Client.__init__ = _patched_httpx_init
    except ImportError:
        pass

    import logging
    logging.getLogger(__name__).info("SSL patches applied (certificate issues detected)")
