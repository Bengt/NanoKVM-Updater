# NanoKVM-Updater

NanoKVM Updater

## GitLab CICD job definition

```yaml
---
.tailscale-and-ssh:
  image: tailscale/tailscale:latest
  variables:
    TS_STATE_DIR: /tmp/tailscale
    TS_EXTRA_ARGS: "--hostname=gitlab-runner-${CI_JOB_ID}"
  before_script:
    - chmod 400 "$PRIVATE_SSH_KEY"
    - mkdir -p /tmp/tailscale
    - tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &
    - sleep 5
    - tailscale up
      --auth-key=${TAILSCALE_OAUTH_CLIENT_SECRET}
      --advertise-tags=tag:cicd
      --hostname=gitlab-runner-${CI_JOB_ID}
    - tailscale status
    - ping -c 1 100.111.59.110
    - apk --no-cache add openssh

upgrade-NanoKVM-server:
  extends: .tailscale-and-ssh
  script:
    - |-
      ssh \
        -i "$PRIVATE_SSH_KEY" \
        -o StrictHostKeyChecking=no \
        "root@100.79.49.123" \
      "
        echo 'Starting NanoKVM update ...' && \
        rm nanokvm-updater.py 2>/dev/null || true && \
        curl -L --insecure -o nanokvm-updater.py https://raw.githubusercontent.com/Bengt/NanoKVM-Updater/refs/heads/main/nanokvm-updater.py && \
        (python nanokvm-updater.py || exit 1) && \
        echo 'Rebooting ...' && \
        (nohup reboot >/dev/null 2>&1 &)
      "
```
