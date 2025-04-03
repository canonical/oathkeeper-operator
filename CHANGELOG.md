# Changelog

## [1.0.2](https://github.com/canonical/oathkeeper-operator/compare/v1.0.1...v1.0.2) (2025-04-03)


### Bug Fixes

* address CVEs ([5329482](https://github.com/canonical/oathkeeper-operator/commit/5329482562abed6f961ed6f659e10f6118bd0da3)), closes [#166](https://github.com/canonical/oathkeeper-operator/issues/166)

## [1.0.1](https://github.com/canonical/oathkeeper-operator/compare/v1.0.0...v1.0.1) (2025-03-26)


### Bug Fixes

* fix the self-signed-certificates charm in integraiton test ([df204d4](https://github.com/canonical/oathkeeper-operator/commit/df204d4dff137bc40773ee81d2412643ad33b1c5))
* provide optional flag in charmcraft.yaml ([e73ac81](https://github.com/canonical/oathkeeper-operator/commit/e73ac815c221b1a391244c2071c73d6197baefea))

## 1.0.0 (2025-03-10)


### Features

* add auth-proxy relation ([2e830e9](https://github.com/canonical/oathkeeper-operator/commit/2e830e97f673d5caf5a7c43e50805af16d58bfd8))
* add dev flag for http(s) scheme ([f3956f8](https://github.com/canonical/oathkeeper-operator/commit/f3956f82a730c8322e80b8692836f4d27acbce6f))
* add forward-auth interface ([cf797b4](https://github.com/canonical/oathkeeper-operator/commit/cf797b439e5be2e9ca5074ec061bb9352da72832))
* add ingress relation ([f32c643](https://github.com/canonical/oathkeeper-operator/commit/f32c643367a3f95eb2d40ed41e8e191861fc9118))
* add more http methods ([0709fc9](https://github.com/canonical/oathkeeper-operator/commit/0709fc931a5bfcfc71ad598979aaf374e70d8412))
* add new methods to auth-proxy ([7b3388c](https://github.com/canonical/oathkeeper-operator/commit/7b3388c414093cb48c439aee35697947fb7c2415))
* add oathkeeper-info interface ([1df6989](https://github.com/canonical/oathkeeper-operator/commit/1df6989c341ca3e501a25b9833687005bef80ad6))
* add oathkeeper-info interface ([85cdcda](https://github.com/canonical/oathkeeper-operator/commit/85cdcda9c4eb8845b88f1cb979529e0341b3e50f))
* add relation_app_name to event parameters ([a882a68](https://github.com/canonical/oathkeeper-operator/commit/a882a6886d7a0840a9ae04075bd96c2f25b62d04))
* add tls certificates relation ([9c70171](https://github.com/canonical/oathkeeper-operator/commit/9c7017137714537f06223626be11c7d2b357ea70))
* add tls relation ([0504aaf](https://github.com/canonical/oathkeeper-operator/commit/0504aaf062ce64b9d9151d6a149730a1b9f4fdbf))
* added automerge and auto-approve to charm lib updates ([02aa397](https://github.com/canonical/oathkeeper-operator/commit/02aa39706169a9138391d6a30c574a1d4e7db71b))
* cos integration ([955171f](https://github.com/canonical/oathkeeper-operator/commit/955171fefe1fad39706a3ba417423a1db0b36ea1))
* create and remove access rules ([bb45164](https://github.com/canonical/oathkeeper-operator/commit/bb451649afaf54e6c02032709bd4e9e67ca5dccd))
* enable anonymous authenticator ([0f15e6c](https://github.com/canonical/oathkeeper-operator/commit/0f15e6c1e7701310a0b2b6a2f463717f91786765))
* Initial oathkeeper charm ([#7](https://github.com/canonical/oathkeeper-operator/issues/7)) ([a45d776](https://github.com/canonical/oathkeeper-operator/commit/a45d7763595a8ee2f623e1d173c14420b2022691))
* modify config template ([e7f606c](https://github.com/canonical/oathkeeper-operator/commit/e7f606c35df6468885fb4ce5e3a3cbf52f63c5a1))
* run update-ca-certificates to push final ca-certs, pass tls related certs as env var ([04f5a0b](https://github.com/canonical/oathkeeper-operator/commit/04f5a0b3e28c5c685ecf1d1b13255d10e25edf8a))
* store config and access rules in configmaps ([38c2c8e](https://github.com/canonical/oathkeeper-operator/commit/38c2c8eaa52d22f65a1f945ed21c6e919445397a))
* support user email and name custom headers ([62f2106](https://github.com/canonical/oathkeeper-operator/commit/62f2106f0d557b5136bb3e3496408f446a8d1b98))
* support user email and name custom headers ([e55a16d](https://github.com/canonical/oathkeeper-operator/commit/e55a16d0f92a9f3ef10562a4c871f6b5bb6eb348))
* update config file with access rules list ([2d31ec3](https://github.com/canonical/oathkeeper-operator/commit/2d31ec3332aeabe4277aed150d5cd1cf166f652e))


### Bug Fixes

* add jsonschema to charmcraft.yaml ([8401634](https://github.com/canonical/oathkeeper-operator/commit/8401634a3e66099c822ccb2e115cd39a1b9b1f07))
* bumped microk8s version to 1.28-strict/stable in CI ([0907c97](https://github.com/canonical/oathkeeper-operator/commit/0907c97e42ddf3a4e86d41f89cd8c892c798aea3))
* check if apps names are not empty ([4173958](https://github.com/canonical/oathkeeper-operator/commit/41739589c662de6bd0067e1f5bde57436ceca7ba))
* check if auth-proxy rel data is available ([7ebeeda](https://github.com/canonical/oathkeeper-operator/commit/7ebeedab8bfd847eda4c64ed399f7bc8fc003999))
* correct the deny regex ([a473354](https://github.com/canonical/oathkeeper-operator/commit/a473354e22f9b7c7efe3823406aad1516dd2f84f))
* correct the regular expressions ([a279163](https://github.com/canonical/oathkeeper-operator/commit/a27916398fcb69b178a23f7ae560898d16909b9c))
* custom events emission ([cfc37f7](https://github.com/canonical/oathkeeper-operator/commit/cfc37f759ba8f1a0c7192407461c0aac59e9d54d))
* enclose regex in angle brackets ([c3e75de](https://github.com/canonical/oathkeeper-operator/commit/c3e75dea4dc3ab34f08189d631207e16f2ca785e))
* get kratos endpoints ([18de8f3](https://github.com/canonical/oathkeeper-operator/commit/18de8f3f6df29ac4a57c3f8262b12b53ec0bf16d))
* get kratos endpoints ([1310026](https://github.com/canonical/oathkeeper-operator/commit/13100264843ca81003b962b1b89f752eab616671))
* include custom headers in template only if requested ([c9626b1](https://github.com/canonical/oathkeeper-operator/commit/c9626b14c7b61bcc16132dc64126de1b2709e5da))
* include custom headers in template only if requested ([f31aeed](https://github.com/canonical/oathkeeper-operator/commit/f31aeed60ab80f1f7d617df5079afaaf90428cb7))
* observe kratos relation changed ([e565b39](https://github.com/canonical/oathkeeper-operator/commit/e565b39715ab0e724389d180523cf428a46b46ca))
* observe relation-broken instead of departed ([d77c769](https://github.com/canonical/oathkeeper-operator/commit/d77c7693c3fb73f68a6aa1201f1ee5f364d9acf0))
* optional trailing slash in allowed urls ([cbac9c2](https://github.com/canonical/oathkeeper-operator/commit/cbac9c24a3011a767b9173cafd3cd0ea75f1f220))
* patch the correct statefulset ([610b70d](https://github.com/canonical/oathkeeper-operator/commit/610b70d69b3246a19b72393dd7bd77a817db905c))
* patch the correct statefulset name ([21d6cac](https://github.com/canonical/oathkeeper-operator/commit/21d6cacd4016c201a4757614356be4a45543163a))
* prepend file locations with ([8e0e830](https://github.com/canonical/oathkeeper-operator/commit/8e0e83089a8710ce6b3936e9fa04c365dd1a5523))
* relation removed event ([eccf47d](https://github.com/canonical/oathkeeper-operator/commit/eccf47d6fd62ea9729f43320261de3d10d1d1ba3))
* relation removed event ([84d9d24](https://github.com/canonical/oathkeeper-operator/commit/84d9d24b6b70fb58814fd634fac218e10fe5d104))
* remove ready check ([5f1a923](https://github.com/canonical/oathkeeper-operator/commit/5f1a923d207da19e2a0f151dab2bea17d5dc8e3b))
* remove relation data on provider side ([81aa7c4](https://github.com/canonical/oathkeeper-operator/commit/81aa7c4a56ae7852c78501fc3d32deda1c4472ac))
* remove relation data on provider side ([ec0c9cf](https://github.com/canonical/oathkeeper-operator/commit/ec0c9cff348cf819b69a2720d9fb568c4457239f))
* remove renovate workflow ([5acc802](https://github.com/canonical/oathkeeper-operator/commit/5acc802ec65878ad094a9123c68f2416b4befcc9))
* retry patching access rules configMap ([04822f2](https://github.com/canonical/oathkeeper-operator/commit/04822f24bb3fa3829a163046eff1dccf32387c7c))
* retry patching access rules configMap ([115d929](https://github.com/canonical/oathkeeper-operator/commit/115d929c6f9f7d7ae1c5a4bc5750a720f395a1fa))
* run with default user ([d655ec9](https://github.com/canonical/oathkeeper-operator/commit/d655ec9c10a68ff4b3cb342f755d61bfe4030099))
* use http ([926bebf](https://github.com/canonical/oathkeeper-operator/commit/926bebf516cb499995cc316d45606103b80dad80))
