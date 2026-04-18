FROM grafana/grafana:latest

USER root

RUN apk add --no-cache bash curl wget ca-certificates \
  && wget -qO- 'https://artifacts-cli.infisical.com/setup.apk.sh' | sh \
  && apk update \
  && apk add --no-cache infisical

USER grafana
