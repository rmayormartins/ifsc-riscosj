"""Diagnóstico do Hidro-WebService da ANA (temporário). Não imprime token, senha nem identificador."""
import base64, json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = 'https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas'
UA = 'RISCO.sj/1.0 (IFSC Campus Sao Jose; painel de apoio a decisao; https://rmayormartins.github.io)'
ID, PW = os.environ.get('ANA_IDENTIFICADOR', '').strip(), os.environ.get('ANA_SENHA', '').strip()
print('identificador: %d caracteres, só dígitos: %s | senha: %d caracteres' % (len(ID), ID.isdigit(), len(PW)))


def req1(url, h):
    r = urllib.request.Request(url, headers=dict({'User-Agent': UA, 'Accept': 'application/json'}, **h))
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def req(url, h):
    for k in range(4):
        st, hd, b = req1(url, h)
        if st not in (502, 503, 504):
            return st, hd, b
        print('    (HTTP %d, nova tentativa em 10 s)' % st)
        time.sleep(10)
    return st, hd, b


def txt(b):
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('latin-1')


def resumo(b, n=260):
    t = txt(b)
    if '<html' in t.lower():
        tit = re.search(r'<title>(.*?)</title>', t, re.S | re.I)
        corpo = re.sub(r'<style.*?</style>|<script.*?</script>', ' ', t, flags=re.S | re.I)
        corpo = re.sub(r'<[^>]+>', ' ', corpo)
        return 'HTML [%s] %s' % (tit.group(1).strip() if tit else '', re.sub(r'\s+', ' ', corpo).strip()[:n])
    return re.sub(r'\s+', ' ', t)[:n]


print('\n== 1. autenticação ==')
body, st = b'', 0
for k in range(5):
    st, hd, body = req(BASE + '/OAUth/v1', {'Identificador': ID, 'Senha': PW})
    print('tentativa %d: HTTP %d, content-type %s, server %s' % (k + 1, st, hd.get('Content-Type'), hd.get('Server')))
    if st == 200:
        break
    print('   ', resumo(body))
    time.sleep(20)
if st != 200:
    raise SystemExit('autenticação indisponível')
d = json.loads(txt(body))
items = d.get('items')
print('campos:', list(d), '| status:', d.get('status'), '| code:', d.get('code'), '| message:', d.get('message'))
print('items é', type(items).__name__, '| campos de items:', list(items) if isinstance(items, dict) else None)
token = (items or {}).get('tokenautenticacao') if isinstance(items, dict) else None
if not token:
    raise SystemExit('sem tokenautenticacao')
print('::add-mask::' + token)
print('token: tamanho %d, partes %d, começa com eyJ %s, espaços %s, prefixo bearer %s' % (
    len(token), token.count('.') + 1, token.startswith('eyJ'), bool(re.search(r'\s', token)), token.lower().startswith('bearer')))
for k, v in items.items():
    if k != 'tokenautenticacao':
        print('  items.%s = %s' % (k, str(v)[:80]))
try:
    pay = json.loads(base64.urlsafe_b64decode(token.split('.')[1] + '=='))
    agora = time.time()
    print('JWT: campos', sorted(pay), '| exp em %s min' % (round((pay['exp'] - agora) / 60) if 'exp' in pay else '?'))
except Exception as e:  # noqa: BLE001
    print('token não é JWT decodificável:', e.__class__.__name__)

hoje = datetime.now(timezone(timedelta(hours=-3))).strftime('%Y-%m-%d')
P = {'CodigoDaEstacao': '84100000', 'TipoFiltroData': 'DATA_LEITURA', 'DataDeBusca': hoje, 'RangeIntervaloDeBusca': 'DIAS_2'}
url = BASE + '/HidroinfoanaSerieTelemetricaAdotada/v1?' + urllib.parse.urlencode(P)


def testar(nome, u, h):
    st, hd, b = req(u, h)
    extra = ''
    if st == 200:
        try:
            j = json.loads(txt(b))
            it = j.get('items') or []
            extra = 'itens: %d%s' % (len(it), (' | campos: %s | último: %s' % (sorted(it[-1]), it[-1].get('Data_Hora_Medicao'))) if it else '')
        except ValueError:
            extra = resumo(b)
    else:
        extra = resumo(b, 180) + (' | WWW-Authenticate: ' + hd['WWW-Authenticate'] if hd.get('WWW-Authenticate') else '')
    print('%-38s HTTP %d  %s' % (nome, st, extra))
    return st


B = {'Authorization': 'Bearer ' + token}
def dia(n):
    return (datetime.now(timezone(timedelta(hours=-3))) + timedelta(days=n)).strftime('%Y-%m-%d')
