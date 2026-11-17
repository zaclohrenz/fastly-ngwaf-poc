#!/bin/bash
cd ~/Downloads/ngwaf-test
until grep -q BATCH2_DONE /tmp/batch2.out; do sleep 10; done
run() { python3 src/run.py "$VAR" "$1" "$2" 0 >/dev/null 2>&1; python3 src/summ.py results/raw/$1 >/dev/null 2>&1; echo "finished $1 $(date +%T)"; }
J=values-J-sigsci_agent_timeout-1000.yaml; K=values-K-debug-standalone-4.yaml
for i in 1 2 3; do VAR=$J NONETPOL=1 FREEZE=25,20 run J-freeze-rep$i 100; done
for i in 1 2 3; do VAR=$J run J-drop-rep$i 120; done
for i in 1 2 3; do VAR=$K run K-standalone4-drop-rep$i 120; done
echo BATCH3_DONE
