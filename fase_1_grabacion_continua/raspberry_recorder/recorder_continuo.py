#!/usr/bin/env python3
"""
Grabadora autonoma para Raspberry Pi.

Fase 1 del sistema de campo: graba audio continuo en segmentos, guarda
metadata y se detiene limpiamente cuando queda poco espacio.
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import signal
import subprocess
import sys
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


STOP_REQUESTED = False


METADATA_FIELDS = [
    "archivo",
    "inicio",
    "fin",
    "duracion_solicitada_seg",
    "duracion_real_seg",
    "sample_rate",
    "canales",
    "bits",
    "formato",
    "espacio_libre_antes_mb",
    "espacio_libre_despues_mb",
    "estado",
    "codigo_salida",
    "error",
]


@dataclass(frozen=True)
class RecorderConfig:
    output_dir: Path
    segment_seconds: int
    sample_rate: int
    channels: int
    bits: int
    audio_format: str
    min_free_mb: int
    device: str | None
    retry_seconds: int
    max_segments: int | None
    dry_run: bool


def parse_args() -> RecorderConfig:
    parser = argparse.ArgumentParser(
        description="Graba audio continuo en segmentos para monitoreo bioacustico."
    )
    parser.add_argument(
        "--output-dir",
        default="/home/pi/fauna_audio",
        help="Carpeta donde se guardaran los audios y metadata.",
    )
    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=60,
        help="Duracion de cada archivo de audio.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=44100,
        help="Frecuencia de muestreo. 44100 es buena para ranas y aves.",
    )
    parser.add_argument("--channels", type=int, default=1, help="Canales de audio.")
    parser.add_argument(
        "--bits",
        type=int,
        choices=[16],
        default=16,
        help="Bits por muestra. Esta version usa 16-bit PCM.",
    )
    parser.add_argument(
        "--format",
        choices=["wav", "flac"],
        default="flac",
        help="Formato final. FLAC ahorra espacio sin perder calidad.",
    )
    parser.add_argument(
        "--min-free-mb",
        type=int,
        default=1024,
        help="Espacio minimo libre antes de detener la grabacion.",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Dispositivo ALSA, por ejemplo plughw:1,0. Si se omite usa default.",
    )
    parser.add_argument(
        "--retry-seconds",
        type=int,
        default=10,
        help="Segundos de espera antes de reintentar si una grabacion falla.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Limite opcional de segmentos, util para pruebas.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No usa microfono: crea archivos WAV pequenos para probar el flujo.",
    )
    args = parser.parse_args()

    if args.segment_seconds <= 0:
        parser.error("--segment-seconds debe ser mayor que 0")
    if args.sample_rate <= 0:
        parser.error("--sample-rate debe ser mayor que 0")
    if args.channels <= 0:
        parser.error("--channels debe ser mayor que 0")
    if args.min_free_mb < 0:
        parser.error("--min-free-mb no puede ser negativo")
    if args.retry_seconds < 0:
        parser.error("--retry-seconds no puede ser negativo")
    if args.max_segments is not None and args.max_segments <= 0:
        parser.error("--max-segments debe ser mayor que 0")

    return RecorderConfig(
        output_dir=Path(args.output_dir),
        segment_seconds=args.segment_seconds,
        sample_rate=args.sample_rate,
        channels=args.channels,
        bits=args.bits,
        audio_format=args.format,
        min_free_mb=args.min_free_mb,
        device=args.device,
        retry_seconds=args.retry_seconds,
        max_segments=args.max_segments,
        dry_run=args.dry_run,
    )


def request_stop(signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    logging.info("Senal %s recibida; se detendra al terminar el segmento actual.", signum)


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "recorder.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def free_mb(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return usage.free // (1024 * 1024)


def ensure_metadata_header(metadata_path: Path) -> None:
    if metadata_path.exists() and metadata_path.stat().st_size > 0:
        return
    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
        writer.writeheader()


def append_metadata(metadata_path: Path, row: dict[str, object]) -> None:
    with metadata_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METADATA_FIELDS)
        writer.writerow(row)
        handle.flush()


def dated_output_paths(config: RecorderConfig, start: datetime) -> tuple[Path, Path, Path]:
    day_dir = config.output_dir / start.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    extension = config.audio_format
    base_name = start.strftime("%H-%M-%S")
    final_path = day_dir / f"{base_name}.{extension}"
    counter = 1
    while final_path.exists():
        final_path = day_dir / f"{base_name}_{counter:03d}.{extension}"
        counter += 1
    temp_wav_path = day_dir / f".{final_path.stem}.tmp.wav"
    metadata_path = day_dir / "metadata.csv"
    ensure_metadata_header(metadata_path)
    return final_path, temp_wav_path, metadata_path


def arecord_command(config: RecorderConfig, temp_wav_path: Path) -> list[str]:
    command = ["arecord"]
    if config.device:
        command.extend(["-D", config.device])
    command.extend(
        [
            "-f",
            "S16_LE",
            "-r",
            str(config.sample_rate),
            "-c",
            str(config.channels),
            "-d",
            str(config.segment_seconds),
            "-t",
            "wav",
            str(temp_wav_path),
        ]
    )
    return command


def create_dry_run_wav(config: RecorderConfig, temp_wav_path: Path) -> subprocess.CompletedProcess[str]:
    frames = config.sample_rate * min(config.segment_seconds, 1)
    sample_width = config.bits // 8
    silence_frame = b"\x00" * sample_width * config.channels
    with wave.open(str(temp_wav_path), "wb") as wav_file:
        wav_file.setnchannels(config.channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(config.sample_rate)
        wav_file.writeframes(silence_frame * frames)
    return subprocess.CompletedProcess(args=["dry-run"], returncode=0, stdout="", stderr="")


def convert_or_move(config: RecorderConfig, temp_wav_path: Path, final_path: Path) -> subprocess.CompletedProcess[str]:
    if config.audio_format == "wav":
        temp_wav_path.replace(final_path)
        return subprocess.CompletedProcess(args=["move-wav"], returncode=0, stdout="", stderr="")

    command = ["flac", "-f", "-s", "-o", str(final_path), str(temp_wav_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        temp_wav_path.unlink(missing_ok=True)
    return result


def record_segment(config: RecorderConfig) -> bool:
    start = datetime.now()
    final_path, temp_wav_path, metadata_path = dated_output_paths(config, start)
    free_before = free_mb(config.output_dir)
    status = "ok"
    return_code = 0
    error = ""

    logging.info("Grabando segmento: %s", final_path)
    started_monotonic = time.monotonic()

    try:
        if config.dry_run:
            result = create_dry_run_wav(config, temp_wav_path)
        else:
            result = subprocess.run(
                arecord_command(config, temp_wav_path),
                capture_output=True,
                text=True,
                check=False,
            )
        return_code = result.returncode
        if result.returncode != 0:
            status = "error_grabacion"
            error = (result.stderr or result.stdout or "arecord fallo").strip()
        elif temp_wav_path.exists() and temp_wav_path.stat().st_size > 0:
            convert_result = convert_or_move(config, temp_wav_path, final_path)
            return_code = convert_result.returncode
            if convert_result.returncode != 0:
                status = "error_conversion"
                error = (convert_result.stderr or convert_result.stdout or "flac fallo").strip()
        else:
            status = "archivo_vacio"
            error = "No se creo audio o el archivo quedo vacio."
    except FileNotFoundError as exc:
        status = "comando_no_encontrado"
        return_code = 127
        error = str(exc)
    except Exception as exc:
        status = "error_inesperado"
        return_code = 1
        error = repr(exc)
    finally:
        if status != "ok":
            temp_wav_path.unlink(missing_ok=True)

    end = datetime.now()
    duration_real = round(time.monotonic() - started_monotonic, 3)
    free_after = free_mb(config.output_dir)
    archivo = final_path.relative_to(config.output_dir).as_posix() if final_path.exists() else ""

    append_metadata(
        metadata_path,
        {
            "archivo": archivo,
            "inicio": start.isoformat(timespec="seconds"),
            "fin": end.isoformat(timespec="seconds"),
            "duracion_solicitada_seg": config.segment_seconds,
            "duracion_real_seg": duration_real,
            "sample_rate": config.sample_rate,
            "canales": config.channels,
            "bits": config.bits,
            "formato": config.audio_format,
            "espacio_libre_antes_mb": free_before,
            "espacio_libre_despues_mb": free_after,
            "estado": status,
            "codigo_salida": return_code,
            "error": error[:500],
        },
    )

    if status == "ok":
        logging.info("Segmento guardado: %s", final_path)
        return True

    logging.error("Segmento fallido (%s): %s", status, error)
    return False


def main() -> int:
    config = parse_args()
    setup_logging(config.output_dir)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    logging.info("Iniciando grabadora continua")
    logging.info("Salida: %s", config.output_dir)
    logging.info(
        "Audio: %s Hz, %s canal(es), %s-bit, formato %s, segmentos de %s s",
        config.sample_rate,
        config.channels,
        config.bits,
        config.audio_format,
        config.segment_seconds,
    )

    segments_done = 0
    while not STOP_REQUESTED:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        current_free_mb = free_mb(config.output_dir)
        if current_free_mb < config.min_free_mb:
            logging.warning(
                "Espacio libre insuficiente: %s MB. Minimo configurado: %s MB.",
                current_free_mb,
                config.min_free_mb,
            )
            return 0

        ok = record_segment(config)
        segments_done += 1
        if config.max_segments is not None and segments_done >= config.max_segments:
            logging.info("Limite de prueba alcanzado: %s segmentos.", config.max_segments)
            break
        if not ok and config.retry_seconds:
            time.sleep(config.retry_seconds)

    logging.info("Grabadora detenida limpiamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
