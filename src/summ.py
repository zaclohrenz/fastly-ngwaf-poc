#!/usr/bin/env python3
"""Per-run summary relative to container startedAt. usage: summ.py <rundir>  -> summary2.json (+prints)"""
import re, sys, json, os, datetime, collections, subprocess
D = sys.argv[1]
def iso(s): return datetime.datetime.strptime(s[:26], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).timestamp()
def pt(s): return datetime.datetime.strptime(s[:26], "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).timestamp()
def rd(f): p = f"{D}/{f}"; return open(p, errors="replace").read() if os.path.exists(p) else ""
pod = json.load(open(f"{D}/pod.json"))
sa = {c["name"]: iso(c["state"]["running"]["startedAt"].replace("Z", ".000000")) for c in pod["status"]["containerStatuses"]}
C0 = sa["controller"]; rel = lambda t: None if t is None else round(t - C0, 2)
mk = {}
for l in rd("markers.txt").splitlines():
    t, m = l.split(" ", 1); mk[m.split()[0]] = float(t)
T0 = mk["T0_scale_up"]
ag = rd("agent.log").splitlines()
def agl(p):
    for i, l in enumerate(ag, 1):
        if re.search(p, l): return i, pt(l.split(" ", 1)[1])
    return None, None
_, a_cfg = agl("Config update failed try 1"); sl, a_sock = agl("Started RPC listener")
ready = next((iso(c["lastTransitionTime"].replace("Z", ".000000")) for c in pod["status"]["conditions"] if c["type"] == "Ready" and c["status"] == "True"), None)
S = dict(run=os.path.basename(D), controller_startedAt=pod["status"]["containerStatuses"][0]["state"]["running"]["startedAt"], agent_first_cfg_attempt_ended=rel(a_cfg), socket_created=rel(a_sock), agent_log_socket_line=sl, pod_Ready=rel(ready))
S["agent_log_lines"] = [re.sub(r"^\S+ ", "", l)[:170] for l in ag]
# upstream
phase = lambda t: "socket_absent" if (a_sock is None or t < a_sock) else "socket_present_disabled"
fz = [mk.get("agent_SIGSTOP"), mk.get("agent_SIGCONT")]
up = collections.Counter(); first = None; atk = collections.Counter(); upl = []
for l in rd("echo.log").splitlines():
    m = re.match(r"(\d+\.\d+) method=\S+ rid=(\S+) sigsci=\[(.*?)\]", l)
    if not m or float(m.group(1)) < T0: continue
    t = float(m.group(1)); hdr = m.group(3) or "none"
    if mk.get("gen_SIGSTOP") and t > mk["gen_SIGSTOP"] + 1: continue
    ph = phase(t)
    if fz[0] and fz[0] <= t <= (fz[1] or 9e18): ph = "agent_frozen"
    elif fz[1] and t > fz[1]: ph = "after_SIGCONT"
    up[(ph, hdr)] += 1; first = first or t; upl.append((t, m.group(2)))
    if any(k in m.group(2) for k in ("sqli", "xss", "traversal", "block-marker")): atk[ph] += 1
S["first_upstream_hit"] = rel(first); S["upstream_by_phase_and_sigsci_header"] = {f"{k[0]} | {k[1]}": v for k, v in sorted(up.items())}
S["attack_payloads_upstream_by_phase"] = dict(atk); S["upstream_after_Ready_total"] = sum(1 for t, _ in upl if ready and t >= ready)
# nginx default-level module lines
cnt = collections.Counter()
for l in rd("nginx.log").splitlines():
    m = re.match(r"(\S+) \d{4}/\d\d/\d\d \S+ \[(\w+)\] \d+#\d+: (?:\*\d+ )?(sigsci\S*.*)", l)
    if not m: continue
    t = iso(m.group(1)); ph = phase(t)
    if fz[0] and fz[0] <= t <= (fz[1] or 9e18): ph = "agent_frozen"
    msg = re.sub(r", client:.*", "", re.sub(r"errno=\d+", "errno=N", re.sub(r"\d+ ms", "N ms", m.group(3))))[:120]
    cnt[f"{ph} | [{m.group(2)}] {msg}"] += 1
S["nginx_module_lines_by_phase"] = dict(cnt)
# gen latency (freeze)
if fz[0] and fz[1]:
    lats = []; cs = collections.Counter()
    for l in rd("gen.log").splitlines()[1:]:
        p = l.split(",")
        if len(p) >= 6 and p[0].replace(".", "").isdigit() and fz[0] <= float(p[0]) <= (fz[1] or 9e18): lats.append(float(p[4])); cs[p[3]] += 1
    lats.sort()
    if lats: S["freeze_window_client"] = dict(n=len(lats), status=dict(cs), lat_ms_p50=lats[len(lats)//2], lat_ms_min=lats[0], lat_ms_p95=lats[int(len(lats)*.95)], lat_ms_max=lats[-1])
# statsd window
sd = collections.Counter(); first_sd = None; last_sd = None
for l in rd("statsd.log").splitlines():
    t = float(l.split()[0])
    if t < T0 or t > mk.get("collect", 9e18): continue
    first_sd = first_sd or t; last_sd = t
    m = re.match(r"\S+ (sigsci\.agent\.\S+?):(-?[\d.]+)\|c", l)
    if m: sd[m.group(1)] += int(float(m.group(2)))
S["statsd_counters_sum"] = dict(sd); S["statsd_first_last_rel_socket"] = [None if first_sd is None else round(first_sd - a_sock, 1), None if last_sd is None else round(last_sd - a_sock, 1)] if a_sock else None
# rpc
if (os.path.exists(f"{D}/rpc.hex") and os.path.getsize(f"{D}/rpc.hex") > 0) or os.path.exists(f"{D}/rpc-decoded.jsonl"):
    if os.path.exists(f"{D}/rpc.hex") and os.path.getsize(f"{D}/rpc.hex") > 0:
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "decode_rpc.py"), f"{D}/rpc.hex"], capture_output=True, text=True).stdout
        open(f"{D}/rpc-decoded.jsonl", "w").write(out)
    else:
        out = open(f"{D}/rpc-decoded.jsonl").read()
    other = 0; req = collections.Counter(); resp = collections.Counter(); err = 0; internal = 0; user = 0; reqs = {}
    for l in out.splitlines():
        o = json.loads(l)
        if "decode_error" in o: err += 1; continue
        if o.get("type") is None: other = other + 1 if "other" in dir() else 1; continue
        if o["type"] == "request":
            u = o["params"][0].get("URI", ""); host = o["params"][0].get("ServerName", "")
            req[o["method"]] += 1
            if o["params"][0].get("HeadersIn") and any(h[0] == "X-Request-ID" for h in o["params"][0]["HeadersIn"]): user += 1
            else: internal += 1
        else: resp[json.dumps(o["result"], sort_keys=True)] += 1
    S["rpc_decoded"] = dict(requests=dict(req), with_X_Request_ID_generator_traffic=user, without_X_Request_ID_controller_internal=internal, responses=dict(resp), decode_errors=err, non_rpc_blocks=other)
json.dump(S, open(f"{D}/summary2.json", "w"), indent=1)
print(json.dumps({k: v for k, v in S.items() if k != "agent_log_lines"}, indent=1))
