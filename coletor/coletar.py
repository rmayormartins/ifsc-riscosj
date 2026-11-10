#!/usr/bin/env python3
"""RISCO.sj: coletor de alertas oficiais, pluviômetros, rios e áreas de risco.

Ramon Mayor Martins, IFSC Câmpus São José, Área de Telecomunicações.

Roda no GitHub Actions a cada 10 minutos e grava dados/alertas.json, que o
painel lê do próprio site (sem CORS e sem expor credenciais). Usa somente a
biblioteca padrão do Python 3.10 ou superior.

Fontes
  Defesa Civil  Feed nacional do IDAP em CAP 1.2 (alertas enviados pelas
                Defesas Civis por SMS 40199, cell broadcast e outros canais)
  INMET         Avisos ativos em JSON; se falhar, RSS com um CAP por aviso
  CEMADEN       Pluviômetros da rede observacional (dados abertos)
  Rios (ANA)    Nível dos rios nas estações telemétricas da ANA (Hidro-WebService,
                com credenciais em ANA_IDENTIFICADOR e ANA_SENHA; sem elas, tenta o
                serviço público antigo)
  SDC/SC site   Feed RSS da categoria Alerta do site da SDC/SC (desligado por
                padrão; ligue com RISCO_SDC_SITE=1 depois de confirmar com a SDC/SC)
  SGB           Setorização de risco (setores de risco alto e muito alto) dos
                municípios da região, gravada em dados/areas-risco.geojson; consulta
                semanal, desligue com RISCO_SGB=0 ou force com RISCO_SGB=forcar

Cada alerta recebe uma classe: chuva (entra no índice), costeiro (ressaca e
ventos costeiros, que agravam alagamentos junto com chuva e maré alta) ou
outro (temperatura, umidade e afins, só informativos).

Uso
  python coletor/coletar.py --saida dados/alertas.json --historico dados/historico
  python coletor/coletar.py --offline pasta_com_mapa_json   (testes, sem rede)
"""

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

VERSAO = '1.4.0'
TZ_BR = timezone(timedelta(hours=-3))
UA = 'RISCO.sj/1.0 (IFSC Campus Sao Jose; painel de apoio a decisao; https://rmayormartins.github.io)'

# Municípios monitorados. Para mudar sem editar o código, crie coletor/municipios.json
# com a mesma estrutura (lista de objetos com nome, ibge, lat e lon).
MUNICIPIOS = [
    {'nome': 'São José', 'ibge': '4216602', 'lat': -27.6085, 'lon': -48.6333},
    {'nome': 'Palhoça', 'ibge': '4211900', 'lat': -27.6449, 'lon': -48.6697},
    {'nome': 'Florianópolis', 'ibge': '4205407', 'lat': -27.5954, 'lon': -48.5480},
    {'nome': 'Biguaçu', 'ibge': '4202305', 'lat': -27.4977, 'lon': -48.6521},
    {'nome': 'Santo Amaro da Imperatriz', 'ibge': '4215703', 'lat': -27.6860, 'lon': -48.7790},
]
# Recorte da Grande Florianópolis: alertas cujo polígono toca esta caixa entram no
# arquivo mesmo sem casar com a lista acima, para o painel conferir com os municípios dele.
CAIXA = {'lat_min': -28.05, 'lat_max': -27.25, 'lon_min': -49.10, 'lon_max': -48.30}
RAIO_PLUVIOMETRO_KM = 12

URL_IDAP = 'https://idapfile.mdr.gov.br/idap/api/rss/cap'
URL_INMET_JSON = 'https://apiprevmet3.inmet.gov.br/avisos/ativos'
URL_INMET_RSS = 'https://apiprevmet3.inmet.gov.br/avisos/rss'
URLS_CEMADEN = [
    'https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=SC',
    'http://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf=SC',
    'https://resources.cemaden.gov.br/dados/311_24.json',
]
URL_SDC_FEED = 'https://www.defesacivil.sc.gov.br/categoria/alerta/feed/'
URL_ANA_WS = 'https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas'
URL_ANA_ANTIGA = 'https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos'
URL_SGB_SETORES = 'https://geoportal.sgb.gov.br/server/rest/services/gestaoterritorial/risco/MapServer/0/query'

# Estações fluviométricas telemétricas com dados no Hidro-WebService da ANA. A 84140000 fica no
# rio Maruim, em São José (CGH Pingo de Ouro, jusante, operada pela Imaruí), com leitura a cada
# 30 min. As estações do rio Cubatão do Sul (84100000 Poço Fundo e 84150100 ETA Casan, da Epagri)
# não publicam a telemetria nessa API (diagnóstico de 10/11/2026). Para trocar ou incluir estações
# e informar as cotas de atenção, alerta e emergência em cm, crie coletor/rios.json.
RIOS = [
    {'codigo': '84140000', 'nome': 'Rio Maruim na CGH Pingo de Ouro (jusante)', 'municipio': 'São José',
     'ibges': ['4216602', '4211900'], 'lat': -27.5808, 'lon': -48.73, 'cotas': None},
]

OFFLINE = None  # dict url -> caminho, usado nos testes
REF_CEMADEN = None  # instante de referência dos acumulados (padrão: agora)


# ---------------------------------------------------------------- utilidades
def agora():
    return datetime.now(TZ_BR)


def norm(s):
    s = unicodedata.normalize('NFD', str(s or ''))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s.lower()).strip()


def iso(dt):
    return dt.astimezone(TZ_BR).isoformat(timespec='minutes') if dt else None


def ler_data(s):
    """Converte datas CAP/ISO/RFC 822 para datetime com fuso."""
    if not s:
        return None
    if isinstance(s, (int, float)) or re.fullmatch(r'\d{10,13}', str(s).strip()):
        v = float(s)
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
    s = str(s).strip()
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=TZ_BR)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})(?:\D+(\d{2}):(\d{2}))?', s)
    if m:
        d, mo, a, h, mi = m.groups()
        return datetime(int(a), int(mo), int(d), int(h or 0), int(mi or 0), tzinfo=TZ_BR)
    return None


def baixar(url, timeout=60, limite=80_000_000, tentativas=3, cabecalhos=None):
    if OFFLINE is not None:
        caminho = OFFLINE.get(url) or OFFLINE.get(url.split('?')[0])
        if not caminho:
            raise urllib.error.URLError('sem fixture para ' + url)
        with open(caminho, 'rb') as f:
            return f.read()
    ultimo = None
    for t in range(tentativas):
        try:
            h = {'User-Agent': UA, 'Accept': '*/*', 'Accept-Encoding': 'gzip'}
            h.update(cabecalhos or {})
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = r.read(limite + 1)
                if len(dados) > limite:
                    raise ValueError('resposta maior que o limite de %d bytes' % limite)
                if (r.headers.get('Content-Encoding') or '').lower() == 'gzip':
                    dados = gzip.decompress(dados)
                return dados
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code in (400, 401, 403, 404, 410):
                break
            espera = 5 * (t + 1) if e.code == 429 else 2 * (t + 1)
            time.sleep(espera)
        except Exception as e:  # noqa: BLE001 (rede é imprevisível)
            ultimo = e
            time.sleep(2 * (t + 1))
    raise ultimo


