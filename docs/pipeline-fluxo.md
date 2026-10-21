# Fluxo da pipeline de revisão por snowballing

Este documento mostra, passo a passo, como a pipeline transforma um conjunto inicial de 16 artigos em uma tabela final de análise para a revisão sobre robôs sociais e socialmente assistivos (SAR).

A ideia central é cortar e organizar em etapas: cada uma amplia, corta ou organiza o que a anterior trouxe, e as decisões que exigem julgamento (por cluster e por resposta) são humanas.

**Legenda das cores** (estado em 21/10/2026)

| Cor | Significado |
|---|---|
| 🟩 | Implementada |
| 🟨 | Em andamento ou aguardando uma decisão |
| ⬜ | Planejada |
| 🟪 | Etapa manual, feita em conjunto |

## Visão geral

```mermaid
flowchart TD
    START[("start_set_dois.csv<br/>16 DOIs")]:::data

    E1["<b>Etapa 01 · Snowballing</b><br/>busca as referências (backward)<br/>de cada rodada no OpenAlex"]:::done
    E2["<b>Etapa 02 · Corte por título</b><br/>regras regex<br/>registram a regra do corte"]:::done
    CAND[("1.519 candidatos<br/>de 17.110 artigos baixados")]:::data
    E3["<b>Etapa 03 · Abstract e clusters</b><br/>recupera abstracts, agrupa por tema<br/>e a revisão decide por cluster"]:::wip
    INC[("included.jsonl<br/>artigos dos clusters mantidos")]:::data
    E4["<b>Etapa 04 · Texto completo</b><br/>baixa e extrai o texto<br/>só dos incluídos"]:::wip
    TXT[("textos completos<br/>e relatório de cobertura")]:::data
    E5["<b>Etapa 05 · RAG por pergunta</b><br/>trecho literal e página<br/>para cada pergunta de pesquisa"]:::wip
    E6["<b>Etapa 06 · Supervisão humana</b><br/>sim ou não por resposta<br/>FEITA EM CONJUNTO"]:::joint
    E7["<b>Etapa 07 · Tabela final</b><br/>LLM e estatística em pandas"]:::todo

    START --> E1
    E1 --> E2
    E2 -->|"aprovados: suas referências<br/>viram a próxima rodada"| E1
    E2 --> CAND
    CAND --> E3
    E3 --> INC
    INC --> E4
    E4 --> TXT
    TXT --> E5
    E5 --> E6
    E6 --> E7

    classDef data fill:#e2f0f0,stroke:#0f6b6e,color:#12302f
    classDef done fill:#a5e3cc,stroke:#0f6b6e,color:#12302f
    classDef wip fill:#fde9b8,stroke:#b07a00,color:#3d2c00
    classDef todo fill:#e6e3dc,stroke:#8a8578,stroke-dasharray:4 3,color:#2b2a26
    classDef joint fill:#d9d6fa,stroke:#5a4fb0,stroke-dasharray:4 3,color:#1f1a4d
```

As perguntas de pesquisa (QP) que guiam as etapas 05 a 07:

| QP | Tema |
|---|---|
| QP1 | Características físicas e visuais do robô: forma, tamanho, materiais, cor, face |
| QP2 | Modalidades e estratégias de comunicação: fala, voz, gestos, movimento, toque, luz, som |
| QP3 | Emoção, expressividade e personalidade |
| QP4 | Métodos e instrumentos de avaliação da interação |
| QP5 | Questões em aberto e desafios não resolvidos |

## Etapas 01 e 02: snowballing e corte por título

O snowballing roda em rodadas. Em cada uma, o corte por título decide quais artigos seguem: só as referências dos aprovados viram a rodada seguinte. A busca para quando nenhuma rodada traz um artigo novo aprovado.

```mermaid
flowchart TD
    CSV[("start_set_dois.csv<br/>16 DOIs")]:::data --> P["DoiParser<br/>lê os DOIs do CSV"]:::done
    P --> S["OpenAlexSnowballer<br/>busca o start set por DOI<br/>numa única chamada"]:::done
    S --> A["Reconstrói os abstracts<br/>a partir do abstract_inverted_index"]:::done
    A --> R["Coleta os referenced_works<br/>e descarta IDs já vistos"]:::done
    R --> B["Busca backward<br/>em lotes de 50 IDs"]:::done
    B --> T{"Etapa 02 · título<br/>passa nas regras?"}:::done

    RULES["Regras de título<br/>termos específicos de SAR aprovam sozinhos<br/>termos genéricos só com contexto de saúde"]:::data
    RULES -.-> T

    T -->|"passed_title"| R
    T -->|"needs_context"| N["Vira candidato, mas não<br/>puxa novas referências<br/>(o abstract decide depois)"]:::done
    T -->|"excluded_by_title"| X["Descartado, com a<br/>regra do corte registrada"]:::done
    T -->|"nenhum aprovado na rodada"| W["Fim da busca<br/>salva em disco, reescrevendo os arquivos inteiros"]:::done

    W --> RAW[("data/raw<br/>JSON bruto e unresolved_ids")]:::data
    W --> JL[("data/jsonl<br/>um Work por linha")]:::data

    classDef data fill:#e2f0f0,stroke:#0f6b6e,color:#12302f
    classDef done fill:#a5e3cc,stroke:#0f6b6e,color:#12302f
```

