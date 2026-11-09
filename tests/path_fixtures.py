r"""Synthetic path fixtures, in one declared place because they must look real.

**Why this file exists and why it is exempt from the identity gate.** The gate refuses any tracked
file carrying a path-shaped string, and it is right to: an embedded path is invisible to
`git grep` and that is exactly how one survives a review. But the tests that pin those patterns
have to contain the shapes, or they prove nothing -- a fixture rewritten as `\\<server>\<share>`
tests the gate's benign filter rather than its detector, and the most valuable test in the suite
is the one asserting that a UNC pattern matches a real UNC path, because the version that shipped
with eight backslashes instead of four matched nothing and reported a confident zero.

So the shapes live here, in a single file listed in `doc_check.IDENTITY_EXEMPT` with a reason,
rather than scattered through the suite where every one would be a finding and the gate would
become something to switch off. This mirrors how the `LICENSE` exemption works: a narrow, named,
explained hole instead of a broad category.

**Every token here is invented.** No account, host or share named below exists. That is the
property that makes the exemption safe, and it is asserted by the suite itself -- a fixture token
matching any real git identity or any host discovered in this repository is a test failure, not a
fixture.
"""

#: An invented account name. Deliberately not a real one, and nothing like a plausible one.
ACCOUNT = 'someacct'

#: Invented hosts. Two, because the inventory and the rewrite are tested independently.
HOST = 'hostname'
HOST_ALT = 'hostbox'

#: An invented share.
SHARE = 'Archive'
SHARE_ALT = 'Store'

# --- Windows user-profile paths -------------------------------------------------------------

PROFILE = rb'C:\Users\someacct\AppData\Local\Temp\copybuffer.blend'
PROFILE_DOCS = rb'C:\Users\someacct\Documents'

# --- POSIX home paths ------------------------------------------------------------------------

POSIX = rb'/home/someacct/src/thing.py and /Users/someacct/other'
POSIX_HOME = rb'/home/someacct'

# --- UNC paths, in each spelling the project has to handle -----------------------------------

UNC = rb'the venv lives on a network share (\\hostname\Archive\proj) and pytest fails'
UNC_DOUBLED = rb"ROOT = '\\\\hostname\\Archive\\proj'"
UNC_EXT = rb'resolves as \\?\UNC\hostname\Archive\proj\python.exe in the self-report'
UNC_FWD = rb"ROOT = os.path.join('//hostname', 'Archive', 'proj')"
UNC_BLEND = rb'\\hostname\Archive\proj\thing.blend'

#: The rewrite's own fixtures use the second host, so the two suites cannot pass by sharing a
#: value that only one of them actually handles.
UNC_ALT = rb'on \\hostbox\Store\proj here'
UNC_ALT_EXT = rb'as \\?\UNC\hostbox\Store\x'
UNC_ALT_FWD = rb"join('//hostbox/Store', 'x')"
UNC_ALT_PATH = rb'\\hostbox\Store\proj\x'
UNC_ALT_SHORT = rb'\\hostbox\Store\x'
UNC_ALT_BLEND = rb'\\hostbox\Store\x.blend'

# --- A mapped-drive path, which is a shape the gate reports but does not refuse ---------------

DRIVE = rb'use <R:\someacct\Designs\thing.scad>;'
DRIVE_FAKE = rb'Q:\Zyzzy\Designs\thing.blend'

#: A base64 run, for the converse tests. Encoded data is wall-to-wall `//token/token/`, which is
#: why no shape may be built on the forward-slash form alone.
BASE64_RUN = rb'//Kd5usbVFZq75Gxw6J17Ive4c2spwv2LrN1Mlsf/93hVVsHk9lcejtalx/7eGs/0PZi98'

#: Regex word boundaries from live source. These present the same shape a UNC host
#: does, and a looser rule read them as one -- which would have substituted a placeholder into a
#: live regex literal.
REGEX_ESCAPES = (rb'\\bwidget\b', rb'\\bwidget_total\\b')


def tokens():
    """Every invented token, for the suite's own check that none of them is real."""
    return (ACCOUNT, HOST, HOST_ALT, SHARE_ALT, 'Zyzzy')
