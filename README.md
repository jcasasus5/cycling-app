# Climber Indoor Cycling

Climber es una aplicacion web para entrenar en un rodillo inteligente usando perfiles reales de subida. Permite crear o importar rutas de altimetria, controlar la dureza del rodillo segun la pendiente de cada tramo, registrar la actividad y guardar entrenamientos completos o parciales.

FastAPI sirve la aplicacion, el navegador se conecta directamente al rodillo por Bluetooth y existen dos modos:

- Desarrollo local con SQLite y sin autenticacion.
- Produccion en Vercel con Supabase Auth, PostgreSQL y aislamiento por usuario mediante RLS.

## Rodillos Compatibles

La conexion real al rodillo usa Bluetooth Low Energy con el estandar FTMS (Fitness Machine Service). No se filtra por marca o modelo: al conectar, la app consulta las capacidades anunciadas por el dispositivo y usa solo las funciones disponibles. El rodillo debe exponer:

- Servicio FTMS (`0x1826`).
- `Indoor Bike Data` para leer velocidad, cadencia y potencia.
- `Fitness Machine Control Point` para enviar control de simulacion.
- Soporte de simulacion de bici indoor para enviar pendiente.

En la practica, esto cubre rodillos smart modernos con Bluetooth FTMS. El modo ERG y la calibracion solo se habilitan cuando el equipo anuncia esas capacidades. ANT+ FE-C no esta implementado, porque desde un navegador web local no hay una API ANT+ estandar equivalente a Web Bluetooth.

## Como Controla El Rodillo

Durante un entrenamiento, la app:

- Lee velocidad, cadencia y potencia reales del rodillo.
- Calcula el avance virtual por la ruta usando la velocidad recibida.
- Busca la pendiente correspondiente al kilometro actual.
- Envia esa pendiente al rodillo mediante FTMS.
- Deja que el propio rodillo gestione el limite fisico de su hardware.
- Puede bloquear pendientes negativas si se desactiva ese ajuste.
- Al pausar, guardar o terminar, intenta devolver el rodillo a `0%` y pausar el control FTMS.

Si el rodillo rechaza una orden FTMS concreta, la app muestra el error recibido. Algunos rodillos rechazan `Start/Resume` si ya estaban activos; ese caso se tolera para poder empezar una ruta nueva sin reconectar.

## Calibracion

Desde `Ajustes` puedes conectar el rodillo y usar `Calibrar ahora`. La calibracion usa el flujo FTMS de spindown cuando el rodillo lo anuncia:

1. La app solicita iniciar spindown.
2. El rodillo devuelve una velocidad objetivo o un rango.
3. Pedaleas hasta entrar en ese rango.
4. Cuando el rodillo lo indique, dejas de pedalear.
5. La app espera el resultado de calibracion.

Cada fabricante puede presentar una secuencia distinta. Si el rodillo no anuncia soporte FTMS de spindown, la app no ofrece calibracion desde el navegador.

## Funciones Principales

- Biblioteca de rutas con distancia, desnivel, pendiente media y pendiente maxima.
- Editor de segmentos con altitud inicial/final y pendiente calculada.
- Rutas privadas por defecto, con opción de compartirlas con todos los usuarios registrados.
- Biblioteca con tus rutas primero y las rutas públicas de otros usuarios después; copias privadas e independientes.
- Importacion de perfiles desde imagen usando OpenAI Vision.
- Grafico uniforme de altimetria en canvas.
- Entrenamiento en vivo con posicion sobre el perfil.
- Conexion Bluetooth FTMS al rodillo desde la pantalla de entrenamiento o Ajustes.
- Autopausa cuando no hay velocidad real del rodillo.
- Guardado de actividades parciales o completadas.
- Historial de actividades con distancia, desnivel, potencia, cadencia y velocidad.
- Conexion OAuth por usuario con Strava y subida automatica de actividades completadas como `VirtualRide`.
- Ajustes de pendientes negativas, peso del ciclista y peso de la bici.

## Requisitos

- Python 3.12 o compatible.
- Chrome o Microsoft Edge para usar Web Bluetooth.
- Abrir la app desde `localhost` o `127.0.0.1`; Web Bluetooth no funciona desde cualquier contexto inseguro.
- Rodillo Bluetooth FTMS encendido y no conectado en exclusiva a otra app.
- Clave de OpenAI solo si quieres importar rutas desde imagen.

## Arrancar En WSL/Linux

