# English Scheduler

Plataforma integral de gestión para escuelas, construida progresivamente con FastAPI, PostgreSQL y Vue.

## Requisitos para Windows

- Docker Desktop con el motor WSL 2 activo.
- Git.
- Node.js y npm (se utilizarán al incorporar el frontend).
- Python es opcional para ejecutar la aplicación con Docker.

## Configuración inicial (PowerShell)

1. Crea tu archivo local de variables de entorno:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Sustituye en `.env` las contraseñas y `JWT_SECRET`. El archivo `.env` es local y no debe subirse a Git.

3. Valida la configuración:

   ```powershell
   docker compose config --quiet
   ```

4. Construye e inicia PostgreSQL y el backend:

   ```powershell
   docker compose up --build
   ```

5. Abre la documentación de la API en <http://localhost:8000/docs> o verifica <http://localhost:8000/health>.

Para detener los servicios, presiona `Ctrl+C`. Si los ejecutaste en segundo plano, usa:

```powershell
docker compose down
```

## Servicios locales

| Servicio | URL |
| --- | --- |
| Frontend Vue | <http://localhost:5173> |
| API FastAPI | <http://localhost:8000> |
| Documentación API | <http://localhost:8000/docs> |

La página inicial del frontend comprueba automáticamente la conexión con `/health`.
