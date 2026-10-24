#!/usr/bin/env bash
# Run the whole test suite. On failure, print the failing test names and tracebacks as GitHub annotations,
# because job logs are hard to reach. Used by both the Test workflow and the publish gate.
set +e
python -m unittest discover -s tests -v 2>&1 | tee /tmp/unittest.txt
rc=${PIPESTATUS[0]}
if [ "$rc" != "0" ]; then
  grep -E "^(FAIL|ERROR):" /tmp/unittest.txt | while read -r l; do echo "::error title=Test failed::$l"; done
  body=$(grep -E -A25 "^(FAIL|ERROR):" /tmp/unittest.txt | head -80 | sed 's/%/%25/g' | sed ':a;N;$!ba;s/\n/%0A/g')
  echo "::error title=Failure details::$body"
fi
exit $rc