```bash
cd /home/jcasas/projects/cycling-app
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Despues abre:

```text
http://127.0.0.1:8001
```

Tambien puedes usar:

```bash
bash start_linux.sh
```

## Arrancar En Windows

Desde PowerShell, entra en la carpeta del proyecto y ejecuta:

```powershell
.\start_windows.bat
```

Despues abre:

```text
http://127.0.0.1:8000
```

## Uso Basico

1. Crea una ruta manualmente o importa una imagen de altimetria.
2. Revisa y guarda los segmentos.
3. Entra en una ruta y pulsa `Entrenar`.
4. Pulsa `Conectar rodillo` y selecciona un equipo Bluetooth FTMS.
5. Inicia el entrenamiento.
6. Guarda parcial, termina manualmente o deja que se complete al llegar al final.

## Rutas públicas y conservación de actividades

Al crear una ruta o abrir una de tus rutas, marca `Hacer pública esta ruta` y guarda los cambios. Todos los usuarios registrados podrán consultarla, entrenar con ella y duplicarla. Solo el creador puede modificarla o eliminarla; los permisos también se comprueban en la API y mediante RLS en Supabase. Desmarca la opción para volver a hacerla privada. Las rutas existentes no se publican automáticamente.

La biblioteca muestra `Tus rutas` primero, incluidas las que has compartido, y después `Rutas públicas` con todas las rutas compartidas por otros usuarios. Se actualiza al entrar en Rutas y carga todas las páginas de Supabase. Al duplicar una ruta, se crea una copia privada con sus segmentos, propiedad del usuario que la duplica; los cambios en esa copia no afectan al original.

Eliminar una ruta **nunca elimina las actividades guardadas sobre ella**, sea pública o privada. Se conservan el nombre registrado, las métricas, las muestras y la descarga TCX. Las actividades siguen siendo privadas. Si la ruta se elimina o deja de ser accesible, su actividad sigue disponible, aunque ya no se puede continuar una actividad parcial sobre esa ruta.

Antes de desplegar este código en Supabase, aplica `supabase/migrations/20260831113544_public_routes.sql`. Incluye la visibilidad, los permisos, la duplicación y el cambio de la relación de actividades a `ON DELETE SET NULL`. La migración opcional de Strava no es necesaria para esta función. En SQLite, la actualización se realiza al arrancar y conserva las actividades y sus muestras existentes dentro de una migración transaccional.

Las pruebas de API y SQLite se ejecutan con `python3 -m pytest -q -s`. La prueba adicional `tests/sql/public_routes.sql` comprueba permisos reales entre dos usuarios en PostgreSQL y revierte sus datos al finalizar. Con un contenedor desechable que tenga el esquema de autenticación de Supabase y las migraciones aplicadas:

```bash
CYCLING_TEST_POSTGRES_CONTAINER=nombre-del-contenedor python3 -m pytest tests/test_public_routes_postgres.py -q -s
```

## OpenAI

Cada usuario configura su propia clave de OpenAI desde `Ajustes`. En produccion se cifra antes de guardarla y nunca se devuelve al navegador despues de almacenarla. Un usuario no puede consultar ni usar la clave de otro.

La clave solo se usa para analizar imagenes de perfiles de altimetria. El control del rodillo no usa OpenAI.

## Strava

### Descarga de datos sin conectar Strava

En `Actividades`, abre un entrenamiento y pulsa `Descargar TCX`. El archivo contiene las muestras registradas de tiempo, distancia, velocidad, cadencia, potencia y altitud virtual. Puedes descargar actividades completadas o parciales; las actividades sin muestras no se pueden exportar.

La descarga no requiere credenciales ni conexion con Strava y no publica nada automaticamente. Para subir el archivo manualmente, utiliza el enlace `Importar archivo en Strava` del detalle de actividad o [el cargador de archivos de Strava](https://www.strava.com/upload/select).

Tampoco requiere la migracion opcional de Strava en Supabase: mientras la integracion no este configurada, la app no consulta sus tablas ni columnas.

El endpoint `GET /api/activities/{id}/export.tcx` utiliza la misma autenticacion y permisos que la consulta de actividades. El archivo se genera al descargarlo, sin guardar copias en el servidor ni modificar la actividad. La integracion OAuth descrita a continuacion se conserva para activarla mas adelante.

### Conexion automatica opcional

Cada usuario puede conectar su propia cuenta desde `Ajustes`. Cuando termina una actividad, la app genera un archivo TCX con tiempo, distancia, velocidad, cadencia, potencia y altitud virtual, y lo envia a Strava como actividad de bici estatica (`VirtualRide`). Las actividades parciales no se publican.

Para activarla con Supabase, aplica primero `supabase/migrations/20260831113543_strava_integration.sql`. Despues registra una aplicacion en el panel de desarrolladores de Strava y configura estas variables en el servidor:

```text
STRAVA_CLIENT_ID
STRAVA_CLIENT_SECRET
STRAVA_REDIRECT_URI
APP_ENCRYPTION_KEY
```

`STRAVA_REDIRECT_URI` debe ser la URL raiz exacta a la que vuelve el navegador, por ejemplo `http://127.0.0.1:8001/` en local o `https://tu-dominio.example/` en produccion. El dominio debe coincidir con el callback registrado en Strava. Los tokens de acceso y renovacion se cifran antes de guardarse y nunca se devuelven al navegador.

