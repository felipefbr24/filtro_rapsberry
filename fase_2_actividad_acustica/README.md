# Fase 2 - Grabacion por Actividad Acustica

Esta fase busca reducir el espacio usado por la Raspberry. En vez de guardar todo el audio, el sistema escuchara continuamente y guardara solo cuando detecte actividad sonora.

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

## Riesgo principal

Un umbral demasiado alto puede perder vocalizaciones suaves o lejanas. Por eso Fase 2 debe probarse primero con audios conocidos antes de usarla como unico modo en campo.

## Salida esperada

```text
fauna_eventos/
+-- recorder_actividad.log
+-- 2026-05-04/
    +-- 22-15-10_evento_001.flac
    +-- 22-18-42_evento_002.flac
    +-- metadata_eventos.csv
```

## Metadata esperada

```csv
archivo,inicio,fin,duracion_real_seg,sample_rate,canales,bits,formato,umbral_dbfs,rms_max_dbfs,rms_promedio_dbfs,pre_buffer_seg,post_buffer_seg,estado,error
```

## Pendiente

- Implementar detector RMS por ventanas. Hecho en simulador sobre dataset.
- Agregar pre-buffer en memoria.
- Agregar post-buffer.
- Guardar eventos en WAV o FLAC.
- Crear metadata de eventos.
- Probar con `-35`, `-30` y `-25 dBFS`.
- Comparar eventos detectados contra audios del dataset.

## Simular con el dataset

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

El archivo `eventos_detectados.csv` incluye la columna `exported_file`, que conecta cada evento detectado con el clip exportado.
