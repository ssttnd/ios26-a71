"""Cancel a GitHub Actions run of ssttnd/ios26-a71.

  python -I -X utf8 tools/flow/cancelrun.py RUN_ID
"""
import os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghauth  # noqa: E402

API = "https://api.github.com/repos/ssttnd/ios26-a71"
req = urllib.request.Request(f'{API}/actions/runs/{sys.argv[1]}/cancel', data=b'', method='POST',
                             headers={'User-Agent': 'ios-a71-check', 'Accept': 'application/vnd.github+json',
                                      'Authorization': 'Bearer ' + ghauth.TOKEN})
print(urllib.request.urlopen(req, timeout=60).status)
