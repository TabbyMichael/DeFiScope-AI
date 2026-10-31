"""Authentication (who you are) and authorization (what you may touch).

Layout, in dependency order:

- ``principal``  - the immutable ``Subject`` and the ``Scope`` it carries.
- ``rbac``       - roles to verbs. The coarse gate.
- ``policy``     - attribute predicates returning an explainable ``Decision``.
- ``passwords``  - scrypt hashing (stdlib only, offline installs intact).
- ``sessions``   - opaque session tokens and the single-use WS ticket.
- ``seed``       - the four demo accounts, only in ``auth_mode == "demo"``.
- ``deps``       - FastAPI glue: ``get_subject`` / ``require(permission)``.

Nothing here imports a router or a service, so the whole layer is testable
without a running app - the same constraint ``analysis/metrics`` follows.
"""
