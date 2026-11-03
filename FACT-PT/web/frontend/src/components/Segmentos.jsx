/** A segmented control: square options in one bordered row, the pressed one inked. Buttons, not
    radios: they fire no input event, so a choice inside the form does not read as the claim being
    edited. A row wider than the page scrolls inside its frame rather than widening the page. */

export default function Segmentos({ opcoes, valor, aoMudar, rotulo, rotuloId, pequeno = false }) {
  return (
    <div role="group" aria-label={rotulo} aria-labelledby={rotuloId} className={`flex w-fit max-w-full overflow-x-auto border border-divisor ${pequeno ? "" : "h-9"}`}>
      {opcoes.map((opcao) => {
        const activa = opcao.valor === valor;
        return (
          <button
            key={opcao.valor}
            type="button"
            aria-pressed={activa}
            lang={opcao.lang}
            title={opcao.titulo}
            onClick={() => !activa && aoMudar(opcao.valor)}
            className={`flex flex-none items-center whitespace-nowrap tabular-nums transition-colors not-first:border-l not-first:border-divisor focus-visible:-outline-offset-2 ${
              pequeno ? "px-2.5 py-1.5 text-[12px] font-semibold tracking-[.04em]" : "px-3 text-[13px]"
            } ${activa ? "cursor-default! bg-tinta text-fundo" : "hover:bg-pairar"}`}
          >
            {opcao.conteudo ?? opcao.texto}
          </button>
        );
      })}
    </div>
  );
}
