# Manual de Instalacion - Grabadora Raspberry Pi

Este manual explica como instalar y probar la grabadora continua en una Raspberry Pi. El objetivo es que la Raspberry empiece a grabar automaticamente apenas se prenda y siga grabando hasta que quede poco espacio libre.

## 1. Objetivo del sistema

La Raspberry funcionara como una grabadora autonoma de campo.

Configuracion recomendada:

```text
Formato: FLAC
Frecuencia: 44100 Hz
Canales: 1 canal, mono
Segmentos: 60 segundos
Carpeta de salida: /home/pi/fauna_audio
Espacio minimo libre: 512 MB
```

La Raspberry no clasifica ranas ni aves en esta fase. Solo graba y organiza los audios. La clasificacion se hace despues en el computador.

## 2. Estructura esperada del proyecto

En la Raspberry, el proyecto debe quedar asi:

```text
/home/pi/gt/
  fase_1_grabacion_continua/
    raspberry_recorder/
      recorder_continuo.py
      fauna-recorder.service.example
      README.md
      MANUAL_INSTALACION_RASPBERRY.md
```

El archivo principal es:

```text
/home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/recorder_continuo.py
```

## 3. Instalar dependencias

Abre la terminal de la Raspberry y ejecuta:

```bash
sudo apt update
sudo apt install -y python3 alsa-utils flac
```

Resultado esperado:

```text
python3 instalado
arecord instalado
flac instalado
```

`arecord` permite grabar desde el microfono. `flac` comprime el audio sin perder calidad.

## 4. Revisar que el microfono exista

Conecta el microfono USB y ejecuta:

```bash
arecord -l
```

Resultado esperado:

```text
card 1: ... USB Audio ...
```

Puede aparecer como `card 1`, `device 0`. En ese caso el dispositivo suele ser:

```text
plughw:1,0
```

Si no aparece ningun microfono, revisa:

```bash
lsusb
```

## 5. Prueba basica del microfono

Ejecuta una grabacion corta de 5 segundos:

```bash
arecord -f S16_LE -r 44100 -c 1 -d 5 -t wav prueba.wav
```

Resultado esperado:

```text
Recording WAVE 'prueba.wav'...
```

Luego revisa que el archivo exista:

```bash
ls -lh prueba.wav
```

Resultado esperado:

```text
prueba.wav con un tamano mayor a 0 bytes
```

Si quieres escucharlo en la Raspberry:

```bash
aplay prueba.wav
```

## 6. Probar la grabadora manualmente

Entra al proyecto:

```bash
cd /home/pi/gt/fase_1_grabacion_continua
```

Ejecuta una prueba corta de 3 segmentos de 10 segundos:

```bash
python3 raspberry_recorder/recorder_continuo.py \
  --output-dir /home/pi/fauna_audio \
  --format flac \
  --sample-rate 44100 \
  --channels 1 \
  --segment-seconds 10 \
  --max-segments 3 \
  --min-free-mb 512
```

Resultado esperado en pantalla:

```text
INFO Iniciando grabadora continua
INFO Grabando segmento: /home/pi/fauna_audio/AAAA-MM-DD/HH-MM-SS.flac
INFO Segmento guardado: /home/pi/fauna_audio/AAAA-MM-DD/HH-MM-SS.flac
INFO Limite de prueba alcanzado: 3 segmentos.
INFO Grabadora detenida limpiamente.
```

## 7. Revisar los resultados de la prueba

Ejecuta:

```bash
ls -R /home/pi/fauna_audio
```

Resultado esperado:

```text
/home/pi/fauna_audio/
  recorder.log
  AAAA-MM-DD/
    HH-MM-SS.flac
    HH-MM-SS.flac
    HH-MM-SS.flac
    metadata.csv
```

Ejemplo:

```text
/home/pi/fauna_audio/
  recorder.log
  2026-05-02/
    18-00-00.flac
    18-00-10.flac
    18-00-20.flac
    metadata.csv
```

Ver metadata:

```bash
cat /home/pi/fauna_audio/$(date +%F)/metadata.csv
```

Resultado esperado:

```text
archivo,inicio,fin,duracion_solicitada_seg,duracion_real_seg,sample_rate,canales,bits,formato,espacio_libre_antes_mb,espacio_libre_despues_mb,estado,codigo_salida,error
2026-05-02/18-00-00.flac,...,ok,0,
```

Lo importante es que la columna `estado` diga:

```text
ok
```

## 8. Configurar arranque automatico

Copia el servicio a systemd:

```bash
sudo cp /home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/fauna-recorder.service.example /etc/systemd/system/fauna-recorder.service
```

