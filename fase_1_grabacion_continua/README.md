# GT - Grabadora Autonoma de Fauna Acustica

Esta carpeta contiene la Fase 1 del sistema de captura de audio para una Raspberry Pi que se usara en campo, monte o zonas rurales para grabar sonidos de ranas, aves y ambiente natural.

La idea principal es separar el trabajo en dos partes:

1. La Raspberry Pi graba audio de forma confiable en campo.
2. El computador analiza y clasifica los audios despues.

Esto evita sobrecargar la Raspberry con modelos pesados y reduce el riesgo de perder datos importantes.

## Objetivo general

Construir una grabadora autonoma que:

- empiece a funcionar apenas se prenda la Raspberry;
- grabe audio continuamente;
- guarde audios en archivos pequenos y ordenados;
- registre metadata de cada segmento;
- siga grabando hasta que quede poco espacio libre;
- permita despues clasificar ranas, aves, ruido o silencio en un computador.

## Contexto de la decision

Primero se penso en usar una BlackBerry, pero luego se aclaro que el dispositivo real era una Raspberry Pi 4 con 4 GB de RAM.

La conclusion fue que la Raspberry es mejor para el trabajo de campo, pero aun asi no conviene hacer clasificacion en tiempo real en la primera version, porque eso consume mas CPU, bateria y memoria.

Por eso se decidio hacer el sistema en fases.

## Fase 1: grabacion continua inteligente

Esta fase ya fue implementada.

La Raspberry funciona como una grabadora autonoma. No intenta reconocer especies. Solo se encarga de capturar audio y guardar todo de forma ordenada.

La llamamos grabadora inteligente porque no es solo una grabadora simple: tambien organiza carpetas, divide el audio en segmentos, guarda metadata, revisa espacio libre y deja logs de errores.

### Que hace actualmente

- Graba todo lo que escucha.
- Crea archivos por segmentos.
- Guarda audio en FLAC o WAV.
- Usa FLAC por defecto para ahorrar espacio sin perder calidad.
- Crea una carpeta por fecha.
- Crea un `metadata.csv` por dia.
- Crea un `recorder.log` general.
- Se detiene cuando queda poco espacio libre.
- Puede ejecutarse automaticamente al prender la Raspberry usando `systemd`.
- Tiene modo `--dry-run` para pruebas sin microfono.

### Configuracion final recomendada

```text
Formato: FLAC
Frecuencia: 44100 Hz
Canales: 1 canal, mono
Bits: 16-bit
Duracion de segmento: 60 segundos
Carpeta de salida: /home/pi/fauna_audio
Espacio minimo libre: 512 MB
```

### Comando final recomendado

Este es el comando que debe ejecutar la Raspberry:

```bash
/usr/bin/python3 /home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/recorder_continuo.py --output-dir /home/pi/fauna_audio --format flac --sample-rate 44100 --channels 1 --segment-seconds 60 --min-free-mb 512
```

## Estructura actual del proyecto

```text
gt/fase_1_grabacion_continua/
+-- README.md
+-- raspberry_recorder/
|   +-- recorder_continuo.py
|   +-- fauna-recorder.service.example
|   +-- README.md
|   +-- MANUAL_INSTALACION_RASPBERRY.md
+-- prueba_grabadora/
+-- prueba_grabadora_audio_real/
+-- prueba_audio_real_windows.py
```

### Archivos importantes

```text
raspberry_recorder/recorder_continuo.py
```

Script principal. Graba audio continuo por segmentos, guarda metadata y revisa espacio libre.

```text
raspberry_recorder/fauna-recorder.service.example
```

Servicio de ejemplo para `systemd`. Permite que la grabadora arranque automaticamente al prender la Raspberry.

```text
raspberry_recorder/MANUAL_INSTALACION_RASPBERRY.md
```

Manual paso a paso para instalar, probar y activar la grabadora en la Raspberry.

```text
raspberry_recorder/README.md
```

Descripcion tecnica corta de la herramienta de grabacion.

```text
prueba_grabadora/
```

Carpeta de salida de pruebas. Puede contener audios falsos o salidas de prueba hechas desde Windows con `--dry-run`.

## Resultado esperado en campo

Cuando la Raspberry este instalada y prendida, debe crear algo asi:

```text
/home/pi/fauna_audio/
+-- recorder.log
+-- 2026-05-02/
|   +-- 18-00-00.flac
|   +-- 18-01-00.flac
|   +-- 18-02-00.flac
|   +-- metadata.csv
+-- 2026-05-03/
|   +-- 00-00-00.flac
|   +-- 00-01-00.flac
|   +-- metadata.csv
```

Cada archivo dura 60 segundos.

El `metadata.csv` debe tener una fila por cada audio:

```csv
archivo,inicio,fin,duracion_solicitada_seg,duracion_real_seg,sample_rate,canales,bits,formato,espacio_libre_antes_mb,espacio_libre_despues_mb,estado,codigo_salida,error
2026-05-02/18-00-00.flac,2026-05-02T18:00:00,2026-05-02T18:01:00,60,60.1,44100,1,16,flac,120000,119996,ok,0,
```

La columna mas importante es:

```text
estado
```

Debe decir:

```text
ok
```

## Como probar rapido en Windows

Esta prueba no graba audio real. Solo confirma que el script crea carpetas, metadata y archivos de prueba.

Desde PowerShell:

```powershell
cd "C:\Users\felipe\Desktop\Codex\gt"
cd ".\fase_1_grabacion_continua"
python .\raspberry_recorder\recorder_continuo.py --output-dir .\prueba_grabadora --format wav --segment-seconds 2 --max-segments 2 --dry-run
```

