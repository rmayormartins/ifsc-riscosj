# RISCO.sj

Painel de apoio à decisão sobre suspensão de aulas por chuva no IFSC Câmpus São José.

Author Ramon Mayor Martins, Ph.D. // [@rmayormartins](https://github.com/rmayormartins) // IFSC SJ - Área de Telecomunicações

## O que o painel faz

Para cada turno de hoje e de amanhã (matutino, vespertino e noturno, incluindo o tempo de deslocamento antes das aulas), o painel:

1. Lê os **alertas da Defesa Civil** publicados no IDAP, o mesmo canal que dispara o SMS 40199 e o Defesa Civil Alerta, com polígono e códigos IBGE.
2. Lê os **avisos do INMET**, a **chuva medida nos pluviômetros do CEMADEN** e o **nível do rio Maruim** na estação telemétrica da ANA.
3. Classifica cada alerta: chuva (entra no índice), costeiro (ressaca e ventos costeiros, que agravam alagamentos) ou informativo (temperatura, umidade e afins, fora do índice).
4. Busca a previsão horária (Open-Meteo) para os municípios de origem dos estudantes, o conjunto de modelos ICON, GFS e ECMWF para o câmpus e a **maré prevista** (Open-Meteo Marine).
5. Cruza tudo com as áreas de risco (deslizamento e inundação).
6. Decide de três formas independentes: índice ponderado (IRC, de 0 a 100), probabilidade com modelo custo-perda e inferência fuzzy. A recomendação final é a mediana dos três e nunca fica abaixo do nível indicado pelo alerta oficial.
7. Estima a **probabilidade de alagamento** em São José por regressão logística (chuva em 1 h, em 3 h e em 72 h, e maré), com uma ferramenta para calibrar o modelo com o histórico de ocorrências.
8. Gera o rascunho do comunicado, registra a decisão tomada e, opcionalmente, pede um parecer em texto a um modelo de linguagem.

## Arquitetura

```
GitHub Actions (a cada 10 min)                 GitHub Pages
  coletor/coletar.py                             index.html
    IDAP (Defesa Civil, CAP 1.2)   ──►  dados/alertas.json  ──►  painel no navegador
    INMET (JSON ou RSS + CAP)                                     + Open-Meteo (previsão e ensemble)
    CEMADEN (pluviômetros)                                        + Open-Meteo Marine (maré)
    ANA (nível dos rios)                dados/modelo-alagamento.json (opcional, gerado pela calibração)
```

O coletor existe por três motivos: os servidores do governo não liberam consulta direta do navegador (CORS), o feed nacional do IDAP tem vários megabytes e não deve ser baixado em cada celular, e credenciais (como as da ANA) ficam guardadas como segredos do repositório.

## Publicar

1. Crie um repositório, por exemplo `ifsc-riscosj`, e envie os arquivos mantendo a estrutura de pastas. A pasta `.github` começa com ponto e fica oculta em muitos exploradores de arquivos; se ela não subir junto, crie o arquivo pelo GitHub em Add file, Create new file, com o nome `.github/workflows/coletar.yml`.
   ```
   index.html
   worker.js                      (opcional)
   README.md
   coletor/coletar.py
   .github/workflows/coletar.yml
   ```
2. Em **Settings, Pages, Build and deployment**, escolha a fonte **GitHub Actions**.
3. Em **Settings, Actions, General, Workflow permissions**, marque **Read and write permissions** (o coletor guarda o histórico de alertas no repositório).
4. Em **Actions, Coletar dados e publicar**, clique em **Run workflow** para a primeira execução. O log mostra uma linha por fonte, com ok ou FALHA e o motivo.
5. O painel fica em `https://rmayormartins.github.io/ifsc-riscosj/`. No topo, a etiqueta **Coletor** mostra há quantos minutos os dados oficiais foram atualizados.
6. Opcional: cadastre as credenciais da ANA para o nível dos rios (veja a seção Nível dos rios).

Depois disso, o workflow roda sozinho a cada 10 minutos e também a cada push na branch `main`.

