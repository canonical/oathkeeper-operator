# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed oathkeeper's constant variables."""

# Application constants
OATHKEEPER_API_PORT = 4456
OATHKEEPER_METRICS_PORT = 9000
PEER = "oathkeeper"
SSL_PATH = "/etc/ssl/certs/ca-certificates.crt"
CA_CERTS_PATH = "/usr/share/ca-certificates"
LOCAL_CA_CERTS_PATH = "/usr/local/share/ca-certificates"
SERVER_CERT_PATH = f"{LOCAL_CA_CERTS_PATH}/server.crt"
SERVER_KEY_PATH = f"{LOCAL_CA_CERTS_PATH}/server.key"
SERVER_CA_CERT_PATH = f"{LOCAL_CA_CERTS_PATH}/oathkeeper-ca.crt"

# Integration constants
GRAFANA_DASHBOARD_RELATION_NAME = "grafana-dashboard"
LOKI_PUSH_API_RELATION_NAME = "logging"
PROMETHEUS_METRICS_PATH = "/metrics/prometheus"
PROMETHEUS_SCRAPE_RELATION_NAME = "metrics-endpoint"
TRACING_RELATION_NAME = "tracing"
