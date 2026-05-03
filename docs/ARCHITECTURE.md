# Architecture

## Services
- auth-service: users/roles/JWT/authZ.
- case-service: case metadata, publication and access-control orchestration.
- ner-service: extensible NER abstraction (`BaseNerProvider`) with regex/rule provider.
- anonymization-service: calls NER, applies deterministic placeholders, stores anonymized/public and restored/private representations separately.

## Data boundaries
- `auth-db`: users, roles, memberships.
- `case-db`: case/document metadata and audit.
- `anonymized-db`: anonymized text and public metadata.
- `personal-data-db`: original text + PII entities + mapping table.

## Network boundaries
- `frontend_net`: edge-facing network.
- `backend_net` (`internal: true`): only backend services and databases.
- Public traffic must go through nginx only.

## Security controls
- JWT with roles for external authn/authz.
- `X-Internal-Service-Token` on all interservice endpoints.
- No nginx route to NER or personal-data storage.
- Restored access requires role/case-participant checks + audit logging in case-service.
