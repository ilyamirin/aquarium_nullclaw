FROM docker.litellm.ai/berriai/litellm:main-latest

RUN apk add --no-cache bash curl ca-certificates \
  && curl -L -o /tmp/infisical.apk \
    https://github.com/Infisical/cli/releases/download/v0.43.75/infisical_0.43.75_linux_arm64.apk \
  && apk add --allow-untrusted /tmp/infisical.apk \
  && rm -f /tmp/infisical.apk

WORKDIR /app
