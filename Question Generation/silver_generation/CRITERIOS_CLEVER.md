# Critérios de anotação das perguntas (guidelines do CLEVER)

Critérios **complementares** aos do `CRITERIOS.md`. Aqueles perguntam *isto é uma boa
pergunta?*; estes perguntam *isto foi escrito como as anotadoras do CLEVER o teriam escrito?* —
ou seja, se o conjunto de perguntas de um claim span segue o protocolo de anotação que produziu
as perguntas **gold** (as guidelines do CLEVER, no Apêndice A.1 da dissertação).
São coisas diferentes: uma pergunta pode ser relevante, fiel, clara e ancorada e mesmo assim
não ser a pergunta que a guideline mandava escrever.

**A unidade não é a mesma nos quatro critérios, e é isso que os distingue.** Dois são
propriedades do *conjunto* — «pelo menos uma geral e uma específica», «os dois pontos da
comparação» — e não têm resposta possível olhando para uma pergunta sozinha. Os outros dois
são propriedades de *cada pergunta*: numa mesma claim, uma pergunta pode estar centrada no
claim object e a outra desviar-se, uma pode ser neutra e a outra pressupor a resposta.

| # | Critério | *Em inglês* | Unidade | Porquê |
|---|---|---|---|---|
| 1 | Estrutura geral → específica | *general–specific structure* | **conjunto de perguntas / claim span** | Só existe através da relação entre as perguntas. |
| 2 | Aderência ao claim object | *claim-object adherence* | **pergunta a pergunta** | Uma pergunta pode estar centrada no claim object e outra não. |
| 3 | Neutralidade e foco factual | *neutrality and factual focus* | **pergunta a pergunta** | Uma pergunta pode ser neutra e outra enviesada. |
| 4 | Casos especiais | *special-case compliance* | **conjunto / claim span, com subcritérios** | Algumas regras exigem cobertura conjunta, sobretudo comparações. |

**A taxa de cada critério conta-se na unidade em que ele é julgado.** Os critérios 2 e 3
contam-se em **perguntas** — a mesma unidade das quatro métricas do `CRITERIOS.md` —, e os
critérios 1 e 4 em **claim spans**.

## 1. Estrutura geral → específica *(conjunto — a taxa conta-se em claim spans)*
*O conjunto segue a hierarquia pretendida — uma pergunta geral sobre o facto central e uma mais
específica que procura informação factual adicional para o verificar. **Quando o claim span não
admite uma distinção significativa entre geral e específica**, as perguntas devem, em vez disso,
manter-se no facto central sem introduzir paráfrases redundantes.*

Há por isso **dois modos de cumprir**, e o segundo não é um consolo: é o que a guideline manda
fazer quando a claim não tem degrau nenhum a que descer.

### A. Há escada (o caso normal)

Cumpre (1) quando existem no conjunto, em qualquer ordem:

- uma pergunta **geral** — ataca o tema amplo do claim object; tipicamente uma pergunta de
  sim/não sobre se o facto alegado se verifica;
- e uma pergunta **específica** — pede o dado concreto que confirma ou desmente: número,
  data, quantidade, nome da instituição, identificação do documento. Tipicamente aberta
  («Quanto...», «Quando...», «Que...», «Em que posição...»), mas uma fechada que acrescente
  um dado novo também serve.

Com três ou quatro perguntas basta que a escada exista; as restantes não penalizam aqui (mas
continuam sujeitas aos critérios 2 e 3).

### B. O span não admite a distinção

Há claims em que não existe «um degrau abaixo» a que descer, porque o facto central **já é** o
dado. Casos típicos:

- o span afirma um **rácio ou uma proporção** e a verificação são os dois números que o compõem;
- o span **compara duas quantidades** e a verificação são as duas contagens;
- o span dá **a mesma grandeza em duas unidades**;
- o span é tão curto ou tão pobre em contexto que uma segunda pergunta não teria onde se ancorar
  (§3 das guidelines, escassez de contexto).

Cumpre (1) quando as **três** coisas se verificam:

1. o span não admite mesmo a distinção — consegue-se nomear o que faria falta e não existe;
2. as perguntas ficam-se pelo **facto central** do claim object, sem derivar para o contexto;
3. **nenhuma é paráfrase redundante de outra** — cada uma traz informação que as outras não
   trazem.

Esta alínea é sobre o span, não sobre as perguntas. Na dúvida entre «não havia degrau» e
«havia degrau e não foi dado», é a alínea A que decide.

### Não cumpre (0)

- há um degrau possível e ele não foi dado: a «específica» só **reformula** a geral sem pedir
  dado novo — trocar a ordem das palavras, passar de sim/não para «o que...?» ou para «quais
  foram...?» sem acrescentar o que se procura, ou estreitar o âmbito com um qualificador que já
  estava na claim;
