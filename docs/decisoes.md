[README](../README.md) · [Estrutura](estrutura.md) · [Decisões](decisoes.md)

# Decisões de projeto

- **JSON bruto e JSONL têm papéis diferentes.** O JSON bruto é cache e prova do que a API devolveu. O JSONL traz só os campos úteis ao filtro da etapa 02 e é o formato de trabalho das etapas seguintes.
- **Abstract ausente só exclui quem o título não aprovou.** Um `passed_title` sem abstract segue pelo título e terá o texto completo buscado depois. Um `needs_context` sem abstract em nenhuma fonte sai com `exclusion_reason = "sem_abstract"`, registrado para o PRISMA, porque não há como decidir o contexto dele.
- **A etapa 03 não usa LLM.** A recuperação, a validação e o agrupamento são determinísticos; a decisão de exclusão é humana, por cluster, conferindo os artigos de borda.
- **O ajuste do KMeans usa só quem tem abstract.** Vetores feitos só de título não puxam os centroides; os `title_only` são atribuídos depois, ao centroide mais próximo.
- **Exclusão por cluster (14/11/2026): mpnet, cosseno, K=10.** Saem quatro temas: robôs humanoides (NAO) em terapia de crianças com TEA, SAR para idosos em casa e em lares, robótica social geral sem tema específico e robôs sociais na educação de crianças. Na análise original (`results/clustering/mpnet_cosine_k10/`, 1.360 artigos) eles eram os clusters 0, 1, 3 e 9; na execução de 14/11/2026 (`data/cluster/mpnet/cosine/assignments_k10.csv`, 1.357 artigos), que é a usada na seleção, são os clusters 2, 6, 3 e 4. Ficam 749 artigos, que vão para `included.jsonl`, mais os 16 do start set na etapa 04.
- **Cluster se identifica pelo tema, não pelo número.** O fit é determinístico para a mesma entrada, mas a entrada muda entre execuções (as APIs da etapa 03 devolvem abstracts um pouco diferentes: 1.201 válidos na análise original, 1.197 em 14/11/2026). Com outra matriz, o `kmeans_plusplus` parte de outros centros, as fronteiras se deslocam e os rótulos 0 a K-1 são renumerados. Toda decisão por cluster cita o tema e o `assignments_k{K}.csv` de onde vem o número.
- **`abstract_source` registra a origem de cada abstract**, para que as fontes adicionadas na etapa 03 fiquem rastreáveis.
- **O start set é rebuscado a cada execução; o backward é acumulado.** `load_backward()` carrega do disco as rodadas anteriores, e só os IDs ainda não vistos são buscados.
- **`save()` reescreve os arquivos inteiros.** Por isso, `load_backward()` precisa ser chamado antes de `fetch_backward()` e `save()`: sem ele, o que foi acumulado nas rodadas anteriores é sobrescrito.
- **A etapa 04 pode ser rodada de novo sem refazer trabalho.** Um arquivo válido já baixado não é baixado de novo, o manifesto não toca nas linhas que já existem ao ser gerado, e a extração pula o JSONL que é mais novo que o documento de origem.
- **`status = manual` nunca é sobrescrito.** É o valor para marcar no manifesto um texto recuperado à mão; o download seguinte não altera essa linha.
- **Arquivos são gravados em `.part` e renomeados no final.** Uma queda no meio do download, da extração ou da escrita do manifesto não deixa arquivo corrompido.
- **Texto completo não encontrado nunca significa exclusão.** O work vai para a fila manual, com os links e o motivo da falha de cada candidata.
- **Dentro da fonte `pmc`, o XML é tentado antes do PDF renderizado.** O JATS já traz seções e parágrafos marcados, o que dispensa as heurísticas de layout do PDF.
