// 앱 화면·차트 라이브러리: 캐시 우선 / 데이터(data/): 네트워크 우선(오프라인 시 마지막 캐시)
const V='chart-v1',SHELL=['./','index.html','manifest.webmanifest','icon-192.png',
  'https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(SHELL)));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))));self.clients.claim()});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET')return;
  const net=()=>fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(V).then(x=>x.put(e.request,c))}return r});
  if(u.pathname.includes('/data/')||u.pathname.endsWith('/')||u.pathname.endsWith('index.html'))
    e.respondWith(net().catch(()=>caches.match(e.request)));
  else e.respondWith(caches.match(e.request).then(r=>r||net()));});
