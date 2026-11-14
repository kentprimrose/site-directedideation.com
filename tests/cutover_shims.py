"""Portable stand-ins for GNU/Linux tools so root scripts run unprivileged on macOS."""

import sys
from pathlib import Path

PY = f"#!{sys.executable}\n"

SHIMS = {
    # flock -w SECONDS -x 9 (real fcntl semantics on inherited fd 9).
    "flock": PY
    + """
import fcntl, sys, time
a = sys.argv[1:]
wait = None
if a[0] == '-w':
    wait = float(a[1]); a = a[2:]
assert a[0] == '-x'
fd = int(a[1])
end = None if wait is None else time.monotonic() + wait
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); break
    except BlockingIOError:
        if end is not None and time.monotonic() >= end: sys.exit(1)
        time.sleep(0.05)
""",
    # stat -c FORMAT [--] PATH with %u forced to 0 (tests are not root).
    "stat": PY
    + """
import os, sys
a = sys.argv[1:]
assert a[0] == '-c'
fmt, path = a[1], a[-1]
st = os.lstat(path)
print(fmt.replace('%u', '0').replace('%a', format(st.st_mode & 0o7777, 'o')).replace('%s', str(st.st_size)))
""",
    "sha256sum": PY
    + """
import hashlib, sys
p = sys.argv[-1]
print(hashlib.sha256(open(p, 'rb').read()).hexdigest() + '  ' + p)
""",
    "timeout": "#!/bin/bash\nshift 3\nexec \"$@\"\n",
    # install -o root -g root -m MODE -- SRC DST
    "install": "#!/bin/bash\nwhile [[ $1 != -- ]]; do [[ $1 == -m ]] && m=$2; shift; done\nshift\ncp -- \"$1\" \"$2\" && chmod \"$m\" \"$2\"\n",
}


def write_shims(directory: Path, extra: dict | None = None) -> None:
    directory.mkdir(exist_ok=True)
    for name, text in {**SHIMS, **(extra or {})}.items():
        path = directory / name
        path.write_text(text)
        path.chmod(0o755)
