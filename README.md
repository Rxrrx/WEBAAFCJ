# Biblioteca de Documentos

Aplicacion web basada en FastAPI para gestionar una biblioteca digital con documentos en PDF, Word, PowerPoint y texto plano. Incluye autenticacion con registro, inicio de sesion y control de permisos para subir o eliminar archivos.

## Caracteristicas principales

- Registro e inicio de sesion con hash de contrasenas (bcrypt).
- Sesiones basadas en cookies y cierre de sesion manual.
- Solo el superusuario puede subir o eliminar documentos; el resto de usuarios puede navegar, visualizar y descargar.
- Previsualizacion de PDFs embebida y descarga directa para todos los formatos.
- Interfaz responsive con biblioteca agrupada por categorias y panel dedicado para el superusuario.
- Administracion de categorias y asignacion obligatoria al subir documentos.
- Historial personal de descargas para cada usuario autenticado.

## Tecnologias

- [FastAPI](https://fastapi.tiangolo.com/) y Jinja2 para la capa web.
- [SQLAlchemy](https://www.sqlalchemy.org/) con SQLite como almacenamiento embebido.
- [Passlib](https://passlib.readthedocs.io/) para hashing de contrasenas.
- Docker y Docker Compose para despliegue reproducible.

## Estructura del proyecto

```
.
|- app
|  |- __init__.py
|  |- database.py
|  |- main.py
|  |- models.py
|  |- security.py
|  |- static
|  |  |- app.js
|  |  |- styles.css
|  |- templates
|     |- admin_upload.html
|     |- index.html
|     |- library.html
|     |- login.html
|     |- profile.html
|     |- register.html
|- data
|  |- (se crea library.db en tiempo de ejecucion)
|- Dockerfile
|- docker-compose.yml
|- requirements.txt
|- README.md
```

## Credenciales del superusuario por defecto

Al iniciar la aplicacion se garantiza la presencia de un superusuario:

- Correo: `super@biblioteca.local`
- Contrasena: `SuperUsuario123!`

Puedes sobrescribir estos valores definiendo las variables de entorno `SUPERUSER_EMAIL`, `SUPERUSER_PASSWORD` y `SUPERUSER_NAME` antes de levantar la aplicacion. El secreto de sesion se controla mediante `APP_SESSION_SECRET` (valor por defecto `dev-secret-key-change-me`).

## Subidas directas para archivos grandes

Las funciones serverless de Vercel aceptan cuerpos de peticion pequeños (~4.5 MB). Para permitir PDF de hasta 30 MB, el backend ahora puede usar cargas directas hacia un bucket tipo S3 y solo guardar metadatos en la base de datos.

1. Crea un bucket (S3, MinIO, Cloudflare R2, etc.) accesible mediante la API S3.
2. Configura CORS para permitir `PUT`, `GET` y `HEAD` desde tu dominio (`https://webaafcj.vercel.app`). Ejemplo rápido:

   ```json
   [
     {
       "AllowedOrigins": ["https://webaafcj.vercel.app"],
       "AllowedMethods": ["GET", "PUT", "HEAD"],
       "AllowedHeaders": ["*"]
     }
   ]
   ```

3. Exporta las variables de entorno:

   | Variable | Descripción |
   | --- | --- |
   | `STORAGE_BACKEND` | Define el modo de almacenamiento. Usa `s3` en producción para habilitar las cargas directas. |
   | `S3_BUCKET_NAME` | Nombre del bucket. |
   | `S3_REGION_NAME` | Región del bucket (p. ej. `us-east-1`). |
   | `S3_ENDPOINT_URL` | (Opcional) Endpoint personalizado si usas un proveedor compatible. |
   | `S3_ACCESS_KEY_ID` y `S3_SECRET_ACCESS_KEY` | Credenciales con permisos `s3:GetObject`, `s3:PutObject` y `s3:HeadObject`. |
   | `S3_PRESIGN_EXPIRATION_SECONDS` | (Opcional, por defecto 900) Vigencia de las URLs firmadas. |
   | `MAX_FILE_SIZE_MB` | Límite lógico mostrado en la UI (30 por defecto para PDFs). |

4. Despliega con esas variables en Vercel (`vercel env`). En local, puedes omitirlas para seguir guardando los archivos dentro de SQLite.

El panel de administración detecta automáticamente cuando `STORAGE_BACKEND=s3` y realiza la carga en tres pasos: solicita una URL firmada, envía el archivo directo al bucket y finalmente registra los metadatos en la base. De esta forma las peticiones hacia el servidor nunca superan el límite de Vercel, pero los usuarios igualmente descargan los archivos mediante enlaces firmados.

## Puesta en marcha con Docker

1. Construir la imagen:
   ```bash
   docker build -t biblioteca-docs .
   ```
2. Ejecutar el contenedor:
   ```bash
   docker run --rm -p 8000:8000 -v "${PWD}/data:/code/data" biblioteca-docs
   ```
   El volumen opcional preserva la base SQLite fuera del contenedor.

3. Visitar [http://localhost:8000](http://localhost:8000) para acceder a la interfaz.

## Con Docker Compose

1. Levantar la aplicacion (construye si es necesario):
   ```bash
   docker compose up -d --build
   ```
2. Consultar el estado:
   ```bash
   docker compose ps
   ```
3. Detener:
   ```bash
   docker compose down
   ```

## Flujo de uso

1. Accede con el superusuario por defecto para crear las categorias necesarias.
2. Sube documentos desde el panel admin seleccionando una categoria existente.
3. Registra usuarios finales para que descarguen y consulten su historial personal desde el perfil.
4. El superusuario puede eliminar documentos y gestionar categorias en cualquier momento.

## Proximos pasos sugeridos

- Integrar un sistema de mensajes (flash) para feedback de formularios.
- Permitir busqueda y filtrado de documentos.
- Migrar a un motor externo (PostgreSQL, MySQL) para entornos productivos.
- Agregar almacenamiento externo (p. ej. S3) para manejar archivos de gran tamaño.
- j
