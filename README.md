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
- `POST /admin/students` y `POST /admin/teachers`: crean el perfil y generan una invitación sin asignar contraseña.
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

## Horarios recurrentes

Los administradores configuran plantillas semanales mediante `/admin/schedule-templates`, indicando nivel, sucursal, salón, horario, vigencia y cupo. El cupo efectivo se calcula como el menor entre el cupo configurado, el predeterminado del nivel y la capacidad física del salón.

Los cierres y bloqueos de calendario se registran en `/admin/schedule-exceptions`. Pueden afectar a toda la organización, una sucursal, un salón o un profesor durante el día completo o un rango horario. Estas excepciones tienen prioridad sobre las plantillas al generar sesiones.

## Sesiones semanales

`POST /admin/class-sessions/generate-week` materializa una semana de plantillas como sesiones individuales. La operación es idempotente, respeta vigencias y excepciones, impide cruces de salón y asigna profesores elegibles con un criterio determinista de disponibilidad y carga reciente. Si ningún profesor cumple las reglas, conserva la sesión como borrador sin asignar para que el administrador pueda resolverla.

Los administradores consultan y ajustan sesiones mediante `/admin/class-sessions`. Una sesión no puede publicarse sin profesor y su cupo efectivo nunca supera la capacidad física del salón. Cada profesor consulta únicamente sus sesiones publicadas en `GET /teachers/me/sessions`.

## Asignación de profesores

La generación semanal clasifica únicamente profesores disponibles, autorizados para el nivel y sin conflictos. El ranking parte de 1000 puntos y descuenta penalizaciones visibles por carga semanal, carga reciente, repetición de nivel, repetición del mismo grupo y repetición de franja horaria.

Los administradores pueden revisar el desglose en `/admin/class-sessions/{id}/teacher-candidates`, aplicar la mejor recomendación o seleccionar manualmente otro profesor con un motivo obligatorio. Cada asignación automática, recomendada o manual queda preservada en `/admin/class-sessions/{id}/assignment-history`.

## Reservaciones

Las políticas de reservación se configuran globalmente o por sucursal mediante `/admin/booking-policies`. La configuración inicial exige 24 horas de anticipación para reservar o cancelar y permite reservar la semana siguiente; también admite múltiples ventanas horarias por día.

Los alumnos consultan lugares y motivos de indisponibilidad en `/students/me/available-sessions`, reservan desde `/students/me/bookings` y revisan su consumo semanal. El backend valida nivel actual, sucursal permitida, vigencia, cupo, cruces de horario y límite de horas. Una cancelación oportuna libera lugar y cuota; una cancelación tardía queda pendiente hasta que un administrador la apruebe o rechace. Cada transición conserva un historial auditable y las excepciones administrativas requieren motivo.

## Lista de espera

Cuando una sesión está llena, el alumno puede unirse a `/students/me/waitlist`. La cola conserva orden FIFO y, al liberarse un lugar, crea una oferta temporal para el siguiente alumno sin confirmar automáticamente la reservación. La duración se configura con `waitlist_offer_minutes` dentro de la política de reservación.

Mientras una oferta está vigente, el lugar queda apartado. El alumno debe aceptarla explícitamente; si vence o abandona la cola, el siguiente recibe la oportunidad. Los avisos quedan disponibles en `/notifications`, y el administrador puede consultar la cola o procesar vencimientos desde `/admin/waitlist`.

## Niveles, currícula y progreso

Los niveles son configurables por organización mediante `/admin/levels`. Cada nivel puede organizarse en capítulos y temas ordenados usando `/admin/levels/{id}/chapters`, `/admin/chapters/{id}/topics` y sus endpoints de actualización o desactivación. Los usuarios autenticados consultan la estructura activa completa en `GET /curriculum`.

Los cambios de nivel de un alumno se registran con `POST /admin/students/{id}/levels`; el periodo anterior se cierra sin eliminarse y puede consultarse en `/admin/students/{id}/level-history`. Administradores y profesores académicamente relacionados registran el avance individual por tema, mientras cada alumno consulta su propio resumen en `/students/me/academic-progress`.

## Profesores

Los administradores crean y gestionan perfiles docentes mediante `/admin/teachers`, incluyendo número de empleado, sucursales asignadas y niveles autorizados. El alta genera la misma invitación segura y de un solo uso empleada para alumnos.

La disponibilidad recurrente y sus excepciones se administran con `/admin/teachers/{id}/availability`. Cada profesor también puede mantener su perfil y disponibilidad desde `/teachers/me` y `/teachers/me/availability`. Las excepciones por fecha tienen prioridad para la futura generación de horarios.

El catálogo base de niveles está disponible en `/admin/levels`; la currícula, capítulos, temas y progreso se incorporarán en la Fase 8.

## Alumnos

El alta se realiza con `POST /admin/students`. Esta operación crea el perfil académico, una cuenta inactiva y una invitación de activación. Los administradores pueden listar, filtrar, consultar, actualizar y dar de baja lógicamente mediante `/admin/students`.

Una vez activada la cuenta, cada alumno puede consultar y actualizar sus datos de contacto con `GET /students/me` y `PATCH /students/me`. La matrícula, sucursal, límite de horas, estado y notas administrativas solamente pueden modificarse desde el flujo administrativo.

## Sucursales y salones

Los administradores gestionan ubicaciones mediante:

- `/admin/branches`: listar y crear sucursales.
- `/admin/branches/{id}`: consultar, actualizar o desactivar una sucursal.
- `/admin/rooms`: listar y crear salones, opcionalmente filtrados por sucursal.
- `/admin/rooms/{id}`: consultar, actualizar o desactivar un salón.

Los `DELETE` son borrados lógicos. Desactivar una sucursal también desactiva sus salones. La base de datos impide que un salón quede asociado a una sucursal de otra organización.
