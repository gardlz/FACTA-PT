"""Energy and emissions measurement (codecarbon), identical for every regime and model.

Offline tracker with the Portuguese grid factor, per-process tracking restricted to the
GPU in CUDA_VISIBLE_DEVICES (one training process per GPU). A measurement failure never
stops the run. Each run writes `<dir>/<name>.json` with its regime, duration, energy and
emissions, which `resumo_carbono.py` adds up per regime.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

PAIS_ISO = os.environ.get("CODECARBON_COUNTRY_ISO_CODE", "PRT")
INTERVALO_SEGUNDOS = float(os.environ.get("CODECARBON_MEASURE_SECS", "15"))


def _gpu_ids():
    """NVML index(es) of this process's GPU, from CUDA_VISIBLE_DEVICES, or None."""
    valor = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if not valor:
        return None
    try:
        return [int(x) for x in valor.split(",") if x.strip() != ""]
    except ValueError:
        return None


def iniciar(nome: str, pasta) -> object:
    """Start the tracker; None if codecarbon is unavailable or fails to start."""
    try:
        from codecarbon import OfflineEmissionsTracker
    except Exception as e:                                    # noqa: BLE001
        print(f"[carbono] codecarbon indisponível ({type(e).__name__}: {e}); "
              f"a corrida continua sem medição.")
        return None
    try:
        pasta = Path(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        kwargs = dict(
            project_name=nome,
            country_iso_code=PAIS_ISO,
            save_to_file=False,
            measure_power_secs=INTERVALO_SEGUNDOS,
            tracking_mode="process",
            log_level="error",
        )
        gpus = _gpu_ids()
        if gpus is not None:
            kwargs["gpu_ids"] = gpus
        tracker = OfflineEmissionsTracker(**kwargs)
        tracker.start()
        print(f"[carbono] a medir '{nome}' (país={PAIS_ISO}, gpu_ids={gpus}) -> {pasta}")
        return tracker
    except Exception as e:                                    # noqa: BLE001
        print(f"[carbono] não foi possível arrancar a medição ({type(e).__name__}: {e}); "
              f"a corrida continua sem ela.")
        return None


def parar(tracker) -> dict:
    """Stop the tracker and return the emissions, duration and energy ({} if nothing was measured)."""
    if tracker is None:
        return {}
    try:
        emissoes_kg = tracker.stop()
    except Exception as e:                                    # noqa: BLE001
        print(f"[carbono] falha ao parar a medição ({type(e).__name__}: {e}).")
        return {}
    dados = getattr(tracker, "final_emissions_data", None)
    resumo = {"emissoes_kg_co2eq": emissoes_kg}
    for campo in ("duration", "energy_consumed"):
        valor = getattr(dados, campo, None)
        if valor is not None:
            resumo[campo] = valor
    return resumo


@contextmanager
def medir(nome: str, pasta, regime: str):
    """Measure a block and write `<pasta>/<nome>.json` (measurement + regime), even if it fails."""
    tracker = iniciar(nome, pasta)
    try:
        yield
    finally:
        resumo = parar(tracker)
        if resumo:
            resumo["regime"] = regime
            try:
                destino = Path(pasta) / f"{nome}.json"
                destino.write_text(json.dumps(resumo, ensure_ascii=False, indent=2, default=str)
                                   + "\n", encoding="utf-8")
                energia = resumo.get("energy_consumed")
                print(f"[carbono] {nome}: {resumo['emissoes_kg_co2eq']:.6f} kg CO2eq"
                      + (f", {energia:.6f} kWh" if isinstance(energia, (int, float)) else "")
                      + f" -> {destino}")
            except Exception as e:                            # noqa: BLE001
                print(f"[carbono] resumo não gravado ({type(e).__name__}: {e}).")
