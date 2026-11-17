#!/bin/bash
cd ~/Downloads/ngwaf-test
until grep -q BATCH6_DONE /tmp/batch6.out; do sleep 10; done
Ia=values-Ia-egress-allowed-no-initcontainer.yaml
for i in 1 2 3; do
  kubectl -n ngwaf delete pod slowprobe --ignore-not-found --wait=true >/dev/null; kubectl apply -f results/manifests/slowprobe.yaml >/dev/null
  VAR=$Ia NONETPOL=1 FREEZE=25,20 GENSTOP=18 python3 src/run.py $Ia IDLEFREEZE-rep$i 90 0 >/dev/null 2>&1
  kubectl -n ngwaf logs slowprobe > results/raw/IDLEFREEZE-rep$i/probe.log; kubectl -n ngwaf delete pod slowprobe --wait=false >/dev/null
  python3 src/summ.py results/raw/IDLEFREEZE-rep$i >/dev/null 2>&1; echo "finished IDLEFREEZE-rep$i $(date +%T)"
done
echo BATCH7_DONE
