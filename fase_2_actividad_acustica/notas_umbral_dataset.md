# Notas de Umbral Basadas en Dataset

Dataset analizado:

```text
C:\Users\felipe\Desktop\dataset_ranas-20260420T011328Z-3-001\dataset_ranas
```

Resultado del analisis:

```text
Archivos WAV encontrados: 105
Archivos analizados: 104
Archivo con error de lectura: 1
Duracion total aproximada: 205.43 minutos
Sample rates encontrados: 44100, 48000, 96000 Hz
```

Energia RMS por ventanas de 250 ms:

```text
p20: -49.3 dBFS
p50: -38.0 dBFS
p75: -27.1 dBFS
p90: -21.6 dBFS
p95: -19.0 dBFS
```

Fraccion de ventanas por encima de cada umbral:

```text
-35 dBFS: 43.2%
-30 dBFS: 32.6%
-25 dBFS: 18.8%
-22 dBFS: 10.8%
-20 dBFS:  6.8%
```

Recomendacion:

```text
Modo conservador: -35 dBFS
Modo inicial recomendado: -30 dBFS
Modo estricto para ahorrar espacio: -25 dBFS
```

Decision actual:

```text
Usar -30 dBFS como valor por defecto configurable.
Usar -35 dBFS en la primera salida de campo si la prioridad es no perder llamados lejanos.
```

## Simulacion de eventos con pre-buffer y post-buffer

Configuracion usada:

```text
ventana_rms_ms: 250
hop_ms: 125
pre_buffer_segundos: 3
post_buffer_segundos: 5
duracion_minima_evento_segundos: 0.5
duracion_maxima_evento_segundos: 60
```

Resultados:

```text
-35 dBFS:
  eventos detectados: 288
  archivos con eventos: 104/104
  audio que se guardaria: 69.14%

-30 dBFS:
  eventos detectados: 276
  archivos con eventos: 104/104
  audio que se guardaria: 55.97%

-25 dBFS:
  eventos detectados: 197
  archivos con eventos: 91/104
  audio que se guardaria: 35.67%
```

Lectura:

```text
-35 dBFS es mas seguro, pero ahorra poco espacio.
-30 dBFS mantiene detecciones en todos los audios analizados y reduce casi la mitad del audio.
-25 dBFS ahorra mas, pero ya deja varios archivos sin eventos detectados.
```

Decision recomendada para implementar:

```text
Valor por defecto: -30 dBFS
Valor para primera prueba de campo: -35 dBFS
Valor estricto opcional: -25 dBFS
```
