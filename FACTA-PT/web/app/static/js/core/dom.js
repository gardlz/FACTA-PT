/** Element builders. */

export function el(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto !== undefined && texto !== null) no.textContent = texto;
  return no;
}

export function botao(classe, texto) {
  const no = el("button", classe, texto);
  no.type = "button";
  return no;
}
