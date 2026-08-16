#!/bin/bash
# Start pAI-OS, and the ability it hosts.
#
# pAI-OS discovers abilities by scanning `abilities/`, and records what it
# found; it does not itself launch an ability's `scripts.start`. So this runs
# both: the OS, and the ability's start command exactly as its metadata
# declares it. That is the honest shape of the integration today, and it is
# worth saying rather than implying the OS supervises it.
set -e

cd /opt

echo '{"lab":"kwaai","event":"paios.starting","detail":{"host":"'"${PAIOS_HOST}"'"}}'
python -m paios &
PAIOS_PID=$!

# Give it long enough to migrate its database and bind, then start the
# ability the way its metadata says to.
sleep 12

cd /opt/paios/abilities/u4a-owner-authority/0.1.0
echo '{"lab":"kwaai","event":"ability.starting","detail":{"start":"python3 main.py"}}'
python3 main.py &
ABILITY_PID=$!

# Either one exiting should take the container down, so a failure is visible
# rather than a half-running box that looks healthy. `wait -n` is a bashism —
# hence the shebang; under sh it is an "Illegal option" and the container dies
# the moment both processes are up, which looks exactly like a crash on start.
wait -n "$PAIOS_PID" "$ABILITY_PID"
exit $?
