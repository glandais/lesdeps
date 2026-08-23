# felt/tippecanoe (https://github.com/felt/tippecanoe) — maintained fork of mapbox/tippecanoe.
# The upstream repo ships no Dockerfile and no published image, so we build it here.
FROM debian:bookworm-slim AS build

ARG TIPPECANOE_VERSION=2.79.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates libsqlite3-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${TIPPECANOE_VERSION}" \
        https://github.com/felt/tippecanoe.git /src \
    && cd /src \
    && make -j"$(nproc)" \
    && make install PREFIX=/usr/local

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlite3-0 zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/bin/tippecanoe* /usr/local/bin/
COPY --from=build /usr/local/bin/tile-join /usr/local/bin/

WORKDIR /data
ENTRYPOINT []
CMD ["tippecanoe", "--version"]
