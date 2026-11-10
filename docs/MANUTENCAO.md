# Guia de manutenção do RISCO.sj

Este guia reúne o que é preciso para publicar, ajustar e manter o painel. A apresentação do sistema está no [README](../README.md).

1. [Publicar](#1-publicar)
2. [Primeiros ajustes no painel](#2-primeiros-ajustes-no-painel)
3. [Nível dos rios (ANA)](#3-nível-dos-rios-ana)
4. [Áreas de risco (setorização do SGB)](#4-áreas-de-risco-setorização-do-sgb)
5. [Calibrar a probabilidade de alagamento](#5-calibrar-a-probabilidade-de-alagamento)
6. [Detalhes das fontes](#6-detalhes-das-fontes)
7. [Primeira execução e diagnóstico](#7-primeira-execução-e-diagnóstico)
8. [Opções do coletor](#8-opções-do-coletor)
9. [Worker opcional (Cloudflare)](#9-worker-opcional-cloudflare)
10. [Como o índice é calculado](#10-como-o-índice-é-calculado)
11. [Histórico e revisão dos pesos](#11-histórico-e-revisão-dos-pesos)
12. [Operação contínua](#12-operação-contínua)

## 1. Publicar

1. Crie um repositório, por exemplo `ifsc-riscosj`, e envie os arquivos mantendo a estrutura de pastas. A pasta `.github` começa com ponto e fica oculta em muitos exploradores de arquivos; se ela não subir junto, crie o arquivo pelo GitHub em Add file, Create new file, com o nome `.github/workflows/coletar.yml`.
   ```
   index.html
   worker.js                      (opcional)
   README.md
   docs/MANUTENCAO.md
   coletor/coletar.py
   .github/workflows/coletar.yml
   ```
2. Em **Settings, Pages, Build and deployment**, escolha a fonte **GitHub Actions**.
3. Em **Settings, Actions, General, Workflow permissions**, marque **Read and write permissions**. O coletor guarda no repositório o histórico de alertas e a setorização do SGB.
4. Em **Actions, Coletar dados e publicar**, clique em **Run workflow** para a primeira execução. O log mostra uma linha por fonte, com ok ou FALHA e o motivo.
5. O painel fica em `https://rmayormartins.github.io/ifsc-riscosj/`. No topo, a etiqueta **Coletor** mostra há quantos minutos os dados oficiais foram atualizados.
6. Cadastre as credenciais da ANA para o nível dos rios (seção 3).

Depois disso, o workflow roda sozinho a cada 10 minutos e também a cada push na branch `main`. Para ver o painel num dia seco, use `?demo=1` no fim do endereço.

## 2. Primeiros ajustes no painel

Tudo fica em Configuração, no fim da página, e é salvo no navegador. Use Exportar configuração para levar os ajustes para outra máquina.

- **Parcela de estudantes por município.** Os valores iniciais (São José 45%, Palhoça 20%, Florianópolis 20%, Biguaçu 10%, Santo Amaro da Imperatriz 5%) são estimativas. Substitua pelos dados da Secretaria Acadêmica.
- **Horários dos turnos e tempo de deslocamento** (padrão: 1,5 h antes do início).
- **Chave da CARTO Basemaps**, se quiser a base Voyager da CARTO. Sem chave, o mapa usa a base cinza da Esri.
- **Ajuste manual dos alertas.** O padrão é automático. Use o ajuste manual só quando a Direção souber de um alerta que ainda não apareceu (por exemplo, um aviso por telefone da Defesa Civil municipal) ou de um alerta do CEMADEN.

Se adicionar municípios no painel, adicione também no coletor criando `coletor/municipios.json` com a lista (`nome`, `ibge`, `lat`, `lon`). Assim os alertas, os pluviômetros e a setorização desses municípios entram nos arquivos do coletor.

## 3. Nível dos rios (ANA)

### Credenciais

Desde 2023 a ANA entrega os dados telemétricos pelo Hidro-WebService, que exige credenciais gratuitas:

1. Envie e-mail para hidro@ana.gov.br com o assunto `[seu CPF] - Solicitação de acesso à API`, pedindo acesso ao Hidro-WebService para uso em painel institucional do IFSC.
2. Com o identificador e a senha recebidos, crie em **Settings, Secrets and variables, Actions** os secrets `ANA_IDENTIFICADOR` e `ANA_SENHA`.
3. Rode o workflow. No log, a fonte `ana_rios` deve aparecer como ok.

### Estação usada

O coletor lê a estação telemétrica **84140000, CGH Pingo de Ouro (jusante)**, no **rio Maruim**, em São José, operada pela Imaruí e publicada a cada 30 minutos (nível, vazão e chuva). Ela foi escolhida depois de um diagnóstico em 10/11/2026 com as estações telemétricas da Grande Florianópolis:

- as estações do rio Cubatão do Sul acompanhadas pela Sala de Situação ANA/Epagri/Ciram (84100000 Poço Fundo, 84150100 ETA Casan montante e 84150050 Cubatão) e outras operadas pela Epagri ou pela Defesa Civil existem no inventário da ANA, mas não publicam a telemetria nessa API. Os dados delas estão no [Rios On-line](https://ciram.epagri.sc.gov.br/rios-online/) da Epagri/Ciram, que não tem API aberta; o caminho é pedir acesso à Epagri;
- os pluviômetros do CEMADEN também aparecem no inventário sem dados, mas já chegam ao painel pelo próprio CEMADEN;
- com dados na API estão principalmente estações de pequenas centrais hidrelétricas, quase todas fora das rotas dos estudantes. Na região, as mais próximas são a do rio Maruim e a 84180000, no rio Farias, em Antônio Carlos.

### Cotas de referência

O nível só entra no índice com cotas de referência (atenção, alerta e emergência, em cm na régua da estação). Informe em Configuração, Alagamento, maré e rios, ou no arquivo `coletor/rios.json`. Com cotas, o rio acima da cota funciona como alerta para São José e Palhoça no dia de hoje (atenção, flexibilizar ou suspender).

Para incluir outras estações, crie `coletor/rios.json` com a lista (`codigo`, `nome`, `municipio`, `ibges`, `cotas`). Se os horários vierem em UTC, o coletor detecta e corrige; para forçar, defina `ANA_FUSO=utc`.

### Detalhes do serviço

Confirmados no diagnóstico:

- o token vem no campo `tokenautenticacao` da resposta de `OAUth/v1` (há outro campo chamado `token`, que não serve) e vale 60 minutos;
- os parâmetros da série usam os rótulos do Swagger, com acento (`Código da Estação`, `Tipo Filtro Data`, `Data de Busca (yyyy-MM-dd)`, `Range Intervalo de busca`), e não os nomes do exemplo em Java do manual;
- com a data de hoje e `DIAS_2`, a resposta traz as 48 h até a leitura mais recente;
- o servidor alterna respostas 503 e 504, e o coletor tenta de novo nesses casos.

## 4. Áreas de risco (setorização do SGB)

### Como funciona

O coletor baixa sozinho a setorização de risco do Serviço Geológico do Brasil para os municípios de origem dos estudantes e grava o resultado em `dados/areas-risco.geojson`. O painel lê esse arquivo e mostra os setores no mapa, cada um com tipologia, grau de risco e estimativa de pessoas expostas. Não é preciso baixar nem converter nada.

- **Fonte:** o serviço de mapas Setorização de Risco do Geoportal do SGB (`geoportal.sgb.gov.br/server/rest/services/gestaoterritorial/risco/MapServer/0`), que reúne os setores de risco alto e muito alto de todo o país. O coletor consulta pelos códigos IBGE dos municípios e pede o resultado em GeoJSON WGS 84.
- **Frequência:** o coletor baixa na primeira execução, quando a lista de municípios muda e às segundas-feiras entre 6 h e 7 h (horário de Brasília). O arquivo só é regravado, e só gera commit, quando algo mudou no SGB.
- **Falha:** se o SGB não responder, o arquivo anterior continua valendo. Se não houver arquivo nenhum, o painel usa a base inicial com seis áreas em posições aproximadas.
- **Conferir:** no painel, a etiqueta **Áreas de risco** mostra quantos setores foram carregados. No log do workflow e em `dados/alertas.json`, a fonte `sgb_setorizacao` mostra a contagem por município.
- **Forçar ou desligar:** crie em Settings, Secrets and variables, Actions, Variables, a variável `RISCO_SGB`. Com valor `forcar`, cada execução consulta o SGB (rode uma vez e apague a variável). Com valor `0`, o coletor não consulta.

Em novembro de 2026 o serviço tinha 185 setores nos cinco municípios: 50 em São José, 48 em Palhoça, 37 em Biguaçu, 30 em Florianópolis e 20 em Santo Amaro da Imperatriz, levantados entre 2014 e 2019.

### Relatórios e pranchas

Cada setor tem uma prancha com fotos, descrição e sugestão de intervenção. Para consultar:

1. No [RIGEO](https://rigeo.sgb.gov.br), o repositório do SGB, procure "Setorização de áreas em alto e muito alto risco" seguido do nome do município. As revisões de 2018 e 2019 de Santa Catarina têm títulos como "Setorização de áreas em alto e muito alto risco a movimentos de massa, enchentes e inundações: Palhoça, SC".
2. Cada item costuma trazer dois arquivos: `produtos_<municipio>_sc_risco.zip`, com as pranchas em PDF, e `sig_<municipio>_sc_risco.zip`, com os dados vetoriais.
3. O código do setor (por exemplo `SC_SAOJOSE_SR_10_CPRM`) aparece no balão de cada setor no painel e identifica a prancha correspondente.

### Usar outro mapeamento

Para usar um levantamento diferente, como um mapeamento mais recente da Defesa Civil de São José:

1. **Converter para GeoJSON em WGS 84.** Pelo [mapshaper.org](https://mapshaper.org): arraste o `.zip` do shapefile (ou os arquivos `.shp`, `.dbf`, `.shx` e `.prj` juntos). Se tiver um arquivo por município, arraste todos e digite no Console `-merge-layers force`. Se o mapa aparecer fora do lugar, digite `-proj wgs84`. Exporte como GeoJSON. Pelo QGIS: Exportar, Salvar feições como, formato GeoJSON, SRC EPSG:4326. Um `.kmz` é um `.zip`: renomeie, extraia e use o `doc.kml` de dentro.
2. **Importar.** No painel, Configuração, Áreas de risco, Importar GeoJSON ou KML. O painel aceita um arquivo por vez, por isso junte os municípios antes.
3. **Atributos lidos.** Nome: `local`, `nome` ou `bairro`. Município: `munic` ou `municipio`. Tipo: `tipolo_g1`, `tipologia` ou `tipo`. Grau: `grau_risco` ou `grau`. Código: `num_setor` ou `setor`. Sem esses campos, o tipo e o grau são deduzidos do texto de todos os atributos.

O arquivo importado vale só naquele navegador e tem prioridade sobre a setorização do SGB. Descartar o arquivo importado volta à setorização do SGB. Para que um mapeamento próprio valha para todos, defina `RISCO_SGB=0` e substitua `dados/areas-risco.geojson` no repositório pelo seu arquivo.

## 5. Calibrar a probabilidade de alagamento

O painel vem com um modelo de referência de especialista (cerca de 1% num dia seco e 50% com 30 mm/h e 40 mm em 3 h). Ele serve para mostrar o funcionamento e, nesse estado, não entra na decisão. Para calibrar, abra **Calibração do modelo de alagamento**, no fim da página.

1. **Ocorrências.** Escolha um CSV com uma linha por ocorrência e ao menos a coluna `data` (dd/mm/aaaa ou aaaa-mm-dd). Colunas opcionais: `municipio`, para filtrar o município, e `tipo`, para manter só alagamentos, inundações e enxurradas (também aceita códigos COBRADE 1.2). A fonte ideal é o registro de ocorrências da Defesa Civil de São José; eventos com decreto ou reconhecimento federal também aparecem no S2iD. Cada dia com pelo menos uma ocorrência conta como dia com alagamento. Os dias marcados com "Houve alagamento" no Registro de decisões também entram, então o modelo melhora com o uso.
2. **Período.** Use o período em que o registro foi mantido de forma contínua: os dias sem ocorrência dentro dele contam como dias sem alagamento.
3. **Chuva.** A reanálise horária do Open-Meteo é automática, mas suaviza os picos. Os CSVs dos pluviômetros do CEMADEN baixados no Mapa Interativo são mais fiéis.
4. **Maré.** Vem do histórico do Open-Meteo Marine quando ele cobrir o período.
5. **Calibrar.** O painel ajusta uma regressão logística regularizada, faz validação cruzada em 5 partes e mostra a AUC, o escore de Brier e a curva de confiabilidade. Recomenda-se pelo menos uns 20 dias com alagamento; com menos de 5 a calibração não roda.
6. **Usar.** Usar neste navegador aplica o modelo só ali. Para que todos os navegadores usem o modelo calibrado, baixe `modelo-alagamento.json` e envie o arquivo para a pasta `dados/` do repositório. Um modelo escolhido no navegador tem prioridade sobre o do repositório.

Exportar tabela diária baixa o CSV com as variáveis de cada dia, para análise em outra ferramenta. Depois de calibrado, o método custo-perda passa a usar a maior entre a probabilidade de chuva forte e a de alagamento (a opção fica em Configuração, Alagamento, maré e rios).

## 6. Detalhes das fontes

| Fonte | Endereço | Observações |
|---|---|---|
| Defesa Civil (IDAP) | `idapfile.mdr.gov.br/idap/api/rss/cap` | Feed nacional CAP 1.2 |
| INMET | `apiprevmet3.inmet.gov.br/avisos/ativos` | Se falhar, RSS com um CAP por aviso |
| CEMADEN | Dados abertos da rede observacional | JSON com acumulados ou CSV com a série de registros |
| ANA | `www.ana.gov.br/hidrowebservice` | Com credenciais (seção 3) |
| SGB | `geoportal.sgb.gov.br`, serviço Setorização de Risco | Semanal (seção 4) |
| Open-Meteo e Open-Meteo Marine | Consultados direto pelo navegador | Previsão, conjunto de modelos e maré |
| SDC/SC (site) | `defesacivil.sc.gov.br/categoria/alerta/feed/` | Desligado por padrão (seção 8) |

**Nível dos alertas da Defesa Civil.** Vem, nesta ordem, de um parâmetro do CAP que informe o nível, do texto do alerta ou da severidade CAP (Minor: baixo; Moderate: moderado; Severe: severo; Extreme: extremo). O painel mostra de onde o nível foi tirado ao passar o cursor sobre a etiqueta.

**Classes dos alertas.** Cada alerta recebe uma classe, deduzida do evento e do título:

- **chuva**: chuva, tempestade, temporal, alagamento, inundação, enxurrada, deslizamento, granizo, vendaval. Entra no índice, na probabilidade e no piso;
- **costeiro**: ressaca, maré e ventos costeiros. Não conta como alerta de chuva: pede no máximo atenção e soma um acréscimo à maré no modelo de alagamento (0,15, 0,30 ou 0,45 m para moderado, alto ou severo, configurável);
- **outro**: temperatura, umidade, geada, estiagem, incêndio. Só informativo.

Na dúvida, o alerta conta como chuva. A etiqueta da classe aparece ao lado do alerta no painel.

**Pluviômetros do CEMADEN.** Confirmado com dados reais (Itajaí, fevereiro de 2025, do projeto anterior `mapa-risco`):

- o código da estação começa com o código IBGE do município (`420820302A` pertence a 4208203, Itajaí), e é assim que cada estação é associada ao município;
- os CSVs usam `;` como separador e vírgula decimal (`-27,036`);
- a estação manda um registro por hora quando não chove e um a cada 10 minutos durante a chuva; os acumulados somam os registros da janela, e uma janela é descartada se tiver falha de transmissão maior que 2 h ou começar antes do primeiro registro;
- os horários do CEMADEN são tratados como UTC. Se a fonte mudar para horário de Brasília, defina a variável `CEMADEN_FUSO=BR` no workflow.

Se a coleta automática dos pluviômetros falhar, baixe as últimas 72 h no [Mapa Interativo do CEMADEN](https://mapainterativo.cemaden.gov.br/) e use **Importar CSV de pluviômetros** no painel, no bloco do CEMADEN. O painel aplica as mesmas regras do coletor.

**Alertas do CEMADEN.** O órgão informou, em resposta a pedido pela Lei de Acesso à Informação, que não tem API para entregar alertas vigentes a outras instituições. Seus alertas seguem para a Defesa Civil, que os divulga pelo IDAP. Um alerta do CEMADEN conhecido pela Direção entra por ajuste manual.

**Maré.** Open-Meteo Marine, variáveis `sea_level_height_msl` e `wave_height`, no primeiro ponto com dados entre a Baía Norte e o mar aberto a leste da Ilha.

## 7. Primeira execução e diagnóstico

Os formatos do IDAP, do INMET e do CEMADEN não têm documentação pública estável. O coletor foi escrito a partir do padrão CAP 1.2 e de projetos públicos que usam essas fontes, e a confirmação final vem das execuções reais. Para diagnosticar, confira em `dados/alertas.json` (no site publicado):

- `fontes`: estado de cada fonte, com a mensagem de erro quando houver;
- `diagnostico.idap`: os nomes de geocódigo e as severidades encontrados no feed;
- `diagnostico.cemaden_chaves`: os campos do JSON dos pluviômetros;
- `rios`: o nível de cada estação da ANA;
- `diagnostico.ana`: o resultado da autenticação e de cada consulta à ANA (sem token, senha nem identificador);
- `fontes.sgb_setorizacao`: a contagem de setores por município e a data da última atualização.

Se uma fonte mudar de formato, o painel continua funcionando com as demais e com o ajuste manual.

## 8. Opções do coletor

| Variável (Settings, Secrets and variables, Actions) | Efeito |
|---|---|
| `ANA_IDENTIFICADOR`, `ANA_SENHA` (secrets) | Credenciais do Hidro-WebService |
| `RISCO_SGB` | `0` desliga a setorização do SGB; `forcar` consulta em toda execução |
| `RISCO_SDC_SITE` | `1` liga o feed do site da SDC/SC |
| `ANA_FUSO` | `utc` força a conversão dos horários da ANA |
| `CEMADEN_FUSO` | `BR` trata os horários do CEMADEN como horário de Brasília |

- **Feed do site da SDC/SC.** O `robots.txt` do site da Defesa Civil de SC restringe acesso automatizado, então essa fonte vem desligada. Os alertas da SDC/SC já chegam pelo IDAP. Ligue só se a SDC/SC autorizar.
- **Arquivos de configuração.** `coletor/municipios.json` (municípios de origem) e `coletor/rios.json` (estações da ANA e cotas) substituem as listas embutidas no coletor.
- **Pluviômetros a cada 10 minutos.** A Plataforma de Entrega de Dados do CEMADEN (ped.cemaden.gov.br) oferece séries com cadastro e token. É uma melhoria possível; as credenciais iriam como secrets.
- **Rodar localmente.** Com Python 3.10 ou superior: `python coletor/coletar.py`, e depois `python -m http.server` na pasta do projeto. O coletor usa só a biblioteca padrão.

## 9. Worker opcional (Cloudflare)

Com o coletor publicado, o Worker só é necessário para o **parecer por modelo de linguagem** (via Groq). Ele também serve de reserva para os avisos do INMET quando o painel é aberto fora do GitHub Pages.

1. No painel da Cloudflare, Workers & Pages, Create, Worker. Cole o conteúdo de `worker.js` e publique.
2. Em Settings, Variables and Secrets, crie `ALLOWED_ORIGIN` = `https://rmayormartins.github.io`, `GROQ_API_KEY` (como secret) e, se quiser, `GROQ_MODEL`.
3. Copie a URL do Worker para Configuração, Integrações, no painel.

Sem Worker, o botão do parecer permite copiar o prompt e colar no assistente de preferência.

## 10. Como o índice é calculado

- Cada fator vira um perigo entre 0 e 1 por limiares configuráveis: intensidade máxima na janela (20, 30 e 60 mm/h, como nos avisos do INMET), acumulado na janela do turno, chuva das 72 h anteriores (saturação do solo), rajada máxima (40, 60 e 100 km/h) e alerta oficial.
- Nas horas que já passaram, a chuva vem da mediana dos pluviômetros do município; nas horas seguintes, da previsão.
- Perigo do município: soma ponderada dos fatores. Perigo regional: 70% da média ponderada pela parcela de estudantes mais 30% do pior município.
- Exposição: cada setor de risco é ativado pela chuva do seu município (deslizamento responde mais à chuva antecedente; inundação, à intensidade), com peso maior para risco muito alto. A exposição combina a média e o máximo das ativações.
- IRC = 100 × [(1 − λ) × perigo regional + λ × exposição], com λ = 20% por padrão. Alertas oficiais impõem pisos de 25, 50 ou 75 pontos.
- Probabilidade: fração de membros do ensemble acima dos limiares, combinada com a probabilidade associada ao alerta oficial. Suspender é recomendado quando ela passa da razão custo-perda C/L (padrão 0,30).
- Fuzzy: sistema Mamdani com 12 regras legíveis; o painel mostra as regras que mais pesaram.
- Alagamento: regressão logística diária, média sobre os membros do ensemble; entra no custo-perda só depois de calibrada.
- Consolidação: mediana dos três níveis (ou o máximo, se configurado), nunca abaixo do piso do alerta oficial.

## 11. Histórico e revisão dos pesos

Pesos, limiares e probabilidades por alerta são valores iniciais de especialista. O coletor grava em `dados/historico/AAAA-MM.jsonl` cada mudança nos alertas oficiais (com a classe de cada um), a mediana da chuva de 24 h dos pluviômetros por município e o nível dos rios. No painel, o Registro de decisões guarda o que a Direção decidiu, se houve alagamento e a probabilidade de alagamento calculada. Com esses dados, depois de uma temporada de chuvas, os pesos do índice podem ser revistos.

## 12. Operação contínua

- O agendamento do GitHub Actions pode atrasar alguns minutos em horários de pico, e é desativado depois de 60 dias sem atividade no repositório. O arquivo mensal do histórico cria pelo menos um commit por mês, o que mantém o agendamento ativo.
- O feed do IDAP guarda poucas horas de alertas; a coleta a cada 10 minutos cobre isso.
- Avisos do GitHub sobre versões de Node.js ou sobre a imagem `ubuntu-latest` não impedem a coleta. Quando aparecerem versões novas das actions usadas no workflow, basta atualizar o número da versão em `.github/workflows/coletar.yml`.
