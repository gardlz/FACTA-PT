/** A small drawing of what each step does, animated while it runs (the motion is in index.css,
    under `.ilustracao`): an empty outline while pending, a loop while running, the finished
    picture once done. Decorative: the step's name and line say the same in words. */

const CAIXA = { viewBox: "0 0 160 64", preserveAspectRatio: "xMinYMid meet", "aria-hidden": true, focusable: false };

/** Questions being written, one line after another. */
function Perguntas() {
  const linhas = [120, 96, 110];
  return linhas.map((largura, i) => (
    <g key={i}>
      <rect className="il-q" x="0" y={8 + i * 20} width="8" height="8" />
      <rect className="il-pista" x="16" y={10 + i * 20} width={largura} height="4" />
      <rect className="il-linha" x="16" y={10 + i * 20} width={largura} height="4" style={{ "--atraso": `${i * 0.45}s` }} />
    </g>
  ));
}

// Which of the 2 × 9 news items the scan keeps as relevant.
const RELEVANTES = new Set([1, 4, 5, 10, 12, 16]);

/** A scan across the retrieved news items, keeping the relevant ones. */
function Evidencia() {
  const colunas = 9;
  return (
    <>
      {Array.from({ length: colunas * 2 }, (_, i) => {
        const coluna = i % colunas;
        return (
          <rect
            key={i}
            className={RELEVANTES.has(i) ? "il-doc il-relevante" : "il-doc"}
            x={1 + coluna * 17}
            y={8 + Math.floor(i / colunas) * 26}
            width="12"
            height="20"
            style={{ "--atraso": `${(coluna / colunas) * 1.8}s` }}
          />
        );
      })}
      <rect className="il-scanner" x="0" y="2" width="2" height="60" />
    </>
  );
}

/** Each piece of evidence leaving the line for its side: up supports, down refutes, on it decides nothing. */
function Classificacao() {
  const destinos = ["il-sobe", "il-desce", "il-fica", "il-sobe", "il-fica"];
  return (
    <>
      <rect className="il-eixo" x="0" y="31" width="150" height="2" />
      {destinos.map((destino, i) => (
        <rect key={i} className={`il-ponto ${destino}`} x={10 + i * 28} y="27" width="10" height="10" style={{ "--atraso": `${i * 0.35}s` }} />
      ))}
    </>
  );
}

/** The article being typed: a title, its lines, a citation and the caret. */
function Artigo() {
  const linhas = [
    { y: 4, largura: 92, altura: 7, titulo: true },
    { y: 20, largura: 148, altura: 3 },
    { y: 30, largura: 126, altura: 3 },
    { y: 40, largura: 150, altura: 3 },
    { y: 50, largura: 88, altura: 3 },
  ];
  return (
    <>
      {linhas.map(({ y, largura, altura, titulo }, i) => (
        <g key={i}>
          <rect className="il-pista" x="0" y={y} width={largura} height={altura} />
          <rect
            className={titulo ? "il-linha il-titulo" : "il-linha il-texto"}
            x="0"
            y={y}
            width={largura}
            height={altura}
            style={{ "--atraso": `${i * 0.5}s` }}
          />
        </g>
      ))}
      <rect className="il-citacao" x="131" y="27" width="9" height="9" />
      <rect className="il-cursor" x="92" y="47" width="2" height="9" />
    </>
  );
}

const DESENHOS = { perguntas: Perguntas, evidencia: Evidencia, classificacao: Classificacao, artigo: Artigo };

export default function Ilustracao({ id, estado, className = "" }) {
  const Desenho = DESENHOS[id];
  return (
    <svg {...CAIXA} className={`ilustracao il-${id} ${className}`} data-estado={estado}>
      <Desenho />
    </svg>
  );
}
