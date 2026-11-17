#!/bin/bash
cd ~/Downloads/ngwaf-test
until grep -q POST_DONE /tmp/post.out; do sleep 5; done
NONETPOL=1 python3 src/run.py H H-default-allowed1 150 0
kubectl get events -A --sort-by=.lastTimestamp -o custom-columns=LAST:.lastTimestamp,NS:.metadata.namespace,TYPE:.type,REASON:.reason,OBJ:.involvedObject.name,MSG:.message > results/raw/H-default-allowed1/events.txt
echo POST2_DONE
