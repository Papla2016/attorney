# Frontend
## Запуск
- `docker compose up --build`
- локально: `cd frontend && npm install && npm run dev`

## Страницы
Публичный поиск `/`, документ `/documents/:documentId`, login/register, `/favorites`, `/my-cases`, `/cases/:caseId/restored`, staff и admin маршруты.

## Роли
REGISTERED_USER, COURT_STAFF, JUDGE, COURT_CLERK, ADMIN.

## VITE_API_BASE_URL
- dev: `http://localhost:8080/api`
- prod: `/api`

## Авторизация
JWT `access_token` хранится в `localStorage`, добавляется в `Authorization: Bearer`.
При `401` токен очищается и пользователь отправляется на `/login`.

## Интеграция с backend
Frontend вызывает только `/api/*` согласно `docs/API_CONTRACT.md`; в production nginx frontend проксирует `/api` на gateway-сервис `nginx`.
