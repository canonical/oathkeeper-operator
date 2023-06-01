# Charmed Ory Oathkeeper

## Description

Python Operator for Ory Oathkeeper - a cloud native Identity & Access Proxy / API (IAP) and Access Control Decision API that authenticates, authorizes, and mutates incoming HTTP(s) requests. For more details and documentation, visit https://www.ory.sh/docs/oathkeeper/

Please note that this charm is currently work in progress.

## Usage

```bash
juju deploy oathkeeper --trust
```

You can follow the deployment status with `watch -c juju status --color`.

## Integrations

<!-- TODO: Expand once integrations are in place -->

## OCI Images

The rock image used by this charm is hosted on [GitHub Container Registry](https://ghcr.io/canonical/oathkeeper) and maintained by Canonical Identity Team.

It is based on [this](https://hub.docker.com/r/oryd/oathkeeper) docker image from Ory.

## Security

Security issues can be reported through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File). Please do not file GitHub issues about security issues.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/oathkeeper-operator/blob/main/CONTRIBUTING.md) for developer guidance.

## License

The Charmed Oathkeeper Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](https://github.com/canonical/oathkeeper-operator/blob/main/LICENSE) for more information.
