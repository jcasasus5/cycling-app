# Tacx Flux Climber

App web local para crear rutas de subida, importar perfiles de altimetría con OpenAI, simular entrenamientos y guardar actividades.

## Abrir En Windows

Desde PowerShell, entra en la carpeta del proyecto y ejecuta:

```powershell
.\start_windows.bat
```

Después abre:

```text
http://127.0.0.1:8000
```

## Abrir En WSL/Linux

```bash
bash start_linux.sh
```

## OpenAI

Puedes configurar la API key desde la pantalla Ajustes de la app. También puedes crear un `.env` a partir de `.env.example`, aunque la app lee y guarda los ajustes en SQLite.

## Tests

```bash
pytest
```

## Estado Del MVP

- FastAPI + SQLite local.
- Frontend web estático servido por FastAPI.
- Importación de imagen mediante OpenAI Vision con revisión editable.
- Biblioteca y edición de rutas.
- Gráfico uniforme de altimetría en canvas.
- Entrenamiento simulado con autopausa y guardado parcial/completo.
- Historial y detalle de actividades.
- Preparado para añadir un adaptador real de rodillo en backend más adelante.
