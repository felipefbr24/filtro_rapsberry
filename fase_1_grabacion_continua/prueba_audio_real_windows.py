#!/usr/bin/env python3
"""
Prueba de grabacion real en Windows usando ffmpeg.

Este script es para probar el microfono del computador. No reemplaza la
grabadora de Raspberry Pi, que usa arecord en Linux.
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
class WindowsRecorderConfig:
    output_dir: Path
    segment_seconds: int
    sample_rate: int
    channels: int
    bits: int
    audio_format: str
    min_free_mb: int
    device: str
    retry_seconds: int
    max_segments: int | None
    ffmpeg: str
    list_devices: bool


def parse_args() -> WindowsRecorderConfig:
    parser = argparse.ArgumentParser(
        description="Graba audio real del microfono en Windows usando ffmpeg."
    )
    parser.add_argument(
        "--output-dir",
        default="prueba_grabadora_audio_real",
        help="Carpeta donde se guardaran los audios y metadata.",
    )
    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=5,
        help="Duracion de cada segmento de prueba.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=44100,
        help="Frecuencia de muestreo.",
    )
    parser.add_argument("--channels", type=int, default=1, help="Canales de audio.")
    parser.add_argument(
        "--bits",
        type=int,
        choices=[16],
        default=16,
        help="Bits por muestra. Esta prueba usa 16-bit.",
    )
    parser.add_argument(
        "--format",
        choices=["wav", "flac"],
        default="wav",
        help="Formato final.",
    )
    parser.add_argument(
        "--min-free-mb",
        type=int,
        default=512,
        help="Espacio minimo libre antes de detener la prueba.",
    )
    parser.add_argument(
        "--device",
        default="default",
        help=(
            "Nombre del microfono en DirectShow. Usa --list-devices para verlo. "
            "Si se omite, intenta usar default."
        ),
    )
    parser.add_argument(
        "--retry-seconds",
        type=int,
        default=3,
        help="Segundos de espera antes de reintentar si una grabacion falla.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=1,
        help="Cantidad de segmentos a grabar. Por defecto graba solo uno.",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="Ruta o nombre del ejecutable ffmpeg.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Lista dispositivos DirectShow detectados por ffmpeg y sale.",
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

    return WindowsRecorderConfig(
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
        ffmpeg=args.ffmpeg,
        list_devices=args.list_devices,
    )


def request_stop(signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    logging.info("Senal %s recibida; se detendra al terminar el segmento actual.", signum)


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "recorder_windows.log"
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


def fix_mojibake(text: str) -> str:
    """Corrige nombres copiados como MicrÃ³fono cuando sea posible."""
    if "Ã" not in text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text


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


def dated_output_paths(config: WindowsRecorderConfig, start: datetime) -> tuple[Path, Path]:
    day_dir = config.output_dir / start.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    base_name = start.strftime("%H-%M-%S")
    final_path = day_dir / f"{base_name}.{config.audio_format}"
    counter = 1
    while final_path.exists():
        final_path = day_dir / f"{base_name}_{counter:03d}.{config.audio_format}"
        counter += 1
    metadata_path = day_dir / "metadata.csv"
    ensure_metadata_header(metadata_path)
    return final_path, metadata_path


def list_devices(config: WindowsRecorderConfig) -> int:
    command = [
        config.ffmpeg,
        "-hide_banner",
        "-list_devices",
        "true",
        "-f",
        "dshow",
        "-i",
        "dummy",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        print(f"No se encontro ffmpeg: {exc}", file=sys.stderr)
        return 127

    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    print(output.strip())
    return 0


def ffmpeg_record_command(config: WindowsRecorderConfig, final_path: Path) -> list[str]:
    codec = "pcm_s16le" if config.audio_format == "wav" else "flac"
    device = fix_mojibake(config.device)
    return [
        config.ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-i",
        f"audio={device}",
        "-t",
        str(config.segment_seconds),
        "-ac",
        str(config.channels),
        "-ar",
        str(config.sample_rate),
        "-acodec",
        codec,
        str(final_path),
    ]


def record_segment(config: WindowsRecorderConfig) -> bool:
    start = datetime.now()
    final_path, metadata_path = dated_output_paths(config, start)
    free_before = free_mb(config.output_dir)
    status = "ok"
    return_code = 0
    error = ""

    logging.info("Grabando microfono real: %s", final_path)
    started_monotonic = time.monotonic()

    try:
        result = subprocess.run(
            ffmpeg_record_command(config, final_path),
            capture_output=True,
            text=True,
            check=False,
        )
        return_code = result.returncode
        if result.returncode != 0:
            status = "error_grabacion"
            error = (result.stderr or result.stdout or "ffmpeg fallo").strip()
        elif not final_path.exists() or final_path.stat().st_size == 0:
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

    if status != "ok":
        final_path.unlink(missing_ok=True)

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
    if config.list_devices:
        return list_devices(config)

    setup_logging(config.output_dir)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    logging.info("Iniciando prueba de audio real en Windows")
    logging.info("Salida: %s", config.output_dir)
    logging.info("Dispositivo: %s", config.device)
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

    logging.info("Prueba detenida limpiamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