Edita el servicio:

```bash
sudo nano /etc/systemd/system/fauna-recorder.service
```

Debe quedar con este comando en `ExecStart`:

```text
ExecStart=/usr/bin/python3 /home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/recorder_continuo.py --output-dir /home/pi/fauna_audio --format flac --sample-rate 44100 --channels 1 --segment-seconds 60 --min-free-mb 512
```

Guarda con:

```text
Ctrl + O
Enter
Ctrl + X
```

Activa el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable fauna-recorder.service
sudo systemctl start fauna-recorder.service
```

Resultado esperado:

```text
Created symlink ... fauna-recorder.service
```

## 9. Revisar que este funcionando

Ver estado:

```bash
systemctl status fauna-recorder.service
```

Resultado esperado:

```text
Active: active (running)
```

Ver logs en vivo:

```bash
journalctl -u fauna-recorder.service -f
```

Resultado esperado:

```text
Iniciando grabadora continua
Grabando segmento: /home/pi/fauna_audio/AAAA-MM-DD/HH-MM-SS.flac
Segmento guardado: /home/pi/fauna_audio/AAAA-MM-DD/HH-MM-SS.flac
```

Salir de los logs:

```text
Ctrl + C
```

## 10. Probar reinicio automatico

Reinicia la Raspberry:

```bash
sudo reboot
```

Espera a que vuelva a prender y revisa:

```bash
systemctl status fauna-recorder.service
```

Resultado esperado:

```text
Active: active (running)
```

Revisa que hayan aparecido nuevos audios:

```bash
ls -lh /home/pi/fauna_audio/$(date +%F)
```

Resultado esperado:

```text
archivos .flac nuevos cada 60 segundos
metadata.csv actualizado
```

## 11. Detener o pausar la grabadora

Para detener temporalmente:

```bash
sudo systemctl stop fauna-recorder.service
```

Para volver a iniciar:

```bash
sudo systemctl start fauna-recorder.service
```

Para desactivar el arranque automatico:

```bash
sudo systemctl disable fauna-recorder.service
```

## 12. Donde quedan los audios finales

Los audios quedan en:

```text
/home/pi/fauna_audio
```

Estructura esperada despues de varias horas:

```text
/home/pi/fauna_audio/
  recorder.log
  2026-05-02/
    18-00-00.flac
    18-01-00.flac
    18-02-00.flac
    metadata.csv
  2026-05-03/
    00-00-00.flac
    00-01-00.flac
    metadata.csv
```

Cada archivo dura 60 segundos.

## 13. Cuando se queda sin espacio

El sistema esta configurado para detenerse cuando queden 512 MB libres:

```text
--min-free-mb 512
```

Resultado esperado en logs:

```text
Espacio libre insuficiente: XXX MB. Minimo configurado: 512 MB.
```

Esto evita llenar la tarjeta al 100%, lo cual podria causar errores en Linux o corrupcion de archivos.

## 14. Comando final recomendado

Este es el comando final que debe usar el servicio:

```bash
/usr/bin/python3 /home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/recorder_continuo.py --output-dir /home/pi/fauna_audio --format flac --sample-rate 44100 --channels 1 --segment-seconds 60 --min-free-mb 512
```

## 15. Problemas comunes

### No aparece el microfono

Ejecuta:

```bash
arecord -l
lsusb
```

Si no aparece, desconecta y conecta el microfono o prueba otro puerto USB.

### El servicio esta activo pero no graba

Ver logs:

```bash
journalctl -u fauna-recorder.service -n 50
```

Busca errores como:

```text
arecord fallo
comando_no_encontrado
No such file or directory
```

### FLAC falla

Instala `flac`:

```bash
sudo apt install -y flac
```

### La ruta del proyecto es diferente

Edita:

```bash
sudo nano /etc/systemd/system/fauna-recorder.service
```

Y corrige la ruta en `ExecStart`.

Luego ejecuta:

```bash
sudo systemctl daemon-reload
sudo systemctl restart fauna-recorder.service
```

## 16. Confirmacion final antes de llevarla al campo

Antes de dejar la Raspberry en el monte, confirma:

```text
[ ] El microfono aparece con arecord -l
[ ] La prueba de 5 segundos crea prueba.wav
[ ] La prueba del script crea 3 audios .flac
[ ] metadata.csv muestra estado ok
[ ] systemctl status muestra active (running)
[ ] Despues de reiniciar, el servicio vuelve a grabar solo
[ ] Hay suficiente espacio en la microSD o disco USB
[ ] La fecha y hora de la Raspberry son correctas
```
