#!/usr/bin/env python3
"""Timeline of one app's FrontBoard scene from a USB log with sweetdtlog=SpringBoard[,APP] os_log.

  a71-scene-timeline.py LOG BUNDLE_ID [--from LINE] [--app PROCESS]

Rejoins the os_log pieces (`|SpringBoard| <timestamp> ...` header line + message lines) and prints, in order:
scene actions sent / completed / annulled, app launches and activations, watchdog violations, and the app's own
lines about received scene updates, deactivation reasons and backgrounding.
"""
import argparse
import re

TS = re.compile(r'^\|([A-Za-z]+)\| (\d{4}-\d\d-\d\d (\d\d:\d\d:\d\d\.\d+))[-+]\d{4} (\S+)\[(\d+):(\d+)\]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('bundle')
    ap.add_argument('--from', dest='start', type=int, default=1)
    ap.add_argument('--app', default='Preferences')
    a = ap.parse_args()
    app_pat = re.compile(
        r'Received action\(s\)|Deactivation reason|didEnterBackground|willEnterForeground|didBecomeActive|'
        r'invalidateConnection|xpc_connection_cancel|Sending response|scene-update|sceneWillEnterForeground|'
        r'Scene (did|will)|lifecycle')
    sb_pat = re.compile(
        re.escape(a.bundle) + r'.*(Sending scene action|Scene action|Provision violated|declined watchdog)|'
        r'Activate application <SBApplication: [^;]*; ' + re.escape(a.bundle) + r'>|'
        r'Got response for <FBSceneSnapshotAction[^>]*' + re.escape(a.bundle) + r'|'
        r'Sending action\(s\) in update.*|scene content state changed|now:<recentPIDs')
    cur = {}
    with open(a.log, 'rb') as f:
        for n, raw in enumerate(f, 1):
            if n < a.start:
                continue
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            m = TS.match(line)
            if m:
                cur[m.group(1)] = (m.group(3), m.group(4), m.group(5), m.group(6))
                continue
            if line.startswith('CRASH ' + a.app) or (a.app + '[') in line and 'exited' in line:
                print(f'{n:>8}  {"":15} KERNEL {line[:160]}')
                continue
            if not line.startswith('|'):
                continue
            proc = line[1:line.find('|', 1)]
            body = line[len(proc) + 3:].strip()
            if proc == 'SpringBoard' and sb_pat.search(body) and (a.bundle in body or 'Sending action(s)' not in body):
                if 'Sending action(s)' in body or 'content state' in body or 'recentPIDs' in body:
                    if a.bundle not in body:
                        continue
                ts = cur.get(proc, ('?',))[0]
                print(f'{n:>8}  {ts:15} SB  {body[:170]}')
            elif proc == a.app and app_pat.search(body):
                ts, name, pid, tid = cur.get(proc, ('?', '?', '?', '?'))
                print(f'{n:>8}  {ts:15} APP[{pid}:{tid}] {body[:150]}')


if __name__ == '__main__':
    main()
