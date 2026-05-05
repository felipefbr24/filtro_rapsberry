# Grabadora Continua para Raspberry Pi

Esta carpeta contiene la Fase 1 del sistema de campo: una Raspberry Pi que graba todo lo que escucha, en segmentos ordenados, hasta que se quede sin espacio suficiente o sea apagada.

No clasifica especies. La Raspberry solo captura audio de forma confiable; la clasificacion queda para el computador.

## Que hace

- Arranca desde terminal o como servicio de `systemd`.
- Graba audio continuo con `arecord`.
- Guarda segmentos por fecha.
- Usa `FLAC` por defecto para ahorrar espacio sin perder calidad.
- Escribe `metadata.csv` por dia.
- Escribe `recorder.log` con eventos y errores.
- Se detiene limpiamente si queda poco espacio libre.
- Puede probarse con `--dry-run` sin microfono.

## Estructura de salida

```text
/home/pi/fauna_audio/
+-- recorder.log
+-- 2026-05-02/
    +-- 18-00-00.flac
    +-- 18-01-00.flac
    +-- metadata.csv
```

## Instalacion en Raspberry Pi

Instalar herramientas de audio:

```bash
sudo apt update
sudo apt install -y alsa-utils flac
```

Probar que el microfono aparece:

```bash
arecord -l
```

Probar una grabacion corta:

```bash
arecord -f S16_LE -r 44100 -c 1 -d 5 -t wav prueba.wav
```

## Uso manual

Desde la carpeta de Fase 1:

```bash
cd /home/pi/gt/fase_1_grabacion_continua
```

```bash
python3 raspberry_recorder/recorder_continuo.py \
  --output-dir /home/pi/fauna_audio \
  --format flac \
  --sample-rate 44100 \
  --channels 1 \
  --segment-seconds 60 \
  --min-free-mb 512
```

Si el microfono USB no es el dispositivo por defecto, usar el valor que muestre `arecord -l`, por ejemplo:

```bash
python3 raspberry_recorder/recorder_continuo.py \
  --device plughw:1,0 \
  --output-dir /home/pi/fauna_audio
```

## Prueba sin microfono

Esto crea dos segmentos falsos y verifica carpetas, metadata y logs:

```bash
python3 raspberry_recorder/recorder_continuo.py \
  --output-dir prueba_grabadora \
  --format wav \
  --segment-seconds 2 \
  --max-segments 2 \
  --dry-run
```

## Arranque automatico al prender

Copiar el servicio de ejemplo:

```bash
sudo cp /home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/fauna-recorder.service.example /etc/systemd/system/fauna-recorder.service
```

Editar rutas si el proyecto no esta en `/home/pi/gt`:

```bash
sudo nano /etc/systemd/system/fauna-recorder.service
```

Activar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable fauna-recorder.service
sudo systemctl start fauna-recorder.service
```

Ver estado:

```bash
systemctl status fauna-recorder.service
```

Ver logs:

```bash
journalctl -u fauna-recorder.service -f
```

## Parametros recomendados

- Ranas y aves: `--sample-rate 44100`
- Mono: `--channels 1`
- Segmentos: `--segment-seconds 60`
- Formato: `--format flac`
- Espacio minimo: `--min-free-mb 512`

Para ranas solamente se podria probar `--sample-rate 22050`, pero para incluir aves conviene mantener `44100`.