## Etapa 03: abstracts e clusters

Os candidatos passam por uma cascata de APIs para recuperar o abstract, sem LLM. Depois são agrupados por tema, e a decisão de incluir ou excluir é tomada por cluster, depois de uma leitura humana.

```mermaid
flowchart TD
    C[("1.519 candidatos")]:::data --> AB["Recupera o abstract em cascata, sem LLM<br/>OpenAlex, Semantic Scholar, Crossref,<br/>Europe PMC e arXiv por título"]:::done
    AB --> V{"abstract válido?<br/>mínimo de 20 palavras,<br/>sem boilerplate"}:::done

    V -->|"sim: 1.201"| EMB["Embedding de título e abstract<br/>SPECTER2"]:::done
    V -->|"não, needs_context: 159"| OUT["Saem, com o motivo<br/>registrado para o PRISMA"]:::done
    V -->|"não, aprovado no título: 159"| TO["Seguem só com o título<br/>(o texto completo vem na Etapa 04)"]:::done

    CMP["Modelos comparados: SPECTER2 (escolhido) e SciNCL,<br/>depois mpnet e Qwen3 como controles de uso geral"]:::data
    CMP -.-> EMB

    EMB --> KM["KMeans esférico (cosseno)<br/>K=10, escolhido pelas curvas<br/>e pela leitura dos clusters"]:::done
    KM --> ASG["Os 159 só com título entram no cluster<br/>do centroide mais próximo do vetor do título"]:::done
    TO --> ASG
    ASG --> CL[("1.360 artigos em 10 clusters")]:::data

    CL --> HR["Revisão humana<br/>nomeia cada cluster lendo os artigos<br/>mais centrais e os de borda"]:::done
    HR --> DEC{"Decisão do orientador<br/>quais clusters excluir"}:::wip
    DEC -->|"mantidos"| INC[("included.jsonl")]:::data
    DEC -->|"excluídos"| EXC["Fora da revisão"]:::wip

    classDef data fill:#e2f0f0,stroke:#0f6b6e,color:#12302f
    classDef done fill:#a5e3cc,stroke:#0f6b6e,color:#12302f
    classDef wip fill:#fde9b8,stroke:#b07a00,color:#3d2c00
```

## Etapa 04: texto completo

Só os artigos incluídos têm o texto completo baixado. As fontes são todas legítimas (APIs, sem scraping), e o relatório final registra a procedência de cada texto.

```mermaid
flowchart TD
    I[("included.jsonl<br/>com as oa_locations de cada artigo")]:::data --> M["Manifesto (manifest.csv)<br/>um registro por artigo"]:::done
    M --> D["Cascata de fontes legítimas<br/>oa_locations do OpenAlex, Europe PMC (XML ou PDF),<br/>Unpaywall e arXiv por título"]:::done
    D --> V{"o conteúdo baixado<br/>é o artigo certo?"}:::done
    V -->|"sim"| X["Extrai o texto<br/>PDF com PyMuPDF, XML do Europe PMC"]:::done
    V -->|"não, ou sem acesso aberto"| Q["Fila manual<br/>(por exemplo, acesso CAFe)"]:::wip
    Q --> X
    X --> TXT[("Texto completo")]:::data
    X --> REP["Relatório de cobertura<br/>com a procedência de cada texto"]:::done

    classDef data fill:#e2f0f0,stroke:#0f6b6e,color:#12302f
    classDef done fill:#a5e3cc,stroke:#0f6b6e,color:#12302f
    classDef wip fill:#fde9b8,stroke:#b07a00,color:#3d2c00
```

## Etapa 05: RAG por pergunta

O RAG não responde às perguntas: ele recupera, em cada artigo, o trecho literal que responde a cada QP e a página, para a supervisão humana conferir.

```mermaid
flowchart TD
    TXT[("Textos completos<br/>dos incluídos")]:::data --> CH["Chunking<br/>divide o texto em trechos,<br/>com teto e mínimo de tamanho"]:::done
    CH --> EM["Embedding dos chunks<br/>Qwen3-Embedding-0.6B<br/>(seção e texto)"]:::done
    EM --> DB[("ChromaDB<br/>similaridade de cosseno")]:::data

    QP["QP1 a QP5<br/>questions.json: sub_queries<br/>e uma instrução por QP"]:::done --> QE["Embedding das queries"]:::done

    QE --> S["Busca, em cada artigo, os chunks<br/>mais próximos de cada QP"]:::wip
    DB --> S
    S --> EXT["Extração por QP<br/>trecho literal que comprova a resposta<br/>e a página"]:::wip
    EXT --> HUM["Etapa 06 · supervisão humana<br/>confere o trecho e a página<br/>sim ou não por resposta"]:::joint

    classDef data fill:#e2f0f0,stroke:#0f6b6e,color:#12302f
    classDef done fill:#a5e3cc,stroke:#0f6b6e,color:#12302f
    classDef wip fill:#fde9b8,stroke:#b07a00,color:#3d2c00
    classDef joint fill:#d9d6fa,stroke:#5a4fb0,stroke-dasharray:4 3,color:#1f1a4d
```
