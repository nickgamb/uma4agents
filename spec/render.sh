#!/usr/bin/env bash
# Render every draft in spec/src to .xml, .txt and .html.
#
# Two steps rather than kdrfc, because kdrfc wants to reach the datatracker to
# resolve the draft name and we would rather it did not: the reference cache in
# spec/.refcache is committed, so a render is reproducible and works offline.
set -euo pipefail

SRC=/spec/src
OUT=${OUT:-/out}
mkdir -p "$OUT" /spec/.refcache

status=0
for md in "$SRC"/*.md; do
    name=$(basename "$md" .md)
    printf '%-40s' "$name"

    if ! kramdown-rfc2629 "$md" > "$OUT/$name.xml" 2>/tmp/kd.err; then
        echo "FAIL (kramdown-rfc)"; cat /tmp/kd.err; status=1; continue
    fi
    # kramdown-rfc writes warnings to stderr and still exits 0; a reference
    # declared twice or a missing anchor is worth failing on rather than
    # discovering in a review. A first-time fetch into the reference cache is
    # not a warning: the fetched file is committed and never fetched again.
    if grep -v 'fetching from' /tmp/kd.err | grep -q .; then
        echo "FAIL (kramdown-rfc warnings)"; grep -v 'fetching from' /tmp/kd.err
        status=1; continue
    fi

    if ! xml2rfc --v3 --text --html --cache /spec/.refcache \
                 --path "$OUT" "$OUT/$name.xml" >/tmp/x2r.out 2>&1; then
        echo "FAIL (xml2rfc)"; cat /tmp/x2r.out; status=1; continue
    fi
    if grep -qiE '^[^ ]*\(([0-9]+)\): (Warning|Error)' /tmp/x2r.out; then
        echo "FAIL (xml2rfc warnings)"; cat /tmp/x2r.out; status=1; continue
    fi

    echo "ok"
done

exit $status
