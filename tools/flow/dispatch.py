"""Dispatch a workflow on ssttnd/ios26-a71 and print the new run id.

  python -I -X utf8 tools/flow/dispatch.py WORKFLOW.yml BRANCH [NAME=VALUE ...]

Uses the token of tools/flow/ghauth.py (git credential store; never printed).
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghauth  # noqa: E402

ghauth.API = "https://api.github.com/repos/ssttnd/ios26-a71"


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    wf, ref = sys.argv[1], sys.argv[2]
    inputs = dict(a.split('=', 1) for a in sys.argv[3:])
    before = {r['id'] for r in ghauth.get(f'/actions/workflows/{wf}/runs?branch={ref}&per_page=10')['workflow_runs']}
    body = json.dumps({'ref': ref, 'inputs': inputs}).encode()
    req = urllib.request.Request(ghauth.API + f'/actions/workflows/{wf}/dispatches', data=body, method='POST',
                                 headers={'User-Agent': 'ios-a71-check', 'Accept': 'application/vnd.github+json',
                                          'Authorization': 'Bearer ' + ghauth.TOKEN})
    urllib.request.urlopen(req, timeout=60).read()
    for _ in range(30):
        time.sleep(4)
        runs = ghauth.get(f'/actions/workflows/{wf}/runs?branch={ref}&per_page=10')['workflow_runs']
        new = [r for r in runs if r['id'] not in before]
        if new:
            r = new[0]
            print(r['id'], r['status'], r['head_sha'][:7], r['html_url'])
            return
    print('dispatched; run id not visible yet')


if __name__ == '__main__':
    main()