def xml_seguro(dados):
    inicio = dados[:20000].lower()
    if b'<!doctype' in inicio or b'<!entity' in inicio:
        raise ValueError('XML com DOCTYPE ou ENTITY recusado')
    return ET.fromstring(dados)


def num(v):
    """Número que aceita vírgula decimal (os CSVs do CEMADEN usam -27,036)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(' ', '')
    if not t:
        return None
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.')
    else:
        t = t.replace(',', '.')
    try:
        return float(t)
    except ValueError:
        return None


def ler_tabela(dados):
    """Aceita JSON, JSONP ou CSV com cabeçalho (separador ; ou ,)."""
    try:
        return json_ou_jsonp(dados)
    except (json.JSONDecodeError, ValueError):
        pass
    texto = dados.decode('utf-8-sig', 'replace').strip()
    linhas = [l for l in texto.splitlines() if l.strip()]
    if len(linhas) < 2:
        raise ValueError('conteúdo não é JSON nem CSV')
    sep = ';' if linhas[0].count(';') >= linhas[0].count(',') else ','
    cab = [c.strip().strip('"') for c in linhas[0].split(sep)]
    return [dict(zip(cab, [c.strip().strip('"') for c in l.split(sep)])) for l in linhas[1:]]


def json_ou_jsonp(dados):
    texto = dados.decode('utf-8', 'replace').strip().lstrip('﻿')
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.match(r'^[\w.$]*\s*\((.*)\)\s*;?\s*$', texto, re.S)
        if m:
            return json.loads(m.group(1))
        raise


def txt(el, nome):
    e = el.find('{*}' + nome)
    return (e.text or '').strip() if e is not None and e.text else ''


def limpar_html(s, maximo=700):
    s = re.sub(r'<[^>]+>', ' ', s or '')
    s = re.sub(r'&nbsp;', ' ', s)
    s = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), s)
    s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) <= maximo else s[:maximo - 1].rstrip() + '…'


def dist_km(a, b, c, d):
    r = math.pi / 180
    x = (d - b) * r * math.cos((a + c) / 2 * r)
    y = (c - a) * r
    return 6371 * math.hypot(x, y)


# ---------------------------------------------------------------- geometria
def ler_poligono(s):
    pts = []
    for par in (s or '').split():
        partes = par.split(',')
        if len(partes) >= 2:
            try:
                pts.append((float(partes[0]), float(partes[1])))
            except ValueError:
                pass
    return pts


def pares_de_numeros(s):
    """Lê pares de coordenadas de um texto qualquer e decide a ordem lat/lon."""
    nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', str(s))]
    pts = []
    for i in range(0, len(nums) - 1, 2):
        a, b = nums[i], nums[i + 1]
        if abs(a) <= 35 and abs(b) > 35:
            pts.append((a, b))
        elif abs(b) <= 35 and abs(a) > 35:
            pts.append((b, a))
    return pts


def dentro(lat, lon, poli):
    n, c = len(poli), False
    j = n - 1
    for i in range(n):
        yi, xi = poli[i]
        yj, xj = poli[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            c = not c
        j = i
    return c


def toca_caixa(poli):
    if not poli:
        return False
    la = [p[0] for p in poli]
    lo = [p[1] for p in poli]
    return not (max(la) < CAIXA['lat_min'] or min(la) > CAIXA['lat_max'] or max(lo) < CAIXA['lon_min'] or min(lo) > CAIXA['lon_max'])


def simplificar(poli, maximo=300):
    if len(poli) <= maximo:
        return [[round(a, 4), round(b, 4)] for a, b in poli]
    passo = len(poli) / maximo
    return [[round(poli[int(i * passo)][0], 4), round(poli[int(i * passo)][1], 4)] for i in range(maximo)]


# ---------------------------------------------------------------- casamento
def regex_municipio(nome):
    # evita casar "São José" com "São José do Cedro", "dos Ausentes", "do Cerrito"
    return re.compile(r'(^|[^a-z])' + re.escape(norm(nome)) + r'(?!\s+d[aoe]s?\s)([^a-z]|$)')


def municipios_atingidos(areas, texto_extra=''):
    hits = set()
    textos = norm(' '.join([a['desc'] for a in areas] + [texto_extra]))
    codigos = set()
    for a in areas:
        for _, v in a['geocodes']:
            codigos.add(re.sub(r'\D', '', v))
    for m in MUNICIPIOS:
        ib = m['ibge']
        if ib in codigos or ib[:6] in codigos:
            hits.add(ib)
            continue
        if any(dentro(m['lat'], m['lon'], p) for a in areas for p in a['poligonos']):
            hits.add(ib)
            continue
        if regex_municipio(m['nome']).search(textos):
            hits.add(ib)
    return sorted(hits)


# ---------------------------------------------------------------- CAP 1.2
def ler_cap(alert):
    d = {k: txt(alert, k) for k in ('identifier', 'sender', 'sent', 'status', 'msgType', 'scope', 'references')}
    infos = []
    for inf in alert.findall('{*}info'):
        params = {}
        for p in inf.findall('{*}parameter'):
            params[txt(p, 'valueName')] = txt(p, 'value')
        areas = []
        for ar in inf.findall('{*}area'):
            polis = [ler_poligono(pe.text) for pe in ar.findall('{*}polygon')]
            geos = [(txt(g, 'valueName'), txt(g, 'value')) for g in ar.findall('{*}geocode')]
            areas.append({'desc': txt(ar, 'areaDesc'), 'poligonos': [p for p in polis if len(p) >= 3], 'geocodes': geos})
        campos = ('language', 'category', 'event', 'urgency', 'severity', 'certainty', 'effective', 'onset',
                  'expires', 'senderName', 'headline', 'description', 'instruction', 'web')
        info = {k: txt(inf, k) for k in campos}
        info['params'] = params
        info['areas'] = areas
        infos.append(info)
    pt = [i for i in infos if i['language'].lower().startswith('pt')]
    d['info'] = (pt or infos or [None])[0]
    return d


NIVEIS_DC = [('extremo', 5), ('muito alto', 4), ('severo', 4), ('alto', 3), ('moderado', 2), ('medio', 2), ('baixo', 1)]
SEVERIDADE_DC = {'minor': 1, 'moderate': 2, 'severe': 4, 'extreme': 5, 'unknown': 2}


def nivel_dc(info):
    """Nível na escala da Portaria MIDR 2.458/2026 (1 baixo a 5 extremo)."""
    for k, v in info['params'].items():
        t = norm(k + ' ' + v)
        if re.search(r'nivel|grau|level|severidade', t):
            for palavra, n in NIVEIS_DC:
                if re.search(r'\b' + palavra + r'\b', norm(v)):
                    return n, 'parâmetro ' + k
    t = norm(info['headline'] + ' ' + info['event'])
    m = re.search(r'\b(nivel|alerta|risco|grau)\s*:?\s*(de\s+)?(extremo|muito alto|severo|alto|moderado|medio|baixo)\b', t)
    if m:
        return dict(NIVEIS_DC)[m.group(3)], 'texto do alerta'
    return SEVERIDADE_DC.get(info['severity'].lower(), 2), 'severidade CAP ' + (info['severity'] or 'ausente')


def nivel_inmet(texto, severidade=''):
    t = norm(texto)
    if 'grande perigo' in t:
        return 3
    if 'perigo potencial' in t:
        return 1
    if 'perigo' in t:
        return 2
    return {'minor': 1, 'moderate': 1, 'severe': 2, 'extreme': 3}.get(severidade.lower(), 1)


RE_CHUVA = re.compile(r'chuv|tempest|tempora|alag|inund|enchent|enxurr|desliz|movimento de massa|granizo|ciclone|vendaval|tornado|\braios?\b')
RE_COSTEIRO = re.compile(r'ressaca|costeir|\bmare\b|agitacao (do )?mar|ondas? (alta|grande)|erosao costeira')
RE_OUTRO = re.compile(r'temperatura|\bfrio\b|calor|geada|umidade|estiagem|\bseca\b|incendio|queimada|\bneve\b|nevoeiro|qualidade do ar|fumaca|poeira')


def classe_alerta(*textos):
    """chuva (conta no índice), costeiro (alimenta o módulo de alagamento) ou outro (informativo)."""
    t = norm(' '.join(str(x) for x in textos if x))
    if RE_CHUVA.search(t):
        return 'chuva'
    if RE_COSTEIRO.search(t):
        return 'costeiro'
    if RE_OUTRO.search(t):
        return 'outro'
    return 'chuva'  # na dúvida, conta (lado conservador)


def resumo_alerta(cap, fonte, nivel, origem_nivel, hits):
    i = cap['info']
    polis, geos = [], set()
    for a in i['areas']:
        polis.extend(simplificar(p) for p in a['poligonos'] if toca_caixa(p) or hits)
        for _, v in a['geocodes']:
            v = re.sub(r'\D', '', v)
            if v.startswith('42'):
                geos.add(v)
    return {
        'fonte': fonte,
        'id': cap['identifier'],
        'remetente': i['senderName'] or cap['sender'],
        'evento': i['event'],
        'classe': classe_alerta(i['event'], i['headline']),
        'nivel': nivel,
        'nivel_origem': origem_nivel,
        'severidade': i['severity'],
        'urgencia': i['urgency'],
        'titulo': limpar_html(i['headline'], 240),
        'descricao': limpar_html(i['description']),
        'instrucao': limpar_html(i['instruction'], 400),
        'inicio': iso(ler_data(i['onset'] or i['effective'] or cap['sent'])),
        'fim': iso(ler_data(i['expires'])),
        'areas': limpar_html('; '.join(a['desc'] for a in i['areas'] if a['desc']), 400),
        'ibges': hits,
        'geocodes': sorted(geos)[:200],
        'poligonos': polis[:12],
    }


def alertas_cap_de_feed(raiz, buscar_links=False, limite_links=60):
    alertas = list(raiz.iterfind('.//{*}alert'))
    if alertas or not buscar_links:
        return alertas, 0
    baixados = 0
    for entrada in list(raiz.iterfind('.//{*}entry')) + list(raiz.iterfind('.//{*}item')):
        if baixados >= limite_links:
            break
        link = ''
        for l in entrada.findall('{*}link'):
            link = l.get('href') or (l.text or '').strip() or link
        if not link:
            continue
        try:
            sub = xml_seguro(baixar(link, timeout=30, tentativas=2))
            alertas.extend(sub.iterfind('.//{*}alert') if sub.tag.split('}')[-1] != 'alert' else [sub])
            baixados += 1
            time.sleep(0.3)
        except Exception:  # noqa: BLE001
            continue
    return alertas, baixados


def filtrar_caps(alertas, fonte, func_nivel, momento):
    cancelados, vistos, saida, diag = set(), set(), [], {'valueNames': set(), 'severidades': {}}
    caps = []
    for el in alertas:
        cap = ler_cap(el)
        if cap['info'] is None:
            continue
        if cap['msgType'].lower() == 'cancel':
            for ref in cap['references'].split():
                cancelados.add(ref.split(',')[1] if ref.count(',') >= 2 else ref)
            continue
        caps.append(cap)
    for cap in caps:
        i = cap['info']
        diag['severidades'][i['severity']] = diag['severidades'].get(i['severity'], 0) + 1
        for a in i['areas']:
            for vn, _ in a['geocodes']:
                diag['valueNames'].add(vn)
        if cap['status'] and cap['status'].lower() != 'actual':
            continue
        if cap['identifier'] in cancelados or cap['identifier'] in vistos:
            continue
        fim = ler_data(i['expires'])
        if fim and fim < momento:
            continue
        hits = municipios_atingidos(i['areas'], i['headline'] + ' ' + i['description'])
        toca = any(toca_caixa(p) for a in i['areas'] for p in a['poligonos'])
        if not hits and not toca:
            continue
        nivel, origem = func_nivel(i)
        vistos.add(cap['identifier'])
        saida.append(resumo_alerta(cap, fonte, nivel, origem, hits))
    diag['valueNames'] = sorted(diag['valueNames'])
    return saida, len(caps), diag


# ---------------------------------------------------------------- fontes
def coletar_idap(momento):
    raiz = xml_seguro(baixar(URL_IDAP, timeout=120))
    alertas, links = alertas_cap_de_feed(raiz, buscar_links=True, limite_links=120)
    saida, total, diag = filtrar_caps(alertas, 'Defesa Civil (IDAP)', nivel_dc, momento)
    msg = '%d alertas vigentes no feed nacional, %d na região' % (total, len(saida))
    if links:
        msg += ' (%d CAPs baixados individualmente)' % links
    return saida, msg, diag


def coletar_inmet_json(momento):
    d = json_ou_jsonp(baixar(URL_INMET_JSON, timeout=40))
    lista = d if isinstance(d, list) else [x for v in d.values() if isinstance(v, list) for x in v] if isinstance(d, dict) else []
    saida = []
    for a in lista:
        if not isinstance(a, dict):
            continue
        geo = a.get('geocodes') or a.get('geocode') or ''
        geo = ','.join(map(str, geo)) if isinstance(geo, list) else str(geo)
        poli = pares_de_numeros(a.get('poligono') or a.get('polygon') or a.get('coordenadas') or '')
        areas = [{'desc': str(a.get('municipios') or a.get('cidades') or ''),
                  'poligonos': [poli] if len(poli) >= 3 else [],
                  'geocodes': [('IBGE', g) for g in re.findall(r'\d{6,7}', geo)]}]
        hits = municipios_atingidos(areas)
        if not hits and not (poli and toca_caixa(poli)):
            continue
        ini = ler_data(a.get('inicio')) or ler_data('%s %s' % (a.get('data_inicio', ''), a.get('hora_inicio', '')))
        fim = ler_data(a.get('fim')) or ler_data('%s %s' % (a.get('data_fim', ''), a.get('hora_fim', '')))
        if fim and fim < momento:
            continue
        sev_txt = str(a.get('severidade') or a.get('nivel') or '')
        saida.append({
            'fonte': 'INMET', 'id': str(a.get('id') or a.get('codigo') or ''),
            'evento': str(a.get('descricao') or a.get('evento') or 'Aviso meteorológico'),
            'nivel': nivel_inmet(sev_txt + ' ' + str(a.get('aviso_cor') or '')), 'severidade': sev_txt,
            'classe': classe_alerta(a.get('descricao') or a.get('evento') or ''),
            'titulo': str(a.get('descricao') or ''), 'descricao': limpar_html(str(a.get('riscos') or '')),
            'instrucao': limpar_html(str(a.get('instrucoes') or ''), 400),
            'inicio': iso(ini), 'fim': iso(fim), 'areas': limpar_html(areas[0]['desc'], 400),
            'ibges': hits, 'geocodes': sorted(g for g in re.findall(r'\d{7}', geo) if g.startswith('42'))[:200],
            'poligonos': [simplificar(poli)] if len(poli) >= 3 else [],
        })
    return saida, '%d avisos ativos no país, %d para a região (JSON)' % (len(lista), len(saida))


def coletar_inmet_cap(momento):
    raiz = xml_seguro(baixar(URL_INMET_RSS, timeout=40))
    itens = list(raiz.iterfind('.//{*}item')) + list(raiz.iterfind('.//{*}entry'))

    def prioridade(it):
        t = norm(' '.join((x.text or '') for x in it.iter()))
        return 0 if ('santa catarina' in t or re.search(r'\bsc\b', t)) else 1
    itens.sort(key=prioridade)
    alertas, baixados = list(raiz.iterfind('.//{*}alert')), 0
    if not alertas:
        for it in itens[:60]:
            link = txt(it, 'link') or ''
            for l in it.findall('{*}link'):
                link = l.get('href') or link
            guid = txt(it, 'guid')
            if not re.search(r'/\d+/?$', link) and re.search(r'\d+', guid or ''):
                link = URL_INMET_RSS + '/' + re.findall(r'\d+', guid)[-1]
            if not link:
                continue
            try:
                sub = xml_seguro(baixar(link, timeout=30, tentativas=2))
                alertas.extend([sub] if sub.tag.split('}')[-1] == 'alert' else list(sub.iterfind('.//{*}alert')))
                baixados += 1
                time.sleep(0.4)
            except Exception:  # noqa: BLE001
                continue

    def nv(i):
        return nivel_inmet(i['headline'] + ' ' + i['description'] + ' ' + i['event'] + ' ' + ' '.join(i['params'].values()), i['severity']), 'texto do aviso'
    saida, total, _ = filtrar_caps(alertas, 'INMET', nv, momento)
    return saida, '%d avisos lidos por CAP (%d baixados), %d para a região' % (total, baixados, len(saida))


def chave(reg, *opcoes):
    nomes = {k: norm(k).replace('_', '') for k in reg}
    for o in opcoes:
        for k, nk in nomes.items():
            if nk == norm(o):
                return k
    for o in opcoes:
        for k, nk in nomes.items():
            if len(o) > 3 and norm(o) in nk:
                return k
    return None


HORIZONTES = (1, 3, 6, 12, 24, 48, 72, 96)


def municipio_da_estacao(codigo, mun, lat, lon):
    """Casa a estação com um município monitorado. O código das estações do CEMADEN
    começa com o código IBGE do município (420820302A = 4208203, Itajaí)."""
    cod = re.sub(r'\D', '', str(codigo or ''))[:7]
    for m in MUNICIPIOS:
        if cod and cod == m['ibge']:
            return m
    for m in MUNICIPIOS:
        if mun and norm(mun) == norm(m['nome']):
            return m
    if lat is not None and lon is not None and not mun and not cod:
        dists = sorted((dist_km(lat, lon, m['lat'], m['lon']), i) for i, m in enumerate(MUNICIPIOS))
        if dists and dists[0][0] <= RAIO_PLUVIOMETRO_KM:
            return MUNICIPIOS[dists[0][1]]
    return None


def campos_estacao(r):
    km = chave(r, 'cidade', 'municipio', 'nomemunicipio')
    ku = chave(r, 'uf', 'estado')
    kla, klo = chave(r, 'latitude', 'lat'), chave(r, 'longitude', 'lon', 'lng')
    kid = chave(r, 'codestacao', 'idestacao', 'idpcd', 'cod', 'id')
    kn = chave(r, 'nomeestacao', 'estacao', 'nome')
    kd = chave(r, 'datahora', 'dataHora', 'ultimadata', 'data')
    return km, ku, kla, klo, kid, kn, kd


def fuso_cemaden():
    return TZ_BR if os.environ.get('CEMADEN_FUSO', 'UTC').upper() in ('BR', 'BRT', 'LOCAL', '-03:00') else timezone.utc


def acumular_serie(pontos, ref):
    """Soma valorMedida (mm por registro) nas janelas que terminam em ref. O pluviômetro
    manda um registro por hora quando seco e a cada 10 min quando chove; uma janela só
    vale se não tiver buraco maior que 2 h nem começar antes do primeiro registro."""
    pontos = sorted(p for p in pontos if p[0] <= ref + timedelta(minutes=10))
    if not pontos or ref - pontos[-1][0] > timedelta(hours=2):
        return {}
    acc = {}
    for h in HORIZONTES:
        ini = ref - timedelta(hours=h)
        dentro = [p for p in pontos if p[0] > ini]
        anteriores = [p for p in pontos if p[0] <= ini]
        if not anteriores and (not dentro or dentro[0][0] - ini > timedelta(hours=1, minutes=10)):
            break
        tempos = [ini] + [p[0] for p in dentro] + [ref]
        if any(b - a > timedelta(hours=2) for a, b in zip(tempos, tempos[1:])):
            break
        acc[str(h)] = round(sum(p[1] for p in dentro), 1)
    return acc


def normalizar_estacoes(registros, ref=None):
    ref = ref or datetime.now(timezone.utc)
    fz = fuso_cemaden()
    instantaneo, series = [], {}
    for r in registros:
        if not isinstance(r, dict):
            continue
        km, ku, kla, klo, kid, kn, kd = campos_estacao(r)
        if ku and norm(r.get(ku)) not in ('sc', 'santa catarina', ''):
            continue
        lat, lon = (num(r.get(kla)), num(r.get(klo))) if kla and klo else (None, None)
        mun = str(r.get(km) or '') if km else ''
        cod = str(r.get(kid) or '') if kid else ''
        perto = municipio_da_estacao(cod, mun, lat, lon)
        if not perto:
            continue
        acc = {}
        for k, v in r.items():
            mm = re.match(r'^(?:acc|acum|acumulado|chuva)[_\s]*(\d{1,3})\s*(?:h|hr|hrs|hora|horas)?$', norm(k))
            val = num(v)
            if mm and val is not None and val >= 0:
                acc[str(int(mm.group(1)))] = round(val, 1)
        quando = ler_data(r.get(kd)) if kd else None
        if quando is not None and quando.tzinfo is TZ_BR and kd and not re.search(r'[+-]\d{2}:?\d{2}$|Z$', str(r.get(kd))):
            quando = quando.replace(tzinfo=fz)
        base = {'id': cod, 'nome': str(r.get(kn) or '') if kn else '', 'municipio': perto['nome'], 'ibge': perto['ibge'], 'lat': lat, 'lon': lon}
        if acc:
            instantaneo.append(dict(base, acc=acc, quando=iso(quando)))
            continue
        kv = chave(r, 'valormedida', 'valor', 'chuva', 'precipitacao')
        val = num(r.get(kv)) if kv else None
        if quando is None or val is None or val < 0:
            continue
        s = series.setdefault(cod or (perto['ibge'] + base['nome']), dict(base, pontos=[]))
        s['pontos'].append((quando, val))
    saida = instantaneo
    for s in series.values():
        acc = acumular_serie(s.pop('pontos'), ref) if s.get('pontos') else {}
        if not acc:
            continue
        saida.append(dict(s, acc=acc, quando=iso(ref)))
    return saida


def achar_lista(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        listas = [v for v in d.values() if isinstance(v, list)]
        if listas:
            return max(listas, key=len)
        if all(isinstance(v, dict) for v in d.values()):
            return list(d.values())
    return []


def coletar_pluviometros():
    erros, chaves = [], []
    for url in URLS_CEMADEN:
        try:
            regs = achar_lista(ler_tabela(baixar(url, timeout=40, tentativas=2)))
            if regs and isinstance(regs[0], dict):
                chaves = sorted(regs[0].keys())
            est = normalizar_estacoes(regs, REF_CEMADEN)
            if est:
                return est, '%d estações na região (%s)' % (len(est), url.split('//')[1].split('?')[0]), chaves
            erros.append('%s: %d registros, nenhum reconhecido na região' % (url.split('//')[1][:60], len(regs)))
        except Exception as e:  # noqa: BLE001
            erros.append('%s: %s' % (url.split('//')[1][:60], str(e)[:120]))
    erro = RuntimeError(' | '.join(erros))
    erro.chaves = chaves
    raise erro

# ---------------------------------------------------------------- rios (ANA)
def chave_com(d, inclui, exclui=()):
    """Primeira chave cujo nome normalizado contém todos os termos de inclui e nenhum de exclui."""
    for k in d:
        nk = norm(k).replace('_', ' ')
        if all(t in nk for t in inclui) and not any(t in nk for t in exclui):
            return k
    return None


def data_ana(s):
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})', str(s or ''))
    if m:
        a, mo, d, h, mi = map(int, m.groups())
    else:
        m = re.search(r'(\d{2})/(\d{2})/(\d{4})\D+(\d{2}):(\d{2})', str(s or ''))
        if not m:
            return None
        d, mo, a, h, mi = map(int, m.groups())
    fz = timezone.utc if os.environ.get('ANA_FUSO', '').lower() == 'utc' else TZ_BR
    return datetime(a, mo, d, h, mi, tzinfo=fz)


DIAG_ANA = []  # tentativas da última coleta, gravadas em diagnostico.ana (sem token, senha nem identificador)
# Os nomes dos parâmetros são os rótulos do Swagger, com acento e espaço. O exemplo em Java do
# manual (CodigoDaEstacao, RangeIntervaloDeBusca) responde 400. Com a data de hoje e DIAS_2, a
# ANA devolve as 48 h até a leitura mais recente. Confirmado em 10/11/2026.
ROTA_SERIE_ANA = 'HidroinfoanaSerieTelemetricaAdotada'


def texto_ana(corpo):
    try:
        return corpo.decode('utf-8')
    except UnicodeDecodeError:
        return corpo.decode('latin-1')


def requisicao_ana(url, cabecalhos, tentativas_5xx=3, espera=12):
    """GET que devolve (status, corpo) também nos erros HTTP. O servidor da ANA alterna respostas
    502, 503 e 504; nesses casos tenta de novo, com espera crescente."""
    for k in range(tentativas_5xx):
        st, corpo = requisicao_ana_1(url, cabecalhos)
        if st not in (502, 503, 504):
            return st, corpo
        time.sleep(espera * (k + 1))
    return st, corpo


def requisicao_ana_1(url, cabecalhos):
    if OFFLINE is not None:
        try:
            return 200, baixar(url)
        except Exception as e:  # noqa: BLE001
            return 404, str(e).encode()
    h = {'User-Agent': UA, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'}
    h.update(cabecalhos)
    ultimo = None
    for t in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                dados = r.read(20_000_000)
                if (r.headers.get('Content-Encoding') or '').lower() == 'gzip':
                    dados = gzip.decompress(dados)
                return r.status, dados
        except urllib.error.HTTPError as e:
            corpo = e.read(4000) or b''
            if (e.headers.get('Content-Encoding') or '').lower() == 'gzip':
                try:
                    corpo = gzip.decompress(corpo)
                except Exception:  # noqa: BLE001
                    pass
            return e.code, corpo
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(2 * (t + 1))
    raise ultimo


def ocultar(texto, segredos):
    texto = str(texto)
    for x in segredos:
        if x and len(x) >= 4:
            texto = texto.replace(x, '***')
    return re.sub(r'\s+', ' ', texto).strip()


def token_ana(ident, senha):
    st, corpo = requisicao_ana(URL_ANA_WS + '/OAUth/v1', {'Identificador': ident, 'Senha': senha}, tentativas_5xx=4)
    texto = texto_ana(corpo)
    try:
        d = json.loads(texto)
    except ValueError:
        d = None
    # Candidatos: campos com "token" no nome. Vence o tokenautenticacao do manual; depois, o que
    # tiver cara de JWT (três partes separadas por ponto); por último, o mais longo.
    cand, pilha = [], [d]
    while pilha:
        x = pilha.pop()
        if isinstance(x, dict):
            for k, v in x.items():
                if 'token' in norm(k) and isinstance(v, str) and len(v.strip()) > 20:
                    cand.append((norm(k).replace('_', '').replace(' ', ''), v.strip()))
                elif isinstance(v, (dict, list)):
                    pilha.append(v)
        elif isinstance(x, list):
            pilha.extend(x)
    cand.sort(key=lambda kv: (kv[0] != 'tokenautenticacao', kv[1].count('.') != 2, -len(kv[1])))
    token = cand[0][1] if cand else None
    if token and token.lower().startswith('bearer '):
        token = token[7:].strip()
    itens = d.get('items') if isinstance(d, dict) else None
    DIAG_ANA.append({'etapa': 'autenticação', 'http': st, 'token_recebido': bool(token),
                     'campos': sorted(d.keys()) if isinstance(d, dict) else None,
                     'campos_items': sorted(itens.keys()) if isinstance(itens, dict) else type(itens).__name__,
                     'campo_usado': cand[0][0] if cand else None, 'candidatos': len(cand),
                     'token_tamanho': len(token) if token else 0, 'token_partes': token.count('.') + 1 if token else 0,
                     'token_com_espaco': bool(token and re.search(r'\s', token)),
                     'mensagem': ocultar(d.get('message', ''), [token, senha, ident])[:160] if isinstance(d, dict) else '',
                     'resposta': ocultar(texto, [token, senha, ident])[:240] if not token else ''})
    if st != 200 or not token:
        raise RuntimeError('autenticação recusada (HTTP %d): %s' % (st, ocultar(texto, [senha, ident])[:160]))
    return token


def pontos_ana(d):
    itens = achar_lista(d.get('items', d) if isinstance(d, dict) else d)
    pontos = []
    for it in itens:
        if not isinstance(it, dict):
            continue
        kd = chave_com(it, ('data', 'hora'), ('status',)) or chave_com(it, ('data',), ('status',))
        kc = chave_com(it, ('cota',), ('status',)) or chave_com(it, ('nivel',), ('status',))
        ks = chave_com(it, ('cota', 'status'))
        kch = chave_com(it, ('chuva',), ('status',))
        kv = chave_com(it, ('vazao',), ('status',))
        if not kd or not kc or str(it.get(ks) or '0').strip() == '2':  # 2 = dado ruim no controle de qualidade da ANA
            continue
        t, n = data_ana(it.get(kd)), num(it.get(kc))
        if t is not None and n is not None:
            pontos.append((t, n, num(it.get(kch)) if kch else None, num(it.get(kv)) if kv else None))
    return pontos


def serie_ana_ws(codigo, ctx, momento):
    """Série telemétrica adotada (cota em cm, chuva, vazão) das últimas 48 h pelo Hidro-WebService."""
    p = {'Código da Estação': codigo, 'Tipo Filtro Data': 'DATA_LEITURA',
         'Data de Busca (yyyy-MM-dd)': momento.astimezone(TZ_BR).strftime('%Y-%m-%d'), 'Range Intervalo de busca': 'DIAS_2'}
    st, corpo = requisicao_ana(URL_ANA_WS + '/' + ROTA_SERIE_ANA + '/v1?' + urllib.parse.urlencode(p), {'Authorization': 'Bearer ' + ctx['token']})
    texto = texto_ana(corpo)
    resumo, pontos, msg = ocultar(texto, ctx['segredos']), None, ''
    if st == 200:
        try:
            d = json.loads(texto)
            pontos, msg = pontos_ana(d), str(d.get('message') or '') if isinstance(d, dict) else ''
        except ValueError:
            resumo = 'resposta sem JSON: ' + resumo
    DIAG_ANA.append({'etapa': 'série', 'estacao': codigo, 'http': st, 'leituras': len(pontos) if pontos is not None else None,
                     'resposta': '' if pontos else (msg or resumo)[:240]})
    if pontos is None:
        raise RuntimeError('HTTP %d: %s' % (st, resumo[:160] or 'sem corpo'))
    return pontos


def serie_ana_antiga(codigo, momento):
    """Serviço público antigo (Telemetria1WS), que a ANA vem substituindo pelo Hidro-WebService."""
    m = momento.astimezone(TZ_BR)
    q = urllib.parse.urlencode({'codEstacao': codigo, 'dataInicio': (m - timedelta(days=2)).strftime('%d/%m/%Y'), 'dataFim': m.strftime('%d/%m/%Y')})
    raiz = xml_seguro(baixar(URL_ANA_ANTIGA + '?' + q, timeout=60, tentativas=2))
    pontos = []
    for el in raiz.iter():
        f = {c.tag.split('}')[-1].lower(): (c.text or '').strip() for c in el}
        if 'datahora' in f and 'nivel' in f:
            t, n = data_ana(f['datahora']), num(f['nivel'])
            if t is not None and n is not None:
                pontos.append((t, n, num(f.get('chuva')), num(f.get('vazao'))))
    return pontos


def resumir_rio(cfg, pontos, momento):
    if not pontos:
        return None
    pontos.sort(key=lambda p: p[0])
    if pontos[-1][0] > momento + timedelta(minutes=30):  # horário em UTC lido como Brasília: corrige
        pontos = [(p[0].replace(tzinfo=timezone.utc),) + tuple(p[1:]) for p in pontos]
    pontos = [p for p in pontos if p[0] <= momento + timedelta(minutes=30)]
    if not pontos:
        return None
    t_ult, n_ult = pontos[-1][0], pontos[-1][1]
    vazoes = [p[3] for p in pontos if len(p) > 3 and p[3] is not None]
    antes = [p for p in pontos if p[0] <= t_ult - timedelta(hours=24)]
    janela = [p for p in pontos if p[0] > t_ult - timedelta(hours=24)]
    chuvas = [p[2] for p in janela if p[2] is not None and p[2] >= 0]
    horas = {}
    for p in pontos:
        if p[0] > t_ult - timedelta(hours=48):
            horas[p[0].astimezone(TZ_BR).strftime('%Y-%m-%dT%H:00')] = p[1]
    cotas = cfg.get('cotas') or None
    estado = None
    if isinstance(cotas, dict):
        estado = 0
        for i, k in enumerate(('atencao', 'alerta', 'emergencia'), 1):
            v = num(cotas.get(k))
            if v is not None and n_ult >= v:
                estado = i
    return {
        'codigo': cfg['codigo'], 'nome': cfg.get('nome', cfg['codigo']), 'municipio': cfg.get('municipio', ''),
        'ibges': cfg.get('ibges', []), 'lat': cfg.get('lat'), 'lon': cfg.get('lon'),
        'nivel_cm': round(n_ult, 1), 'quando': iso(t_ult),
        'variacao_24h_cm': round(n_ult - antes[-1][1], 1) if antes else None,
        'max_24h_cm': round(max(p[1] for p in janela), 1),
        'vazao_m3s': round(vazoes[-1], 2) if vazoes else None,
        'chuva_24h_mm': round(sum(chuvas), 1) if chuvas else None,
        'cotas': cotas, 'estado': estado,
        'serie': sorted(horas.items()),
    }


def coletar_rios(momento):
    ident, senha = os.environ.get('ANA_IDENTIFICADOR', '').strip(), os.environ.get('ANA_SENHA', '').strip()
    DIAG_ANA.clear()
    token = token_ana(ident, senha) if ident and senha else None
    ctx = {'token': token, 'segredos': [token, senha, ident]}
    saida, erros = [], []
    for r in RIOS:
        try:
            pontos = serie_ana_ws(r['codigo'], ctx, momento) if token else serie_ana_antiga(r['codigo'], momento)
            res = resumir_rio(r, pontos, momento)
            if res:
                saida.append(res)
            else:
                erros.append('%s sem leituras recentes' % r['codigo'])
        except Exception as e:  # noqa: BLE001
            erros.append('%s: %s' % (r['codigo'], str(e)[:120]))
    if not saida:
        raise RuntimeError(' | '.join(erros) or 'nenhuma estação configurada')
    via = 'Hidro-WebService' if token else 'serviço público antigo'
    return saida, '%d de %d estações com leitura (%s)%s' % (len(saida), len(RIOS), via, ('; ' + ' | '.join(erros)) if erros else '')


TRACOS = r'\s[-' + chr(0x2013) + chr(0x2014) + r']\s'  # separadores dos títulos da SDC/SC
NIVEIS_SDC = [('alerta maximo', 4), ('emergencia', 4), ('alerta', 3), ('atencao', 2), ('observacao', 1)]


def coletar_sdc_site(momento):
    raiz = xml_seguro(baixar(URL_SDC_FEED, timeout=40))
    saida = []
    for it in raiz.iterfind('.//{*}item'):
        titulo = txt(it, 'title')
        corpo = ' '.join((x.text or '') for x in it if x.tag.split('}')[-1] in ('description', 'encoded'))
        pub = ler_data(txt(it, 'pubDate'))
        if not pub:
            continue
        t = norm(titulo)
        nivel = next((n for p, n in NIVEIS_SDC if t.startswith(p)), None)
        if nivel is None:
            continue
        mh = re.search(r'proximas\s+(\d{1,2})\s+horas', norm(titulo + ' ' + corpo))
        fim = pub + timedelta(hours=int(mh.group(1)) if mh else 6)
        if fim < momento:
            continue
        texto = titulo + ' ' + limpar_html(corpo, 4000)
        hits = municipios_atingidos([{'desc': texto, 'poligonos': [], 'geocodes': []}])
        if not hits and 'grande florianopolis' in norm(texto):
            hits = [m['ibge'] for m in MUNICIPIOS]
        if not hits:
            continue
        saida.append({'fonte': 'SDC/SC (site)', 'id': txt(it, 'guid') or txt(it, 'link'), 'remetente': 'Defesa Civil de Santa Catarina',
                      'evento': re.split(TRACOS, titulo)[-1].strip(), 'classe': classe_alerta(titulo), 'nivel': nivel, 'nivel_origem': 'título da publicação',
                      'titulo': limpar_html(titulo, 240), 'descricao': limpar_html(corpo), 'inicio': iso(pub), 'fim': iso(fim),
                      'areas': '', 'ibges': hits, 'geocodes': [], 'poligonos': []})
    return saida, '%d publicações vigentes para a região' % len(saida)


# ---------------------------------------------------------------- setorização do SGB
CAMPOS_SGB = ('munic', 'cd_geocmu', 'num_setor', 'local', 'tipolo_g1', 'tipolo_e1', 'tipolo_g2', 'tipolo_e2',
              'grau_risco', 'num_edif', 'num_pess', 'data_setor')


def data_sgb(v):
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
    return str(v or '')[:10]


def ler_setorizacao(arquivo):
    try:
        with open(arquivo, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get('features'), list) else None
    except (OSError, ValueError):
        return None


def coletar_setorizacao(arquivo, momento, forcar=False):
    """Setores de risco alto e muito alto do SGB nos municípios da região, em GeoJSON WGS 84.

    Consulta o serviço quando o arquivo não existe, quando a lista de municípios muda,
    às segundas-feiras entre 6 h e 7 h (horário de Brasília) ou quando forçado. Grava só se algo mudou."""
    atual = ler_setorizacao(arquivo)
    ibges = sorted(m['ibge'] for m in MUNICIPIOS)
    semana = momento.weekday() == 0 and momento.hour == 6
    if atual and atual.get('municipios') == ibges and not (forcar or semana):
        return len(atual['features']), '%d setores (atualizado em %s); verificação semanal às segundas' % (
            len(atual['features']), str(atual.get('atualizado_em', ''))[:10])
    params = {'where': 'cd_geocmu IN (%s)' % ','.join("'%s'" % c for c in ibges),
              'outFields': ','.join(CAMPOS_SGB), 'outSR': '4326', 'geometryPrecision': '6',
              'maxAllowableOffset': '0.00003', 'f': 'geojson'}
    d = json.loads(baixar(URL_SGB_SETORES + '?' + urllib.parse.urlencode(params), timeout=90).decode('utf-8'))
    if not isinstance(d, dict) or d.get('error'):
        raise ValueError('resposta inesperada do SGB: %s' % str((d or {}).get('error', d))[:200])
    feats = []
    for f in d.get('features') or []:
        g = f.get('geometry') or {}
        if g.get('type') not in ('Polygon', 'MultiPolygon'):
            continue
        p = {k: v for k, v in (f.get('properties') or {}).items() if k in CAMPOS_SGB and v not in (None, '', ' ')}
        if 'data_setor' in p:
            p['data_setor'] = data_sgb(p['data_setor'])
        feats.append({'type': 'Feature', 'properties': p, 'geometry': g})
    if not feats:
        raise ValueError('o SGB não devolveu setores para os municípios %s' % ', '.join(ibges))
    feats.sort(key=lambda f: (f['properties'].get('cd_geocmu', ''), f['properties'].get('num_setor', ''), json.dumps(f['geometry'])[:80]))
    por_mun = {}
    for f in feats:
        por_mun[f['properties'].get('munic', '?')] = por_mun.get(f['properties'].get('munic', '?'), 0) + 1
    resumo = ', '.join('%s %d' % kv for kv in sorted(por_mun.items()))
    if atual and atual.get('municipios') == ibges and atual.get('features') == feats:
        return len(feats), '%d setores, sem mudança no SGB (%s)' % (len(feats), resumo)
    saida = {'type': 'FeatureCollection',
             'fonte': 'Serviço Geológico do Brasil (SGB), Setorização de Risco, setores de risco alto e muito alto',
             'url': URL_SGB_SETORES, 'municipios': ibges, 'atualizado_em': iso(momento), 'features': feats}
    os.makedirs(os.path.dirname(os.path.abspath(arquivo)), exist_ok=True)
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, separators=(',', ':'))
    return len(feats), '%d setores gravados em %s (%s)' % (len(feats), os.path.basename(arquivo), resumo)


# ---------------------------------------------------------------- principal
def executar(nome, func, *args):
    t0 = time.time()
    try:
        res = func(*args)
        return res, {'ok': True, 'msg': res[1], 'ms': int(1000 * (time.time() - t0))}
    except Exception as e:  # noqa: BLE001
        msg = str(e).strip() or e.__class__.__name__
        print('[falha] %s: %s' % (nome, msg), file=sys.stderr)
        return None, {'ok': False, 'msg': msg[:300], 'ms': int(1000 * (time.time() - t0))}


def gravar_historico(pasta, momento, dados):
    os.makedirs(pasta, exist_ok=True)
    assinatura = [(a['fonte'], a['id'], a['nivel'], a.get('fim')) for a in dados['defesa_civil'] + dados['inmet']]
    h = hashlib.sha256(json.dumps(sorted(assinatura, key=str)).encode()).hexdigest()[:16]
    arq_hash = os.path.join(pasta, '.ultimo-hash')
    anterior = open(arq_hash).read().strip() if os.path.exists(arq_hash) else ''
    arq_mes = os.path.join(pasta, momento.strftime('%Y-%m') + '.jsonl')
    novo_mes = not os.path.exists(arq_mes)
    if h == anterior and not novo_mes:
        return False
    por_mun = {}
    for e in dados['pluviometros']:
        v = num((e.get('acc') or {}).get('24'))
        if v is not None:
            por_mun.setdefault(e['municipio'], []).append(v)

    def mediana(v):
        v = sorted(v)
        k = len(v) // 2
        return round(v[k] if len(v) % 2 else (v[k - 1] + v[k]) / 2, 1)
    linha = {'em': iso(momento), 'hash': h,
             'alertas': [{k: a.get(k) for k in ('fonte', 'id', 'nivel', 'classe', 'evento', 'titulo', 'inicio', 'fim', 'ibges')} for a in dados['defesa_civil'] + dados['inmet']],
             'pluviometros_24h': {m: mediana(v) for m, v in sorted(por_mun.items())},
             'rios_cm': {r['codigo']: r['nivel_cm'] for r in dados.get('rios', [])}}
    with open(arq_mes, 'a', encoding='utf-8') as f:
        f.write(json.dumps(linha, ensure_ascii=False) + '\n')
    with open(arq_hash, 'w') as f:
        f.write(h)
    return True


def principal():
    global OFFLINE, MUNICIPIOS, REF_CEMADEN, RIOS
    ap = argparse.ArgumentParser(description='Coletor do RISCO.sj')
    ap.add_argument('--saida', default='dados/alertas.json')
    ap.add_argument('--historico', default='dados/historico')
    ap.add_argument('--offline', help='pasta com mapa.json (url -> arquivo) para testes sem rede')
    ap.add_argument('--sdc-site', action='store_true', help='inclui o feed do site da SDC/SC')
    ap.add_argument('--agora', help='instante de referência ISO para os acumulados (testes com dados antigos)')
    ap.add_argument('--areas', help='arquivo GeoJSON da setorização do SGB (padrão: areas-risco.geojson ao lado da saída)')
    args = ap.parse_args()

    base = os.path.dirname(os.path.abspath(__file__))
    arq_mun = os.path.join(base, 'municipios.json')
    if os.path.exists(arq_mun):
        MUNICIPIOS = json.load(open(arq_mun, encoding='utf-8'))
    arq_rios = os.path.join(base, 'rios.json')
    if os.path.exists(arq_rios):
        RIOS = json.load(open(arq_rios, encoding='utf-8'))
    if args.offline:
        mapa = json.load(open(os.path.join(args.offline, 'mapa.json'), encoding='utf-8'))
        OFFLINE = {u: os.path.join(args.offline, f) for u, f in mapa.items()}

    momento = agora()
    if args.agora:
        REF_CEMADEN = ler_data(args.agora)
    dados = {'versao': 1, 'coletor': VERSAO, 'gerado_em': iso(momento), 'municipios': MUNICIPIOS,
             'fontes': {}, 'defesa_civil': [], 'inmet': [], 'pluviometros': [], 'rios': [], 'diagnostico': {}}

    res, st = executar('IDAP', coletar_idap, momento)
    st['url'] = URL_IDAP
    dados['fontes']['idap'] = st
    if res:
        dados['defesa_civil'].extend(res[0])
        dados['diagnostico']['idap'] = res[2]

    res, st = executar('INMET (JSON)', coletar_inmet_json, momento)
    st['url'] = URL_INMET_JSON
    if not res:
        res2, st2 = executar('INMET (RSS/CAP)', coletar_inmet_cap, momento)
        st2['url'] = URL_INMET_RSS
        st2['msg'] = ('JSON falhou (%s); ' % st['msg'][:80]) + st2['msg']
        res, st = res2, st2
    dados['fontes']['inmet'] = st
    if res:
        dados['inmet'] = res[0]

    t0 = time.time()
    try:
        est, msg, chaves = coletar_pluviometros()
        dados['pluviometros'] = est
        dados['fontes']['cemaden_pluviometros'] = {'ok': True, 'msg': msg, 'ms': int(1000 * (time.time() - t0))}
        dados['diagnostico']['cemaden_chaves'] = chaves[:40]
    except Exception as e:  # noqa: BLE001
        erro = e.args[0] if e.args else e
        dados['diagnostico']['cemaden_chaves'] = getattr(e, 'chaves', [])[:40]
        dados['fontes']['cemaden_pluviometros'] = {'ok': False, 'msg': str(erro)[:400], 'ms': int(1000 * (time.time() - t0))}
        print('[falha] pluviômetros CEMADEN: %s' % erro, file=sys.stderr)

    res, st = executar('Rios (ANA)', coletar_rios, momento)
    if res:
        dados['rios'] = res[0]
    elif not (os.environ.get('ANA_IDENTIFICADOR') and os.environ.get('ANA_SENHA')):
        st = {'ok': None, 'ms': st['ms'],
              'msg': 'sem credenciais da ANA (secrets ANA_IDENTIFICADOR e ANA_SENHA); o serviço público antigo não respondeu: ' + st['msg'][:160]}
    st['url'] = URL_ANA_WS
    dados['fontes']['ana_rios'] = st
    if DIAG_ANA:
        dados['diagnostico']['ana'] = DIAG_ANA[:20]

    if args.sdc_site or os.environ.get('RISCO_SDC_SITE') == '1':
        res, st = executar('SDC/SC site', coletar_sdc_site, momento)
        st['url'] = URL_SDC_FEED
        dados['fontes']['sdc_site'] = st
        if res:
            dados['defesa_civil'].extend(res[0])
    else:
        dados['fontes']['sdc_site'] = {'ok': None, 'msg': 'desativado (ligue com RISCO_SDC_SITE=1)'}

    modo_sgb = (os.environ.get('RISCO_SGB') or '').strip().lower()
    if modo_sgb == '0':
        dados['fontes']['sgb_setorizacao'] = {'ok': None, 'msg': 'desativado (RISCO_SGB=0)'}
    else:
        arq_areas = args.areas or os.path.join(os.path.dirname(os.path.abspath(args.saida)), 'areas-risco.geojson')
        res, st = executar('Setorização (SGB)', coletar_setorizacao, arq_areas, momento, modo_sgb == 'forcar')
        st['url'] = URL_SGB_SETORES
        dados['fontes']['sgb_setorizacao'] = st

    dados['fontes']['cemaden_alertas'] = {'ok': None, 'msg': 'o CEMADEN não publica API de alertas; eles chegam à população pela Defesa Civil (IDAP)'}

    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    with open(args.saida, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, separators=(',', ':'))
    mudou = gravar_historico(args.historico, momento, dados) if args.historico else False

    print('RISCO.sj coletor %s em %s' % (VERSAO, dados['gerado_em']))
    for k, v in dados['fontes'].items():
        estado = 'ok' if v['ok'] else ('--' if v['ok'] is None else 'FALHA')
        print('  %-22s %-5s %s' % (k, estado, v['msg']))
    classes = {}
    for a in dados['defesa_civil'] + dados['inmet']:
        classes[a.get('classe')] = classes.get(a.get('classe'), 0) + 1
    print('  defesa civil: %d | inmet: %d | classes: %s | pluviômetros: %d | rios: %d | histórico %s' % (
        len(dados['defesa_civil']), len(dados['inmet']), ', '.join('%s %d' % kv for kv in sorted(classes.items(), key=str)) or 'nenhum',
        len(dados['pluviometros']), len(dados['rios']), 'atualizado' if mudou else 'sem mudança'))
    return 0


if __name__ == '__main__':
    sys.exit(principal())
