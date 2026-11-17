#!/usr/bin/env python3
"""Aggregate summary2.json across reps. usage: aggregate.py PREFIX [PREFIX...]"""
import json, glob, re, sys, os, statistics as st
R = os.path.expanduser("~/Downloads/ngwaf-test/results/raw")
def reason(lines, run=None):
    lines = open(f"{R}/{run}/agent.log", errors="replace").read().splitlines() if run else lines
    for l in lines:
        if "Config update failed try 1" in l:
            m = re.findall(r'(no such host|connection reset by peer|connection refused|context deadline exceeded|got HTTP error[^,]*?: \d+|i/o timeout)', l)
            return sorted(set(m))
    return []
for pre in sys.argv[1:]:
    runs = sorted(glob.glob(f"{R}/{pre}-rep*/summary2.json")) or sorted(glob.glob(f"{R}/{pre}*/summary2.json"))
    print(f"=== {pre} ({len(runs)} runs)")
    for f in runs:
        S = json.load(open(f)); d = S.get("rpc_decoded", {})
        print(f"  {S['run']}: socket@{S['socket_created']}s Ready@{S['pod_Ready']}s firstUp@{S['first_upstream_hit']}s | upstream {S['upstream_by_phase_and_sigsci_header']} | attack {S['attack_payloads_upstream_by_phase']}")
        print(f"      cfg-fail reason: {reason(None, S['run'])} | rpc resp: {d.get('responses')} user={d.get('with_X_Request_ID_generator_traffic')} internal={d.get('without_X_Request_ID_controller_internal')}")
        print(f"      statsd: {S.get('statsd_counters_sum')} | nginx: {S['nginx_module_lines_by_phase']}")
        if "freeze_window_client" in S: print(f"      freeze client: {S['freeze_window_client']}")
