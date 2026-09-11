# The Internet-Draft render pipeline: kramdown-rfc turns the Markdown source
# into xml2rfc v3 XML, xml2rfc turns that into the .txt and .html an I-D is
# actually read as. Both tools in one image because the two steps always run
# together and a two-image pipeline would need a shared volume to hand the XML
# across.
#
# Pinned, for the same reason every other image here is: a spec that renders
# differently next month is a spec whose diffs stop meaning anything.
FROM ruby:3.3-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-lxml \
 && rm -rf /var/lib/apt/lists/*

# lxml comes from apt rather than pip: building it needs libxml2/libxslt headers
# and a compiler, which is a hundred megabytes of toolchain to produce a wheel
# Debian already ships.

RUN gem install --no-document kramdown-rfc2629 -v 1.7.31
RUN pip3 install --no-cache-dir --break-system-packages xml2rfc==3.34.1

WORKDIR /spec
