# Fluxo da pipeline de revisão por snowballing

Este documento mostra, passo a passo, como a pipeline transforma um conjunto inicial de 16 artigos em uma tabela final de análise para a revisão sobre robôs sociais e socialmente assistivos (SAR).

A ideia central é cortar e organizar em etapas: cada uma amplia, corta ou organiza o que a anterior trouxe, e as decisões que exigem julgamento (por cluster e por resposta) são humanas.

**Legenda das cores** (estado em 19/11/2026)

| Cor | Significado |
|---|---|
| 🟩 | Implementada |
| 🟨 | Em andamento ou aguardando uma decisão |
| ⬜ | Planejada |
| 🟪 | Etapa manual, feita em conjunto |

## Visão geral

O snowballing segue o método do Wohlin. Cada rodada parte dos selecionados da rodada anterior, faz backward e forward ao mesmo tempo e passa os works novos pela triagem completa. Só os selecionados no texto completo voltam para a rodada seguinte.

```mermaid
flowchart TD
    START[("Rodada 0 · start set<br/>16 DOIs")]:::data
    SEEDS[("seeds da rodada N<br/>selecionados da rodada N-1")]:::data

    E1["<b>Etapa 01 · Coleta</b><br/>backward (referências) e forward (citações)<br/>juntos, OpenAlex + Semantic Scholar<br/>ignora o que já foi visto"]:::done
    E2["<b>Etapa 02 · Corte por título</b><br/>regras regex"]:::done
    E3["<b>Etapa 03 · Abstract e clusters</b><br/>sweep e fit por rodada<br/>decisão humana por cluster"]:::wip
    E4["<b>Etapa 04 · Texto completo</b><br/>download, fila manual (UFLA)<br/>e decisão include/exclude"]:::joint
    SEL[("selected.jsonl<br/>da rodada N")]:::data
    STOP{"algum<br/>selecionado?"}:::done
    E5["<b>Etapa 05 · RAG por pergunta</b><br/>trecho literal e página<br/>para cada pergunta de pesquisa"]:::wip
    E6["<b>Etapa 06 · Supervisão humana</b><br/>sim ou não por resposta<br/>FEITA EM CONJUNTO"]:::joint
    E7["<b>Etapa 07 · Tabela final</b><br/>LLM e estatística em pandas"]:::todo

    START --> SEEDS
    SEEDS --> E1 --> E2 --> E3 --> E4 --> SEL --> STOP
    STOP -->|"sim: rodada N+1"| SEEDS
    STOP -->|"não: convergiu"| E5
    E5 --> E6 --> E7

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

## Etapas 01 e 02: coleta de uma rodada e corte por título

```mermaid
flowchart TD
    SEEDS[("seeds<br/>r(N-1)/selected.jsonl")]:::data --> BW["Backward<br/>referenced_works dos seeds<br/>em lotes de 50 IDs"]:::done
    SEEDS --> FW["Forward<br/>OpenAlex cites: e Semantic Scholar<br/>(DOIs do S2 buscados no OpenAlex)"]:::done
    SEEN[("já vistos<br/>works de todas as rodadas anteriores")]:::data -.-> DEDUP
    BW --> DEDUP["Dedup por ID e DOI<br/>nas duas direções: direction = both"]:::done
    FW --> DEDUP
    DEDUP --> W[("rN/works.jsonl<br/>e hits.jsonl (seed → work)")]:::data
    W --> T{"Etapa 02 · título"}:::done
    T -->|"passed_title ou needs_context"| C[("rN/candidates.jsonl<br/>para a etapa 03")]:::data
    T -->|"excluded_by_title"| X["Descartado, com a<br/>regra do corte registrada"]:::done

    classDef data fill:#e2f0f0,stroke:#0f6b6e,color:#12302f
    classDef done fill:#a5e3cc,stroke:#0f6b6e,color:#12302f
```

## Etapa 03: abstracts e clusters

Os candidatos passam por uma cascata de APIs para recuperar o abstract, sem LLM. Depois são agrupados por tema, e a decisão de incluir ou excluir é tomada por cluster, depois de uma leitura humana. Isso se repete em toda rodada; os números do diagrama são da pipeline anterior (histórico).

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
    HR --> DEC{"Decisão do orientador<br/>quais clusters excluir<br/>(mpnet K=10: saem TEA, idosos em casa,<br/>robótica geral e educação)"}:::done
    DEC -->|"mantidos"| INC[("included.jsonl<br/>749 artigos")]:::data
    DEC -->|"excluídos"| EXC["Fora da revisão"]:::done

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
