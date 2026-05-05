# Grabadora por Actividad para Raspberry Pi

Esta carpeta contiene la version instalable de la Fase 2: una grabadora que escucha continuamente, pero solo guarda audio cuando detecta actividad acustica por encima de un umbral RMS en dBFS.

No clasifica especies. Solo decide cuando guardar eventos sonoros.

## Flujo

```text
Raspberry prende
-> systemd inicia recorder_actividad.py
-> arecord entrega audio crudo al script
-> Python calcula RMS por ventanas
-> si RMS supera el umbral, abre un evento
-> incluye pre-buffer para no perder el inicio
-> incluye post-buffer para no cortar el final
-> guarda WAV o FLAC
-> escribe metadata_eventos.csv
-> sigue hasta quedar con poco espacio libre
```

## Configuracion recomendada

```text
Formato: FLAC
Frecuencia: 44100 Hz
Canales: 1 canal, mono
Umbral: -30 dBFS
Modo conservador: -35 dBFS
Ventana RMS: 250 ms
Hop RMS: 125 ms
Pre-buffer: 3 s
Post-buffer: 5 s
Duracion minima de actividad: 0.5 s
Duracion maxima de evento: 60 s
Espacio minimo libre: 512 MB
Salida: /home/pi/fauna_eventos
```

## Prueba sin microfono

Desde la raiz del proyecto:

```bash
cd /home/pi/gt
python3 fase_2_actividad_acustica/raspberry_activity_recorder/recorder_actividad.py \
  --output-dir prueba_fase2_actividad \
  --format wav \
  --threshold-dbfs -30 \
  --max-events 2 \
  --dry-run
```

## Prueba con microfono en Raspberry

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

Si el microfono no es el dispositivo por defecto, usar `--device`, por ejemplo:

```bash
--device plughw:1,0
```

## Salida esperada

```text
/home/pi/fauna_eventos/
+-- recorder_actividad.log
+-- 2026-05-05/
    +-- 18-03-22_evento_001.flac
    +-- 18-10-44_evento_002.flac
    +-- metadata_eventos.csv
```

## Servicio systemd

El archivo `fauna-activity-recorder.service.example` sirve para que la Raspberry empiece a detectar actividad apenas se prenda.