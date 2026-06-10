# Tacx Flux Climber

Tacx Flux Climber es una aplicacion web para entrenar en un rodillo inteligente usando perfiles reales de subida. Permite crear o importar rutas de altimetria, controlar la dureza del rodillo segun la pendiente de cada tramo, registrar la actividad y guardar entrenamientos completos o parciales.

FastAPI sirve la aplicacion, el navegador se conecta directamente al rodillo por Bluetooth y existen dos modos:

- Desarrollo local con SQLite y sin autenticacion.
- Produccion en Vercel con Supabase Auth, PostgreSQL y aislamiento por usuario mediante RLS.

## Rodillos Compatibles

La conexion real al rodillo usa Bluetooth Low Energy con el estandar FTMS (Fitness Machine Service). Esta implementacion esta orientada y probada a nivel de protocolo para el Tacx FLUX 2 Smart, pero tambien puede funcionar con otros rodillos inteligentes que expongan:

- Servicio FTMS (`0x1826`).
- `Indoor Bike Data` para leer velocidad, cadencia y potencia.
- `Fitness Machine Control Point` para enviar control de simulacion.
- Soporte de simulacion de bici indoor para enviar pendiente.

En la practica, esto cubre rodillos smart modernos con Bluetooth FTMS. ANT+ FE-C no esta implementado en esta app, porque desde un navegador web local no hay una API ANT+ estandar equivalente a Web Bluetooth.

## Como Controla El Rodillo

Durante un entrenamiento, la app:

- Lee velocidad, cadencia y potencia reales del rodillo.
- Calcula el avance virtual por la ruta usando la velocidad recibida.
- Busca la pendiente correspondiente al kilometro actual.
- Envia esa pendiente al rodillo mediante FTMS.
- Limita la pendiente enviada usando el ajuste `Pendiente maxima rodillo`.
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

En el Tacx FLUX 2 Smart es normal ver una secuencia parecida a la de la app oficial de Tacx: acelerar hasta una velocidad objetivo y dejar de pedalear. Si el rodillo no anuncia soporte FTMS de spindown, la app no ofrece calibracion desde el navegador.

## Funciones Principales

- Biblioteca de rutas con distancia, desnivel, pendiente media y pendiente maxima.
- Editor de segmentos con altitud inicial/final y pendiente calculada.
- Importacion de perfiles desde imagen usando OpenAI Vision.
- Grafico uniforme de altimetria en canvas.
- Entrenamiento en vivo con posicion sobre el perfil.
- Conexion Bluetooth FTMS al rodillo desde la pantalla de entrenamiento o Ajustes.
- Autopausa cuando no hay velocidad real del rodillo.
- Guardado de actividades parciales o completadas.
- Historial de actividades con distancia, desnivel, potencia, cadencia y velocidad.
- Ajustes de pendiente maxima, pendientes negativas, suavizado, peso del ciclista y peso de la bici.

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
4. Pulsa `Conectar Tacx` y selecciona el rodillo.
5. Inicia el entrenamiento.
6. Guarda parcial, termina manualmente o deja que se complete al llegar al final.

## OpenAI

Cada usuario configura su propia clave de OpenAI desde `Ajustes`. En produccion se cifra antes de guardarla y nunca se devuelve al navegador despues de almacenarla. Un usuario no puede consultar ni usar la clave de otro.

La clave solo se usa para analizar imagenes de perfiles de altimetria. El control del rodillo no usa OpenAI.

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
