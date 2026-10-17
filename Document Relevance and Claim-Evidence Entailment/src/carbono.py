"""Energy and CO2eq of a block of computation, measured with CodeCarbon in offline mode.

Each block appends a row to outputs/emissoes/emissions.csv; the totals go into the result
records. A failed measurement leaves the fields as None and never stops a run.
"""

import contextlib
import pathlib
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "outputs/emissoes"
PAIS = "PRT"


class Medicao:
    """Result of one measured block; fields stay None when nothing was measured."""

    def __init__(self, nome):
        self.nome = nome
        self.emissoes_kg = None
        self.energia_kwh = None
        self.segundos = None
        self.motivo = None          # why there is no measurement, when there is none

    def como_dict(self):
        return {"bloco": self.nome, "segundos": self.segundos,
                "emissoes_kg": self.emissoes_kg, "energia_kwh": self.energia_kwh,
                "medido": self.motivo is None, "motivo": self.motivo}

    def __str__(self):
        if self.motivo or self.energia_kwh is None or self.emissoes_kg is None:
            return f"[carbono] {self.nome}: sem medição ({self.motivo or 'sem valores'})"
        return (f"[carbono] {self.nome}: {self.segundos:.0f} s · "
                f"{self.energia_kwh * 1000:.1f} Wh · {self.emissoes_kg * 1000:.2f} g CO2eq")


@contextlib.contextmanager
def medir(nome, saida=SAIDA, pais=PAIS, intervalo=15):
    """Measures the enclosed block; yields a `Medicao` filled in on exit (sampling every 15 s)."""
    m = Medicao(nome)
    t0 = time.time()
    seguidor = None
    try:
        from codecarbon import OfflineEmissionsTracker
        saida = pathlib.Path(saida)
        # the tracker swallows a missing output_dir silently and then records nothing
        saida.mkdir(parents=True, exist_ok=True)
        seguidor = OfflineEmissionsTracker(
            country_iso_code=pais,       # carbon intensity from codecarbon's own tables
            project_name=nome,
            output_dir=str(saida),
            output_file="emissions.csv",
            measure_power_secs=intervalo,
            log_level="error",
            allow_multiple_runs=True,
        )
        seguidor.start()
    except Exception as e:                                  # noqa: BLE001 — never stops a run
        m.motivo = f"{type(e).__name__}: {e}"
        seguidor = None

    try:
        yield m
    finally:
        m.segundos = time.time() - t0
        if seguidor is not None:
            try:
                emissoes = seguidor.stop()
                dados = getattr(seguidor, "final_emissions_data", None)
                # codecarbon swallows errors in start/stop; stop() then returns None
                if emissoes is None or dados is None:
                    m.motivo = ("o codecarbon engoliu um erro no start/stop (o stop() não "
                                "devolveu dados)")
                else:
                    m.emissoes_kg = float(emissoes)
                    m.energia_kwh = float(getattr(dados, "energy_consumed", 0.0) or 0.0)
            except Exception as e:                          # noqa: BLE001
                m.motivo = f"stop: {type(e).__name__}: {e}"
        try:
            print(m, flush=True)
        except Exception:                                   # noqa: BLE001
            pass
