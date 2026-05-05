# GT - Sistema de Grabacion Bioacustica

Proyecto para capturar audio de fauna acustica con Raspberry Pi. El sistema esta dividido en dos fases: grabacion continua confiable y grabacion por actividad acustica para ahorrar espacio.

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
    +-- simular_detector_actividad.py
    +-- config_fase2_ejemplo.json
    +-- notas_umbral_dataset.md
    +-- raspberry_activity_recorder/
```

## Fase 1: grabacion continua

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

Uso recomendado: primera salida de campo o sesiones donde la prioridad sea no perder ningun audio.

## Fase 2: actividad acustica

Carpeta:

```text
fase_2_actividad_acustica/
```

Estado: simulador offline implementado y grabadora instalable para Raspberry creada.

Objetivo: escuchar continuamente, detectar actividad acustica y guardar solo eventos relevantes con pre-buffer y post-buffer.

Incluye:

- simulador sobre audios WAV existentes;
- resultados de calibracion con umbrales `-35`, `-30` y `-25 dBFS`;
- exportacion de clips detectados para revision;
- grabadora real para Raspberry en `raspberry_activity_recorder/`;
- servicio `systemd` para arrancar al prender la Raspberry;
- manual de instalacion de Fase 2.

Parametros iniciales recomendados:

```text
umbral_actividad_dbfs: -30
modo_conservador_dbfs: -35
ventana_rms_ms: 250
hop_ms: 125
pre_buffer_segundos: 3
post_buffer_segundos: 5
duracion_minima_evento_segundos: 0.5
duracion_maxima_evento_segundos: 60
```

Resultados actuales del simulador sobre el dataset de ranas:

```text
-35 dBFS: 288 eventos, 69.14% del audio se guardaria
-30 dBFS: 276 eventos, 55.97% del audio se guardaria
-25 dBFS: 197 eventos, 35.67% del audio se guardaria
```

## Siguiente paso recomendado

Probar la grabadora de Fase 2 en la Raspberry real con microfono USB:

```bash
cd /home/pi/gt
python3 fase_2_actividad_acustica/raspberry_activity_recorder/recorder_actividad.py \
  --output-dir /home/pi/fauna_eventos \
  --format flac \
  --sample-rate 44100 \
  --channels 1 \
  --threshold-dbfs -30 \
  --max-events 3
```

Si la prioridad es no perder llamados suaves en la primera salida, usar:

```bash
--threshold-dbfs -35
```

Despues de validar manualmente, activar el servicio `systemd` de Fase 2.

## Relacion entre fases

```text
Fase 1 = mas segura, guarda todo, usa mas espacio.
Fase 2 = ahorra espacio, pero depende de calibrar bien el umbral.
```

La recomendacion para campo es probar Fase 2 en paralelo o compararla contra audios de Fase 1 antes de depender solo de deteccion por actividad.