Resultado esperado:

```text
INFO Iniciando grabadora continua
INFO Grabando segmento...
INFO Segmento guardado...
INFO Grabadora detenida limpiamente.
```

## Como grabar audio real en Windows

Para probar el microfono real del computador, usar el script separado:

```powershell
python .\prueba_audio_real_windows.py --list-devices
```

Si `ffmpeg` muestra un microfono, copiar el nombre exacto y grabar un segmento de 5 segundos:

```powershell
python .\prueba_audio_real_windows.py --output-dir .\prueba_grabadora_audio_real --device "NOMBRE EXACTO DEL MICROFONO" --format wav --segment-seconds 5 --max-segments 1
```

Tambien se puede probar primero con el dispositivo por defecto:

```powershell
python .\prueba_audio_real_windows.py --output-dir .\prueba_grabadora_audio_real --format wav --segment-seconds 5 --max-segments 1
```

Esta prueba si usa el microfono real. En Windows puede hacer falta permitir acceso al microfono en la configuracion de privacidad del sistema.

## Como probar en la Raspberry

Instalar dependencias:

```bash
sudo apt update
sudo apt install -y python3 alsa-utils flac
```

Probar microfono:

```bash
arecord -l
arecord -f S16_LE -r 44100 -c 1 -d 5 -t wav prueba.wav
```

Probar el script con 3 segmentos de 10 segundos:

```bash
cd /home/pi/gt/fase_1_grabacion_continua
python3 raspberry_recorder/recorder_continuo.py \
  --output-dir /home/pi/fauna_audio \
  --format flac \
  --sample-rate 44100 \
  --channels 1 \
  --segment-seconds 10 \
  --max-segments 3 \
  --min-free-mb 512
```

Resultado esperado:

```text
/home/pi/fauna_audio/
+-- recorder.log
+-- AAAA-MM-DD/
    +-- HH-MM-SS.flac
    +-- HH-MM-SS.flac
    +-- HH-MM-SS.flac
    +-- metadata.csv
```

## Arranque automatico

La Raspberry debe empezar a grabar apenas se prenda. Para eso se usa `systemd`.

Pasos principales:

```bash
sudo cp /home/pi/gt/fase_1_grabacion_continua/raspberry_recorder/fauna-recorder.service.example /etc/systemd/system/fauna-recorder.service
sudo systemctl daemon-reload
sudo systemctl enable fauna-recorder.service
sudo systemctl start fauna-recorder.service
```

Verificar:

```bash
systemctl status fauna-recorder.service
journalctl -u fauna-recorder.service -f
```

Resultado esperado:

```text
Active: active (running)
```

## Fase 2: grabacion por actividad acustica

Esta fase todavia no esta implementada.

La idea futura es que la Raspberry no guarde todo el audio, sino solo fragmentos donde detecte actividad sonora.

El flujo pensado es:

```text
Escuchar continuamente
Medir energia o volumen del audio
Si supera un umbral, empezar a guardar
Incluir unos segundos previos con pre-buffer
Seguir grabando mientras haya actividad
Guardar unos segundos extra con post-buffer
Cerrar archivo y volver a esperar actividad
```

Parametros esperados para esa fase:

```text
umbral_actividad
pre_buffer_segundos
post_buffer_segundos
duracion_minima_evento
duracion_maxima_evento
```

Esta fase puede ahorrar mucho espacio, pero tiene riesgo: si el umbral queda mal calibrado, puede perder ranas o aves lejanas. Por eso primero se hizo la Fase 1 de grabacion continua.

## Filosofia del proyecto

La prioridad en campo es no perder audio.

Por eso:

```text
Raspberry = capturar audio de forma confiable
Computador = analizar, filtrar y clasificar despues
```

La clasificacion de especies debe hacerse despues con los audios recolectados, usando herramientas mas pesadas en un computador.

## Relacion con Proyecto_Ranas

Este proyecto `gt` es aparte de `Proyecto_Ranas`.

`Proyecto_Ranas` contiene trabajo de datasets, entrenamiento y clasificacion acustica.

Este proyecto `gt` contiene la parte de captura en campo con Raspberry Pi.

No mezclar codigo ni salidas entre ambos proyectos sin una decision explicita.

## Estado actual

Hecho:

- Script de grabacion continua.
- Guardado por fecha.
- Metadata por dia.
- Logs.
- Limite de espacio libre.
- Modo de prueba sin microfono.
- Servicio de ejemplo para arranque automatico.
- Manual de instalacion para Raspberry.

Pendiente:

- Probar en Raspberry real con microfono USB.
- Confirmar el dispositivo ALSA correcto con `arecord -l`.
- Activar `systemd` en la Raspberry.
- Hacer prueba de reinicio.
- Implementar Fase 2 de deteccion de actividad.
- Definir estrategia para pasar audios desde la Raspberry al computador.
- Conectar los audios capturados con el pipeline de clasificacion posterior.

## Checklist para retomar el proyecto

Si otra IA o persona retoma este trabajo, primero debe revisar:

```text
1. Este README.md
2. raspberry_recorder/MANUAL_INSTALACION_RASPBERRY.md
3. raspberry_recorder/recorder_continuo.py
4. raspberry_recorder/fauna-recorder.service.example
```

Antes de modificar el codigo, confirmar si la meta actual es:

```text
A. Probar Fase 1 en Raspberry real
B. Ajustar grabacion continua
C. Implementar Fase 2 por actividad
D. Integrar con clasificacion en computador
```
