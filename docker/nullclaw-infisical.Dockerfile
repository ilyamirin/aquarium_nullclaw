FROM ghcr.io/nullclaw/nullclaw:latest

USER root

RUN apk add --no-cache bash curl wget \
  && wget -qO- 'https://artifacts-cli.infisical.com/setup.apk.sh' | sh \
  && apk update \
  && apk add --no-cache infisical

USER 65534:65534
