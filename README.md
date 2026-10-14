# Backend Django

Requisitos: Docker e Docker Compose.

Após clonar, copie o exemplo e ajuste o `.env`:

```bash
cp .env.example .env
docker compose up --build -d
```

Acesse http://localhost (ou a porta definida em `HTTP_PORT`). As dependências,
incluindo Django REST Framework, são instaladas no build. O Django usa PostgreSQL;
o container aguarda o banco ficar disponível, aplica as migrações e coleta os
arquivos estáticos antes de iniciar o Gunicorn.

Configure `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` e as credenciais `DB_*` no `.env`.
Para outro domínio ou porta, ajuste também `CSRF_TRUSTED_ORIGINS` com a URL completa.
Dentro do Compose, mantenha `DB_HOST=db` e `DB_PORT=5432`.
As credenciais do PostgreSQL são aplicadas na criação inicial do volume; alterar
apenas o `.env` não altera a senha de um banco já existente.

```bash
docker compose exec web python manage.py createsuperuser
docker compose logs -f web
docker compose down
```

O banco persiste em um volume. Após alterar dependências, rode novamente
`docker compose up --build -d`. Migrações novas devem ser criadas durante o
desenvolvimento e incluídas no repositório.
