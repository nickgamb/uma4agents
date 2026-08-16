# pAI-OS with the U4A ability installed.
#
# Kwaai's Personal AI Operating System, built from a pinned upstream ref the
# same way the AAuth person server is — cloned by `make fetch-upstream`, not
# vendored. What this image adds is one directory under `abilities/`, which is
# how pAI-OS takes an extension: "akin to plugins in WordPress."
#
# Two upstream accommodations, both noted rather than hidden:
#
#   setuptools<81   the pinned ref imports pkg_resources, which setuptools 81
#                   removed. Their own warning says to pin, so we do.
#   PAIOS_HOST      it defaults to localhost, which binds to nothing reachable
#                   from another container. Same class of thing the MCP SDK
#                   does; the variable exists and we set it.
#
# The frontend is not built. It needs node and it is not what this
# demonstrates — the ability runs as a process either way, and the API is up.

FROM python:3.12-slim

RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# `python -m paios` resolves the package by directory name, so the checkout
# has to sit at /opt/paios and the working directory has to be its parent.
COPY aauth/upstream/paios /opt/paios

RUN python3 -m venv /opt/paios/.venv \
 && /opt/paios/.venv/bin/pip install -q --no-cache-dir "setuptools<81" \
 && /opt/paios/.venv/bin/pip install -q --no-cache-dir -r /opt/paios/backend/requirements.txt \
 && /opt/paios/.venv/bin/pip install -q --no-cache-dir httpx cryptography

# The ability, in the layout pAI-OS scans for: abilities/<id>/<semver>/.
COPY kwaai/abilities/u4a-owner-authority /opt/paios/abilities/u4a-owner-authority

# The implementation the ability imports, and the signature module it needs.
# Shipped beside it rather than vendored into the ability, so what runs inside
# pAI-OS is the same code `make kwaai-check` exercises.
COPY kwaai/ability /opt/u4a/ability
COPY lib /opt/u4a/lib
COPY kwaai/paios_check.py /opt/u4a/paios_check.py

RUN mkdir -p /driver/keys

ENV PATH="/opt/paios/.venv/bin:$PATH" \
    PAIOS_HOST=0.0.0.0 \
    U4A_ABILITY_LIB=/opt/u4a/ability \
    U4A_LIB=/opt/u4a/lib \
    U4A_ABILITY_LOG=/opt/paios/data/ability.log

COPY kwaai/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

EXPOSE 8443
CMD ["/opt/entrypoint.sh"]
