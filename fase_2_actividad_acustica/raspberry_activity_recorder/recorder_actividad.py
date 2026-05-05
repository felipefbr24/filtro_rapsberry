#!/usr/bin/env python3
"""
Grabadora por actividad acustica para Raspberry Pi.

Fase 2: escucha audio crudo desde arecord, calcula RMS en vivo y guarda
solamente eventos que superan un umbral dBFS, incluyendo pre-buffer y
post-buffer.
"""

from __future__ import annotations

import argparse
import csv
import logging
import math
import shutil
import signal
import struct
import subprocess
import sys
import time
import wave
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Iterable


STOP_REQUESTED = False


METADATA_FIELDS = [
    "archivo",
    "inicio",
    "fin",
    "duracion_real_seg",
    "duracion_actividad_seg",
    "sample_rate",
    "canales",
    "bits",
    "formato",
    "umbral_dbfs",
    "rms_max_dbfs",
    "rms_promedio_dbfs",
    "pre_buffer_seg",
    "post_buffer_seg",
    "ventana_rms_ms",
    "hop_ms",
    "espacio_libre_antes_mb",
    "espacio_libre_despues_mb",
    "estado",
    "codigo_salida",
    "error",
]


@dataclass(frozen=True)
class ActivityConfig:
    output_dir: Path
    sample_rate: int
    channels: int
    bits: int
    audio_format: str
    threshold_dbfs: float
    window_ms: float
    hop_ms: float
    pre_buffer_seconds: float
    post_buffer_seconds: float
    min_event_seconds: float
    max_event_seconds: float
    min_free_mb: int
    device: str | None
    retry_seconds: int
    max_events: int | None
    heartbeat_seconds: int
    dry_run: bool


@dataclass
class EventState:
    index: int
    chunks: list[bytes]
    event_start_stream_sec: float
    active_start_stream_sec: float
    last_active_stream_sec: float
    start_wall_time: datetime
    rms_values: list[float]
    free_before_mb: int


@dataclass(frozen=True)
class Chunk:
    data: bytes
    start_sec: float
    end_sec: float


@dataclass(frozen=True)
class EventResult:
    saved: bool
    status: str
    path: Path | None
    return_code: int
    error: str


class AudioStream:
    def __iter__(self) -> Iterable[Chunk]:
        raise NotImplementedError

    def close(self) -> tuple[int, str]:
        return 0, ""


class ARecordStream(AudioStream):
    def __init__(self, config: ActivityConfig, hop_bytes: int, hop_seconds: float) -> None:
        command = ["arecord"]
        if config.device:
            command.extend(["-D", config.device])
        command.extend(
            [
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(config.sample_rate),
                "-c",
                str(config.channels),
                "-t",
                "raw",
            ]
        )
        self.command = command
        self.hop_bytes = hop_bytes
        self.hop_seconds = hop_seconds
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def __iter__(self) -> Iterable[Chunk]:
        assert self.process.stdout is not None
        stream_time = 0.0
        while not STOP_REQUESTED:
            data = read_exact(self.process.stdout, self.hop_bytes)
            if not data:
                break
            if len(data) < self.hop_bytes:
                break
            yield Chunk(data=data, start_sec=stream_time, end_sec=stream_time + self.hop_seconds)
            stream_time += self.hop_seconds

    def close(self) -> tuple[int, str]:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        stderr = ""
        if self.process.stderr is not None:
            try:
                stderr = self.process.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                stderr = ""
        return self.process.returncode or 0, stderr.strip()


