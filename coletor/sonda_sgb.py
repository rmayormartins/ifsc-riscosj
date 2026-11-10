# Temporário: verifica a camada nacional de setorização de risco do SGB.
import json, urllib.parse, urllib.request
BASE = 'https://geoportal.sgb.gov.br/server/rest/services/gestaoterritorial/risco/MapServer/0/query'
IBGES = ['4216602', '4211900', '4205407', '4202305', '4215703']
def q(params, rotulo):
    url = BASE + '?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'RISCO.sj sonda'})
        with urllib.request.urlopen(req, timeout=60) as r:
            corpo = r.read()
            print('==', rotulo, 'HTTP', r.status, r.headers.get('Content-Type'), len(corpo), 'bytes')
            return json.loads(corpo.decode('utf-8'))
    except Exception as e:
        print('==', rotulo, 'ERRO', repr(e)[:300])
        return None
d = q({'where': "uf='SC'", 'outFields': 'munic,cd_geocmu', 'returnGeometry': 'false', 'returnDistinctValues': 'true', 'f': 'json'}, 'distintos SC')
if d:
    print('erro' in d and d['error'])
    fs = d.get('features') or []
    print('municipios SC:', len(fs))
    for f in fs:
        a = f['attributes']
        if any(s in (a.get('munic') or '') for s in ['José', 'Palho', 'Florian', 'Bigua', 'Amaro']) or a.get('cd_geocmu') in IBGES:
            print('  ', a)
    print('amostra cd_geocmu:', [f['attributes'].get('cd_geocmu') for f in fs[:5]])
w = "cd_geocmu IN (%s)" % ','.join("'%s'" % c for c in IBGES)
d = q({'where': w, 'returnCountOnly': 'true', 'f': 'json'}, 'contagem por IBGE')
print(d)
d = q({'where': w, 'outFields': 'munic,cd_geocmu,num_setor,local,tipolo_g1,tipolo_e1,cobrade_01,grau_risco,num_pess,data_setor', 'returnGeometry': 'false', 'f': 'json'}, 'atributos')
if d and d.get('features'):
    from collections import Counter
    print(Counter((f['attributes']['munic'], f['attributes']['grau_risco']) for f in d['features']))
    print(Counter(f['attributes']['tipolo_g1'] for f in d['features']))
    print(Counter(f['attributes']['tipolo_e1'] for f in d['features']))
    print(Counter(str(f['attributes']['data_setor'])[:4] for f in d['features']))
    for f in d['features'][:4]: print('  ', f['attributes'])
d = q({'where': w, 'outFields': 'munic,cd_geocmu,num_setor,local,tipolo_g1,tipolo_e1,grau_risco,num_pess', 'outSR': '4326', 'f': 'geojson'}, 'geojson 4326')
if d and d.get('features'):
    f = d['features'][0]
    print('tipo', d.get('type'), 'n', len(d['features']), 'geom', f['geometry']['type'], json.dumps(f['geometry'])[:200])
    print('props', f['properties'])
d = q({'where': w, 'outFields': 'munic,num_setor,local,tipolo_g1,grau_risco', 'outSR': '4326', 'geometryPrecision': '5', 'maxAllowableOffset': '0.00005', 'f': 'geojson'}, 'geojson simplificado')
