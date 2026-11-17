#!/bin/bash
cd ~/Downloads/ngwaf-test
until grep -q BATCH3_DONE /tmp/batch3.out; do sleep 10; done
rm -rf results/raw/RST-rep*
I=values-I-default-nginx-agent-statsd-rpcdump.yaml
for i in 1 2 3; do VAR=$I NONETPOL=1 RSTMODE=1 python3 src/run.py $I RST-rep$i 120 0 >/dev/null 2>&1; python3 src/summ.py results/raw/RST-rep$i >/dev/null 2>&1; echo "finished RST-rep$i $(date +%T)"; done
echo BATCH4_DONE
