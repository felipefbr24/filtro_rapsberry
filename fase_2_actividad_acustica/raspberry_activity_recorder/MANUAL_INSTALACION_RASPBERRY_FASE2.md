# Manual de Instalacion - Fase 2 Actividad Acustica

Este manual instala la grabadora por actividad acustica en Raspberry Pi. A diferencia de Fase 1, esta version no guarda todo: escucha continuamente y guarda solo eventos donde el nivel RMS supera un umbral.

## 1. Instalar dependencias

```bash
sudo apt update
sudo apt install -y python3 alsa-utils flac
```

## 2. Verificar microfono

```bash
arecord -l
```

Si aparece como `card 1, device 0`, normalmente se usa:

```text
plughw:1,0
```

Prueba rapida:

```bash
arecord -f S16_LE -r 44100 -c 1 -d 5 -t wav prueba.wav
ls -lh prueba.wav
```

## 3. Probar sin microfono

```bash
cd /home/pi/gt
python3 fase_2_actividad_acustica/raspberry_activity_recorder/recorder_actividad.py \
  --output-dir prueba_fase2_actividad \
  --format wav \
  --threshold-dbfs -30 \
  --max-events 2 \
  --dry-run
```

Resultado esperado:

```text
Actividad detectada: evento 001
Evento guardado: ...evento_001.wav
Actividad detectada: evento 002
Evento guardado: ...evento_002.wav
```

## 4. Probar con microfono real

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

Si no graba, especificar dispositivo:

```bash
python3 fase_2_actividad_acustica/raspberry_activity_recorder/recorder_actividad.py \
  --device plughw:1,0 \
  --output-dir /home/pi/fauna_eventos \
  --format flac \
  --threshold-dbfs -30 \
  --max-events 3
```

## 5. Revisar resultados

```bash
ls -R /home/pi/fauna_eventos
cat /home/pi/fauna_eventos/$(date +%F)/metadata_eventos.csv
```

La columna `estado` debe decir `ok` para eventos guardados correctamente.

## 6. Activar arranque automatico

```bash
sudo cp /home/pi/gt/fase_2_actividad_acustica/raspberry_activity_recorder/fauna-activity-recorder.service.example /etc/systemd/system/fauna-activity-recorder.service
sudo systemctl daemon-reload
sudo systemctl enable fauna-activity-recorder.service
sudo systemctl start fauna-activity-recorder.service
```

Ver estado:

```bash
systemctl status fauna-activity-recorder.service
journalctl -u fauna-activity-recorder.service -f
```

Resultado esperado:

```text
Active: active (running)
Escuchando actividad acustica
```

## 7. Configuracion final recomendada

```bash
/usr/bin/python3 /home/pi/gt/fase_2_actividad_acustica/raspberry_activity_recorder/recorder_actividad.py --output-dir /home/pi/fauna_eventos --format flac --sample-rate 44100 --channels 1 --threshold-dbfs -30 --window-ms 250 --hop-ms 125 --pre-buffer-seconds 3 --post-buffer-seconds 5 --min-event-seconds 0.5 --max-event-seconds 60 --min-free-mb 512
```

Para primera salida conservadora, cambiar:

```text
--threshold-dbfs -30
```

por:

```text
--threshold-dbfs -35
```

## 8. Detener servicio

```bash
sudo systemctl stop fauna-activity-recorder.service
```

Para desactivar arranque automatico:

```bash
sudo systemctl disable fauna-activity-recorder.service
```

## 9. Precaucion

Fase 2 ahorra espacio, pero puede perder sonidos suaves si el umbral es alto. Para una salida importante, primero comparar contra Fase 1 o usar `-35 dBFS`.