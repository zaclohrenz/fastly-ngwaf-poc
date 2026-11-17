#!/usr/bin/env python3
"""Run one startup scenario: python3 run.py <variant:A|B|...> <label> <hold_s> <release:0|1> [post_release_s]"""
import subprocess as sp, sys, time, os, json, threading
V, LABEL, HOLD, REL = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4] == "1"
import re as _re
# per user decision: readiness delays and J/K option probes are 1 rep (reps 2,3 are no-ops) unless an option changes behavior
if _re.match(r"^(R\d+|J-.*|K-.*)-rep[23]$", LABEL) and os.environ.get("FORCE_REPS") != "1": sys.exit(0)
POST = float(sys.argv[5]) if len(sys.argv) > 5 else 40
ROOT = os.path.expanduser("~/Downloads/ngwaf-test"); M = f"{ROOT}/results/manifests"
OUT = f"{ROOT}/results/raw/{LABEL}"; os.makedirs(OUT, exist_ok=True)
VALUES = {"A": "values-A-noprobe.yaml", "B": "values-B-probe.yaml", "D": "values-D-debugflags.yaml", "E": "values-E-allthethings.yaml", "F": "values-F-noprobe-debugflags.yaml", "G": "values-G-fastly-default.yaml", "H": "values-H-fastly-default-egress-allowed.yaml"}.get(V, V)
def k(*a, **kw): return sp.run(["kubectl", *a], capture_output=True, text=True, **kw)
def node(cmd): return sp.run(["podman","exec","ngwaf-control-plane","bash","-c",cmd],capture_output=True,text=True)
def host_pid(name):
    cid=node(f"crictl ps --name '^{name}$' -q | head -1").stdout.strip()
    return node("crictl inspect -o go-template --template '{{.info.pid}}' "+cid).stdout.strip()
def mark(m): 
    t = time.time(); open(f"{OUT}/markers.txt", "a").write(f"{t:.3f} {m}\n"); print(f"{t:.3f} {m}", flush=True)
def watcher(args, fn):
    f = open(f"{OUT}/{fn}", "w")
    p = sp.Popen(["kubectl", *args], stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
    def pump():
        for line in p.stdout: f.write(f"{time.time():.3f} {line}"); f.flush()
    threading.Thread(target=pump, daemon=True).start(); return p
open(f"{OUT}/markers.txt", "w").close()
STOP = threading.Event()
def stream(pod, container, fn):
    """Follow container logs continuously (kubelet rotates at 10MiB; nginx debug logging exceeds that in seconds)."""
    f = open(f"{OUT}/{fn}", "w"); last = ""
    def run():
        nonlocal last
        while not STOP.is_set():
            cmd = ["kubectl","-n","ingress-nginx","logs","-f","--timestamps",pod,"-c",container] + ([f"--since-time={last}"] if last else [])
            p = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.DEVNULL, text=True, errors="replace")
            for line in p.stdout:
                ts = line.split(" ", 1)[0]
                if ts <= last: continue
                last = ts; f.write(line); f.flush()
            p.wait(); time.sleep(0.3)
    t = threading.Thread(target=run, daemon=True); t.start(); return t
# state: make sure helm release matches variant, netpol on, controller scaled to 0
sp.run(["helm","upgrade","ingress-nginx","ingress-nginx/ingress-nginx","--version","4.15.1","-n","ingress-nginx","-f",f"{M}/{VALUES}"], capture_output=True)
NONET = os.environ.get("NONETPOL") == "1"
if NONET: k("delete","-f",f"{M}/netpol-block-agent-egress.yaml","--ignore-not-found")
else: k("apply","-f",f"{M}/netpol-block-agent-egress.yaml")
k("-n","ingress-nginx","scale","deploy/ingress-nginx-controller","--replicas=0")
k("-n","ingress-nginx","wait","--for=delete","pod","-l","app.kubernetes.io/component=controller","--timeout=90s")
k("-n","ngwaf","delete","pod","poller","--ignore-not-found","--wait=true")
k("-n","ngwaf","rollout","restart","deploy/echo"); k("-n","ngwaf","rollout","status","deploy/echo","--timeout=90s")  # fresh echo log each run (kubelet rotates at 10 MiB)
time.sleep(3)
w1 = watcher(["-n","ingress-nginx","get","pods","-w","-o","custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type==\"Ready\")].status,PHASE:.status.phase,CS:.status.containerStatuses[*].ready","--no-headers"], "pods-watch.txt")
w2 = watcher(["-n","ingress-nginx","get","endpoints","ingress-nginx-controller","-w","-o","custom-columns=NAME:.metadata.name,ADDR:.subsets[*].addresses[*].ip,NOTREADY:.subsets[*].notReadyAddresses[*].ip","--no-headers"], "endpoints-watch.txt")
time.sleep(1); mark("T0_scale_up (egress ALLOWED, no netpol)" if NONET else "T0_scale_up (netpol egress block ACTIVE)")
T0 = time.time()
k("-n","ingress-nginx","scale","deploy/ingress-nginx-controller","--replicas=1")
ip = ""
for _ in range(100):
    ip = k("-n","ingress-nginx","get","pod","-l","app.kubernetes.io/component=controller","-o","jsonpath={.items[0].status.podIP}").stdout.strip()
    if ip: break
    time.sleep(0.2)