## Despliegue automático desde main

`.github/workflows/deploy.yml` ejecuta las pruebas en cada pull request y cada push a `main`. Primero aplica todas las migraciones en PostgreSQL desechable y prueba los permisos entre usuarios. En `main`, si las pruebas pasan, construye la aplicación, aplica las migraciones pendientes a Supabase y despliega ese mismo build en Vercel producción. También se puede ejecutar manualmente desde GitHub Actions.

Configura estos secretos en GitHub, en `Settings > Secrets and variables > Actions` (o en el entorno `production`):

| Secreto | Valor |
| --- | --- |
| `VERCEL_TOKEN` | Token de Vercel con acceso al proyecto |
| `VERCEL_ORG_ID` | `orgId` del archivo local `.vercel/project.json` |
| `VERCEL_PROJECT_ID` | `projectId` del archivo local `.vercel/project.json` |
| `SUPABASE_ACCESS_TOKEN` | Token personal de Supabase con acceso al proyecto |
| `SUPABASE_DB_PASSWORD` | Contraseña de la base de datos del proyecto |
| `SUPABASE_PROJECT_ID` | Referencia del proyecto Supabase de producción |

No guardes tokens, contraseñas ni archivos `.env` en Git. El workflow comprueba estos secretos y se detiene si falta alguno. Si caduca un token, actualízalo en GitHub y vuelve a ejecutar el workflow.

`vercel.json` desactiva el despliegue directo de la integración Git para `main`: la publicación debe pasar por el workflow para no adelantarse a las migraciones. Los previews de otras ramas conservan su comportamiento. No hay despliegue automático efectivo hasta configurar los secretos anteriores. Se serializan los despliegues y se comprueba que el commit sigue siendo el último de `main` antes de publicarlo.

El historial local de `supabase/migrations/` coincide con las versiones registradas en producción, incluido el índice histórico de imágenes importadas. No cambies versiones de migraciones ya aplicadas ni uses `db reset` contra producción. Si falla una migración, el workflow no despliega. Si falla el despliegue después de migrar, la base de datos no se revierte automáticamente; las migraciones deben ser compatibles con la versión anterior durante la transición.

## Despliegue Y Seguridad

El despliegue de produccion usa:

- Vercel conectado al repositorio de GitHub.
- `main` como rama de produccion.
- Supabase Auth con registro publico por correo y contraseña.
- PostgreSQL con RLS en todas las tablas expuestas.
- Una variable secreta `APP_ENCRYPTION_KEY` para cifrar las claves personales de OpenAI.

Los forks de GitHub no tienen permiso para hacer push al repositorio original. Sus cambios solo pueden llegar mediante una pull request que el propietario revise y fusione. Un fork puede desplegar su propia copia, pero necesita crear su propio proyecto de Supabase y configurar sus propias variables.

Los secretos no se guardan en Git. Las variables necesarias para produccion son:

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
APP_ENCRYPTION_KEY
```

Las variables `STRAVA_*` son opcionales y solo deben configurarse al activar la conexion automatica, despues de aplicar su migracion.

La publishable key de Supabase puede aparecer en el navegador; la seguridad de los datos depende de la autenticacion y las politicas RLS. No se debe usar una `service_role` key en el frontend.

## Datos Locales

La base de datos SQLite se guarda por defecto en:

```text
data/cycling-app.db
```

Puedes cambiar la ruta usando la variable de entorno:

```bash
CYCLING_APP_DB=/ruta/a/otro.db
```

El modo SQLite solo se activa fuera de Vercel. Un despliegue de Vercel sin variables de Supabase queda bloqueado para evitar que se publique accidentalmente sin autenticacion.

## Tests

```bash
python -m pytest -q -s
```
