#!/bin/bash
cd ~/Downloads/ngwaf-test
until grep -q BATCH_DONE /tmp/batch.out; do sleep 5; done
kubectl apply -f results/manifests/00-base.yaml >/dev/null; kubectl -n ngwaf rollout restart deploy/echo >/dev/null; kubectl -n ngwaf rollout status deploy/echo >/dev/null
python3 src/run.py G G-default1 150 0
kubectl get events -A --sort-by=.lastTimestamp -o custom-columns=LAST:.lastTimestamp,NS:.metadata.namespace,TYPE:.type,REASON:.reason,OBJ:.involvedObject.name,MSG:.message > results/raw/G-default1/events.txt
echo POST_DONE