mark(f"pod_ip_assigned {ip}")
pod0 = k("-n","ingress-nginx","get","pod","-l","app.kubernetes.io/component=controller","-o","jsonpath={.items[0].metadata.name}").stdout.strip()
if os.environ.get("RSTMODE") == "1":
    sbx = node(f"crictl pods --name {pod0} -q | head -1").stdout.strip()
    pid = node("crictl inspectp -o go-template --template '{{.info.pid}}' "+sbx).stdout.strip()
    r = node(f"nsenter -t {pid} -n iptables -I OUTPUT -p tcp --dport 443 ! -d 10.0.0.0/8 -j REJECT --reject-with tcp-reset && nsenter -t {pid} -n iptables -S OUTPUT")
    mark("rst_rule_inserted rc=%d %s" % (r.returncode, r.stdout.replace(chr(10), " | ")[:200] + r.stderr[:100]))
stream(pod0, "controller", "nginx.log"); stream(pod0, "sigsci-agent", "agent.log")
if V != "A" and ip:
    y = open(f"{M}/poller.yaml.tmpl").read().replace("__IP__", ip)
    sp.run(["kubectl","apply","-f","-"], input=y, text=True, capture_output=True); mark("poller_started")
def freeze_thread():
    delay, dur = [float(x) for x in os.environ["FREEZE"].split(",")]
    while "Started RPC listener" not in open(f"{OUT}/agent.log").read(): time.sleep(0.2)
    mark("socket_created_seen_by_orchestrator"); time.sleep(delay)
    pid = host_pid("sigsci-agent"); r = node(f"kill -STOP {pid}"); mark(f"agent_SIGSTOP pid={pid} rc={r.returncode}")
    time.sleep(dur); r = node(f"kill -CONT {pid}"); mark(f"agent_SIGCONT rc={r.returncode}")
if os.environ.get("FREEZE"): threading.Thread(target=freeze_thread, daemon=True).start()
GENSTOP = os.environ.get("GENSTOP")
def genstop_thread():
    time.sleep(max(0, T0 + float(GENSTOP) - time.time()))
    r = node(f"kill -STOP {host_pid('gen')}"); mark(f"gen_SIGSTOP rc={r.returncode}")
if GENSTOP: threading.Thread(target=genstop_thread, daemon=True).start()
time.sleep(HOLD)
if REL:
    k("delete","-f",f"{M}/netpol-block-agent-egress.yaml"); mark("netpol_RELEASED"); time.sleep(POST)
mark("collect"); time.sleep(2); STOP.set()
pod = k("-n","ingress-nginx","get","pod","-l","app.kubernetes.io/component=controller","-o","jsonpath={.items[0].metadata.name}").stdout.strip()
def save(fn, *a): open(f"{OUT}/{fn}","w").write(k(*a).stdout)
save("pod.json","-n","ingress-nginx","get","pod",pod,"-o","json")
save("pod-describe.txt","-n","ingress-nginx","describe","pod",pod)
save("agent-previous.log","-n","ingress-nginx","logs",pod,"-c","sigsci-agent","--previous")
save("echo.log","-n","ngwaf","logs","deploy/echo","--since=900s")
save("gen.log","-n","ngwaf","logs","deploy/gen","--since=900s")
save("statsd.log","-n","ngwaf","logs","statsd","--since=900s")
save("sigsci-tmp-ls.txt","-n","ingress-nginx","exec",pod,"-c","controller","--","ls","-la","/sigsci/tmp")
save("rpc.hex","-n","ingress-nginx","exec",pod,"-c","controller","--","sh","-c","head -c 60000000 /sigsci/tmp/rpc.hex")
if V != "A": save("poller.log","-n","ngwaf","logs","poller")
for p in (w1, w2): p.terminate()
k("-n","ngwaf","delete","pod","poller","--ignore-not-found","--wait=false")
save("events.txt","get","events","-A","--sort-by=.lastTimestamp","-o","custom-columns=LAST:.lastTimestamp,NS:.metadata.namespace,TYPE:.type,REASON:.reason,OBJ:.involvedObject.name,MSG:.message")
open(f"{OUT}/events-this-pod.txt","w").write("".join(l for l in open(f"{OUT}/events.txt") if pod in l))
if GENSTOP: k("-n","ngwaf","rollout","restart","deploy/gen"); k("-n","ngwaf","rollout","status","deploy/gen","--timeout=90s")
mark("done")