def serie(rota, cod, data, faixa, filtro='DATA_LEITURA'):
    q = {'Código da Estação': cod, 'Tipo Filtro Data': filtro, 'Data de Busca (yyyy-MM-dd)': data, 'Range Intervalo de busca': faixa}
    st, hd, b = req(BASE + '/' + rota + '/v1?' + urllib.parse.urlencode(q), B)
    if st != 200:
        return 'HTTP %d %s' % (st, resumo(b, 120))
    j = json.loads(txt(b)); it = j.get('items') or []
    if not it:
        return 'HTTP 200, 0 itens | message: %s' % j.get('message')
    ds = sorted(str(x.get('Data_Hora_Medicao')) for x in it)
    ex = it[-1]
    return 'HTTP 200, %d itens, de %s a %s | exemplo: %s' % (len(it), ds[0], ds[-1], {k: ex[k] for k in list(ex)[:12]})

print('\n== Rios On-line: usos das constantes de base ==')
r = urllib.request.Request('https://ciram.epagri.sc.gov.br/rios-online/main.125be630afefcdb4.js', headers={'User-Agent': UA})
with urllib.request.urlopen(r, timeout=60) as resp:
    c = txt(resp.read())
m = re.search(r"const (_0x[0-9a-f]+)='/api/rios-online-server/webresources/monitoramentohidrologia/',(_0x[0-9a-f]+)='/api/rios-online-server/'", c)
A, Bb = m.group(1), m.group(2)
print('constantes:', A, Bb)
for nome in (A, Bb):
    for k, mm in enumerate(re.finditer(re.escape(nome) + r'(?![0-9a-f])', c)):
        if k == 0:
            continue
        print('  [%s] ...%s...' % (nome, c[max(0, mm.start() - 140): mm.end() + 200].replace('\n', ' ')))
        if k > 14:
            break
print('\n== tentativas diretas ==')
def get(u):
    try:
        rq = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'})
        with urllib.request.urlopen(rq, timeout=40) as resp:
            return resp.status, resp.headers.get('Content-Type'), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type'), e.read()
    except Exception as e:  # noqa: BLE001
        return 0, '', str(e).encode()
for u in ['https://ciram.epagri.sc.gov.br/api/rios-online-server/cache/bacias.txt', 'https://ciram.epagri.sc.gov.br/rios-online/cache/bacias.txt']:
    st, ct, b = get(u)
    print(u, 'HTTP', st, ct, len(b), 'bytes |', resumo(b, 500))
raise SystemExit(0)

print('\n== inventário ==')
for cod in ['84100000', '84150100']:
    st, hd, b = req(BASE + '/HidroInventarioEstacoes/v1?' + urllib.parse.urlencode({'Código da Estação': cod}), B)
    it = (json.loads(txt(b)).get('items') or [{}])[0] if st == 200 else {}
    print(cod, 'HTTP', st, {k: it.get(k) for k in ['Estacao_Nome', 'Municipio_Nome', 'Rio_Nome', 'Latitude', 'Longitude', 'Operando', 'Tipo_Estacao', 'Tipo_Estacao_Telemetrica', 'Data_Periodo_Telemetrica_Inicio', 'Data_Periodo_Telemetrica_Fim', 'Data_Ultima_Atualizacao', 'Operadora_Sigla', 'Responsavel_Sigla']})

print('\n== série adotada, 84100000 ==')
for data, faixa in [(dia(0), 'DIAS_2'), (dia(-1), 'DIAS_2'), (dia(1), 'DIAS_2'), (dia(0), 'HORA_24'), (dia(0), 'DIAS_7'), (dia(0), 'DIAS_30'), ('2026-10-15', 'DIAS_7')]:
    print('%s %-8s %s' % (data, faixa, serie('HidroinfoanaSerieTelemetricaAdotada', '84100000', data, faixa)))
print('filtro DATA_ULTIMA_ATUALIZACAO, hoje DIAS_2:', serie('HidroinfoanaSerieTelemetricaAdotada', '84100000', dia(0), 'DIAS_2', 'DATA_ULTIMA_ATUALIZACAO'))
print('\n== série detalhada, 84100000 ==')
for data, faixa in [(dia(0), 'DIAS_2'), (dia(-1), 'DIAS_2'), (dia(0), 'DIAS_7')]:
    print('%s %-8s %s' % (data, faixa, serie('HidroinfoanaSerieTelemetricaDetalhada', '84100000', data, faixa)))
print('\n== 84150100 ==')
for rota in ['HidroinfoanaSerieTelemetricaAdotada', 'HidroinfoanaSerieTelemetricaDetalhada']:
    for data, faixa in [(dia(0), 'DIAS_2'), (dia(0), 'DIAS_7')]:
        print('%-10s %s %-8s %s' % (rota[-9:], data, faixa, serie(rota, '84150100', data, faixa)))
