#!/bin/bash
cd ~/Downloads/ngwaf-test
Ia=values-Ia-egress-allowed-no-initcontainer.yaml; Ja=values-Ja-timeout1000-egress-allowed-no-initcontainer.yaml
I=values-I-default-nginx-agent-statsd-rpcdump.yaml; J=values-J-sigsci_agent_timeout-1000.yaml; K=values-K-debug-standalone-4.yaml
run() { python3 src/run.py "$VAR" "$1" "$2" 0 >/dev/null 2>&1; python3 src/summ.py results/raw/$1 >/dev/null 2>&1; echo "finished $1 $(date +%T)"; }
for i in 2 3; do VAR=G run G-default$i 150; VAR=H NONETPOL=1 run H-default-allowed$i 150; done
for i in 1 2 3; do VAR=$Ia NONETPOL=1 FREEZE=25,20 run FREEZE-rep$i 100; done
for i in 1 2 3; do VAR=$Ia NONETPOL=1 GENSTOP=80 run RECON-rep$i 200; done
VAR=$Ja NONETPOL=1 FREEZE=25,20 run J-freeze-rep1 100
VAR=$J run J-drop-rep1 120
VAR=$K run K-standalone4-drop-rep1 120
echo BATCH5_PART1_DONE
for i in 1 2 3; do VAR=$I NONETPOL=1 RSTMODE=1 run RST-rep$i 120; done
echo BATCH5_DONE
