# Local HTTPS WorkOS experiment disabled

The former harness is disabled and exits without starting Pi, creating a profile,
opening a listener, generating a certificate, or contacting WorkOS. Do not use
an older copy: proxy environment variables cannot enforce network isolation.
A client or subprocess can ignore them and send credentials directly to the
real public staging endpoint. Detecting a proxy bypass afterward is too late.

The former `NO_PROXY` configuration also allowed an issuer domain that was a
suffix of the staging hostname to bypass the proxy. Its self-signed certificate
was a CA trusted process-wide, not a host-scoped leaf. Neither routing nor
certificate trust is configured by the disabled script. Environment-based Pi
profile isolation was not independently verified; the disabled script does not
launch Pi or touch any profile, including global credentials.

A future replacement needs independently enforced egress isolation for the
client and all descendants, including DNS and direct connections, before any
credentials are available; a proxy or post-hoc traffic check alone is not
sufficient. It must also address issuer access, browser isolation, scoped TLS
trust, and credential-store isolation. No such replacement is provided here.
Previously created temporary profiles may remain after abnormal termination;
review them separately without sharing their contents.

Offline regression tests:

```sh
.venv/bin/python -m pytest -q tests/test_workos_local_https.py
```
