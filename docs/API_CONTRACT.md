# API Contract

## Gateway
- Base URL: `http://localhost:8080`
- Auth routes: `/api/auth/*`
- Cases routes: `/api/cases/*`

## Auth
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/auth/users/{user_id}` (ADMIN/internal)
- `POST /api/auth/users/{user_id}/roles` (ADMIN)

## Cases
- `GET /api/cases/public/documents`
- `GET /api/cases/public/documents/{document_id}`
- `POST /api/cases`
- `POST /api/cases/{case_id}/documents`
- `GET /api/cases/{case_id}/restored`

## Internal
- `POST /internal/ner/extract`
- `POST /internal/anonymization/process`

## Error format
```json
{"error":{"code":"ACCESS_DENIED","message":"Недостаточно прав","details":{}}}
```

## Enums
Roles: REGISTERED_USER, COURT_STAFF, JUDGE, COURT_CLERK, ADMIN.
Act types: DECISION, SENTENCE, RULING, DETERMINATION, COURT_ORDER, OTHER.
Instance: FIRST, APPEAL, CASSATION, SUPERVISION, NEW_OR_NEWLY_DISCOVERED.
