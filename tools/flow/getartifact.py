"""Download a GitHub Actions artifact of ssttnd/ios26-a71 and unzip it.

  python -I -X utf8 tools/flow/getartifact.py ARTIFACT_ID OUTDIR
"""
import hashlib, io, os, sys, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghauth  # noqa: E402

ghauth.API = "https://api.github.com/repos/ssttnd/ios26-a71"


def main():
    aid, out = sys.argv[1], sys.argv[2]
    data = ghauth.get(f'/actions/artifacts/{aid}/zip', binary=True)
    print('zip', len(data), 'bytes sha256', hashlib.sha256(data).hexdigest())
    os.makedirs(out, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(data)).extractall(out)
    for name in sorted(os.listdir(out)):
        p = os.path.join(out, name)
        if os.path.isfile(p):
            print(hashlib.sha256(open(p, 'rb').read()).hexdigest(), name)


if __name__ == '__main__':
    main()
