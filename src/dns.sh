#!/bin/bash
# usage: dns.sh on|off   -> NXDOMAIN (rcode) for the agent's config/upload endpoints via CoreDNS template plugin
set -e
kubectl -n kube-system get cm coredns -o jsonpath='{.data.Corefile}' > /tmp/Corefile.cur
python3 - "$1" <<'PY'
import sys,re
c=open('/tmp/Corefile.cur').read()
c=re.sub(r"    template IN ANY \{[^}]*\}\n","",c)  # idempotent
if sys.argv[1]=="on":
    blk='''    template IN ANY {
       match "^(wafconf|c)[.]signalsciences[.]net[.]$"
       rcode NXDOMAIN
       fallthrough
    }
    template IN ANY {
       match "^sigsci-agent-wafconf(-us-west-2)?[.]s3[.]amazonaws[.]com[.]$"
       rcode NXDOMAIN
       fallthrough
    }
'''
    c=c.replace("    ready\n","    ready\n"+blk,1)
import json
json.dump({"Corefile":c},open('/tmp/patch.json','w'))
PY
kubectl -n kube-system patch cm coredns --type merge --patch "{\"data\":$(cat /tmp/patch.json)}" >/dev/null
kubectl -n kube-system rollout restart deploy/coredns >/dev/null; kubectl -n kube-system rollout status deploy/coredns --timeout=60s >/dev/null
