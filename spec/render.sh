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

# The committed cache is the reference, so an entry is never renewed. By
# default kramdown-rfc refetches anything older than a day or a week, judged
# by file mtime: a render then depends on the network and on when the files
# were last touched. A reference not yet in the cache is still fetched once.
export KRAMDOWN_REFCACHETTL=3153600000 KRAMDOWN_REFCACHETTL_RFC=3153600000 \
       KRAMDOWN_REFCACHETTL_DOI_IANA=3153600000

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
    # The document date is pinned in each draft's front matter so a render is
    # reproducible, which makes xml2rfc's "more than 3 days away from today"
    # a statement about the calendar rather than the document.
    if grep -v 'days away from today' /tmp/x2r.out \
            | grep -qiE '^[^ ]*\(([0-9]+)\): (Warning|Error)'; then
        echo "FAIL (xml2rfc warnings)"; cat /tmp/x2r.out; status=1; continue
    fi

    # Drop xml2rfc's generator banner from the HTML.
    #
    # It lists every Python package in the render environment, including
    # xml2rfc's transitive dependencies, which nothing pins — so a draft
    # nobody edited renders to different bytes the day platformdirs ships a
    # release. The Dockerfile pins the two tools for exactly the reason this
    # undoes: a spec that renders differently next month is a spec whose diffs
    # stop meaning anything. CI asserts the committed renders match a fresh
    # one, and that assertion is only worth making if a difference means the
    # document changed. The .xml and .txt outputs carry no such banner.
    sed -i '/^<!-- Generator version information:/,/^-->$/d' "$OUT/$name.html"

    echo "ok"
done

exit $status
