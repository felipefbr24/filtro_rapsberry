#!/usr/bin/env python3
"""
Simula deteccion de actividad acustica sobre un dataset de WAV.

No modifica los audios. Calcula RMS por ventanas cortas, detecta eventos con
pre-buffer/post-buffer y genera CSV para comparar umbrales antes de implementar
la grabadora real de Fase 2.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


SUMMARY_FIELDS = [
    "threshold_dbfs",
    "files_total",
    "files_analyzed",
    "files_with_events",
    "files_with_errors",
    "events_total",
    "audio_duration_sec",
    "detected_duration_sec",
    "detected_percent",
    "avg_events_per_file",
]


EVENT_FIELDS = [
    "threshold_dbfs",
    "file",
    "sample_rate",
    "channels",
    "audio_duration_sec",
    "event_index",
    "event_start_sec",
    "event_end_sec",
    "event_duration_sec",
    "active_start_sec",
    "active_end_sec",
    "rms_max_dbfs",
    "rms_mean_dbfs",
    "exported_file",
]


ERROR_FIELDS = ["file", "error"]


@dataclass(frozen=True)
class Config:
    dataset_dir: Path
    output_dir: Path
    thresholds_dbfs: tuple[float, ...]
    export_audio: bool
    export_threshold_dbfs: float
    export_format: str
    max_export_events: int | None
    window_ms: float
    hop_ms: float
    pre_buffer_seconds: float
    post_buffer_seconds: float
    min_event_seconds: float
    max_event_seconds: float
    limit_files: int | None


@dataclass(frozen=True)
class AudioStats:
    relative_path: str
    sample_rate: int
    channels: int
    duration_sec: float
    frame_times: np.ndarray
    frame_dbfs: np.ndarray


@dataclass(frozen=True)
class Event:
    active_start_sec: float
    active_end_sec: float
    event_start_sec: float
    event_end_sec: float
    rms_max_dbfs: float
    rms_mean_dbfs: float

    @property
    def duration_sec(self) -> float:
        return self.event_end_sec - self.event_start_sec


def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="Simula deteccion de actividad acustica en WAV."
    )
    parser.add_argument(
        "dataset_dir",
        type=Path,
        help="Carpeta raiz con audios WAV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("fase_2_actividad_acustica") / "resultados_simulacion",
        help="Carpeta donde se guardaran los CSV.",
    )
    parser.add_argument(
        "--thresholds-dbfs",
        type=float,
        nargs="+",
        default=[-35.0, -30.0, -25.0],
        help="Umbrales a comparar en dBFS.",
    )
    parser.add_argument(
        "--export-audio",
        action="store_true",
        help="Exporta clips de eventos detectados para escucharlos.",
    )
    parser.add_argument(
        "--export-threshold-dbfs",
        type=float,
        default=-30.0,
        help="Umbral usado para exportar clips cuando --export-audio esta activo.",
    )
    parser.add_argument(
        "--export-format",
        choices=["wav", "flac"],
        default="wav",
        help="Formato de los clips exportados.",
    )
    parser.add_argument(
        "--max-export-events",
        type=int,
        default=None,
        help="Limita la cantidad total de clips exportados.",
    )
    parser.add_argument(
        "--window-ms",
        type=float,
        default=250.0,
        help="Tamano de ventana RMS en milisegundos.",
    )
    parser.add_argument(
        "--hop-ms",
        type=float,
        default=125.0,
        help="Salto entre ventanas RMS en milisegundos.",
    )
    parser.add_argument(
        "--pre-buffer-seconds",
        type=float,
        default=3.0,
        help="Segundos que se agregan antes de la actividad detectada.",
    )
    parser.add_argument(
        "--post-buffer-seconds",
        type=float,
        default=5.0,
        help="Segundos que se agregan despues de la actividad detectada.",
    )
    parser.add_argument(
        "--min-event-seconds",
        type=float,
        default=0.5,
        help="Duracion minima de actividad real para aceptar un evento.",
    )
    parser.add_argument(
        "--max-event-seconds",
        type=float,
        default=60.0,
        help="Duracion maxima de cada evento guardado.",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="Limita la cantidad de archivos para pruebas rapidas.",
    )
    args = parser.parse_args()

    if not args.dataset_dir.exists():
        parser.error(f"No existe dataset_dir: {args.dataset_dir}")
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
    if args.limit_files is not None and args.limit_files <= 0:
        parser.error("--limit-files debe ser mayor que 0")
    if args.max_export_events is not None and args.max_export_events <= 0:
        parser.error("--max-export-events debe ser mayor que 0")

    thresholds_set = set(float(v) for v in args.thresholds_dbfs)
    if args.export_audio:
        thresholds_set.add(float(args.export_threshold_dbfs))
    thresholds = tuple(sorted(thresholds_set))
    return Config(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        thresholds_dbfs=thresholds,
        export_audio=args.export_audio,
        export_threshold_dbfs=float(args.export_threshold_dbfs),
        export_format=args.export_format,
        max_export_events=args.max_export_events,
        window_ms=args.window_ms,
        hop_ms=args.hop_ms,
        pre_buffer_seconds=args.pre_buffer_seconds,
        post_buffer_seconds=args.post_buffer_seconds,
        min_event_seconds=args.min_event_seconds,
        max_event_seconds=args.max_event_seconds,
        limit_files=args.limit_files,
    )


def rms_dbfs(samples: np.ndarray) -> float:
    rms = math.sqrt(float(np.mean(samples * samples)))
    return 20.0 * math.log10(max(rms, 1e-12))


def analyze_audio(path: Path, root: Path, config: Config) -> AudioStats:
    data, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    mono = data.mean(axis=1)
    duration_sec = len(mono) / sample_rate if sample_rate else 0.0
    window_samples = max(1, int(sample_rate * config.window_ms / 1000.0))
    hop_samples = max(1, int(sample_rate * config.hop_ms / 1000.0))

    frame_dbfs: list[float] = []
    frame_times: list[float] = []
    if len(mono) == 0:
        frame_dbfs.append(-240.0)
        frame_times.append(0.0)
    else:
        last_start = max(0, len(mono) - window_samples)
        starts = range(0, last_start + 1, hop_samples)
        for start in starts:
            frame = mono[start : start + window_samples]
            if len(frame) < window_samples:
                frame = np.pad(frame, (0, window_samples - len(frame)))
            frame_dbfs.append(rms_dbfs(frame))
            frame_times.append(start / sample_rate)

    return AudioStats(
        relative_path=path.relative_to(root).as_posix(),
        sample_rate=sample_rate,
        channels=data.shape[1],
        duration_sec=duration_sec,
        frame_times=np.asarray(frame_times, dtype=np.float64),
        frame_dbfs=np.asarray(frame_dbfs, dtype=np.float64),
    )


def split_long_event(event: Event, config: Config) -> list[Event]:
    events: list[Event] = []
    cursor = event.event_start_sec
    while cursor < event.event_end_sec:
        chunk_end = min(event.event_end_sec, cursor + config.max_event_seconds)
        events.append(
            Event(
                active_start_sec=max(event.active_start_sec, cursor),
                active_end_sec=min(event.active_end_sec, chunk_end),
                event_start_sec=cursor,
                event_end_sec=chunk_end,
                rms_max_dbfs=event.rms_max_dbfs,
                rms_mean_dbfs=event.rms_mean_dbfs,
            )
        )
        cursor = chunk_end
    return events


def detect_events(stats: AudioStats, threshold_dbfs: float, config: Config) -> list[Event]:
    active = stats.frame_dbfs >= threshold_dbfs
    if not np.any(active):
        return []

    raw_events: list[Event] = []
    indices = np.flatnonzero(active)
    groups: list[tuple[int, int]] = []
    start = int(indices[0])
    previous = int(indices[0])
    for idx in indices[1:]:
        idx = int(idx)
        expected_next_time = stats.frame_times[previous] + config.hop_ms / 1000.0
        if stats.frame_times[idx] <= expected_next_time + 1e-9:
            previous = idx
            continue
        groups.append((start, previous))
        start = idx
        previous = idx
    groups.append((start, previous))

    window_sec = config.window_ms / 1000.0
    for first, last in groups:
        active_start = float(stats.frame_times[first])
        active_end = min(stats.duration_sec, float(stats.frame_times[last]) + window_sec)
        if active_end - active_start < config.min_event_seconds:
            continue
        event_start = max(0.0, active_start - config.pre_buffer_seconds)
        event_end = min(stats.duration_sec, active_end + config.post_buffer_seconds)
        active_dbfs = stats.frame_dbfs[first : last + 1]
        raw_events.append(
            Event(
                active_start_sec=active_start,
                active_end_sec=active_end,
                event_start_sec=event_start,
                event_end_sec=event_end,
                rms_max_dbfs=float(np.max(active_dbfs)),
                rms_mean_dbfs=float(np.mean(active_dbfs)),
            )
        )

    merged_events = merge_overlapping_events(raw_events)
    final_events: list[Event] = []
    for event in merged_events:
        final_events.extend(split_long_event(event, config))
    return final_events


def merge_overlapping_events(events: list[Event]) -> list[Event]:
    if not events:
        return []

    merged: list[Event] = []
    current = events[0]
    for event in events[1:]:
        if event.event_start_sec > current.event_end_sec:
            merged.append(current)
            current = event
            continue
        current = Event(
            active_start_sec=min(current.active_start_sec, event.active_start_sec),
            active_end_sec=max(current.active_end_sec, event.active_end_sec),
            event_start_sec=min(current.event_start_sec, event.event_start_sec),
            event_end_sec=max(current.event_end_sec, event.event_end_sec),
            rms_max_dbfs=max(current.rms_max_dbfs, event.rms_max_dbfs),
            rms_mean_dbfs=(current.rms_mean_dbfs + event.rms_mean_dbfs) / 2.0,
        )
    merged.append(current)
    return merged


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def safe_filename(text: str) -> str:
    keep = []
    for char in text:
        if char.isalnum() or char in "-_.":
            keep.append(char)
        else:
            keep.append("_")
    return "".join(keep).strip("_")[:180] or "audio"


def export_audio_clip(
    source_path: Path,
    output_path: Path,
    event: Event,
    sample_rate: int,
    export_format: str,
) -> None:
    start_sample = max(0, int(round(event.event_start_sec * sample_rate)))
    end_sample = max(start_sample + 1, int(round(event.event_end_sec * sample_rate)))
    data, _sample_rate = sf.read(
        source_path,
        start=start_sample,
        stop=end_sample,
        always_2d=True,
        dtype="float32",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "wav":
        sf.write(output_path, data, sample_rate, subtype="PCM_16")
    else:
        sf.write(output_path, data, sample_rate, format="FLAC")


def main() -> int:
    config = parse_args()
    wav_files = sorted(config.dataset_dir.rglob("*.wav"))
    if config.limit_files is not None:
        wav_files = wav_files[: config.limit_files]

    print(f"Dataset: {config.dataset_dir}")
    print(f"WAV encontrados: {len(wav_files)}")
    print(f"Umbrales: {', '.join(str(v) for v in config.thresholds_dbfs)} dBFS")

    analyzed: list[AudioStats] = []
    error_rows: list[dict[str, object]] = []
    for index, path in enumerate(wav_files, start=1):
        if index == 1 or index % 25 == 0:
            print(f"Analizando {index}/{len(wav_files)}...")
        try:
            analyzed.append(analyze_audio(path, config.dataset_dir, config))
        except Exception as exc:
            error_rows.append({"file": path.as_posix(), "error": repr(exc)})

    event_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    exported_count = 0

    for threshold in config.thresholds_dbfs:
        files_with_events = 0
        events_total = 0
        audio_duration = 0.0
        detected_duration = 0.0

        for stats in analyzed:
            audio_duration += stats.duration_sec
            events = detect_events(stats, threshold, config)
            if events:
                files_with_events += 1
            events_total += len(events)
            detected_duration += sum(event.duration_sec for event in events)

            for event_index, event in enumerate(events, start=1):
                exported_file = ""
                should_export = (
                    config.export_audio
                    and threshold == config.export_threshold_dbfs
                    and (
                        config.max_export_events is None
                        or exported_count < config.max_export_events
                    )
                )
                if should_export:
                    source_path = config.dataset_dir / stats.relative_path
                    threshold_name = str(threshold).replace("-", "m").replace(".", "p")
                    stem = safe_filename(Path(stats.relative_path).with_suffix("").as_posix())
                    exported_name = f"{stem}__evento_{event_index:03d}.{config.export_format}"
                    exported_path = (
                        config.output_dir
                        / "audios_cortados"
                        / f"threshold_{threshold_name}_dbfs"
                        / exported_name
                    )
                    export_audio_clip(
                        source_path,
                        exported_path,
                        event,
                        stats.sample_rate,
                        config.export_format,
                    )
                    exported_file = exported_path.relative_to(config.output_dir).as_posix()
                    exported_count += 1

                event_rows.append(
                    {
                        "threshold_dbfs": threshold,
                        "file": stats.relative_path,
                        "sample_rate": stats.sample_rate,
                        "channels": stats.channels,
                        "audio_duration_sec": round(stats.duration_sec, 3),
                        "event_index": event_index,
                        "event_start_sec": round(event.event_start_sec, 3),
                        "event_end_sec": round(event.event_end_sec, 3),
                        "event_duration_sec": round(event.duration_sec, 3),
                        "active_start_sec": round(event.active_start_sec, 3),
                        "active_end_sec": round(event.active_end_sec, 3),
                        "rms_max_dbfs": round(event.rms_max_dbfs, 2),
                        "rms_mean_dbfs": round(event.rms_mean_dbfs, 2),
                        "exported_file": exported_file,
                    }
                )

        detected_percent = (detected_duration / audio_duration * 100.0) if audio_duration else 0.0
        avg_events = events_total / len(analyzed) if analyzed else 0.0
        summary_rows.append(
            {
                "threshold_dbfs": threshold,
                "files_total": len(wav_files),
                "files_analyzed": len(analyzed),
                "files_with_events": files_with_events,
                "files_with_errors": len(error_rows),
                "events_total": events_total,
                "audio_duration_sec": round(audio_duration, 3),
                "detected_duration_sec": round(detected_duration, 3),
                "detected_percent": round(detected_percent, 2),
                "avg_events_per_file": round(avg_events, 2),
            }
        )

    write_csv(config.output_dir / "resumen_umbral.csv", SUMMARY_FIELDS, summary_rows)
    write_csv(config.output_dir / "eventos_detectados.csv", EVENT_FIELDS, event_rows)
    write_csv(config.output_dir / "errores_lectura.csv", ERROR_FIELDS, error_rows)

    print()
    print("Resumen:")
    for row in summary_rows:
        print(
            f"{row['threshold_dbfs']:>6} dBFS | "
            f"eventos={row['events_total']} | "
            f"archivos_con_eventos={row['files_with_events']}/{row['files_analyzed']} | "
            f"audio_guardado={row['detected_percent']}%"
        )
    print()
    print(f"CSV generados en: {config.output_dir}")
    if config.export_audio:
        print(f"Clips exportados: {exported_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
