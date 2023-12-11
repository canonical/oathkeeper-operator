# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


# TODO: move all constants to a constants.py file
OATHKEEPER_API_PORT = 4456
PEER = "oathkeeper"
SSL_PATH = "/etc/ssl/certs/ca-certificates.crt"
CA_CERTS_PATH = "/usr/share/ca-certificates"
LOCAL_CA_CERTS_PATH = "/usr/local/share/ca-certificates"
SERVER_CERT_PATH = f"{LOCAL_CA_CERTS_PATH}/server.crt"
SERVER_KEY_PATH = f"{LOCAL_CA_CERTS_PATH}/server.key"
SERVER_CA_CERT_PATH = f"{LOCAL_CA_CERTS_PATH}/oathkeeper-ca.crt"
