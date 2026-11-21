# Egress allowlist proxy for cell containers -- harness v5.0 (Fault 11).
#
# Cells run on an INTERNAL docker network with no route to the internet. This
# container is the single exception: it is attached to both that internal
# network and a normal bridge, and it forwards only to the model API. The
# effect is that a cell can talk to Claude and to nothing else -- it cannot
# fetch upstream HotCRP source, and it cannot install packages, which is what
# made Fault 11 possible.
FROM alpine:3.20
RUN apk add --no-cache tinyproxy
COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY filter         /etc/tinyproxy/filter
EXPOSE 8888
ENTRYPOINT ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