- duas perguntas **logicamente equivalentes**: a mesma proposição com a polaridade invertida
  («já tinha tido algum antes?» / «foi a primeira vez?»), em que responder a uma responde à
  outra;
- **paráfrase redundante** — duas perguntas que pedem a mesma informação por outras palavras,
  ainda que o span não admitisse escada. A alínea B **não** salva isto.

## 2. Aderência ao claim object *(pergunta a pergunta — a taxa conta-se em perguntas)*
*A pergunta formula a necessidade de verificação em torno do claim object anotado.*

O claim object é o termo mais específico dentro do claim span, e é ele que as guidelines mandam
privilegiar (etapa 2: «Isolamento do claim object»). É mais estreito do que a **Relevância** do
`CRITERIOS.md`: uma pergunta pode falar da informação certa do span e mesmo assim não girar em
torno do objeto que as anotadoras identificaram como núcleo.

Não cumpre (0) quando a pergunta:

- verifica um elemento do span que não é o claim object — a circunstância, um adjunto, o
  contexto em volta;
- dilui o objeto num tema mais vasto de que ele é só um caso;
- troca o objeto por outro do mesmo span: quando o span traz vários claim objects, cada
  pergunta tem de se atar ao que lhe corresponde;
- deixa por resolver um objeto vago («tivemos», «os mesmos», «isso») sem o substituir pelo que
  ele designa dentro do span.

Cumpre quando o objeto lá está, ainda que reformulado ou desdobrado, e quando a pergunta usa o
claimer, o time ou os links de identidade **ao serviço** do objeto — a guideline permite-o
expressamente («Sempre que o claim object não for suficiente...»). Resolver um objeto vago pelo
conteúdo do span é o que a guideline manda fazer, e cumpre.

## 3. Neutralidade e foco factual *(pergunta a pergunta — a taxa conta-se em perguntas)*
*A pergunta procura o facto sem pressupor o veredito e sem julgar quem o proferiu.*

Junta três regras das guidelines: formulação neutra; imparcialidade independentemente de o
stance ser *Affirm* ou *Refute*; e foco estrito no facto alegado, não na opinião ou crença do
claimer.

Não cumpre (0) quando a pergunta:

- **pressupõe a resposta** — «Porque falhou a medida X?» dá a falha por assente; a forma neutra
  é «Qual foi o resultado da medida X?»;
- carrega o vocabulário avaliativo do claimer sem distância («o desastre», «a promessa
  quebrada», «o descalabro»);
- pergunta pela **opinião, intenção, motivação ou credibilidade** de alguém em vez de por um
  facto («Por que razão X mentiu?», «X tem razão quando diz...?»);
- transforma a verificação num juízo sobre o claimer em vez de sobre o que ele alegou.

Cumpre quando a pergunta é respondível por evidência com «sim», «não» ou um valor, sem que a
redação já tenha escolhido. Uma pergunta fechada de sim/não **não** é enviesada por ser
fechada — o gold do CLEVER é quase todo assim. E quando o próprio facto alegado é um ato de
fala («X disse que...»), perguntar o que X disse **é** perguntar pelo facto.

## 4. Casos especiais *(conjunto, com subcritérios — Cumpre / Não cumpre / Não se aplica)*
*As regras condicionais das guidelines que as outras métricas não cobrem.*

Três condições, verificadas **no claim span** (não na pergunta). Se nenhuma se verificar, o
critério **não se aplica** e o span não entra na taxa deste critério.

| Condição (no claim span) | Resposta exigida (no conjunto de perguntas) |
|---|---|
| A validade do facto **depende de quem o profere** — a claim é sobre a autoridade, a competência, a autoria ou a responsabilidade de um ator, e sem o nome não há o que verificar. | O ator está nomeado nas perguntas. |
| O span faz uma **comparação** — «mais do que», «menos do que», «subiu», «desceu», «do que no ano passado», «do que noutros países», «pela primeira vez desde». | As perguntas permitem obter **os dois** termos da comparação. |
| O span invoca um **estudo, relatório, sondagem, ranking ou documento**. | Alguma pergunta permite chegar ao documento original — nomeia-o, ou pede quem o fez, quando, ou qual. |

Cumpre (1) só quando **todas** as condições que se verificam têm resposta; basta uma falhar
para o span falhar. Não se aplica quando nenhuma se verifica.

Nota sobre o claimer: a condição é «a validade depende de quem o profere», não «há um claimer
anotado» — todo o span tem claimer. Um facto do mundo vale-se por si e a condição não se
verifica; um facto sobre o próprio ator depende dele e verifica-se.

## O que estes critérios não avaliam

Data, região e resolução de pronomes **não se avaliam aqui**: são a **Âncora temporal e local**
e a **Clareza / pesquisabilidade** do `CRITERIOS.md`. Uma pergunta sem baliza temporal falha
lá, não aqui; uma pergunta com «este sistema» por resolver falha lá, não aqui.
