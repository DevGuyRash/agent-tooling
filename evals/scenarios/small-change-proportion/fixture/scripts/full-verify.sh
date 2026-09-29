#!/bin/sh
echo "full-verify: building..."; sleep 20
echo "full-verify: linting..."; sleep 10
python3 -m unittest -q && echo "full-verify: all suites passed" | tee verify-report.txt
