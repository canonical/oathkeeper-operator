# Charmed Ory Oathkeeper

[![CharmHub Badge](https://charmhub.io/oathkeeper/badge.svg)](https://charmhub.io/oathkeeper)
[![Juju](https://img.shields.io/badge/Juju%20-3.0+-%23E95420)](https://github.com/juju/juju)
[![License](https://img.shields.io/github/license/canonical/oathkeeper-operator?label=License)](https://github.com/canonical/oathkeeper-operator/blob/main/LICENSE)

[![Continuous Integration Status](https://github.com/canonical/oathkeeper-operator/actions/workflows/on_push.yaml/badge.svg?branch=main)](https://github.com/canonical/oathkeeper-operator/actions?query=branch%3Amain)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-%23FE5196.svg)](https://conventionalcommits.org)

## Description

Python Operator for Ory Oathkeeper - a cloud native Identity & Access Proxy /
API (IAP) and Access Control Decision API that authenticates, authorizes, and
mutates incoming HTTP(s) requests. For more details and documentation,
visit <https://www.ory.sh/docs/oathkeeper>.

## Usage

```shell
juju deploy oathkeeper --channel edge --trust
```

You can follow the deployment status with `watch -c juju status --color`.

## Integrations

Applications that do not conform to OAuth/OIDC standards or don't offer built-in
access control can be secured using the Identity and Access Proxy (IAP)
solution,
which offers a possibility to protect endpoints by intercepting incoming
requests and delegating the authn/authz process to the relevant components of
the [Identity Platform](https://charmhub.io/identity-platform).

Oathkeeper is the main entrypoint to plug the Identity and Access Proxy to your
charmed operator. It can be achieved using the juju integrations described
below.

### Traefik ForwardAuth

Oathkeeper offers integration with
Traefik [ForwardAuth](https://doc.traefik.io/traefik/middlewares/http/forwardauth/)
feature via `forward_auth` interface.

It can be done by deploying
the [Traefik charmed operator](https://charmhub.io/traefik-k8s), enabling the
experimental feature and adding a juju integration:

```shell
juju deploy traefik-k8s traefik-public
juju config traefik-public enable_experimental_forward_auth=True
juju integrate oathkeeper traefik-public::experimental-forward-auth
```

### Auth Proxy

Oathkeeper can be integrated with downstream charmed operators
using `auth_proxy` interface.

To have your charm protected by the Identity and Access Proxy, make sure that:

- it is integrated with traefik-k8s using one of the ingress interfaces
- it provides Oathkeeper with necessary data by supporting
  the [integration](https://github.com/canonical/oathkeeper-operator/blob/main/lib/charms/oathkeeper/v0/auth_proxy.py).

Then complete setting up the proxy:

```shell
juju integrate your-charm traefik-public
juju integrate oathkeeper your-charm:auth-proxy
```

### Identity Platform

Oathkeeper connects with the Identity Platform with the use of Kratos charmed
operator:

```shell
juju integrate oathkeeper kratos
juju config kratos dev=True
```

Refer
to [this](https://charmhub.io/topics/canonical-identity-platform/tutorials/e2e-tutorial)
tutorial to learn how to deploy and configure the Identity Platform.

### Observability

The Oathkeeper Operator integrates
with [Canonical Observability Stack (COS)](https://charmhub.io/topics/canonical-observability-stack) bundle.
It comes with a Grafana dashboard and Loki and Prometheus alert rules for basic
common scenarios. To integrate with the COS bundle, after
you [deploy it](https://charmhub.io/topics/canonical-observability-stack/tutorials/install-microk8s#heading--deploy-the-cos-lite-bundle),
you can run:

```shell
juju integrate oathkeeper:grafana-dashboard grafana:grafana-dashboard
juju integrate oathkeeper:metrics-endpoint prometheus:metrics-endpoint
juju integrate loki:logging oathkeeper:logging
```

To integrate with `tracing`, additionally run:

```shell
juju deploy tempo-k8s
juju integrate oathkeeper:tracing tempo-k8s:tracing
```

## Actions

Oathkeeper charmed operator offers the following juju actions:

- `list-rules` lists all access rules
- `get-rule` allows to get an access rule content by its id.

## OCI Images

The rock image used by this charm is hosted
on [GitHub Container Registry](https://ghcr.io/canonical/oathkeeper) and
maintained by Canonical Identity Team.

It is based on [this](https://hub.docker.com/r/oryd/oathkeeper) docker image
from Ory.

## Security

Please see [SECURITY.md](https://github.com/canonical/oathkeeper-operator/blob/main/SECURITY.md)
for guidelines on reporting security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on
enhancements to this charm following best practice guidelines,
and [CONTRIBUTING.md](https://github.com/canonical/oathkeeper-operator/blob/main/CONTRIBUTING.md)
for developer guidance.

## License

The Charmed Oathkeeper Operator is free software, distributed under the Apache
Software License, version 2.0.
See [LICENSE](https://github.com/canonical/oathkeeper-operator/blob/main/LICENSE)
for more information.
