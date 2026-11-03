/** Who is behind the project: the names shown on the About page and the institutions in the
    footer. Not translated, so they live here; the roles are keys of `sobre.papeis`, and each
    person's `instituicoes` are ids of `INSTITUICOES`, in the order shown. */

export const INSTITUICOES = [
  { id: "ubi", sigla: "UBI", nome: "Universidade da Beira Interior", url: "https://www.ubi.pt" },
  { id: "up", sigla: "U.Porto", nome: "Universidade do Porto", url: "https://www.up.pt" },
  { id: "inesctec", sigla: "INESC TEC", nome: "Instituto de Engenharia de Sistemas e Computadores, Tecnologia e Ciência", url: "https://www.inesctec.pt" },
  { id: "labcom", sigla: "LabCom", nome: "Laboratório de Comunicação", url: "https://labcom.ubi.pt" },
];

/** In the paper's author order. */
export const EQUIPA = [
  { nome: "Gabriel Lázaro", papel: "mestrado", instituicoes: ["ubi", "inesctec"] },
  { nome: "Rodrigo Silva", papel: "mestrado", instituicoes: ["ubi", "inesctec"] },
  { nome: "Nuno Guimarães", papel: "docente", instituicoes: ["up", "inesctec"] },
  { nome: "João Canavilhas", papel: "docente", instituicoes: ["ubi"] },
  { nome: "Purificação Silvano", papel: "docente", instituicoes: ["up", "inesctec"] },
  { nome: "Ricardo Campos", papel: "docente", instituicoes: ["ubi", "inesctec"] },
  // { nome: "Rodrigo Batista", papel: "mestrado", instituicoes: ["up", "inesctec"] },
];

/** The models behind each step: FACTA-PT's own, published on Hugging Face, and the two the
    article can be written with. The task names are keys of `sobre.modelos.tarefas`. */
export const MODELOS = [
  { tarefa: "perguntas", nome: "AMALIA-9B-0626-DPO + QLoRA", url: "https://huggingface.co/liaad/facta-pt-qg-amalia-9b-0626-dpo" },
  { tarefa: "relevancia", nome: "BERTimbau-base", url: "https://huggingface.co/liaad/facta-pt-relevance-bertimbau-base" },
  { tarefa: "classificacao", nome: "XLM-R-large-XNLI", url: "https://huggingface.co/liaad/facta-pt-cee-xlm-roberta-large-xnli" },
  { tarefa: "artigo", nome: "Gemma 4 (OpenRouter)", url: "https://openrouter.ai/models?q=gemma-4" },
  { tarefa: "artigo", nome: "AMALIA-9B-0626-DPO", url: "https://huggingface.co/amalia-llm/AMALIA-9B-0626-DPO" },
];
