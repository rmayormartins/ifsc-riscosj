# RISCO.sj

Painel de apoio à decisão sobre suspensão de aulas por chuva no IFSC Câmpus São José.

Author Ramon Mayor Martins, Ph.D. // [@rmayormartins](https://github.com/rmayormartins) // IFSC SJ - Área de Telecomunicações

**[Abrir o painel](https://rmayormartins.github.io/ifsc-riscosj/)** · **[Modo demonstração](https://rmayormartins.github.io/ifsc-riscosj/?demo=1)** (dados sintéticos, para ver o painel funcionando num dia seco) · [Guia de manutenção](docs/MANUTENCAO.md)

## Para que serve

Em dia de chuva forte, a Direção do câmpus precisa decidir, turno a turno, se mantém as aulas, se flexibiliza a presença ou se suspende as atividades presenciais. As informações que pesam nessa decisão ficam espalhadas: alertas da Defesa Civil, avisos do INMET, chuva medida, previsão, maré, nível dos rios e áreas de risco por onde os estudantes passam.

O RISCO.sj reúne essas fontes numa única página, atualizada a cada 10 minutos, e traduz o conjunto numa recomendação com cinco níveis: **manter aulas**, **manter em atenção**, **flexibilizar**, **suspender o turno** e **suspender todas as atividades presenciais**. O painel não decide sozinho. Ele mostra a recomendação, os números que a sustentam e as regras que pesaram, para que a Direção decida com a mesma base de informação e possa explicar a decisão depois.

## Como funciona

Para cada turno de hoje e de amanhã (matutino, vespertino e noturno, incluindo o tempo de deslocamento antes das aulas), o painel:

1. Lê os **alertas da Defesa Civil** publicados no IDAP, o mesmo canal que dispara o SMS 40199 e o Defesa Civil Alerta, e os **avisos do INMET**.
2. Lê a **chuva medida** nos pluviômetros do CEMADEN e o **nível do rio Maruim** na estação telemétrica da ANA.
3. Busca a **previsão horária** para os municípios de origem dos estudantes, o **conjunto de modelos** ICON, GFS e ECMWF para o câmpus e a **maré prevista**.
4. Cruza tudo com os **setores de risco** de deslizamento e inundação mapeados pelo Serviço Geológico do Brasil.
5. Decide de três formas independentes e consolida o resultado, respeitando o nível do alerta oficial.
6. Estima a **probabilidade de alagamento** em São José a partir da chuva e da maré.
7. Gera o rascunho do comunicado, registra a decisão tomada e, se a Direção quiser, pede um parecer em texto a um modelo de linguagem.

## Fontes de dados

### Já funcionando

| Fonte | O que entra no painel | Atualização |
|---|---|---|
| Defesa Civil (IDAP) | Alertas oficiais à população, com nível (baixo a extremo, Portaria MIDR nº 2.458/2026), vigência, polígono e municípios atingidos | A cada 10 minutos |
| INMET | Avisos meteorológicos amarelo, laranja e vermelho | A cada 10 minutos |
| CEMADEN | Chuva medida nos pluviômetros automáticos, acumulada de 1 a 96 horas | A cada 10 minutos |
| ANA | Nível, vazão e chuva do rio Maruim na estação 84140000 (CGH Pingo de Ouro, São José) | A cada 10 minutos; a estação mede a cada 30 |
| Open-Meteo | Previsão horária por município e conjunto de modelos ICON, GFS e ECMWF | A cada abertura do painel e a cada 10 minutos |
| Open-Meteo Marine | Maré prevista e altura de onda na Baía Norte e no mar aberto | A cada abertura do painel e a cada 10 minutos |
| Serviço Geológico do Brasil (SGB) | Setorização de risco: setores de risco alto e muito alto nos municípios de origem dos estudantes (185 setores em novembro de 2026, 50 deles em São José), com tipologia, grau e pessoas expostas | Conferida toda semana |

### O que falta

| Dado | Para que serve | Com quem | Situação |
|---|---|---|---|
| Registro de ocorrências de alagamento | Calibrar a probabilidade de alagamento com a história real de São José. Até lá, ela usa um modelo de referência e fica fora da decisão | Defesa Civil de São José | Solicitado |
| Cotas de referência do rio Maruim (atenção, alerta e emergência) | Fazer o nível do rio entrar no índice. Hoje o nível aparece no painel, mas não pesa na recomendação | Defesa Civil de São José ou a operadora da estação | Pendente |
| Telemetria do rio Cubatão do Sul | Acompanhar o rio que mais afeta Palhoça e Santo Amaro da Imperatriz. Os dados existem no Rios On-line da Epagri/Ciram, mas não estão abertos para consulta automática | Epagri/Ciram | Pendente |
| Parcela de estudantes por município | Pesar cada município pela quantidade real de estudantes que vêm dele. Hoje os pesos são estimativas | Secretaria Acadêmica do câmpus | Pendente |

O CEMADEN não oferece API de alertas para outras instituições: seus alertas seguem para a Defesa Civil, que os divulga pelo IDAP. Por isso o painel usa do CEMADEN a chuva medida.

Cada alerta é classificado pelo evento e pelo título. Alertas de **chuva** (tempestade, alagamento, inundação, enxurrada, deslizamento, granizo, vendaval) entram no índice. Alertas **costeiros** (ressaca, maré, ventos costeiros) pedem no máximo atenção e entram no modelo de alagamento, porque mar alto dificulta o escoamento quando chove forte. Os demais (temperatura, umidade, geada e afins) são apenas informativos.

## Como a recomendação é calculada

O painel usa três métodos independentes, para que nenhum deles decida sozinho.

- **Índice de risco (IRC, de 0 a 100).** Soma ponderada de cinco perigos: intensidade da chuva, acumulado no turno, chuva dos três dias anteriores (solo encharcado), rajada de vento e alerta oficial. Cada município pesa pela parcela de estudantes que vem dele, e o pior município tem peso extra. Uma parte do índice mede quanto os setores de risco do SGB estão ativados pela chuva prevista.
- **Probabilidade e custo-perda.** A fração de membros do conjunto de modelos acima dos limiares de chuva forte, combinada com a probabilidade associada ao alerta oficial, é comparada com a razão entre o custo de suspender e a perda evitada (método clássico de Thompson e Murphy).
- **Inferência fuzzy.** Um sistema Mamdani com 12 regras escritas em linguagem natural, como "solo encharcado e chuva alta". As regras que mais pesaram aparecem na tela.

A recomendação final é a mediana dos três (ou o mais cauteloso, se a Direção preferir) e nunca fica abaixo do nível pedido pelo alerta oficial da Defesa Civil ou do INMET.

A **probabilidade de alagamento** é estimada por regressão logística com a chuva máxima em 1 hora e em 3 horas, a chuva das 72 horas anteriores e a maré. O painel já traz a ferramenta para calibrar o modelo com o histórico de ocorrências; depois de calibrado, ele passa a entrar no método custo-perda.

O **parecer por modelo de linguagem** é opcional e apenas comenta os números do painel em texto corrido.

Todos os pesos, limiares e regras podem ser consultados e ajustados na seção Configuração do painel, e a seção Método descreve cada cálculo em detalhe.

## Arquitetura

```
GitHub Actions (a cada 10 min)                    GitHub Pages
  coletor/coletar.py                                index.html
    Defesa Civil (IDAP, CAP 1.2)     ──►  dados/alertas.json        ──►  painel no navegador
    INMET (JSON ou RSS + CAP)                                             + Open-Meteo (previsão e conjunto de modelos)
    CEMADEN (pluviômetros)                                                + Open-Meteo Marine (maré)
    ANA (Hidro-WebService)
    SGB (setorização, semanal)       ──►  dados/areas-risco.geojson
                                          dados/historico/ (alertas, chuva e rios, para calibração)
```

O coletor existe por três motivos: os servidores do governo não liberam consulta direta do navegador (CORS), o feed nacional do IDAP tem vários megabytes e não deve ser baixado em cada celular, e as credenciais da ANA ficam guardadas como segredos do repositório. O painel é um único arquivo HTML, sem servidor próprio e sem custo de hospedagem.

## Limitações

- A previsão tem resolução de alguns quilômetros e não representa chuvas muito localizadas.
- A maré prevista inclui a maré astronômica e o efeito da pressão, mas não o empilhamento de água pelo vento; o acréscimo por alerta de ressaca compensa isso de forma aproximada.
- Antes da calibração com ocorrências reais, os números da probabilidade de alagamento são ilustrativos.
- A setorização do SGB cobre os setores de risco alto e muito alto mapeados em campo entre 2014 e 2019; áreas novas ou alteradas depois disso podem não aparecer.
- O agendamento do GitHub Actions pode atrasar alguns minutos em horários de pico.
- O painel apoia a decisão e não substitui os alertas e comunicados oficiais da Defesa Civil.

## Créditos dos dados

Alertas: Defesa Civil (IDAP, Ministério da Integração e do Desenvolvimento Regional) e INMET. Chuva medida: CEMADEN/MCTI. Nível dos rios: ANA. Previsão, conjunto de modelos e maré: [Open-Meteo](https://open-meteo.com) e Open-Meteo Marine (CC BY 4.0). Setorização de risco: Serviço Geológico do Brasil. Mapa: Esri e colaboradores do OpenStreetMap, ou CARTO.

## Manutenção

Publicação, credenciais, ajustes, calibração e diagnóstico estão no [Guia de manutenção](docs/MANUTENCAO.md).

RISCO.sj versão 1.4, 2026. Contato: ramon.mayor@ifsc.edu.br
