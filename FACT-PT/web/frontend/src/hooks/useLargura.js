import { useLayoutEffect, useState } from "react";

/** The element's content width, kept current as it resizes. */
export function useLargura(ref) {
  const [largura, setLargura] = useState(0);
  useLayoutEffect(() => {
    const no = ref.current;
    if (!no) return undefined;
    setLargura(no.clientWidth);
    const observador = new ResizeObserver(() => setLargura(no.clientWidth));
    observador.observe(no);
    return () => observador.disconnect();
  }, [ref]);
  return largura;
}
