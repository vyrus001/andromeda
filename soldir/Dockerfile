# syntax=docker/dockerfile:1.4
FROM tinkr-agent:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
      nodejs npm \
 && rm -rf /var/lib/apt/lists/*

COPY --from=tinkr . /tinkr
COPY --from=tailor . /tailor
COPY . /soldir

WORKDIR /soldir

RUN rm -rf .venv node_modules data *.egg-info \
 && python3 -m pip install --no-cache-dir . \
 && npm ci

ENV TINKR_ROOT=/tinkr \
    TAILOR_ROOT=/tailor \
    SOLDIR_HOST=0.0.0.0 \
    SOLDIR_PORT=8765

EXPOSE 8765

ENTRYPOINT ["/soldir/start.sh"]
CMD ["--host", "0.0.0.0"]
