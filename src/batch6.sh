#!/bin/bash
cd ~/Downloads/ngwaf-test
until grep -q BATCH5_DONE /tmp/batch5.out; do sleep 10; done
I=values-I-default-nginx-agent-statsd-rpcdump.yaml; J=values-J-sigsci_agent_timeout-1000.yaml; K=values-K-debug-standalone-4.yaml
mkdir -p results/raw/_invalid-echo-log-rotated; for d in DNS-rep2 G-default2 J-drop-rep1; do mv results/raw/$d results/raw/_invalid-echo-log-rotated/$d; done
run() { python3 src/run.py "$VAR" "$1" "$2" 0 >/dev/null 2>&1; python3 src/summ.py results/raw/$1 >/dev/null 2>&1; echo "finished $1 $(date +%T)"; }
src/dns.sh on; sleep 5
VAR=$I NONETPOL=1 run DNS-rep2 120
src/dns.sh off; sleep 5
VAR=G run G-default2 150
VAR=$J run J-drop-rep1 120
for i in 2 3; do VAR=$K FORCE_REPS=1 run K-standalone4-drop-rep$i 120; done
echo BATCH6_DONE