Para ver o painel funcionando em um dia seco, use o modo demonstração: `https://rmayormartins.github.io/ifsc-riscosj/?demo=1`.

## Primeiros ajustes no painel

Tudo fica em Configuração, no fim da página, e é salvo no navegador. Use Exportar configuração para levar os ajustes para outra máquina.

- **Parcela de estudantes por município.** Os valores iniciais (São José 45%, Palhoça 20%, Florianópolis 20%, Biguaçu 10%, Santo Amaro da Imperatriz 5%) são estimativas. Substitua pelos dados da Secretaria Acadêmica.
- **Horários dos turnos e tempo de deslocamento** (padrão: 1,5 h antes do início).
- **Chave da CARTO Basemaps**, se quiser a base Voyager da CARTO. Sem chave, o mapa usa a base cinza da Esri.
- **Ajuste manual dos alertas.** O padrão é automático. Use o ajuste manual só quando a Direção souber de um alerta que ainda não apareceu (por exemplo, um aviso por telefone da Defesa Civil municipal).

Se adicionar municípios no painel, adicione também no coletor criando `coletor/municipios.json` com a lista (`nome`, `ibge`, `lat`, `lon`). Assim os alertas e pluviômetros desses municípios entram no arquivo.

## Fontes de dados

| Fonte | O que entra | Como |
|---|---|---|
| Defesa Civil (IDAP) | Alertas à população, com nível de baixo a extremo (Portaria MIDR nº 2.458/2026), vigência, polígono e códigos IBGE | Feed nacional CAP 1.2 em `idapfile.mdr.gov.br/idap/api/rss/cap` |
| INMET | Avisos amarelo, laranja e vermelho | `apiprevmet3.inmet.gov.br/avisos/ativos`; se falhar, RSS com um CAP por aviso |
| CEMADEN | Chuva acumulada em 1, 3, 6, 12, 24, 48, 72 e 96 h nos pluviômetros automáticos | Dados abertos da rede observacional (JSON com acumulados ou CSV com a série de registros) |
| ANA | Nível dos rios (cm), variação em 24 h e série de 48 h nas estações telemétricas | Hidro-WebService, com credenciais; sem elas, tenta o serviço público antigo |
| Open-Meteo | Previsão horária e ensemble | Consultado direto pelo navegador |
| Open-Meteo Marine | Nível do mar previsto (maré) e altura de onda | Consultado direto pelo navegador |
| SDC/SC (site) | Publicações da categoria Alerta | Desligado por padrão (veja abaixo) |

Sobre o CEMADEN: o órgão informou, em resposta a pedido pela Lei de Acesso à Informação, que não tem API para entregar alertas vigentes a outras instituições. Seus alertas seguem para a Defesa Civil, que os divulga pelo IDAP. Por isso o painel usa do CEMADEN a chuva medida, e o alerta do CEMADEN só entra por ajuste manual.

Detalhes dos pluviômetros, confirmados com dados reais do CEMADEN (Itajaí, fevereiro de 2025, do projeto anterior `mapa-risco`):

- o código da estação começa com o código IBGE do município (`420820302A` pertence a 4208203, Itajaí), e é assim que cada estação é associada ao município;
- os CSVs usam `;` como separador e vírgula decimal (`-27,036`);
- a estação manda um registro por hora quando não chove e um a cada 10 minutos durante a chuva; os acumulados somam os registros da janela, e uma janela é descartada se tiver falha de transmissão maior que 2 h ou começar antes do primeiro registro;
- os horários do CEMADEN são tratados como UTC. Se a fonte mudar para horário de Brasília, defina a variável `CEMADEN_FUSO=BR` no workflow.

