#!/usr/bin/env python3
"""Correlate one run per request ID. usage: analyze.py <rundir>   -> correlation.csv + summary.json (+ prints summary)"""
import sys, re, csv, json, datetime, collections, os
D = sys.argv[1]
def iso(s): return datetime.datetime.strptime(s[:26], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).timestamp()
def rd(f): 
    p = f"{D}/{f}"; return open(p, errors="replace").read() if os.path.exists(p) else ""
mk = {}
for l in rd("markers.txt").splitlines():
    t, m = l.split(" ", 1); mk[m.split()[0]] = float(t)
T0 = mk["T0_scale_up"]
agent = rd("agent.log").splitlines()
def agent_ts(pat):
    for l in agent:
        if re.search(pat, l): return iso(l.split()[0])
a_start = agent_ts("starting as user"); a_sock = agent_ts("Started RPC listener"); a_cfg1 = agent_ts("Config update failed try 1")
# endpoint ready time (host clock; ~30ms skew vs cluster clock)
ep_ready = None
for l in rd("endpoints-watch.txt").splitlines():
    p = l.split(None, 3)
    if len(p) >= 3 and re.match(r"\d+\.\d+\.\d+\.\d+", p[2]) and ep_ready is None: ep_ready = float(p[0])
# startup probe 503->200 transition
poll = [(float(a), b) for a, b in (l.split() for l in rd("poller.log").splitlines() if l.strip())]
first200 = next((t for t, s in poll if s == "200"), None)
first503 = next((t for t, s in poll if s == "503"), None)
# nginx per-connection trace
conns = collections.defaultdict(dict)
for l in rd("nginx.log").splitlines():
    m = re.match(r"(\S+) \d{4}/\d\d/\d\d \S+ \[(\w+)\] \d+#\d+: \*(\d+) (.*)", l)
    if not m: continue
    ts, lvl, c, msg = m.groups(); d = conns[c]
    if (h := re.match(r'http header: "X-Request-ID: (\S+)"', msg)): d["rid"] = h.group(1); d["t_nginx"] = iso(ts)
    if "sigsci_transport_open: cannot connect uds" in msg: d["cls"] = "no-socket"; d["detail"] = re.search(r"errno=(\d+)", msg).group(0)
    if (h := re.search(r"prerequest complete: (\d+) ms: ret=(-?\d+) agent-resp-code=(-?\d+)", msg)):
        d["pre_ms"] = int(h.group(1)); d["ret"] = h.group(2); d["agent_code"] = int(h.group(3))
        d.setdefault("cls", "agent-answered" if int(h.group(3)) == 200 else f"other(code={h.group(3)})")
    if "X-SigSci-Agent:" in msg and "proxy header" in msg: d["agent_hdr"] = msg.split("X-SigSci-Agent:")[1].strip(' "')
    if re.search(r"timed? ?out|timeout", msg, re.I) and "sigsci" in msg.lower(): d["timeout_msg"] = msg[:120]
byrid = {d["rid"]: d for d in conns.values() if "rid" in d}
echo = {}
for l in rd("echo.log").splitlines():
    m = re.match(r"(\d+\.\d+) method=\S+ rid=(\S+) sigsci=\[(.*?)\]", l)
    if m: echo[m.group(2)] = (float(m.group(1)), m.group(3))
rows = []
for l in rd("gen.log").splitlines()[1:]:
    p = l.split(",")
    if len(p) < 6 or not p[0].replace(".", "").isdigit(): continue
    t = float(p[0])
    if t < T0 - 5: continue
    rid = p[1]; n = byrid.get(rid, {}); e = echo.get(rid)
    rows.append(dict(sent=t, rel_T0=round(t - T0, 3), rid=rid, kind=p[2], client_status=p[3], err=p[5],
        nginx_seen=bool(n), module_class=n.get("cls", "" if not n else "no-sigsci-line"), module_detail=n.get("detail", ""), agent_code=n.get("agent_code", ""),
        agent_hdr=n.get("agent_hdr", ""), pre_ms=n.get("pre_ms", ""), upstream_received=bool(e), upstream_ts=e[0] if e else "", upstream_sigsci_hdrs=e[1] if e else ""))
with open(f"{D}/correlation.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
def phase(r):
    t = r["sent"]
    if a_sock and t >= a_sock: return "3_socket_present_no_rules"
    if r["nginx_seen"]: return "2_nginx_up_socket_absent"
    return "1_pod_not_serving"
S = collections.OrderedDict()
for r in rows:
    k = (phase(r), r["module_class"], "upstream" if r["upstream_received"] else "no-upstream", r["client_status"])
    S[k] = S.get(k, 0) + 1
rel = lambda t: None if t is None else round(t - T0, 2)
atk = [r for r in rows if r["kind"] in ("sqli", "xss", "traversal", "block-marker") and r["upstream_received"]]
summary = dict(run=os.path.basename(D), T0=T0, agent_start=rel(a_start), first_config_attempt_failed=rel(a_cfg1), rpc_socket_created=rel(a_sock),
    endpoints_ready=rel(ep_ready), probe_first_503=rel(first503), probe_first_200=rel(first200),
    n_requests=len(rows), n_reached_upstream=sum(r["upstream_received"] for r in rows), n_attack_payloads_reached_upstream=len(atk),
    n_attack_reached_upstream_while_socket_absent=sum(1 for r in atk if phase(r).startswith("2")),
    n_attack_reached_upstream_while_socket_present_no_rules=sum(1 for r in atk if phase(r).startswith("3")),
    module_timeout_messages=sum(1 for d in conns.values() if "timeout_msg" in d),
    counts=[dict(phase=k[0], module=k[1], upstream=k[2], client_status=k[3], n=v) for k, v in sorted(S.items())])
json.dump(summary, open(f"{D}/summary.json", "w"), indent=1)
print(json.dumps({k: v for k, v in summary.items() if k != "counts"}))
for c in summary["counts"]: print("  ", c)
