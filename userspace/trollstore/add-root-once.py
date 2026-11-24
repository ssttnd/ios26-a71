"""Add launchd job org.a71.root-once to a merged /System/Library/xpc/launchd.plist.

usage: add-root-once.py IN_PLIST OUT_PLIST
The job runs /private/var/local/root-once.sh as root at load, logging to /private/var/local/root-once.log.
"""
import plistlib
import sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, 'rb') as f:
    data = plistlib.load(f)
jobs = data['LaunchDaemons']
key = '/System/Library/LaunchDaemons/org.a71.root-once.plist'
if key in jobs:
    raise SystemExit('org.a71.root-once already present')
jobs[key] = {
    'Label': 'org.a71.root-once',
    'ProgramArguments': ['/bin/sh', '/private/var/local/root-once.sh'],
    'RunAtLoad': True,
    'UserName': 'root',
    'EnvironmentVariables': {'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
    'StandardOutPath': '/private/var/local/root-once.log',
    'StandardErrorPath': '/private/var/local/root-once.log',
}
with open(dst, 'wb') as f:
    plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
print('jobs', len(jobs))
