"""Runs `gerar_artigos.py` under a CodeCarbon tracker and records its energy use and emissions.

All arguments are passed to the generator unchanged. Each run appends one row to
`dados/carbono/emissoes.csv`, with project name `<short model name>[_sem_gramatica]__<condition>`.

    python geracao/carbono.py --modelo Qwen/Qwen3.5-9B --condicao full
"""

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import gerar_artigos as ga                     # noqa: E402
from codecarbon import OfflineEmissionsTracker    # noqa: E402

PASTA = AQUI.parent / "dados" / "carbono"
FICHEIRO = "emissoes.csv"


def _valor(args, opcao: str, omissao=None):
    if opcao in args and args.index(opcao) + 1 < len(args):
        return args[args.index(opcao) + 1]
    return omissao


def main() -> None:
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(0)
    modelo = _valor(args, "--modelo")
    if not modelo:
        raise SystemExit("uso: carbono.py --modelo <modelo HF> [opções do gerar_artigos.py]")
    condicao = _valor(args, "--condicao", "full")
    # A run without the grammar has its own model folder (`<short name>_sem_gramatica`); its
    # measurement is named the same way.
    curto = ga.nome_curto(modelo) + ("_sem_gramatica" if "--sem_gramatica" in args else "")
    nome = f"{curto}__{condicao}"
    PASTA.mkdir(parents=True, exist_ok=True)
    # Process mode: RAM, and CPU when RAPL is unavailable, are estimated for this process and its
    # children (generator and vLLM engine); RAPL and NVML measure the whole CPU package and GPU.
    medidor = OfflineEmissionsTracker(country_iso_code="PRT", project_name=nome,
                                      output_dir=str(PASTA), output_file=FICHEIRO,
                                      tracking_mode="process", log_level="warning")
    medidor.start()
    codigo = 1
    try:
        # The generator runs in a child process: the vLLM engine (started with spawn) does not
        # start with the tracker in the same process.
        codigo = subprocess.run([sys.executable, str(AQUI / "gerar_artigos.py"), *args]).returncode
    finally:
        emissoes = medidor.stop() or 0.0
        energia = getattr(medidor.final_emissions_data, "energy_consumed", 0.0) or 0.0
        print(f"[carbono] {nome}: {energia:.4f} kWh, {emissoes:.4f} kg CO2eq -> {PASTA / FICHEIRO}",
              flush=True)
    sys.exit(codigo)


if __name__ == "__main__":
    main()
