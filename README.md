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

## Migraciones de base de datos

El backend ejecuta `alembic upgrade head` al iniciar. Para revisar el estado o crear una migración desde PowerShell:

```powershell
docker compose exec backend alembic current
docker compose exec backend alembic history
docker compose exec backend alembic revision --autogenerate -m "describir cambio"
```

No uses `Base.metadata.create_all()` para evolucionar el esquema. Todos los cambios deben quedar representados mediante Alembic.

## Autenticación

La API expone los siguientes flujos:

- `POST /auth/login`: crea una sesión y entrega access/refresh tokens.
- `POST /auth/refresh`: rota el refresh token.
- `POST /auth/logout`: revoca la sesión actual.
- `GET /auth/me`: devuelve el usuario autenticado.
- `POST /admin/invitations`: invita a un profesor o alumno sin asignarle contraseña.
- `POST /auth/activate`: activa una invitación de un solo uso.
- `POST /auth/forgot-password`: solicita recuperación sin revelar si la cuenta existe.
- `POST /auth/reset-password`: cambia la contraseña y revoca las sesiones anteriores.

En `ENVIRONMENT=development`, las respuestas de invitación y recuperación incluyen el enlace necesario para probar localmente. En producción esos enlaces no se devuelven y deberán enviarse mediante el servicio de correo que se conectará en la fase de notificaciones.

## SUPER_ADMIN y permisos delegados

El primer propietario de la plataforma se crea de forma interactiva para no guardar su contraseña en archivos ni historial de comandos:

```powershell
docker compose exec backend python -m app.cli.create_super_admin --email owner@example.com
```

Los roles poseen permisos predeterminados. Un administrador puede consultar el catálogo y delegar permisos específicos —con expiración opcional— mediante `/admin/users/{user_id}/permissions`. Las operaciones siempre verifican la organización en backend.

## Sucursales y salones

Los administradores gestionan ubicaciones mediante:

- `/admin/branches`: listar y crear sucursales.
- `/admin/branches/{id}`: consultar, actualizar o desactivar una sucursal.
- `/admin/rooms`: listar y crear salones, opcionalmente filtrados por sucursal.
- `/admin/rooms/{id}`: consultar, actualizar o desactivar un salón.

Los `DELETE` son borrados lógicos. Desactivar una sucursal también desactiva sus salones. La base de datos impide que un salón quede asociado a una sucursal de otra organización.
