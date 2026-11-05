// RISCO.sj - Cloudflare Worker opcional
// Ramon Mayor Martins, IFSC Câmpus São José
//
// Rotas
//   GET  /proxy?url=<endereço>   repassa consultas aos avisos do INMET com CORS liberado (cache de 5 min).
//                                Só é usado quando o coletor do GitHub Actions não está publicado.
//   POST /llm                    recebe {system, prompt} e devolve {text}, usando a API da Groq
//
// Variáveis do Worker
//   GROQ_API_KEY    (secret, obrigatória só para /llm)
//   GROQ_MODEL      (opcional; confira os modelos disponíveis no console da Groq)
//   ALLOWED_ORIGIN  (recomendado; ex.: https://rmayormartins.github.io)

const HOSTS_PERMITIDOS = ['apiprevmet3.inmet.gov.br'];
const MODELO_PADRAO = 'llama-3.3-70b-versatile';

export default {
  async fetch(request, env, ctx) {
    const origem = request.headers.get('Origin') || '';
    const permitidas = (env.ALLOWED_ORIGIN || '*').split(',').map(s => s.trim()).filter(Boolean);
    const liberada = permitidas.includes('*') || permitidas.includes(origem);
    const cors = {
      'Access-Control-Allow-Origin': permitidas.includes('*') ? '*' : (liberada ? origem : permitidas[0]),
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Vary': 'Origin'
    };
    const json = (obj, status = 200) => new Response(JSON.stringify(obj), {
      status, headers: { ...cors, 'Content-Type': 'application/json; charset=utf-8' }
    });

    if (request.method === 'OPTIONS') return new Response(null, { headers: cors });
    const url = new URL(request.url);

    if (url.pathname === '/proxy' && request.method === 'GET') {
      let alvo;
      try { alvo = new URL(url.searchParams.get('url') || ''); } catch (e) { return json({ error: 'url inválida' }, 400); }
      if (alvo.protocol !== 'https:' || !HOSTS_PERMITIDOS.includes(alvo.hostname)) return json({ error: 'host não permitido' }, 403);

      const cache = caches.default;
      const chave = new Request(alvo.toString(), { method: 'GET' });
      let resp = await cache.match(chave);
      if (!resp) {
        const r = await fetch(alvo.toString(), { headers: { 'Accept': 'application/json', 'User-Agent': 'RISCO.sj (IFSC Campus Sao Jose)' } });
        if (!r.ok) return json({ error: 'a origem respondeu ' + r.status }, 502);
        resp = new Response(await r.text(), { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'max-age=300' } });
        ctx.waitUntil(cache.put(chave, resp.clone()));
      }
      return new Response(await resp.text(), { headers: { ...cors, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'max-age=300' } });
    }

    if (url.pathname === '/llm' && request.method === 'POST') {
      if (!liberada) return json({ error: 'origem não autorizada' }, 403);
      if (!env.GROQ_API_KEY) return json({ error: 'GROQ_API_KEY não configurada no Worker' }, 500);
      let corpo;
      try { corpo = await request.json(); } catch (e) { return json({ error: 'JSON inválido' }, 400); }
      const prompt = String(corpo.prompt || '').slice(0, 12000);
      const system = String(corpo.system || '').slice(0, 4000);
      if (!prompt) return json({ error: 'prompt vazio' }, 400);

      const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + env.GROQ_API_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: env.GROQ_MODEL || MODELO_PADRAO,
          temperature: 0.2,
          max_tokens: 900,
          messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }]
        })
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) return json({ error: (j.error && j.error.message) || ('a Groq respondeu ' + r.status) }, 502);
      const texto = (j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || '';
      return json({ text: texto });
    }

    return json({ error: 'rota não encontrada', rotas: ['GET /proxy?url=', 'POST /llm'] }, 404);
  }
};
