#!/bin/bash
cd ~/Downloads/ngwaf-test
for i in 1 2 3; do python3 src/run.py A A-rep$i 90 0; done
for i in 1 2 3; do python3 src/run.py B B-rep$i 90 0; done
for i in 1 2 3; do python3 src/run.py F F-rep$i 150 0; done
python3 src/run.py A A-release1 70 1 60
echo BATCH_DONE
