# DigitalOcean MCP Server Deployment Context

## Purpose

This document describes the current state and intended configuration of the DigitalOcean Droplet that will host an MCP server.

Use this document as persistent context when administering the server or planning/deploying services to it.

The immediate objective is:

> Deploy an Internet-accessible MCP server using Docker while maintaining a simple, secure, maintainable production configuration.

Do not unnecessarily replace or undo existing security configuration.

---

# Server

Provider: DigitalOcean
Platform: Droplet
Operating system: Ubuntu 24.04.5 LTS
Architecture: x86_64 / amd64
Kernel at initial setup: 6.8.0-147-generic

Public IPv4:

```text
138.197.24.16
```

Private IPv4 observed at initial setup:

```text
10.17.0.5
```

IPv6 observed at initial setup:

```text
2604:a880:800:14:0:3:c714:b000
```

Initial disk size:

```text
~47 GB
```

Initial server size:

```text
1 vCPU
2 GB RAM
```

The Droplet hostname currently appears as:

```text
ubuntu-s-1vcpu-2gb-nyc3
```

---

# Administrative Account

Routine administration should be performed using:

```text
kent
```

Connect using the dedicated DigitalOcean SSH key:

```bash
ssh -i ~/.ssh/id_ed25519_digitalocean kent@138.197.24.16
```

The `kent` account has working `sudo` privileges.

This was verified with:

```bash
sudo whoami
```

returning:

```text
root
```

Do not use the root account for routine administration.

---

# SSH Security

SSH public-key authentication is enabled.

Password authentication is disabled.

Direct SSH login as root has been disabled.

The intended effective SSH configuration is:

```text
permitrootlogin no
pubkeyauthentication yes
passwordauthentication no
```

Root login was explicitly tested after hardening:

```bash
ssh -i ~/.ssh/id_ed25519_digitalocean root@138.197.24.16
```

and correctly returned:

```text
Permission denied (publickey).
```

SSH hardening is configured using:

```text
/etc/ssh/sshd_config.d/99-hardening.conf
```

with:

```text
PermitRootLogin no
```

Do not re-enable root SSH login or SSH password authentication without a specific reason.

---

# Firewall

UFW is enabled and active.

Current intentionally exposed services are:

```text
OpenSSH
80/tcp
443/tcp
```

for both IPv4 and IPv6.

The firewall was verified with:

```bash
sudo ufw status
```

The intended public attack surface is therefore:

```text
22/tcp    SSH
80/tcp    HTTP
443/tcp   HTTPS
```

Do not expose additional application ports publicly unless there is a deliberate architectural reason.

---

# System Updates

The initial Ubuntu package updates were applied during server setup.

Before significant deployment work, normal maintenance can be performed with:

```bash
sudo apt update
sudo apt upgrade
```

Do not perform a distribution release upgrade without first evaluating compatibility and deployment impact.

---

# Docker Repository

Docker is being installed from Docker's official Ubuntu APT repository rather than Ubuntu's `docker.io` package.

Docker signing key:

```text
/etc/apt/keyrings/docker.asc
```

Docker repository definition:

```text
/etc/apt/sources.list.d/docker.sources
```

Repository:

```text
https://download.docker.com/linux/ubuntu
```

Ubuntu suite:

```text
noble
```

Architecture:

```text
amd64
```

`apt update` has successfully retrieved packages from:

```text
https://download.docker.com/linux/ubuntu noble/stable amd64
```

---

# Docker Installation

The intended Docker packages are:

```text
docker-ce
docker-ce-cli
containerd.io
docker-buildx-plugin
docker-compose-plugin
```

Installation command:

```bash
sudo apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

After installation, verify Docker with:

```bash
sudo systemctl status docker
```

and:

```bash
sudo docker run --rm hello-world
```

Docker Compose should use Compose v2 syntax:

```bash
sudo docker compose ...
```

rather than the old standalone:

```text
docker-compose
```

Unless the server state shows otherwise, assume Docker commands require `sudo`.

Do not automatically add `kent` to the `docker` group. Membership in that group effectively grants root-level access. Prefer explicit `sudo docker ...` commands unless there is a reason to change this policy.

---

# Important Docker Firewall Consideration

Do not assume UFW alone protects ports published by Docker.

Docker manages iptables/nftables rules and published container ports can be reachable even when corresponding ports have not been explicitly allowed through ordinary UFW rules.

Therefore avoid configurations such as:

```yaml
ports:
  - "3000:3000"
```

for internal application services unless public exposure of that port is intentional.

The preferred architecture is for HTTP applications to communicate over Docker networks behind a reverse proxy.

---

# Intended Hosting Architecture

This Droplet may eventually host multiple applications/sites.

The desired general architecture is:

```text
                    Internet
                       |
                +------+------+
                |             |
               :80           :443
                |             |
                +------+------+
                       |
                 Reverse Proxy
                       |
              Docker network(s)
                       |
        +--------------+--------------+
        |              |              |
     MCP Server      Site A         Site B
        |              |              |
   internal port   internal port  internal port
