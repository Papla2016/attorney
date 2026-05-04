# FRONTEND BACKEND REQUIREMENTS

Frontend ожидает следующие endpoint для страницы аккаунта:

- `PATCH /api/auth/me` — изменение логина/почты текущего пользователя.
- `POST /api/auth/me/change-password` — изменение пароля текущего пользователя.

Если endpoint отсутствуют (404/405), frontend показывает пользователю сообщение:
"Изменение данных аккаунта пока не реализовано на backend."
