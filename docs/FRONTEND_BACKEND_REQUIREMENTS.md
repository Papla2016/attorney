# FRONTEND BACKEND REQUIREMENTS

Frontend ожидает следующие endpoint для страницы аккаунта:

- `PATCH /api/auth/me` — изменение логина/почты текущего пользователя.
- `POST /api/auth/me/change-password` — изменение пароля текущего пользователя.

Дополнительные требования для нового frontend функционала:

- `GET /api/cases/public/documents` должен поддерживать фильтр query-параметром `judge`.
- Для админки пользователей:
  - `GET /api/auth/users`
  - `POST /api/auth/users/{user_id}/roles` c payload `{ "roles": ["REGISTERED_USER", "ADMIN"] }`.
- Для справочника судов:
  - `GET /api/cases/admin/courts`
  - `POST /api/cases/admin/courts`
  - `PATCH /api/cases/admin/courts/{court_id}`
  - `DELETE /api/cases/admin/courts/{court_id}`
- Для журнала аудита:
  - `GET /api/cases/admin/audit`

Если endpoint отсутствуют (404/405), frontend показывает пользователю понятные сообщения на соответствующих страницах.
