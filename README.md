# Court Documents Backend (Microservices)

Сервисы: nginx, auth-service, case-service, ner-service, anonymization-service.

БД: auth-db, case-db, anonymized-db, personal-data-db.

Почему PII отдельно: минимизация риска утечек и контроль доступа к восстановлению.

## Запуск
```bash
cp .env.example .env
docker compose up --build
```

## Поток загрузки документа
1) staff загружает текст в case-service
2) case-service вызывает anonymization-service
3) anonymization-service вызывает ner-service
4) сохраняются anonymized + original/mappings раздельно

## Тестовые пользователи
- admin/admin123
- user/user123
- staff/staff123
- judge/judge123
