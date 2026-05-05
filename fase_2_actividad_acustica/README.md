# Fase 2 - Grabacion por Actividad Acustica

Esta fase busca reducir el espacio usado por la Raspberry. En vez de guardar todo el audio, el sistema escucha continuamente y guarda solo cuando detecta actividad sonora.

## Estado actual

La fase ya tiene dos partes:

```text
1. Simulador offline sobre audios WAV existentes.
2. Grabadora instalable para Raspberry Pi.
```

El simulador sirve para calibrar umbrales antes de salir al campo. La grabadora real usa esos parametros para escuchar el microfono en vivo.

## Estructura

```text
fase_2_actividad_acustica/
+-- README.md
+-- config_fase2_ejemplo.json
+-- notas_umbral_dataset.md
+-- simular_detector_actividad.py
+-- resultados_simulacion/
+-- prueba_audios_cortados/
+-- raspberry_activity_recorder/
    +-- recorder_actividad.py
    +-- fauna-activity-recorder.service.example
    +-- README.md
    +-- MANUAL_INSTALACION_RASPBERRY_FASE2.md
```

## Idea principal

```text
Escuchar continuamente
Calcular energia RMS en ventanas cortas
Si la energia supera un umbral, abrir evento
Guardar segundos previos usando pre-buffer
Seguir grabando mientras haya actividad
Guardar segundos extra usando post-buffer
Cerrar evento
Volver a escuchar
```

## Parametros iniciales

Segun el analisis del dataset local de ranas, el punto de partida recomendado es:

```text
umbral_actividad_dbfs: -30
ventana_rms_ms: 250
hop_ms: 125
pre_buffer_segundos: 3
post_buffer_segundos: 5
duracion_minima_evento_segundos: 0.5
duracion_maxima_evento_segundos: 60
```

Para una primera salida de campo donde la prioridad sea no perder ranas lejanas, usar:

```text
umbral_actividad_dbfs: -35
```

Si se guarda demasiado ruido o silencio, subir el umbral:

```text
-35 -> -30 -> -25
```

Si se pierden llamados suaves, bajar el umbral:

```text
-30 -> -35 -> -40
```

## Version instalable para Raspberry

Carpeta:

```text
raspberry_activity_recorder/
```

Script principal:

```text
raspberry_activity_recorder/recorder_actividad.py
```

Servicio de arranque automatico:

```text
raspberry_activity_recorder/fauna-activity-recorder.service.example
```

Manual:

```text
raspberry_activity_recorder/MANUAL_INSTALACION_RASPBERRY_FASE2.md
```

Comando final recomendado:

```bash
/usr/bin/python3 /home/pi/gt/fase_2_actividad_acustica/raspberry_activity_recorder/recorder_actividad.py --output-dir /home/pi/fauna_eventos --format flac --sample-rate 44100 --channels 1 --threshold-dbfs -30 --window-ms 250 --hop-ms 125 --pre-buffer-seconds 3 --post-buffer-seconds 5 --min-event-seconds 0.5 --max-event-seconds 60 --min-free-mb 512
```

## Salida esperada en Raspberry

```text
/home/pi/fauna_eventos/
+-- recorder_actividad.log
+-- 2026-05-05/
    +-- 18-03-22_evento_001.flac
    +-- 18-10-44_evento_002.flac
    +-- metadata_eventos.csv
```

Metadata esperada:

```csv
archivo,inicio,fin,duracion_real_seg,duracion_actividad_seg,sample_rate,canales,bits,formato,umbral_dbfs,rms_max_dbfs,rms_promedio_dbfs,pre_buffer_seg,post_buffer_seg,ventana_rms_ms,hop_ms,espacio_libre_antes_mb,espacio_libre_despues_mb,estado,codigo_salida,error
```

## Simulador offline

Script:

```text
simular_detector_actividad.py
```

Desde la raiz del proyecto:

```powershell
python .\fase_2_actividad_acustica\simular_detector_actividad.py "C:\Users\felipe\Desktop\dataset_ranas-20260420T011328Z-3-001\dataset_ranas"
```

Esto genera:

```text
fase_2_actividad_acustica/resultados_simulacion/
+-- resumen_umbral.csv
+-- eventos_detectados.csv
+-- errores_lectura.csv
```

Resultados actuales con el dataset de ranas:

```text
-35 dBFS: 288 eventos, 69.14% del audio se guardaria
-30 dBFS: 276 eventos, 55.97% del audio se guardaria
-25 dBFS: 197 eventos, 35.67% del audio se guardaria
```

Para probar otros umbrales:

```powershell
python .\fase_2_actividad_acustica\simular_detector_actividad.py "C:\Users\felipe\Desktop\dataset_ranas-20260420T011328Z-3-001\dataset_ranas" --thresholds-dbfs -40 -35 -30 -25
```

## Exportar audios cortados

Para generar clips WAV de los eventos detectados y poder escucharlos:

```powershell
python .\fase_2_actividad_acustica\simular_detector_actividad.py "C:\Users\felipe\Desktop\dataset_ranas-20260420T011328Z-3-001\dataset_ranas" --thresholds-dbfs -30 --export-audio --export-threshold-dbfs -30 --max-export-events 12 --output-dir .\fase_2_actividad_acustica\prueba_audios_cortados
```

Los clips quedan en:

```text
fase_2_actividad_acustica/prueba_audios_cortados/audios_cortados/
```

## Riesgo principal

Un umbral demasiado alto puede perder vocalizaciones suaves o lejanas. Por eso Fase 2 debe probarse en paralelo con Fase 1 antes de usarla como unico modo en campo.

## Pendiente

- Probar `recorder_actividad.py` en Raspberry real con microfono USB.
- Confirmar dispositivo ALSA con `arecord -l`.
- Probar arranque automatico con `systemd`.
- Comparar una noche de Fase 1 continua contra Fase 2 por actividad.
- Ajustar umbral para el sitio real de muestreo.