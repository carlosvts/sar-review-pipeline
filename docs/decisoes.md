[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Decisões de projeto

- **JSON bruto e JSONL têm papéis diferentes.** O JSON bruto é cache e prova do que a API devolveu. O JSONL traz só os campos úteis ao filtro da etapa 02 e é o formato de trabalho das etapas seguintes.
- **Abstract ausente só exclui quem o título não aprovou.** Um `passed_title` sem abstract segue pelo título e terá o texto completo buscado depois. Um `needs_context` sem abstract em nenhuma fonte sai com `exclusion_reason = "sem_abstract"`, registrado para o PRISMA, porque não há como decidir o contexto dele.
- **A etapa 03 não usa LLM.** A recuperação, a validação e o agrupamento são determinísticos; a decisão de exclusão é humana, por cluster, conferindo os artigos de borda.
- **O ajuste do KMeans usa só quem tem abstract.** Vetores feitos só de título não puxam os centroides; os `title_only` são atribuídos depois, ao centroide mais próximo.
- **`abstract_source` registra a origem de cada abstract**, para que as fontes adicionadas na etapa 03 fiquem rastreáveis.
- **O start set é rebuscado a cada execução; o backward é acumulado.** `load_backward()` carrega do disco as rodadas anteriores, e só os IDs ainda não vistos são buscados.
- **`save()` reescreve os arquivos inteiros.** Por isso, `load_backward()` precisa ser chamado antes de `fetch_backward()` e `save()`: sem ele, o que foi acumulado nas rodadas anteriores é sobrescrito.
- **A etapa 04 pode ser rodada de novo sem refazer trabalho.** Um arquivo válido já baixado não é baixado de novo, o manifesto não toca nas linhas que já existem ao ser gerado, e a extração pula o JSONL que é mais novo que o documento de origem.
- **`status = manual` nunca é sobrescrito.** É o valor para marcar no manifesto um texto recuperado à mão; o download seguinte não altera essa linha.
- **Arquivos são gravados em `.part` e renomeados no final.** Uma queda no meio do download, da extração ou da escrita do manifesto não deixa arquivo corrompido.
- **Texto completo não encontrado nunca significa exclusão.** O work vai para a fila manual, com os links e o motivo da falha de cada candidata.
- **Dentro da fonte `pmc`, o XML é tentado antes do PDF renderizado.** O JATS já traz seções e parágrafos marcados, o que dispensa as heurísticas de layout do PDF.