class DryRunStream(AudioStream):
    def __init__(self, config: ActivityConfig, hop_samples: int, hop_seconds: float) -> None:
        self.config = config
        self.hop_samples = hop_samples
        self.hop_seconds = hop_seconds
        self.events_to_generate = config.max_events or 2

    def __iter__(self) -> Iterable[Chunk]:
        stream_time = 0.0
        pattern: list[tuple[str, float]] = []
        for _event in range(self.events_to_generate):
            pattern.extend(
                [
                    ("silence", max(1.0, self.config.pre_buffer_seconds + 0.5)),
                    ("tone", 1.5),
                    ("silence", max(1.0, self.config.post_buffer_seconds + 0.5)),
                ]
            )
        for kind, duration in pattern:
            chunks = max(1, int(math.ceil(duration / self.hop_seconds)))
            for _ in range(chunks):
                data = self.make_chunk(kind, stream_time)
                yield Chunk(data=data, start_sec=stream_time, end_sec=stream_time + self.hop_seconds)
                stream_time += self.hop_seconds
                if STOP_REQUESTED:
                    return

    def make_chunk(self, kind: str, stream_time: float) -> bytes:
        if kind == "silence":
            return b"\x00\x00" * self.hop_samples * self.config.channels
        frames = bytearray()
        amplitude = int(32767 * 0.12)
        frequency = 1200.0
        for index in range(self.hop_samples):
            value = int(amplitude * math.sin(2.0 * math.pi * frequency * (stream_time + index / self.config.sample_rate)))
            frame = struct.pack("<h", value)
            frames.extend(frame * self.config.channels)
        return bytes(frames)


def parse_args() -> ActivityConfig:
    parser = argparse.ArgumentParser(
        description="Graba eventos acusticos en Raspberry Pi usando umbral RMS dBFS."
    )
    parser.add_argument("--output-dir", default="/home/pi/fauna_eventos")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--channels", type=int, default=1)
    parser.add_argument("--bits", type=int, choices=[16], default=16)
    parser.add_argument("--format", choices=["wav", "flac"], default="flac")
    parser.add_argument("--threshold-dbfs", type=float, default=-30.0)
    parser.add_argument("--window-ms", type=float, default=250.0)
    parser.add_argument("--hop-ms", type=float, default=125.0)
    parser.add_argument("--pre-buffer-seconds", type=float, default=3.0)
    parser.add_argument("--post-buffer-seconds", type=float, default=5.0)
    parser.add_argument("--min-event-seconds", type=float, default=0.5)
    parser.add_argument("--max-event-seconds", type=float, default=60.0)
    parser.add_argument("--min-free-mb", type=int, default=512)
    parser.add_argument("--device", default=None, help="Dispositivo ALSA, por ejemplo plughw:1,0.")
    parser.add_argument("--retry-seconds", type=int, default=10)
    parser.add_argument("--max-events", type=int, default=None, help="Limite opcional para pruebas.")
    parser.add_argument("--heartbeat-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true", help="Genera audio sintetico para probar sin microfono.")
    args = parser.parse_args()

    if args.sample_rate <= 0:
        parser.error("--sample-rate debe ser mayor que 0")
    if args.channels <= 0:
        parser.error("--channels debe ser mayor que 0")
    if args.window_ms <= 0:
        parser.error("--window-ms debe ser mayor que 0")
    if args.hop_ms <= 0:
        parser.error("--hop-ms debe ser mayor que 0")
    if args.pre_buffer_seconds < 0:
        parser.error("--pre-buffer-seconds no puede ser negativo")
    if args.post_buffer_seconds < 0:
        parser.error("--post-buffer-seconds no puede ser negativo")
    if args.min_event_seconds <= 0:
        parser.error("--min-event-seconds debe ser mayor que 0")
    if args.max_event_seconds <= 0:
        parser.error("--max-event-seconds debe ser mayor que 0")
    if args.min_free_mb < 0:
        parser.error("--min-free-mb no puede ser negativo")
    if args.retry_seconds < 0:
        parser.error("--retry-seconds no puede ser negativo")
    if args.max_events is not None and args.max_events <= 0:
        parser.error("--max-events debe ser mayor que 0")
    if args.heartbeat_seconds <= 0:
        parser.error("--heartbeat-seconds debe ser mayor que 0")

    return ActivityConfig(
        output_dir=Path(args.output_dir),
        sample_rate=args.sample_rate,
        channels=args.channels,
        bits=args.bits,
        audio_format=args.format,
        threshold_dbfs=args.threshold_dbfs,
        window_ms=args.window_ms,
        hop_ms=args.hop_ms,
        pre_buffer_seconds=args.pre_buffer_seconds,
        post_buffer_seconds=args.post_buffer_seconds,
        min_event_seconds=args.min_event_seconds,
        max_event_seconds=args.max_event_seconds,
        min_free_mb=args.min_free_mb,
        device=args.device,
        retry_seconds=args.retry_seconds,
        max_events=args.max_events,
        heartbeat_seconds=args.heartbeat_seconds,
        dry_run=args.dry_run,
    )