```

Only the reverse proxy should normally expose HTTP/HTTPS ports to the Internet.

Application containers should normally expose their service ports only to Docker networks.

---

# Reverse Proxy

A reverse proxy has not yet been established as part of this handoff unless inspection of the server shows otherwise.

A likely choice is Caddy because of its simple configuration and automatic HTTPS support.

Before installing or configuring a reverse proxy:

1. Determine the hostname/domain that will be used for the MCP service.
2. Verify its DNS configuration.
3. Determine whether the MCP implementation requires HTTP/SSE, Streamable HTTP, WebSocket support, or another transport.
4. Determine the MCP application's internal listening port.
5. Keep the application port private where practical.
6. Terminate public TLS at the reverse proxy.

Do not assume that the MCP application's internal port should be directly exposed to the Internet.

---

# MCP Deployment Goals

The MCP server should preferably:

- Run in Docker.
- Be managed through Docker Compose.
- Restart automatically after host reboots.
- Be accessible through HTTPS.
- Use a DNS hostname rather than requiring clients to connect directly to the IP address.
- Sit behind a reverse proxy.
- Avoid exposing its internal application port publicly.
- Store persistent state outside the disposable container filesystem when applicable.
- Keep secrets out of Git and out of the Docker image.
- Use environment files or another appropriate secrets mechanism.
- Produce logs accessible through standard Docker tooling.
- Have a straightforward update/rollback procedure.

A likely deployment layout is:

```text
/opt/
└── <mcp-service>/
    ├── compose.yaml
    ├── .env
    └── <service-specific files>
```

Application source may instead live under an appropriate Git-managed directory if the deployment workflow requires it.

Protect secret-containing files appropriately, for example:

```bash
chmod 600 .env
```

---

# Docker Compose Expectations

Prefer declarative Compose configuration.

Containers intended to survive reboots should normally use an appropriate restart policy such as:

```yaml
restart: unless-stopped
```

Prefer named volumes or explicit host mounts for persistent data.

Prefer Docker networks for communication between containers rather than exposing internal service ports on the host.

Before binding a port with Compose, determine whether it actually needs to be reachable from outside Docker.

---

# DNS and HTTPS

Before production exposure, establish a DNS record such as:

```text
mcp.<domain>
```

pointing to:

```text
138.197.24.16
```

The exact hostname has not been established by this document.

Do not make DNS changes based solely on assumptions. Confirm the intended domain/hostname first.

Once DNS resolves correctly, configure HTTPS through the selected reverse proxy.

---

# Security Principles

When making changes to this server:

1. Preserve SSH key access for `kent`.
2. Do not enable SSH password authentication.
3. Do not enable remote root SSH login.
4. Keep UFW enabled.
5. Minimize publicly exposed ports.
6. Avoid publishing Docker application ports unnecessarily.
7. Use HTTPS for Internet-facing MCP traffic.
8. Do not commit credentials, API keys, tokens, or `.env` files to Git.
9. Prefer least-privilege containers where supported by the application.
10. Verify configuration before restarting SSH, Docker, or networking services.
11. Avoid destructive commands without understanding existing server state.
12. Back up persistent application data before potentially destructive upgrades.

---

# Working Style for AI-Assisted Administration

When using this file as context for an AI coding/administration agent:

- Inspect current state before making assumptions.
- Explain consequential infrastructure changes before executing them.
- Prefer incremental, reversible changes.
- Verify each important change after making it.
- Do not weaken existing SSH or firewall security merely to make deployment easier.
- Do not expose application ports publicly when Docker networking and a reverse proxy can accomplish the same goal.
- Distinguish between commands that merely inspect state and commands that modify the server.
- When uncertainty exists about an existing configuration, inspect it rather than overwriting it.
- Keep deployment configuration reproducible in files such as `compose.yaml`, proxy configuration, and deployment documentation.

For major deployment work, use a plan → implement → verify workflow.

---

# Current Deployment Checklist

Known completed work:

- [x] DigitalOcean Droplet created
- [x] Ubuntu 24.04 LTS running
- [x] Initial Ubuntu updates applied
- [x] `kent` administrative user created
- [x] SSH key authentication for `kent` verified
- [x] `kent` sudo access verified
- [x] SSH password authentication disabled
- [x] Direct root SSH login disabled
- [x] UFW enabled
- [x] SSH allowed through UFW
- [x] HTTP/80 allowed through UFW
- [x] HTTPS/443 allowed through UFW
- [x] Official Docker APT repository configured
- [x] Docker repository successfully verified by `apt update`
- [ ] Docker Engine installation verified
- [ ] Docker `hello-world` test verified
- [ ] MCP implementation selected/prepared
- [ ] MCP hostname selected
- [ ] DNS configured
- [ ] Reverse proxy installed/configured
- [ ] MCP Docker Compose deployment created
- [ ] Persistent storage requirements addressed
- [ ] Secrets/configuration established
- [ ] HTTPS verified
- [ ] External MCP connectivity verified
- [ ] Reboot/restart behavior verified
- [ ] Backup strategy verified

---

# Immediate Next Step

Inspect whether Docker installation has been completed:

```bash
sudo systemctl status docker
```

and:

```bash
sudo docker run --rm hello-world
```

If Docker is healthy, proceed by planning the MCP deployment architecture before exposing or publishing additional ports.
