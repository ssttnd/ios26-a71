"""Wait for a GitHub Actions run of ssttnd/ios26-a71 to finish; print its conclusion and artifacts.

  python -I -X utf8 tools/flow/waitrun.py RUN_ID [POLL_SECONDS]
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghauth  # noqa: E402

ghauth.API = "https://api.github.com/repos/ssttnd/ios26-a71"


def main():
    run, poll = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 60
    while True:
        try:
            r = ghauth.get(f'/actions/runs/{run}')
        except Exception as e:  # transient network errors
            print('poll error', e, flush=True)
            time.sleep(poll)
            continue
        if r['status'] == 'completed':
            print(run, r['conclusion'], r['head_sha'][:7])
            for a in ghauth.get(f'/actions/runs/{run}/artifacts')['artifacts']:
                print('artifact', a['id'], a['name'], a['size_in_bytes'])
            return
        time.sleep(poll)


if __name__ == '__main__':
    main()