def request_stop(signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    logging.info("Senal %s recibida; cerrando cuando sea seguro.", signum)


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "recorder_actividad.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def read_exact(stream: BinaryIO, byte_count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < byte_count:
        data = stream.read(byte_count - len(chunks))
        if not data:
            break
        chunks.extend(data)
    return bytes(chunks)


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


def day_paths(config: ActivityConfig, wall_time: datetime) -> tuple[Path, Path]:
    day_dir = config.output_dir / wall_time.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = day_dir / "metadata_eventos.csv"
    ensure_metadata_header(metadata_path)
    return day_dir, metadata_path


def unique_event_path(day_dir: Path, start_wall_time: datetime, event_index: int, extension: str) -> Path:
    base = f"{start_wall_time.strftime('%H-%M-%S')}_evento_{event_index:03d}"
    path = day_dir / f"{base}.{extension}"
    counter = 1
    while path.exists():
        path = day_dir / f"{base}_{counter:03d}.{extension}"
        counter += 1
    return path


def pcm16_dbfs(chunks: Iterable[bytes]) -> float:
    total_squares = 0
    total_samples = 0
    for chunk in chunks:
        usable = len(chunk) - (len(chunk) % 2)
        for (sample,) in struct.iter_unpack("<h", chunk[:usable]):
            total_squares += sample * sample
            total_samples += 1
    if total_samples == 0:
        return -240.0
    rms = math.sqrt(total_squares / total_samples) / 32768.0
    return 20.0 * math.log10(max(rms, 1e-12))


def write_wav(path: Path, chunks: list[bytes], config: ActivityConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(config.channels)
        wav_file.setsampwidth(config.bits // 8)
        wav_file.setframerate(config.sample_rate)
        wav_file.writeframes(b"".join(chunks))


def convert_or_move(temp_wav_path: Path, final_path: Path, config: ActivityConfig) -> EventResult:
    if config.audio_format == "wav":
        temp_wav_path.replace(final_path)
        return EventResult(True, "ok", final_path, 0, "")

    command = ["flac", "-f", "-s", "-o", str(final_path), str(temp_wav_path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return EventResult(False, "comando_no_encontrado", None, 127, str(exc))
    if result.returncode == 0:
        temp_wav_path.unlink(missing_ok=True)
        return EventResult(True, "ok", final_path, 0, "")
    error = (result.stderr or result.stdout or "flac fallo").strip()
    return EventResult(False, "error_conversion", None, result.returncode, error)


def save_event(config: ActivityConfig, event: EventState, end_stream_sec: float, forced_status: str = "ok") -> EventResult:
    active_duration = max(0.0, event.last_active_stream_sec - event.active_start_stream_sec)
    day_dir, metadata_path = day_paths(config, event.start_wall_time)
    free_before = event.free_before_mb
    final_path = unique_event_path(day_dir, event.start_wall_time, event.index, config.audio_format)
    temp_wav_path = day_dir / f".{final_path.stem}.tmp.wav"
    status = forced_status
    return_code = 0
    error = ""
    saved_path: Path | None = None

    if active_duration < config.min_event_seconds:
        status = "descartado_evento_corto"
        result = EventResult(False, status, None, 0, "")
    else:
        try:
            write_wav(temp_wav_path, event.chunks, config)
            result = convert_or_move(temp_wav_path, final_path, config)
            status = result.status if result.status != "ok" else forced_status
            return_code = result.return_code
            error = result.error
            saved_path = result.path
        except Exception as exc:
            status = "error_guardado"
            return_code = 1
            error = repr(exc)
            temp_wav_path.unlink(missing_ok=True)
            result = EventResult(False, status, None, return_code, error)

    event_duration = max(0.0, end_stream_sec - event.event_start_stream_sec)
    end_wall_time = event.start_wall_time + timedelta(seconds=event_duration)
    free_after = free_mb(config.output_dir)
    archivo = saved_path.relative_to(config.output_dir).as_posix() if saved_path else ""
    rms_max = max(event.rms_values) if event.rms_values else -240.0
    rms_mean = sum(event.rms_values) / len(event.rms_values) if event.rms_values else -240.0

    append_metadata(
        metadata_path,
        {
            "archivo": archivo,
            "inicio": event.start_wall_time.isoformat(timespec="seconds"),
            "fin": end_wall_time.isoformat(timespec="seconds"),
            "duracion_real_seg": round(event_duration, 3),
            "duracion_actividad_seg": round(active_duration, 3),
            "sample_rate": config.sample_rate,
            "canales": config.channels,
            "bits": config.bits,
            "formato": config.audio_format,
            "umbral_dbfs": config.threshold_dbfs,
            "rms_max_dbfs": round(rms_max, 2),
            "rms_promedio_dbfs": round(rms_mean, 2),
            "pre_buffer_seg": config.pre_buffer_seconds,
            "post_buffer_seg": config.post_buffer_seconds,
            "ventana_rms_ms": config.window_ms,
            "hop_ms": config.hop_ms,
            "espacio_libre_antes_mb": free_before,
            "espacio_libre_despues_mb": free_after,
            "estado": status,
            "codigo_salida": return_code,
            "error": error[:500],
        },
    )

    if result.saved:
        logging.info("Evento guardado: %s", saved_path)
    elif status == "descartado_evento_corto":
        logging.info("Evento descartado por corto: %.3f s de actividad", active_duration)
    else:
        logging.error("Evento fallido (%s): %s", status, error)
    return result


def build_stream(config: ActivityConfig, hop_samples: int, hop_bytes: int, hop_seconds: float) -> AudioStream:
    if config.dry_run:
        return DryRunStream(config, hop_samples, hop_seconds)
    return ARecordStream(config, hop_bytes, hop_seconds)


def run_once(config: ActivityConfig) -> tuple[int, str, int]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    hop_samples = max(1, int(round(config.sample_rate * config.hop_ms / 1000.0)))
    hop_seconds = hop_samples / config.sample_rate
    hop_bytes = hop_samples * config.channels * (config.bits // 8)
    window_chunks_count = max(1, int(math.ceil(config.window_ms / config.hop_ms)))
    pre_chunks_count = max(1, int(math.ceil(config.pre_buffer_seconds / hop_seconds)))

    pre_buffer: deque[Chunk] = deque(maxlen=pre_chunks_count + window_chunks_count)
    window_buffer: deque[bytes] = deque(maxlen=window_chunks_count)
    current_event: EventState | None = None
    events_saved = 0
    event_counter = 0
    last_heartbeat = time.monotonic()
    last_dbfs = -240.0

    stream = build_stream(config, hop_samples, hop_bytes, hop_seconds)
    logging.info("Escuchando actividad acustica")

    try:
        for chunk in stream:
            current_free = free_mb(config.output_dir)
            if current_free < config.min_free_mb:
                logging.warning(
                    "Espacio libre insuficiente: %s MB. Minimo configurado: %s MB.",
                    current_free,
                    config.min_free_mb,
                )
                if current_event is not None:
                    save_event(config, current_event, chunk.end_sec, forced_status="cerrado_por_espacio")
                return 0, "sin_espacio", events_saved

            pre_buffer.append(chunk)
            window_buffer.append(chunk.data)
            last_dbfs = pcm16_dbfs(window_buffer)
            active = last_dbfs >= config.threshold_dbfs

            if current_event is None and active:
                event_counter += 1
                pre_chunks = list(pre_buffer)
                start_stream = pre_chunks[0].start_sec if pre_chunks else chunk.start_sec
                seconds_since_event_start = max(0.0, chunk.end_sec - start_stream)
                start_wall = datetime.now() - timedelta(seconds=seconds_since_event_start)
                current_event = EventState(
                    index=event_counter,
                    chunks=[item.data for item in pre_chunks],
                    event_start_stream_sec=start_stream,
                    active_start_stream_sec=chunk.start_sec,
                    last_active_stream_sec=chunk.end_sec,
                    start_wall_time=start_wall,
                    rms_values=[last_dbfs],
                    free_before_mb=current_free,
                )
                logging.info("Actividad detectada: evento %03d, RMS %.2f dBFS", event_counter, last_dbfs)
            elif current_event is not None:
                current_event.chunks.append(chunk.data)
                if active:
                    current_event.last_active_stream_sec = chunk.end_sec
                    current_event.rms_values.append(last_dbfs)

                event_duration = chunk.end_sec - current_event.event_start_stream_sec
                silence_after_activity = chunk.end_sec - current_event.last_active_stream_sec
                should_close = silence_after_activity >= config.post_buffer_seconds
                forced_status = "ok"
                if event_duration >= config.max_event_seconds:
                    should_close = True
                    forced_status = "cerrado_por_duracion_maxima"

                if should_close:
                    result = save_event(config, current_event, chunk.end_sec, forced_status=forced_status)
                    if result.saved:
                        events_saved += 1
                    current_event = None
                    if config.max_events is not None and events_saved >= config.max_events:
                        logging.info("Limite de prueba alcanzado: %s eventos.", config.max_events)
                        return 0, "max_events", events_saved

            now = time.monotonic()
            if now - last_heartbeat >= config.heartbeat_seconds:
                logging.info(
                    "Heartbeat: RMS %.2f dBFS, activo=%s, espacio_libre=%s MB",
                    last_dbfs,
                    "si" if current_event is not None else "no",
                    current_free,
                )
                last_heartbeat = now

        if current_event is not None:
            save_event(config, current_event, current_event.event_start_stream_sec + len(current_event.chunks) * hop_seconds, forced_status="cerrado_por_fin_stream")
    finally:
        return_code, error = stream.close()

    return return_code, error, events_saved


def main() -> int:
    config = parse_args()
    setup_logging(config.output_dir)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    logging.info("Iniciando grabadora por actividad")
    logging.info("Salida: %s", config.output_dir)
    logging.info(
        "Audio: %s Hz, %s canal(es), %s-bit, formato %s",
        config.sample_rate,
        config.channels,
        config.bits,
        config.audio_format,
    )
    logging.info(
        "Detector: umbral %.2f dBFS, ventana %.1f ms, hop %.1f ms, pre %.1f s, post %.1f s",
        config.threshold_dbfs,
        config.window_ms,
        config.hop_ms,
        config.pre_buffer_seconds,
        config.post_buffer_seconds,
    )

    while not STOP_REQUESTED:
        try:
            return_code, error, _events_saved = run_once(config)
        except FileNotFoundError as exc:
            return_code, error = 127, str(exc)
        except Exception as exc:
            return_code, error = 1, repr(exc)

        if STOP_REQUESTED or config.dry_run or config.max_events is not None:
            break
        if return_code == 0 and not error:
            logging.warning("El stream de audio termino sin error; reintentando en %s s.", config.retry_seconds)
        else:
            logging.error("Stream fallo con codigo %s: %s", return_code, error)
        time.sleep(config.retry_seconds)

    logging.info("Grabadora por actividad detenida limpiamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())