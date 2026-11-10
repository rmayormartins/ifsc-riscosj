"""Diagnóstico do Hidro-WebService da ANA (temporário). Não imprime token, senha nem identificador."""
import base64, json, os, re, subprocess, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

BASE = 'https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas'
UA = 'RISCO.sj/1.0 (IFSC Campus Sao Jose; painel de apoio a decisao; https://rmayormartins.github.io)'
ID, PW = os.environ.get('ANA_IDENTIFICADOR', '').strip(), os.environ.get('ANA_SENHA', '').strip()
print('identificador: %d caracteres, só dígitos: %s | senha: %d caracteres' % (len(ID), ID.isdigit(), len(PW)))


def req(url, h):
    r = urllib.request.Request(url, headers=dict({'User-Agent': UA, 'Accept': 'application/json'}, **h))
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


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


print('\n== 2. formas de enviar o token (série adotada, DIAS_2) ==')
testar('Authorization: Bearer <token>', url, {'Authorization': 'Bearer ' + token})
testar('Authorization: <token>', url, {'Authorization': token})
testar('Authorization: bearer <token>', url, {'Authorization': 'bearer ' + token})
testar('cabeçalho Token', url, {'Token': token})
testar('cabeçalho tokenautenticacao', url, {'tokenautenticacao': token})
print('\n== 3. parâmetros (com Bearer) ==')
B = {'Authorization': 'Bearer ' + token}
testar('sem DataDeBusca, DIAS_30 (manual)', BASE + '/HidroinfoanaSerieTelemetricaAdotada/v1?' + urllib.parse.urlencode({k: v for k, v in dict(P, RangeIntervaloDeBusca='DIAS_30').items() if k != 'DataDeBusca'}), B)
testar('DIAS_30 com data', BASE + '/HidroinfoanaSerieTelemetricaAdotada/v1?' + urllib.parse.urlencode(dict(P, RangeIntervaloDeBusca='DIAS_30')), B)
testar('HORA_24 com data', BASE + '/HidroinfoanaSerieTelemetricaAdotada/v1?' + urllib.parse.urlencode(dict(P, RangeIntervaloDeBusca='HORA_24')), B)
testar('rótulos do Swagger', BASE + '/HidroinfoanaSerieTelemetricaAdotada/v1?' + urllib.parse.urlencode({'Código da Estação': '84100000', 'Tipo Filtro Data': 'DATA_LEITURA', 'Data de Busca (yyyy-MM-dd)': hoje, 'Range Intervalo de busca': 'DIAS_2'}), B)
testar('série detalhada', BASE + '/HidroinfoanaSerieTelemetricaDetalhada/v1?' + urllib.parse.urlencode(P), B)
testar('inventário da estação', BASE + '/HidroInventarioEstacoes/v1?' + urllib.parse.urlencode({'Código da Estação': '84100000'}), B)
testar('inventário (CodigoDaEstacao)', BASE + '/HidroInventarioEstacoes/v1?' + urllib.parse.urlencode({'CodigoDaEstacao': '84100000'}), B)
print('\n== 4. curl (como o Swagger) ==')
for nome, h in [('curl Bearer', 'Authorization: Bearer ' + token), ('curl sem Bearer', 'Authorization: ' + token)]:
    r = subprocess.run(['curl', '-sS', '-m', '60', '-o', '/tmp/c.json', '-w', '%{http_code}', '-H', 'accept: */*', '-H', h, url], capture_output=True, text=True)
    print('%-38s HTTP %s  %s' % (nome, r.stdout, resumo(open('/tmp/c.json', 'rb').read(), 160) if os.path.exists('/tmp/c.json') else r.stderr[:160]))
