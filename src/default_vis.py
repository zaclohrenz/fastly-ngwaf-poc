import re,sys,json,datetime,collections
def iso(s): return datetime.datetime.strptime(s[:26],"%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).timestamp()
def pt(s): return datetime.datetime.strptime(s[:26],"%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).timestamp()
D=sys.argv[1]
pod=json.load(open(f"{D}/pod.json"))
sa={c["name"]:iso(c["state"]["running"]["startedAt"].replace("Z",".000000")) for c in pod["status"]["containerStatuses"]}
mk={l.split(" ",1)[1].split()[0]:float(l.split()[0]) for l in open(f"{D}/markers.txt")}
T0=mk["T0_scale_up"]
ag=open(f"{D}/agent.log").read().splitlines()
def agl(p): 
    for i,l in enumerate(ag,1):
        if re.search(p,l): return i,pt(l.split(" ",1)[1])
a1,a_first=agl("starting as user"); _,a_cfg=agl("Config update failed try 1"); sl,a_sock=agl("Started RPC listener")
print("agent first log line (agent clock, s) rel to agent startedAt:",round(a_first-sa["sigsci-agent"],2),"(startedAt is 1s-granular: floor)")
print("config attempt 1 failed at +%.2fs, RPC socket created at +%.2fs (agent.log:%d) rel agent startedAt"%(a_cfg-sa["sigsci-agent"],a_sock-sa["sigsci-agent"],sl))
# nginx: module messages only (exclude access log lines)
ng=open(f"{D}/nginx.log").read().splitlines()
msgs=collections.OrderedDict(); first_line={}
for i,l in enumerate(ng,1):
    m=re.match(r"(\S+) \d{4}/\d\d/\d\d \S+ \[(\w+)\] \d+#\d+: (?:\*\d+ )?(sigsci\S*.*)",l)
    if not m: continue
    ts,lvl,msg=m.groups(); key=(lvl,re.sub(r"errno=\d+","errno=N",re.sub(r", client:.*","",re.sub(r"\d+ ms","N ms",msg)))[:110])
    ph="no-socket" if iso(ts)<a_sock else "socket-present"
    k=(ph,)+key; msgs[k]=msgs.get(k,0)+1; first_line.setdefault(k,i)
print("nginx module-originated log lines at default level (phase, level, message): count @first line")
for k,v in msgs.items(): print("  ",k,v,"@nginx.log:%d"%first_line[k])
# any nginx line (non-access-log) after socket created?
lv=collections.Counter()
for l in ng:
    m=re.match(r"(\S+) \d{4}/\d\d/\d\d \S+ \[(\w+)\]",l)
    if m: lv[("no-socket" if iso(m.group(1))<a_sock else "socket-present",m.group(2))]+=1
print("all error-log lines by phase/level:",dict(lv))
# upstream: only this run's window (>=T0), classify by phase
ec=open(f"{D}/echo.log").read().splitlines(); ph=collections.Counter(); first=None; ex={}
for i,l in enumerate(ec,1):
    m=re.match(r"(\d+\.\d+) method=\S+ rid=(\S+) sigsci=\[(.*?)\]",l)
    if not m or float(m.group(1))<T0: continue
    t=float(m.group(1)); p="no-socket" if t<a_sock else "socket-present"
    if first is None: first=(t,i)
    k=(p,m.group(3) or "(no X-SigSci-* header)"); ph[k]+=1; ex.setdefault(k,i)
print("first upstream hit: +%.2fs rel controller startedAt (echo.log:%d); socket created +%.2fs"%(first[0]-sa["controller"],first[1],a_sock-sa["controller"]))
for k,v in ph.items(): print("  upstream",k,v,"first @echo.log:%d"%ex[k])
