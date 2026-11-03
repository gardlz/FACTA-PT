/** Inline icons. Strokes follow `currentColor`. */

const TRACO = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
};

export function SetaEsquerda(props) {
  return <svg {...TRACO} {...props}><path d="m14 6-6 6 6 6" /></svg>;
}

export function SetaDireita(props) {
  return <svg {...TRACO} {...props}><path d="m10 6 6 6-6 6" /></svg>;
}

export function Avancar(props) {
  return <svg {...TRACO} {...props}><path d="M5 12h14" /><path d="m12 5 7 7-7 7" /></svg>;
}

export function Recuar(props) {
  return <svg {...TRACO} {...props}><path d="m12 19-7-7 7-7" /><path d="M19 12H5" /></svg>;
}

export function Fechar(props) {
  return <svg {...TRACO} {...props}><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>;
}

export function Calendario(props) {
  return (
    <svg {...TRACO} strokeWidth={1.7} {...props}>
      <rect x="3" y="5" width="18" height="16" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  );
}

export function Lua(props) {
  return <svg {...TRACO} {...props}><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" /></svg>;
}

export function Sol(props) {
  return (
    <svg {...TRACO} {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

export function Info(props) {
  return <svg {...TRACO} {...props}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 7.5h.01" /></svg>;
}

export function Sair(props) {
  return (
    <svg {...TRACO} {...props}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="M10 17l-5-5 5-5" />
      <path d="M5 12h10" />
    </svg>
  );
}

export function Desfazer(props) {
  return (
    <svg {...TRACO} {...props}>
      <path d="M9 14 4 9l5-5" />
      <path d="M4 9h10a6 6 0 0 1 0 12h-3" />
    </svg>
  );
}

export function Refazer(props) {
  return (
    <svg {...TRACO} {...props}>
      <path d="m15 14 5-5-5-5" />
      <path d="M20 9H10a6 6 0 0 0 0 12h3" />
    </svg>
  );
}

export function Historico(props) {
  return (
    <svg {...TRACO} {...props}>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

export function Lapis(props) {
  return (
    <svg {...TRACO} {...props}>
      <path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z" />
      <path d="m13.5 6.5 4 4" />
    </svg>
  );
}

export function Menu(props) {
  return <svg {...TRACO} {...props}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
}
