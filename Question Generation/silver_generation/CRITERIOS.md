# Critérios de avaliação das perguntas silver

A unidade avaliada é a **pergunta**, não o claim span: um span com três perguntas dá três
avaliações. Cada pergunta recebe quatro vereditos binários — 1 (cumpre) ou 0 (não cumpre).

## 1. Relevância
*A pergunta verifica o claim span — e não informação periférica do artigo.*

Não cumpre (0) quando a pergunta:
- verifica outra coisa do artigo, incluindo uma afirmação vizinha do mesmo discurso;
- verifica o **ato de fala de quem profere a claim** ("X afirmou que...?") em vez do facto;
- é sobre opinião ou intenção em vez de facto verificável;
- **repete uma pergunta irmã** — mesma proposição, mesma evidência, mesma resposta. Nesse
  caso falha a que aparece **depois**; a primeira mantém-se a 1.

Uma pergunta geral emparelhada com outra específica sobre o mesmo span **não** é repetição:
é o padrão que o gold do CLEVER usa. Quando o próprio span é sobre o que alguém disse,
perguntar pelo que essa pessoa disse **é** verificar o facto.

## 2. Fidelidade
*A pergunta mantém-se fiel ao contexto, sem inventar factos, nomes ou números.*

Não cumpre (0) quando a pergunta:
- introduz entidade, número, valor, período ou causa que não está no artigo nem é derivável dele;
- troca o sujeito (uma região por um concelho, um conjunto pelo seu superconjunto);
- muda a grandeza afirmada (de «há X» para «aumentou X»);
- transforma uma parte em todo.

Resolver uma expressão relativa pela data de publicação («hoje», «no ano passado»,
«recentemente») **é fiel**. Um intervalo concreto («entre 2011 e 2015») só é fiel se o artigo
o suportar, direta ou indiretamente. Nomear uma organização onde ir procurar a resposta
(«organizações como o IPCC») não é inventar um facto.

## 3. Clareza / pesquisabilidade
*A pergunta é autocontida: os pronomes estão resolvidos pelos nomes próprios.*

Não cumpre (0) quando sobra «isso», «este», «nós», «lá», «a medida», ou uma instituição
referida **pela função e não pelo nome** («o Governo», «o Ministério da tutela», «o
ministro»). Uma pasta nomeada («o Ministro da Cultura», «o Ministério das Infraestruturas»)
é nome de instituição e cumpre.

## 4. Âncora temporal e local
*A pergunta inclui a data e a região quando são relevantes para a verificação.*

Cumpre (1) quando traz a baliza temporal e/ou o território de que a verificação precisa —
ou quando não são precisos (regra estável, facto intemporal). Não cumpre (0) quando a
verificação exige data (números que mudam, comparações, «continua», «aumentou»,
«recentemente») ou exige o local (facto regional) e a pergunta não o traz.
