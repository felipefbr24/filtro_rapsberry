# GT - Sistema de Grabacion Bioacustica

Proyecto para capturar audio de fauna acustica con Raspberry Pi y preparar una segunda etapa de grabacion por actividad sonora.

## Estructura

```text
gt/
+-- README.md
+-- fase_1_grabacion_continua/
|   +-- README.md
|   +-- raspberry_recorder/
|   +-- prueba_audio_real_windows.py
|   +-- prueba_grabadora/
|   +-- prueba_grabadora_audio_real/
+-- fase_2_actividad_acustica/
    +-- README.md
    +-- config_fase2_ejemplo.json
    +-- notas_umbral_dataset.md
```

## Fase 1

Carpeta:

```text
fase_1_grabacion_continua/
```

Estado: implementada.

Objetivo: grabar audio continuamente en segmentos, guardar metadata, organizar carpetas por fecha y detenerse antes de llenar el almacenamiento.

Incluye:

- grabadora para Raspberry Pi con `arecord`;
- servicio `systemd` de ejemplo;
- manual de instalacion;
- prueba dry-run sin microfono;
- prueba de audio real en Windows usando `ffmpeg`;
- salidas de prueba generadas.

## Fase 2

Carpeta:

```text
fase_2_actividad_acustica/
```

Estado: iniciada como diseno.

Objetivo: escuchar continuamente, detectar actividad acustica y guardar solo eventos relevantes con pre-buffer y post-buffer.

Ya incluye un simulador para probar umbrales sobre audios `.wav` antes de implementar la grabadora real.

Parametros iniciales recomendados a partir del dataset de ranas:

```text
umbral_actividad_dbfs: -30
modo_conservador_dbfs: -35
ventana_rms_ms: 250
pre_buffer_segundos: 3
post_buffer_segundos: 5
duracion_minima_evento_segundos: 0.5
duracion_maxima_evento_segundos: 60
```

## Siguiente paso recomendado

Antes de implementar el codigo definitivo de Fase 2, probar el umbral con audios reales de campo y revisar cuantos eventos guarda con `-35 dBFS`, `-30 dBFS` y `-25 dBFS`.

Comando base:

```powershell
python .\fase_2_actividad_acustica\simular_detector_actividad.py "C:\Users\felipe\Desktop\dataset_ranas-20260420T011328Z-3-001\dataset_ranas"
```