Se a coleta automática dos pluviômetros falhar, baixe as últimas 72 h no [Mapa Interativo do CEMADEN](https://mapainterativo.cemaden.gov.br/) e use **Importar CSV de pluviômetros** no painel, no bloco do CEMADEN. O painel aplica as mesmas regras do coletor.

Cada alerta recebe uma **classe**, deduzida do evento e do título:

- **chuva**: chuva, tempestade, temporal, alagamento, inundação, enxurrada, deslizamento, granizo, vendaval. Entra no índice, na probabilidade e no piso, como antes;
- **costeiro**: ressaca, maré e ventos costeiros. Não conta como alerta de chuva: pede no máximo atenção e soma um acréscimo à maré no modelo de alagamento (0,15, 0,30 ou 0,45 m para moderado, alto ou severo, configurável), porque ressaca e maré alta dificultam o escoamento quando chove forte;
- **outro**: temperatura, umidade, geada, estiagem, incêndio. Só informativo.

Na dúvida, o alerta conta como chuva. A etiqueta da classe aparece ao lado do alerta no painel.

O nível de cada alerta da Defesa Civil vem, nesta ordem, de um parâmetro do CAP que informe o nível, do texto do alerta ou da severidade CAP (Minor: baixo; Moderate: moderado; Severe: severo; Extreme: extremo). O painel mostra de onde o nível foi tirado ao passar o cursor sobre a etiqueta.

## Primeira execução e diagnóstico

Os formatos do IDAP, do INMET e do CEMADEN não têm documentação pública estável. O coletor foi escrito a partir do padrão CAP 1.2 e de projetos públicos que usam essas fontes, e foi testado com arquivos no mesmo formato, mas a confirmação final vem da primeira execução real. Depois dela, confira em `dados/alertas.json` (no site publicado):

- `fontes`: estado de cada fonte, com a mensagem de erro quando houver;
- `diagnostico.idap`: os nomes de geocódigo e as severidades encontrados no feed;
- `diagnostico.cemaden_chaves`: os campos do JSON dos pluviômetros;
- `rios`: o nível de cada estação da ANA, quando as credenciais estiverem configuradas;
- `diagnostico.ana`: o resultado da autenticação e de cada consulta à ANA (sem token, senha nem identificador).

Se uma fonte mudar de formato, o painel continua funcionando com as demais e com o ajuste manual.

## Opções do coletor

- **Feed do site da SDC/SC.** O `robots.txt` do site da Defesa Civil de SC restringe acesso automatizado, então essa fonte vem desligada. Os alertas da SDC/SC já chegam pelo IDAP. Se a SDC/SC autorizar, crie em Settings, Secrets and variables, Actions, Variables, a variável `RISCO_SDC_SITE` com valor `1`.
- **Pluviômetros com dados a cada 10 minutos.** A Plataforma de Entrega de Dados do CEMADEN (ped.cemaden.gov.br) oferece séries com cadastro e token. É uma melhoria possível; as credenciais iriam como segredos do repositório.
- **Rodar localmente.** Com Python 3.10 ou superior: `python coletor/coletar.py`, e depois `python -m http.server` na pasta do projeto.

## Nível dos rios (ANA)

O coletor lê a estação telemétrica **84140000, CGH Pingo de Ouro (jusante)**, no **rio Maruim**, em São José, operada pela Imaruí e publicada no Hidro-WebService da ANA a cada 30 minutos (nível, vazão e chuva). Ela foi escolhida depois de um diagnóstico em 10/11/2026 com as estações telemétricas da Grande Florianópolis:

- as estações do rio Cubatão do Sul acompanhadas pela Sala de Situação ANA/Epagri/Ciram (84100000 Poço Fundo, 84150100 ETA Casan montante e 84150050 Cubatão) e outras operadas pela Epagri ou pela Defesa Civil existem no inventário da ANA, mas não publicam a telemetria nessa API. Os dados delas estão no [Rios On-line](https://ciram.epagri.sc.gov.br/rios-online/) da Epagri/Ciram, que não tem API aberta; o caminho é pedir acesso à Epagri;
- os pluviômetros do CEMADEN também aparecem no inventário sem dados, mas já chegam ao painel pelo próprio CEMADEN;
- com dados na API estão principalmente estações de pequenas centrais hidrelétricas, quase todas fora das rotas dos estudantes. Na região, as mais próximas são a do rio Maruim e a 84180000, no rio Farias, em Antônio Carlos.

Desde 2023 a ANA entrega esses dados pelo Hidro-WebService, que exige credenciais gratuitas:

1. Envie e-mail para hidro@ana.gov.br com o assunto `[seu CPF] - Solicitação de acesso à API`, pedindo acesso ao Hidro-WebService para uso em painel institucional do IFSC.
2. Com o identificador e a senha recebidos, crie em Settings, Secrets and variables, Actions, os secrets `ANA_IDENTIFICADOR` e `ANA_SENHA`.
3. Rode o workflow. No log, a fonte `ana_rios` deve aparecer como ok.

Detalhes do serviço confirmados no diagnóstico: o token vem no campo `tokenautenticacao` da resposta de `OAUth/v1` (há outro campo chamado `token`, que não serve) e vale 60 minutos; os parâmetros da série usam os rótulos do Swagger, com acento (`Código da Estação`, `Tipo Filtro Data`, `Data de Busca (yyyy-MM-dd)`, `Range Intervalo de busca`), e não os nomes do exemplo em Java do manual; com a data de hoje e `DIAS_2`, a resposta traz as 48 h até a leitura mais recente; o servidor alterna respostas 503 e 504, e o coletor tenta de novo nesses casos.

O nível só entra no índice com **cotas de referência** (atenção, alerta e emergência, em cm na régua da estação). Informe em Configuração, Alagamento, maré e rios, ou no arquivo `coletor/rios.json`. Com cotas, o rio acima da cota funciona como alerta para São José e Palhoça no dia de hoje (atenção, flexibilizar ou suspender). Para incluir outras estações, crie `coletor/rios.json` com a lista (`codigo`, `nome`, `municipio`, `ibges`, `cotas`). Se os horários vierem em UTC, o coletor detecta e corrige; para forçar, defina `ANA_FUSO=utc`.

## Probabilidade de alagamento

A seção Probabilidade de alagamento estima a chance de haver alagamento registrado em São José no período do turno, por regressão logística com quatro variáveis medidas na janela: chuva máxima em 1 h, chuva máxima em 3 h, chuva das 72 h anteriores e maré máxima (mais o acréscimo por alerta de ressaca). A chuva vem de cada membro do ensemble, e a probabilidade é a média sobre os membros; nas horas que já passaram, a chuva dos pluviômetros entra quando é maior que a prevista.

O painel vem com um **modelo de referência** de especialista (cerca de 1% num dia seco e 50% com 30 mm/h e 40 mm em 3 h). Ele serve para mostrar o funcionamento e, nesse estado, não entra na decisão. Depois de calibrado, o método custo-perda passa a usar a maior entre a probabilidade de chuva forte e a de alagamento (a opção fica em Configuração, Alagamento, maré e rios).

### Como calibrar

Recomenda-se pelo menos uns 20 dias com alagamento; com menos de 5 a calibração não roda. Os dias marcados com "Houve alagamento" no Registro de decisões também entram, então o modelo melhora com o uso. **Exportar tabela diária** baixa o CSV com as variáveis de cada dia, para análise em outra ferramenta.

## Importar a setorização do SGB

A base inicial traz seis áreas com posição aproximada (pontos citados pela Defesa Civil de São José e trechos da bacia do rio Forquilhas). Para uso oficial:

1. No repositório RIGEO do Serviço Geológico do Brasil (rigeo.sgb.gov.br), procure "Setorização de áreas de risco geológico" de São José e dos municípios vizinhos. Os produtos vêm em shapefile ou KML.
2. Converta para GeoJSON em WGS 84 (EPSG:4326). Pelo [mapshaper.org](https://mapshaper.org): arraste o `.zip` do shapefile e exporte como GeoJSON. Pelo QGIS: Exportar, Salvar feições como, formato GeoJSON, SRC EPSG:4326.
3. No painel, Configuração, Áreas de risco, Importar GeoJSON ou KML.

## Worker opcional (Cloudflare)

Com o coletor publicado, o Worker só é necessário para o **parecer por modelo de linguagem** (via Groq). Ele também serve de reserva para os avisos do INMET quando o painel é aberto fora do GitHub Pages.

1. No painel da Cloudflare, Workers & Pages, Create, Worker. Cole o conteúdo de `worker.js` e publique.
2. Em Settings, Variables and Secrets, crie `ALLOWED_ORIGIN` = `https://rmayormartins.github.io`, `GROQ_API_KEY` (como secret) e, se quiser, `GROQ_MODEL`.
3. Copie a URL do Worker para Configuração, Integrações, no painel.

## Como o índice é calculado

- Cada fator vira um perigo entre 0 e 1 por limiares configuráveis: intensidade máxima na janela (20, 30 e 60 mm/h, como nos avisos do INMET), acumulado na janela do turno, chuva das 72 h anteriores (saturação do solo), rajada máxima (40, 60 e 100 km/h) e alerta oficial.
- Nas horas que já passaram, a chuva vem da mediana dos pluviômetros do município; nas horas seguintes, da previsão.
- Perigo do município: soma ponderada dos fatores. Perigo regional: 70% da média ponderada pela parcela de estudantes mais 30% do pior município.
- IRC = 100 × [(1 − λ) × perigo regional + λ × exposição das áreas de risco], com λ = 20% por padrão. Alertas oficiais impõem pisos de 25, 50 ou 75 pontos.
- Probabilidade: fração de membros do ensemble acima dos limiares, combinada com a probabilidade associada ao alerta oficial. Suspender é recomendado quando ela passa da razão custo-perda C/L (padrão 0,30).
- Fuzzy: sistema Mamdani com 12 regras legíveis; o painel mostra as regras que mais pesaram.
- Alagamento: regressão logística diária, média sobre os membros do ensemble; entra no custo-perda só depois de calibrada.

## Calibração

Pesos, limiares e probabilidades por alerta são valores iniciais de especialista. O coletor grava em `dados/historico/AAAA-MM.jsonl` cada mudança nos alertas oficiais (com a classe de cada um), a mediana da chuva de 24 h dos pluviômetros por município e o nível dos rios. No painel, o Registro de decisões guarda o que a Direção decidiu, se houve alagamento e a probabilidade de alagamento calculada. O modelo de alagamento já tem ferramenta própria de calibração (seção anterior); os pesos do índice podem ser revistos com os mesmos dados depois de uma temporada de chuvas.

## Limitações

- O agendamento do GitHub Actions pode atrasar alguns minutos em horários de pico, e é desativado depois de 60 dias sem atividade no repositório. O arquivo mensal do histórico cria pelo menos um commit por mês.
- O feed do IDAP guarda poucas horas de alertas; a coleta a cada 10 minutos cobre isso.
- A previsão tem resolução de alguns quilômetros e não representa chuvas muito localizadas.
- A maré do Open-Meteo inclui a maré astronômica e o efeito da pressão, mas não o empilhamento de água pelo vento, e tem precisão limitada perto da costa. O acréscimo por ressaca compensa isso de forma aproximada.
- O modelo de alagamento é diário e não representa a drenagem de cada bairro; antes da calibração, seus números são ilustrativos.
- O painel apoia a decisão e não substitui os alertas e comunicados oficiais da Defesa Civil.

## Créditos dos dados

Alertas: Defesa Civil (IDAP, Ministério da Integração e do Desenvolvimento Regional) e INMET. Chuva medida: CEMADEN/MCTI. Nível dos rios: ANA. Previsão, ensemble e maré: [Open-Meteo](https://open-meteo.com) e Open-Meteo Marine (CC BY 4.0). Setorização de risco: Serviço Geológico do Brasil. Mapa: Esri e colaboradores do OpenStreetMap, ou CARTO.

RISCO.sj versão 1.3, 2026. Contato: ramon.mayor@ifsc.edu.br
