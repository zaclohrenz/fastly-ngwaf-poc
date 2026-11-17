#!/bin/bash
cd ~/Downloads/ngwaf-test
I=values-I-default-nginx-agent-statsd-rpcdump.yaml
run() { # label hold [release]  (env passes through)
  python3 src/run.py "$VAR" "$1" "$2" "${3:-0}" ${4:-} >/dev/null 2>&1; python3 src/summ.py results/raw/$1 >/dev/null 2>&1; echo "finished $1 $(date +%T)"; }
# 1. failure-mode matrix
for i in 1 2 3; do VAR=$I NONETPOL=1 run DNS-rep$i 120; done
src/dns.sh off; sleep 5
for i in 1 2 3; do VAR=$I NONETPOL=1 RSTMODE=1 run RST-rep$i 120; done
for i in 1 2 3; do VAR=$I NONETPOL=1 run CRED403-rep$i 120; done
for i in 1 2 3; do VAR=$I run DROP-rep$i 150; done
# 3. readiness delays, egress dropped, 90 s
for d in 10 30 60; do for i in 1 2 3; do VAR=values-R$d-readiness-delay-$d.yaml run R$d-rep$i 90; done; done
# 4. freeze
for i in 1 2 3; do VAR=$I NONETPOL=1 FREEZE=25,20 run FREEZE-rep$i 100; done
# 5. reconciliation
VAR=$I NONETPOL=1 GENSTOP=100 run RECON-rep1 260
# 6. default-settings repeats
for i in 2 3; do VAR=G run G-default$i 150; VAR=H NONETPOL=1 run H-default-allowed$i 150; done
echo BATCH2_DONE
