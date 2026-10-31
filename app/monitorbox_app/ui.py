PAGE = r"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>MonitorBox</title>
<link rel=icon href=/favicon.svg type=image/svg+xml><link rel=icon href=/favicon.ico sizes=64x64 type=image/png><link rel=apple-touch-icon href=/apple-touch-icon.png><link rel=manifest href=/manifest.webmanifest>
<meta name=theme-color content="#174041"><meta name=apple-mobile-web-app-capable content=yes><meta name=apple-mobile-web-app-title content=MonitorBox>
<style>
@font-face{font-family:Sora;src:url(/brand/sora.ttf) format('truetype');font-weight:100 800;font-display:swap}
@font-face{font-family:Figtree;src:url(/brand/figtree.ttf) format('truetype');font-weight:300 900;font-display:swap}
:root{--bg:#08171C;--ink:#F1F7F4;--sub:#9BB5AD;--acc:#34D399;--glow:rgba(52,211,153,.20);--line:rgba(255,255,255,.10);--card:rgba(255,255,255,.05);--accl:rgba(52,211,153,.45);--beam:rgba(52,211,153,.12)}
body[data-s=yellow]{--beam:rgba(251,191,36,.12);--accl:rgba(251,191,36,.45);--bg:#161507;--ink:#F8F5EA;--sub:#BDB48F;--acc:#FBBF24;--glow:rgba(251,191,36,.20)}
body[data-s=blue]{--beam:rgba(96,165,250,.12);--accl:rgba(96,165,250,.45);--bg:#0A1426;--ink:#EEF3FB;--sub:#9DB2D1;--acc:#60A5FA;--glow:rgba(96,165,250,.22)}
body[data-s=red]{--beam:rgba(248,113,113,.13);--accl:rgba(248,113,113,.5);--bg:#1B0C0E;--ink:#FBF1F0;--sub:#D1A5A1;--acc:#F87171;--glow:rgba(248,113,113,.24)}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(900px 460px at 15% 0%,var(--glow),transparent 70%),var(--bg);color:var(--ink);
 font:16px/1.4 Figtree,-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}
body::before{content:"";position:fixed;left:0;top:0;width:100%;height:560px;z-index:0;pointer-events:none;background:linear-gradient(100deg,var(--beam),transparent 62%);clip-path:polygon(0 8%,100% 0,100% 92%,0 36%);opacity:.9}
main,#hdr{position:relative}#hdr{position:sticky}
h1,h2,h3,.head,.card .t,.item b,.hub b,.big{font-family:Sora,Figtree,system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 20px 60px}
#hdr{position:sticky;top:0;z-index:4;background:rgba(8,18,22,.82);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border-bottom:1px solid var(--line);box-shadow:0 1px 0 var(--accl)}
#hdr[hidden]{display:none}
#hdr .bar{max-width:1100px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:8px;position:relative}
#hdr .home{flex:none;display:block;border-radius:10px;line-height:0}
#hdr .home img{width:40px;height:40px;border-radius:11px;display:block}
#hdr .name{font-weight:700;font-size:18px;margin:0 6px 0 2px;flex:none;color:var(--ink);text-decoration:none}
#hdr nav.tabs{display:flex;gap:6px;flex:1 1 auto;min-width:0;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;scrollbar-width:none;padding:2px 22px 2px 2px;-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 26px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 26px),transparent)}
#hdr nav.tabs::-webkit-scrollbar{display:none}
#hdr .grow{flex:1 1 auto}
#hdr .tab{display:flex;align-items:center;gap:8px;padding:0 14px;min-height:44px;border-radius:99px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:inherit;font-weight:600;cursor:pointer;white-space:nowrap;scroll-snap-align:start;flex:none}
#hdr .tab[aria-pressed=true]{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc) inset;background:rgba(255,255,255,.10)}
#hdr .sd{width:10px;height:10px;border-radius:99px;flex:none}
#hdr .hb{position:relative;flex:none;width:46px;height:46px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--ink);display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0}
#hdr .hb.on{border-color:var(--accl)}
#hdr .badge{position:absolute;top:-6px;right:-6px;min-width:22px;height:22px;padding:0 5px;box-sizing:border-box;border-radius:99px;background:var(--acc);color:var(--bg);font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center;border:2px solid var(--bg)}
#hdr .ver{flex:none;height:46px;padding:0 14px;border-radius:14px;border:1px solid var(--line);background:var(--card);color:var(--sub);font-size:14px;font-weight:600;cursor:pointer}
#hdr .all{max-width:1100px;margin:0 auto;padding:0 20px 8px;color:var(--sub);font-size:.9rem;overflow-wrap:anywhere}
#bell{position:absolute;z-index:7;right:20px;top:calc(100% + 8px);width:min(400px,calc(100vw - 24px));border-radius:22px;background:rgba(14,28,33,.97);border:1px solid rgba(255,255,255,.14);box-shadow:0 24px 60px rgba(0,0,0,.55);padding:8px}
#bell h3{margin:0;padding:10px 12px 6px;font-size:15px}
table.perf{width:100%;border-collapse:collapse;font-size:14px;margin:.2rem 0 .6rem}table.perf td,table.perf th{padding:.25rem .4rem;border-bottom:1px solid var(--line,#2a3442);text-align:right}table.perf td:first-child,table.perf th:first-child{text-align:left;word-break:break-all}#perfout h4{margin:.8rem 0 .2rem;font-size:14px}
#bell .nitem{display:flex;gap:14px;align-items:center;width:100%;text-align:left;padding:12px;border-radius:16px;border:0;background:transparent;color:var(--ink);font:inherit;cursor:pointer;min-height:44px}
#bell .nitem:hover{background:rgba(255,255,255,.06)}
#bell .nic{flex:none;width:44px;height:44px;border-radius:14px;display:flex;align-items:center;justify-content:center}
#bell .nitem .grow{flex:1 1 auto;min-width:0}#bell .nitem b{display:block;font-size:16px}
#bell .cta{flex:none;font-size:14px;font-weight:700}
#bell .none{padding:6px 12px 14px;color:var(--sub)}
.vfoot{display:none;text-align:center;margin:26px 0 0;font-size:12px;color:var(--sub)}
@media(max-width:700px){#hdr .ver{display:none}#hdr .name{display:none}#hdr .bar{padding:8px 12px}.vfoot{display:block}}
button,input,select,textarea{font:inherit;color:inherit}
button{cursor:pointer}
a.btn,label.btn{color:inherit;text-decoration:none;cursor:pointer;display:inline-block}
.pw{-webkit-text-security:disc;text-security:disc}
.btn,select,input[type=password],input[type=text],input[type=number],input:not([type]),textarea{padding:.6rem .9rem;border-radius:12px;border:1px solid var(--line);background:rgba(255,255,255,.07)}
.btn.pri{background:var(--acc);color:var(--bg);border:0;font-weight:700}
.btn.sm{padding:.35rem .8rem;min-height:38px}
.mnode{border-left:2px solid rgba(255,255,255,.1);padding:6px 0 6px 12px;margin:2px 0}.mnode details{margin:2px 0}.mnode summary{cursor:pointer}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px;font-weight:700;font-size:18px}
.logo{width:36px;height:36px;border-radius:10px;display:block}
.gear{width:44px;height:44px;border-radius:12px;border:1px solid var(--line);background:var(--card);display:flex;align-items:center;justify-content:center}
small,.sub{color:var(--sub)}
.head{font-size:clamp(40px,9vw,92px);line-height:1;font-weight:800;letter-spacing:-.045em;margin:34px 0 0}
.head em{font-style:normal;color:var(--acc);text-shadow:0 0 60px var(--glow)}
.lede{font-size:clamp(17px,2.4vw,22px);margin:16px 0 0;max-width:820px;color:var(--sub)}
.eyebrow{font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--sub);margin:34px 0 10px}
.item{display:flex;align-items:center;gap:14px;padding:16px 20px;border-radius:20px;background:linear-gradient(90deg,var(--glow),rgba(255,255,255,.04) 55%);border:1px solid var(--accl);margin-bottom:10px;cursor:pointer;flex-wrap:wrap}
.item .grow{flex:1 1 220px}.item .chip{align-self:flex-start;margin-top:3px}.item b{font-size:19px}
.chip{display:inline-block;padding:4px 11px;border-radius:999px;font-size:13px;font-weight:700;white-space:nowrap}
.chip.expected{background:rgba(255,255,255,.10);color:#B9C7C2}.chip.healthy{background:rgba(52,211,153,.16);color:#6EE7B7}.chip.degraded{background:rgba(251,191,36,.16);color:#FCD34D}
.chip.failed{background:rgba(248,113,113,.18);color:#FCA5A5}.chip.unknown{background:rgba(96,165,250,.18);color:#93C5FD}
.chip.pending{background:rgba(255,255,255,.1);color:var(--sub)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:30px}
.hubg{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:1rem}
.hub{text-align:left;padding:18px 20px;border-radius:20px;border:1px solid var(--line);background:var(--card);display:flex;flex-direction:column;gap:6px;min-height:104px;color:var(--ink);font:inherit;cursor:pointer}.hub b{font-size:19px}.hub small{color:var(--acc)}
.card{text-align:left;padding:22px;border-radius:26px;border:1px solid rgba(255,255,255,.11);background:linear-gradient(160deg,rgba(255,255,255,.08),rgba(255,255,255,.03));display:flex;flex-direction:column;gap:12px;min-height:130px;width:100%}
.card .r{display:flex;justify-content:space-between;align-items:center}.card .t{font-size:22px;font-weight:700;letter-spacing:-.02em;display:flex;align-items:center;gap:12px}
.tiles{display:flex;gap:14px;margin-top:30px;flex-wrap:wrap}
.tile{flex:1 1 180px;padding:16px 20px;border-radius:20px;background:var(--card);border:1px solid var(--line)}
.tile b{display:block;font:800 38px/1.1 Sora,Figtree,sans-serif;letter-spacing:-.03em}.tile span{font-size:14px;color:var(--sub)}
.strip{display:flex;gap:3px;height:26px;align-items:flex-end;margin:2px 0}.strip:empty{display:none}.strip:not(:empty){cursor:pointer}
#tsheet{position:fixed;z-index:8;left:50%;top:50%;transform:translate(-50%,-50%);width:min(560px,calc(100vw - 24px));max-height:78vh;display:flex;flex-direction:column;border-radius:24px;background:rgba(14,28,33,.98);border:1px solid rgba(255,255,255,.16);box-shadow:0 30px 80px rgba(0,0,0,.65);padding:18px 18px 14px}
#tsheet h3{margin:0;font-size:20px}#tsheet .rows{overflow:auto;margin:10px 0;-webkit-overflow-scrolling:touch}
#tsheet .tr,#hp-list .tr{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid rgba(255,255,255,.08)}#tsheet .tr .dot,#hp-list .tr .dot{margin-top:7px}
#tsheet .tr b,#hp-list .tr b{display:block}#hp-list .tr .sub{display:block}#hp-list .tr:first-child{border-top:0}#tsheet .note,#hp-list .note{margin:0 0 10px;font-size:13px;color:var(--sub)}
.strip i{flex:1 1 0;border-radius:3px;height:100%;background:rgba(255,255,255,.10)}
.strip i.healthy{background:#34D399;height:58%;opacity:.8}.strip i.degraded{background:#FBBF24}.strip i.failed{background:#F87171}.strip i.unknown{background:#60A5FA;height:70%;opacity:.7}.strip i.none{height:14%}
.cico{flex:none;width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.08);color:var(--acc)}
.card .big{font-size:30px;font-weight:800;letter-spacing:-.02em}
.seg{display:inline-flex;border-radius:12px;border:1px solid var(--line);overflow:hidden;height:44px}
.seg button{padding:0 16px;border:0;background:transparent;color:var(--sub);min-height:44px}
.seg button[aria-pressed=true]{background:var(--acc);color:var(--bg);font-weight:700}
.grid.dense{display:flex;gap:16px;align-items:flex-start}
.grid.dense .col{flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:16px}
.grid.dense .card{min-height:0}
.fld{display:flex;flex-direction:column;gap:6px;flex:1 1 220px;min-width:0}.fld>label{font-size:14px;color:var(--sub)}
.fld input,.fld select{min-height:52px;font-size:17px;width:100%;box-sizing:border-box}
.fm{display:flex;flex-wrap:wrap;gap:14px;margin:.9rem 0}
.devrow.srv.open{background:rgba(255,255,255,.04);border-radius:14px;padding:12px 14px;margin:6px 0}.srvbody{margin-top:.4rem}.devrow{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 0;border-top:1px solid rgba(255,255,255,.07)}.devrow .grow{flex:1 1 220px;min-width:0}
.okbox,.badbox{padding:14px 16px;border-radius:14px;margin:.8rem 0}
.okbox{background:rgba(52,211,153,.10);border:1px solid rgba(52,211,153,.35)}.badbox{background:rgba(248,113,113,.10);border:1px solid rgba(248,113,113,.4)}
.btn.big{min-height:52px;font-size:17px}
.det{display:block;cursor:default;min-height:0;padding:16px 18px}
.det .hd{display:flex;justify-content:space-between;align-items:center;width:100%;border:0;background:none;padding:0;text-align:left}
.det .rows{margin-top:6px;display:flex;flex-direction:column}
.rw{display:flex;align-items:center;gap:10px;min-height:44px;width:100%;padding:2px 0;border:0;border-top:1px solid rgba(255,255,255,.07);background:none;text-align:left}
.rw .nm{flex:1 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rw .dt{color:var(--sub);flex:0 1 auto;max-width:55%;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right;font-size:14px}
.rw .cv{color:var(--sub);flex:none;transition:transform .15s}.rw[aria-expanded=true] .cv{transform:rotate(90deg)}
.rw.sub1{min-height:40px}
.rw.two{align-items:flex-start;padding:8px 0}.rw.two .dot{margin-top:7px}
.rw.two .tx{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.rw.two .tx .dt{max-width:100%;white-space:normal;text-align:left;flex:none}
.hbar{position:relative;height:8px;border-radius:4px;background:rgba(255,255,255,.08);overflow:hidden;margin:6px 0 2px}.hbar i{position:absolute;top:0;bottom:0}
.hbar i.healthy{background:#34D399}.hbar i.degraded{background:#FBBF24}.hbar i.failed{background:#F87171}.hbar i.unknown{background:#60A5FA}
.dot{width:10px;height:10px;border-radius:99px;flex:none;background:rgba(255,255,255,.3)}
.dot.expected{background:#9BB5AD}.dot.healthy{background:#34D399}.dot.degraded{background:#FBBF24}.dot.failed{background:#F87171}.dot.unknown{background:#60A5FA}
.svcrow{display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid rgba(255,255,255,.07)}.svcrow.sub2{padding-left:28px}
.ico{width:40px;height:40px;border-radius:11px;flex:none;display:flex;align-items:center;justify-content:center;background:#e7eef2;color:#07111f;font-weight:800;font-size:14px;overflow:hidden;text-decoration:none;padding:6px;border:1px solid rgba(255,255,255,.1)}.ico img{width:100%;height:100%;object-fit:contain}
.svcrow .grow{flex:1 1 auto;min-width:0}.svcrow a.open{font-size:20px;text-decoration:none;padding:6px 10px}.svcenv{margin:18px 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.7}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:5}
.camgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(clamp(200px,31%,560px),1fr));gap:10px;margin:12px 0}   /* the pictures grow with the panel */
.dgrip{position:sticky;top:0;width:18px;height:100vh;margin:-20px 0 calc(20px - 100vh) -20px;cursor:ew-resize;touch-action:none;z-index:2}.dgrip::after{content:'';position:absolute;left:6px;top:50%;height:44px;width:4px;margin-top:-22px;border-radius:2px;background:var(--line)}
.cam{margin:0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--card);cursor:pointer}
.cam.big{grid-column:1/-1}.cam .ph{position:relative;aspect-ratio:16/9;background:#0004}.cam img{width:100%;height:100%;object-fit:cover;display:block}
.cam .nop{position:absolute;inset:0;display:none;align-items:center;justify-content:center;color:var(--sub)}.cam .ph.none .nop,.cam.off .nop{display:flex}.cam.off img,.cam .ph.none img{display:none}
.cam figcaption{padding:8px 10px}.camctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0}.camctl select{min-height:44px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--fg);padding:0 10px;font:inherit}
.cam video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;background:#000;display:block}.cam .ls{position:absolute;left:8px;bottom:8px;background:#000a;color:#fff;border-radius:999px;padding:3px 10px;font-size:13px;max-width:calc(100% - 16px)}.cam .ls.ok::before{content:'● ';color:#4ade80}.cam .gl{margin-top:6px}
.drawer{position:fixed;right:0;top:0;bottom:0;width:min(var(--dw,520px),100%);background:var(--bg);border-left:1px solid var(--line);z-index:6;overflow:auto;padding:20px}
.node{padding:14px 0;border-top:1px solid var(--line)}.rw.note .dt,.checks .note{color:#E7B94A}.node.inl{border-top:0;padding:2px 0 12px 58px}.node.inl.sub2{padding-left:86px}.svcrow.on{border-bottom:0}
.checks{margin:8px 0 0;padding:0;list-style:none;font-size:14px;color:var(--sub)}
.checks li{display:flex;gap:8px;flex-wrap:wrap;padding:3px 0}
.ribbon{white-space:nowrap;background:var(--acc);color:var(--bg);font-weight:800;font-size:12px;padding:3px 9px;border-radius:999px;letter-spacing:.08em}
.err{padding:12px 16px;border-radius:14px;background:rgba(248,113,113,.15);margin-top:20px}
.row{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
#alset code{overflow-wrap:anywhere;word-break:break-all}
.busybar{height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin-top:.5rem}.busybar i{display:block;height:100%;width:35%;border-radius:3px;background:var(--accent,#2dd4a8);animation:busyslide 1.2s ease-in-out infinite}
@keyframes busyslide{0%{margin-left:-35%}100%{margin-left:100%}}
@media (prefers-reduced-motion:reduce){.busybar i{animation:none;width:100%;opacity:.5}}
.box{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem;margin:.75rem 0}
textarea{width:100%;min-height:260px;font:13px/1.4 ui-monospace,Menlo,monospace}
.lg-bar{display:flex;gap:.5rem;flex-wrap:wrap;padding:.6rem 0}
.lg-bar select,.lg-bar input{min-height:44px;flex:1 1 9rem;min-width:0}
.lg-bar input{flex:2 1 12rem;-webkit-appearance:none;appearance:none;background:rgba(255,255,255,.07);border:1px solid var(--line);border-radius:12px;color:inherit;padding:.6rem .9rem}
#lg-nw{position:sticky;top:72px;height:0;z-index:3;text-align:center}
#lg-new{margin:.2rem auto;box-shadow:0 4px 18px rgba(0,0,0,.5)}
#lg-new[hidden],#lg-menu[hidden]{display:none}
.lg-day{margin:1rem 0 .2rem;font-size:13px;color:var(--sub);text-transform:uppercase;letter-spacing:.04em}
.lg-l{display:grid;grid-template-columns:auto auto 1fr;gap:.1rem .6rem;align-items:baseline;padding:.55rem .1rem;border-bottom:1px solid var(--line);cursor:pointer;min-height:44px}
.lg-l .lg-x{grid-column:1/-1;font-size:15px;overflow-wrap:anywhere}
.lg-l:not(.open) .lg-x{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lg-t{font-variant-numeric:tabular-nums;color:var(--sub);font-size:13px}
.lg-s{color:var(--sub);font-size:13px;text-align:right}
.lg-lv{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;padding:.05rem .4rem;border-radius:99px;border:1px solid var(--line)}
.lg-lv.warning{color:#FBBF24;border-color:#FBBF24}.lg-lv.error{color:#F87171;border-color:#F87171}.lg-lv.debug{color:var(--sub)}
.lg-d{grid-column:1/-1;font-size:13px;color:var(--sub);padding-top:.3rem}
.lg-l.open{background:rgba(255,255,255,.05);border-left:3px solid var(--sub);padding-left:.5rem}
.lg-c{font-style:normal;color:var(--sub);font-size:11px}
</style><body><header id=hdr hidden></header><main id=m>Loading…</main><div id=dr></div><script>
const $=s=>document.querySelector(s);
/* Sites: with another site's tab picked, every call except these goes to that site through the main box (/api/site/<id>/…) */
let SITE=(()=>{try{return localStorage.getItem('mb-site')||''}catch(e){return ''}})(),siCfg=null,siTimer=null,siPoll=null,locBanner=null;
const LOCAL_API=/^(health|state|display|sites|login|logout|setup)(\/|\?|$)/;
const apiPath=p=>SITE&&!LOCAL_API.test(p)?'site/'+SITE+'/'+p:p, U=p=>'/api/'+apiPath(p);
async function api(path,body){if(body!==undefined)SXC=null;let r;try{r=await fetch(U(path),body===undefined?{}:{method:'POST',
 headers:{'Content-Type':'application/json','X-MB':'1'},body:JSON.stringify(body)})}finally{if(body!==undefined)SXC=null}   /* cleared again once the change is done: a read that started while a slow change ran (a full backup) must not leave the old answer behind */
 let j={};try{j=await r.json()}catch(e){} if(!r.ok)throw Object.assign(new Error(j.error||r.status),{status:r.status,data:j});return j}
/* a read that must not hang: Settings asks for nine things at once and waits for all of them, so one request stuck on a dead connection (after the box restarted, or behind a proxy)
   held the page for as long as the browser cared to wait. It gives up after APIQ_MS and asks once more, on a fresh connection. Only for plain reads, never for a change. */
let APIQ_MS=window.APIQ_MS||12000;
async function apiq(path){const once=async()=>{const ac=new AbortController(),t=setTimeout(()=>ac.abort(),window.APIQ_MS||APIQ_MS);
  try{const r=await fetch(U(path),{signal:ac.signal});let j={};try{j=await r.json()}catch(e){}if(!r.ok)throw Object.assign(new Error(j.error||r.status),{status:r.status,data:j});return j}finally{clearTimeout(t)}};
 try{return await once()}catch(e){if(e&&e.status)throw e;return await once()}}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const SDOT={green:'#34d399',yellow:'#fbbf24',red:'#f87171',blue:'#60a5fa',unknown:'#7a8699'};
function siteTabs(){const c=siCfg;if(!c||!c.sites.length)return[];
 const here=(SITE===''&&snap&&snap.banner)||locBanner;
 return [{id:'',name:c.name||c.nameDefault,st:here?here.status:'unknown',head:here?here.headline:'checking…'}].concat(c.sites.map(s=>{const l=s.link||{};
  const cn=snap&&snap.nodes&&snap.nodes['site-'+s.id],cs=cn?ds(cn,cn.state):'';
  if(cs==='failed')return {id:s.id,name:s.name,st:'red',head:'Down'};  /* this box's own check says that site is down: that wins over its last report */
  const w=cs==='degraded'?{st:'yellow',head:'Link trouble'}:null;
  if(l.state==='linked'&&l.banner){const r={red:3,yellow:2,blue:1,green:0};return w&&(r[l.banner.status]||0)<2?{id:s.id,name:s.name,st:w.st,head:w.head}:{id:s.id,name:s.name,st:l.banner.status,head:l.banner.headline}}
  return {id:s.id,name:s.name,st:'unknown',head:'Unknown'+(l.lastSeen?' · last heard '+siAgo(l.lastSeen):''),unk:1}}))}
function renderTabs(){renderHeader()}
/* ---------- the header: on every page once signed in. Mark (home), site tabs that swipe, the bell, the version, Settings ---------- */
let SXC=null,rsTok=0,UPDCHK=0,LASTV='';
let PERFTXT='';
async function perfRun(){const out=$('#perfout');if(!out)return;out.innerHTML='<p class=sub>Measuring…</p>';$('#perfcopy').hidden=true;
 const med=async p=>{const a=[];for(let i=0;i<3;i++){const t=performance.now();try{await api(p)}catch(e){}a.push(performance.now()-t)}a.sort((x,y)=>x-y);return Math.round(a[1])};
 const rows=[['reach this box (no work)','health'],['status','state'],['versions','versions'],['monitoring','config/monitoring'],['about','about'],['alerts','alerts']];
 const mine=[];for(const [l,p] of rows)mine.push([l,await med(p)]);
 let P=null,err='';try{P=await api('perf')}catch(e){err=e.message}
 const nm=(siteTabs().find(t=>t.id===SITE)||{}).name||'this box',L=[`MonitorBox performance · ${nm} · ${new Date().toLocaleString([],Object.assign({},tzo()))}${P?' · v'+P.version:''}`,
  'From this browser, median of 3 (ms): '+mine.map(x=>x[0]+' '+x[1]).join(' · ')];
 let h=`<h4>From this browser (ms, median of 3)</h4><table class=perf>${mine.map(x=>`<tr><td>${esc(x[0])}</td><td>${x[1]}</td></tr>`).join('')}</table>`;
 if(P){const tb=(t,r)=>r.length?`<h4>${t}</h4><table class=perf><tr><th></th><th>n</th><th>avg</th><th>p95</th><th>max</th></tr>${r.slice(0,12).map(x=>`<tr><td>${esc(x.key)}</td><td>${x.count}</td><td>${x.avgMs}</td><td>${x.p95Ms}</td><td>${x.maxMs}</td></tr>`).join('')}</table>`:'';
  h+=tb('Requests the box handled (ms)',P.requests)+tb('Calls to modules (ms)',P.modules);
  h+=`<h4>Memory (MB, fair share)</h4><table class=perf>${P.processes.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.mb}</td></tr>`).join('')}</table>`+(P.about&&P.about.containerMb!=null?`<small class=sub>Container total ${P.about.containerMb} MB (file cache not counted) · ${P.cpus} CPUs</small>`:'');
  L.push('Requests handled (n / avg / p95 / max ms): '+P.requests.slice(0,12).map(x=>`${x.key} ${x.count}/${x.avgMs}/${x.p95Ms}/${x.maxMs}`).join(' · '));
  L.push('Module calls (n / avg / p95 / max ms): '+(P.modules.slice(0,12).map(x=>`${x.key} ${x.count}/${x.avgMs}/${x.p95Ms}/${x.maxMs}`).join(' · ')||'none yet'));
  L.push('Slow module calls (over 3 s, newest first): '+((P.slow||[]).map(x=>`${x.what} ${(x.ms/1000).toFixed(1)} s, ${x.agoSec<120?x.agoSec+' s':Math.round(x.agoSec/60)+' min'} ago`).join(' · ')||'none'));
  L.push('Requests still waiting (over 1 s): '+((P.waiting||[]).map(x=>`${x.what} ${x.ageSec} s`).join(' · ')||'none'));
  L.push('Memory MB: '+P.processes.map(x=>x.name+' '+x.mb).join(' · ')+(P.about&&P.about.containerMb!=null?` · container ${P.about.containerMb}`:''))}
 else h+=`<p class=sub>The box did not give its own timings${err?' ('+esc(err)+')':''}. It may be running an older version.</p>`;
 PERFTXT=L.join('\n');out.innerHTML=h;$('#perfcopy').hidden=false}
async function perfCopy(){let ok=false;try{await navigator.clipboard.writeText(PERFTXT);ok=true}catch(e){}
 const out=$('#perfout');if(ok){const b=$('#perfcopy');b.textContent='Copied';setTimeout(()=>{b.textContent='Copy'},1500)}
 else{out.insertAdjacentHTML('afterbegin',`<textarea id=perftxt readonly rows=8 style="width:100%">${esc(PERFTXT)}</textarea>`);const t=$('#perftxt');t.focus();t.select()}}
/* Settings, Advanced: what the switches say about their ports and neighbours. Read-only; the copy is what the LAN map gets designed from. */
let LANTXT='';
async function lanRun(){const out=$('#lanout');if(!out)return;out.innerHTML='<p class=sub>Asking the switches… this takes a few seconds.</p>';$('#lancopy').hidden=true;
 let R=null,err='';try{R=await api('lan/report')}catch(e){err=e.message}
 if(!R){out.innerHTML=`<p class=sub>The box could not make the report${err?' ('+esc(err)+')':''}. It may be running an older version.</p>`;return}
 const nm=(siteTabs().find(t=>t.id===SITE)||{}).name||'this box';let h='';
 if(!R.sources.length)h='<p class=sub>No UniFi or SNMP connection is set up yet, so there is nothing to ask.</p>';
 for(const x of R.sources){const r=x.report;
  if(!r){h+=`<p class=sub><b>${esc(x.connection)}</b> (${x.module==='snmp'?'SNMP':'UniFi'}): ${esc(x.error||'no answer')}</p>`;continue}
  if(x.module==='snmp')h+=`<p class=sub><b>${esc(x.connection)}</b> (SNMP${r.sysName?' · '+esc(r.sysName):''}): ${r.ports.length} ports in use, ${r.downPorts||0} down${(r.notes||[]).length?' · '+esc(r.notes.join('; ')):''}</p>`;
  else{const ds=r.devices||[];h+=`<p class=sub><b>${esc(x.connection)}</b> (UniFi): ${ds.length} devices, ${ds.reduce((a,d)=>a+d.ports.length,0)} ports in use${r.clients?', '+r.clients.length+' clients':(r.clientsNote?' · no client list ('+esc(r.clientsNote)+')':'')}</p>`}}
 LANTXT=JSON.stringify({report:'MonitorBox switch report',site:nm,when:new Date().toISOString(),sources:R.sources});
 out.innerHTML=h;$('#lancopy').hidden=!R.sources.length}
async function lanCopy(){let ok=false;try{await navigator.clipboard.writeText(LANTXT);ok=true}catch(e){}
 const out=$('#lanout');if(ok){const b=$('#lancopy');b.textContent='Copied';setTimeout(()=>{b.textContent='Copy'},1500)}
 else{out.insertAdjacentHTML('afterbegin',`<textarea id=lantxt readonly rows=8 style="width:100%">${esc(LANTXT)}</textarea>`);const t=$('#lantxt');t.focus();t.select()}}
/* Settings, Advanced: what the gateway says about its flows (the data behind UniFi's Insights, Flows page). Read-only; the copy is what the flows list gets designed from. */
let FLOWTXT='';
async function flowRun(){const out=$('#flowout');if(!out)return;out.innerHTML='<p class=sub>Asking the gateway… this takes a few seconds.</p>';$('#flowcopy').hidden=true;
 let R=null,err='';try{R=await api('lan/flows-look')}catch(e){err=e.message}
 if(!R){out.innerHTML=`<p class=sub>The box could not make the report${err?' ('+esc(err)+')':''}. It may be running an older version.</p>`;return}
 const nm=(siteTabs().find(t=>t.id===SITE)||{}).name||'this box';let h='';
 if(!R.sources.length)h='<p class=sub>No UniFi connection is set up yet, so there is nothing to ask.</p>';
 for(const x of R.sources){const r=x.report;
  if(!r){h+=`<p class=sub><b>${esc(x.connection)}</b>: ${esc(x.error||'no answer')}</p>`;continue}
  h+=`<p class=sub><b>${esc(x.connection)}</b>:<br>${(r.attempts||[]).map(a=>esc(a.request)+' → '+a.status).join('<br>')}</p>`}
 FLOWTXT=JSON.stringify({report:'MonitorBox flows look',site:nm,when:new Date().toISOString(),sources:R.sources});
 out.innerHTML=h;$('#flowcopy').hidden=!R.sources.length}
async function flowCopy(){let ok=false;try{await navigator.clipboard.writeText(FLOWTXT);ok=true}catch(e){}
 const out=$('#flowout');if(ok){const b=$('#flowcopy');b.textContent='Copied';setTimeout(()=>{b.textContent='Copy'},1500)}
 else{out.insertAdjacentHTML('afterbegin',`<textarea id=flowtxt readonly rows=8 style="width:100%">${esc(FLOWTXT)}</textarea>`);const t=$('#flowtxt');t.focus();t.select()}}
let hdrInfo={ver:''},hdrSites={},bellOpen=false,hdrSig='';
const HI={bell:'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9 M10.3 21a1.9 1.9 0 0 0 3.4 0',box:'M21 8l-9-5-9 5v8l9 5 9-5V8z M3.3 7.5L12 12l8.7-4.5 M12 12v9',down:'M12 3v12 M7 10l5 5 5-5 M4 20h16',
 cog:'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z'};
const hico=d=>`<svg width=22 height=22 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="${d}"/></svg>`;
/* what the bell lists: new things found on the network, and an update that is ready. Each says where tapping it goes. */
function hdrItems(){const o=[],multi=!!(siCfg&&siCfg.sites.length);
 for(const s of (siCfg?siCfg.sites:[])){const n=snap&&snap.nodes&&snap.nodes['site-'+s.id],st=n?ds(n,n.state):'';  /* a paired site that is down or not answering */
  if(st==='failed'||st==='degraded')o.push({id:'sitedown'+s.id,site:s.id,icon:HI.bell,tint:st==='failed'?'rgba(248,113,113,.18)':'rgba(251,191,36,.18)',ink:st==='failed'?'#FCA5A5':'#FCD34D',title:s.name+(st==='failed'?' is down':' has link trouble'),sub:n.detail||'',cta:'Look',go:'#/'})}
 for(const t of (siteTabs().length?siteTabs():[{id:'',name:''}])){const d=hdrSites[t.id];if(!d||t.unk)continue; /* a site that is not answering adds nothing: silence stays Unknown */
  const pre=multi?t.name+': ':'',fu=d.fu,p=d.pend,nf=fu.reduce((a,x)=>a+(x.labels?x.labels.length:1),0); /* things, not offers: three containers from one machine are 3 */
  if(fu.length)o.push({id:'fu'+t.id,site:t.id,icon:HI.box,tint:'rgba(52,211,153,.18)',ink:'#6EE7B7',title:pre+(nf===1?'1 new thing found':nf+' new things found'),sub:[...new Set(fu.map(x=>x.on?'On '+x.on:x.title))].slice(0,3).join(', ')+(fu.length>3?' and '+(fu.length-3)+' more':''),cta:'Set up',go:'#/settings/servers'});
  if(p)o.push({id:'upd'+t.id,site:t.id,icon:HI.down,tint:'rgba(96,165,250,.20)',ink:'#93C5FD',title:pre+(p.target?'Update '+p.target+' is ready':'An update is ready'),sub:p.what,cta:'Update',go:'#/settings/updates'});
  for(const a of d.auto||[])o.push(a.kind==='problem'?{id:'auto'+t.id+a.id,site:t.id,icon:HI.bell,tint:'rgba(248,113,113,.18)',ink:'#FCA5A5',title:pre+a.text,sub:'MonitorBox itself had trouble. The log has the details.',cta:'Logs',go:a.go||'#/logs',seen:a.id}:{id:'auto'+t.id+a.id,site:t.id,icon:HI.down,tint:'rgba(52,211,153,.18)',ink:'#6EE7B7',title:pre+a.text,sub:'',cta:'OK',go:'#/settings/updates',seen:a.id});
  if(d.img)o.push({id:'img'+t.id,site:t.id,icon:HI.down,tint:'rgba(251,191,36,.18)',ink:'#FCD34D',title:pre+'The container image needs updating',sub:'Re-pull it to get the newest base.',cta:'How',go:'#/settings/updates'})}
 return o}
function renderHeader(){const h=$('#hdr');if(!h||h.hidden)return;
 const ts=siteTabs(),items=hdrItems(),n=items.length;
 const rank={red:3,yellow:2,blue:1,green:0},bad=ts.filter(x=>!x.unk&&(rank[x.st]||0)>0),unk=ts.filter(x=>x.unk);
 const all=bad.length||unk.length?bad.concat(unk).map(x=>x.name+': '+x.head).join(' · '):'';
 const sig=JSON.stringify([ts,all,items.map(x=>[x.id,x.title,x.sub]),hdrInfo.ver,bellOpen,SITE]);if(sig===hdrSig)return;hdrSig=sig;
 const old=h.querySelector('nav.tabs'),sl=old?old.scrollLeft:0;
 const tabs=ts.length?`<nav class=tabs aria-label="Sites, swipe sideways">${ts.map(x=>`<button class=tab aria-pressed=${x.id===SITE} onclick="setSite('${esc(x.id)}')" title="${esc(x.head)}"><span class=sd style="background:${SDOT[x.st]||SDOT.unknown}"></span>${esc(x.name)}</button>`).join('')}</nav>`:'<span class=grow></span>';
 const bell=bellOpen?`<section id=bell aria-label=Notifications><h3>${n?'New for you':'Notifications'}</h3>${n?items.map((x,i)=>`<button class=nitem onclick="bellGo(${i})"><span class=nic style="background:${x.tint}"><svg width=22 height=22 viewBox="0 0 24 24" fill=none stroke="${x.ink}" stroke-width=2 stroke-linecap=round stroke-linejoin=round aria-hidden=true><path d="${x.icon}"/></svg></span><span class=grow><b>${esc(x.title)}</b><span class=sub>${esc(x.sub)}</span></span><span class=cta style="color:${x.ink}">${esc(x.cta)} ›</span></button>`).join(''):'<p class=none>Nothing new. New servers and cameras MonitorBox finds, and updates, show up here.</p>'}</section>`:'';
 h.innerHTML=`<div class=bar><a class=home href="#" onclick="goHome();return false" aria-label="MonitorBox: back to the main screen"><img src=/favicon.svg alt="" width=40 height=40></a><a class=name href="#" onclick="goHome();return false">MonitorBox</a>${tabs}
  <button class="hb${bellOpen?' on':''}" id=bellbtn aria-label="Notifications${n?', '+n+' new':''}" aria-expanded=${bellOpen} onclick="toggleBell(event)">${hico(HI.bell)}${n?`<span class=badge>${n}</span>`:''}</button>
  <button class=ver aria-label="Version ${esc(hdrInfo.ver)}, open the Versions page" onclick="location.hash='#/settings/updates'">${hdrInfo.ver?'v'+esc(hdrInfo.ver):'…'}</button>
  <button class=hb aria-label=Settings onclick="location.hash='#/settings'">${hico(HI.cog)}</button>${bell}</div>${all?`<div class=all>${esc(all)}</div>`:''}`;
 const nv=h.querySelector('nav.tabs');if(nv)nv.scrollLeft=sl}
function hdrReveal(){const nv=document.querySelector('#hdr nav.tabs'),a=nv&&nv.querySelector('.tab[aria-pressed=true]');if(a)nv.scrollLeft=a.offsetLeft-(nv.clientWidth-a.offsetWidth)/2}
function goHome(){bellOpen=false;if(location.hash){location.hash=''}else{if(drawer||svcOpen)closeDrawer();scrollTo(0,0);renderHeader()}}
function toggleBell(e){if(e)e.stopPropagation();bellOpen=!bellOpen;renderHeader()}
function bellGo(i){const x=hdrItems()[i];bellOpen=false;if(x&&x.seen){const d=hdrSites[x.site];if(d)d.auto=(d.auto||[]).filter(a=>a.id!==x.seen);fetch((x.site?'/api/site/'+x.site+'/':'/api/')+'updates/seen',{method:'POST',headers:{'Content-Type':'application/json','X-MB':'1'},body:JSON.stringify({ids:[x.seen]})}).catch(()=>{})} /* a note about an update that already happened: tapping it clears it */ if(x&&x.site!==SITE)setSite(x.site);renderHeader();if(x)location.hash=x.go}
/* pointerdown, not click: iPad Safari sends no click for a tap on plain page background, so a click listener never saw those taps */
addEventListener('pointerdown',e=>{if(bellOpen&&!e.target.closest('#bell,#bellbtn')){bellOpen=false;renderHeader()}},true);
addEventListener('keydown',e=>{if(e.key==='Escape'&&bellOpen){bellOpen=false;renderHeader();const b=$('#bellbtn');if(b)b.focus()}});
addEventListener('hashchange',()=>{if(bellOpen){bellOpen=false;renderHeader()}});
/* the version and the two things the bell can list; the versions page is already cached on the box, so asking is cheap */
/* a module is waiting for the owner only when it is already installed and has a newer version (the same rule the box uses to update by itself); a module that is not installed is never offered here */
const modWaiting=c=>!!(c.needsApply&&c.target&&!(c.failed||[]).includes(c.target)&&(c.running||c.installed));
async function hdrOne(id){const pre='/api/'+(id?'site/'+id+'/':'');
 const g=async p=>{const r=await fetch(pre+p);if(!r.ok)throw new Error(r.status);return r.json()};
 const [v,f]=await Promise.all([g('versions'),g('followups').catch(()=>({suggestions:[]}))]);
 const mods=Object.entries(v.modules||{}).filter(([k,c])=>modWaiting(c)),appUp=v.app&&v.app.needsApply&&v.app.target&&!(v.app.failed||[]).includes(v.app.target);
 return {ver:v.version||'',auto:(v.autoNotes||[]).map(x=>({id:x.id,text:x.text,kind:x.kind,go:x.go})),img:!!(v.image&&v.image.outdated),fu:(f.suggestions||[]).map(x=>({title:x.title,on:x.on,labels:x.labels})),pend:(appUp||mods.length)?{target:appUp?v.app.target:'',what:appUp?'MonitorBox itself'+(mods.length?' and '+mods.length+' module'+(mods.length==1?'':'s'):''):mods.length+' module'+(mods.length==1?'':'s')+' ready to install'}:null}}
/* the bell covers every site: ask this box and each linked site (through the pass-through) once a minute. A site that fails to answer keeps its last answer out of the bell; it is simply left out. */
let hdrRun=null,hdrAgain=false,rowSig='';
/* One round at a time. Asked again while one is running, it runs one more round straight after (what was asked for may have changed since the running one began) and the caller waits for that. */
function hdrPoll(){if(($('#hdr')||{}).hidden)return Promise.resolve();if(hdrRun){hdrAgain=true;return hdrRun}
 hdrRun=(async()=>{try{do{hdrAgain=false;await hdrPollNow()}while(hdrAgain)}finally{hdrRun=null}})();return hdrRun}
const remoteWaitingNow=()=>((siCfg&&siCfg.sites)||[]).filter(x=>(x.link||{}).state==='linked'&&hdrSites[x.id]&&hdrSites[x.id].pend).map(x=>x.id).join();
async function hdrPollNow(){
 const ids=[''].concat(((siCfg&&siCfg.sites)||[]).filter(s=>(s.link||{}).state==='linked').map(s=>s.id));
 const res=await Promise.all(ids.map(id=>hdrOne(id).then(d=>[id,d],()=>[id,null])));
 const next={};for(const [id,d] of res)if(d)next[id]=d;
 hdrSites=next;const cur=next[SITE];if(cur){hdrInfo={ver:cur.ver};fuN=cur.fu.length}
 renderHeader();
 if(location.hash.startsWith('#/settings/updates')&&rowSig!==''&&rowSig!==remoteWaitingNow())renderSettings().catch(()=>{})}   /* the buttons on the Updates page follow what the sites say, without a tab switch */
/* every 15 seconds while the page is in front, and at once when it comes back to the front; a page nobody is looking at asks nothing. A round that is still waiting on a slow site is not started twice. */
setInterval(()=>{if(!document.hidden&&!hdrRun)hdrPoll()},15000);
addEventListener('visibilitychange',()=>{if(!document.hidden)hdrPoll()});
async function refreshSites(){try{siCfg=await api('sites')}catch(e){siCfg=null}
 {const want=SITE;let j=null;if(want){try{const r=await fetch('/api/site/'+want+'/site-links');if(r.ok)j=await r.json()}catch(e){}}   /* the site being looked at tells which boxes it is paired with: its own side of the pairing */
  if(want===SITE&&JSON.stringify(j)!==JSON.stringify(siRemote)){siRemote=j;if(snap&&typeof render==='function')try{render()}catch(e){}}}
 if(siCfg&&SITE&&!siCfg.sites.some(s=>s.id===SITE)){SITE='';try{localStorage.removeItem('mb-site')}catch(e){};closeStream();route()}
 if(siCfg){try{const r=await fetch('/api/status');if(r.ok)locBanner=(await r.json()).banner}catch(e){}}
 renderTabs()}
function liveReset(){for(const k of [...lv.keys()])stopLive(k);if(hub){try{hub.close()}catch(e){}hub=null}hubWait=null;liveQ=[]}
function setSite(id){if(id===SITE)return;liveReset();SITE=id;siRemote=null;try{id?localStorage.setItem('mb-site',id):localStorage.removeItem('mb-site')}catch(e){}
 closeStream();BOXTZ='';loadTz();for(const k in hist)delete hist[k];camLive.clear();
 /* everything the screens fetched belongs to the site they were fetched from: forget it, so the other site's screens load their own */
 grCfg=[];grData=null;bzData=null;bzPanel=null;flPanel=null;grLoaded=0;grPick=null;alCfg=null;cams=null;camT=0;box=null;setupConns=[];setupMon=null;setupRev=0;scans={};openCards.clear();
 try{sessionStorage.removeItem('mb-sx')}catch(e){}
 renderTabs();hdrInfo={ver:''};hdrPoll();hdrReveal();route();if(id)refreshSites()}   /* fetch the other site's pairings now, not at the next 10 s round, so its card is complete on first open */
function remoteDown(name,msg){snap=null;lastJson='';$('#m').innerHTML=`<div class=box><h2 style="margin-top:0">${esc(name)} is not answering from here</h2><p>${esc(msg)}</p><p class=sub>That does not mean it is down: ${esc(name)} keeps running and alerting on its own. This screen comes back by itself when it answers. Use the tabs above to go to another site.</p></div>`}
let drawerSig='',svcTop='',svcPrev=[],ICONS=null,view=getView(),lastTouch=0,deferred=null,drawerTop=0,snap=null,live=false,lastEvent=0,es=null,drawer=null,svcOpen=false,lastJson='';
const chip=(st,label)=>`<span class="chip ${esc(st)}">${esc(label)}</span>`;
function ago(ms){const s=Math.max(0,Math.round(ms/1000));if(s<10)return'just now';if(s<60)return s+' s ago';const m=Math.round(s/60);return m<60?m+' min ago':Math.round(m/60)+' h ago'}
function dur(iso){if(!iso)return'';const s=Math.max(0,(Date.now()-Date.parse(iso))/1000);if(s<60)return'just now';const m=Math.floor(s/60);
 return m<60?m+' min':m<1440?Math.floor(m/60)+' h '+(m%60)+' min':Math.floor(m/1440)+' d'}
function since(label,iso){return iso?`${esc(label)} ${esc(dur(iso))}`:''}

/* ---------- sign in ---------- */
async function boot(){
 const hd=$('#hdr');if(hd)hd.hidden=true;let h;try{h=await api('health')}catch(e){$('#m').textContent='MonitorBox is starting…';return setTimeout(boot,2000)}
 if(h.version&&window.__v&&window.__v!==h.version)return location.reload(); if(h.version)window.__v=h.version;  // App was updated: load its new page
 if(!h.passwordSet)return welcome();
 try{await api('state')}catch(e){return mpage().innerHTML=`<h1 class=head style="font-size:44px">MonitorBox</h1><div class=box>${h.passkeyOnly?'<p class=sub style="margin-top:0">From outside your home network, sign in with a passkey.</p>':`<form id=f class=row>
  <input id=p type=password placeholder=Password autocomplete=current-password><button class="btn pri">Sign in</button></form>`}${h.passkeys?`<div class=row style="margin-top:.6rem"><button class="btn${h.passkeyOnly?' pri':''}" id=pk onclick="passkeySignIn()">Sign in with a passkey</button></div>`:''}<p id=e></p></div>`,
  $('#f')&&($('#f').onsubmit=async ev=>{ev.preventDefault();try{await api('login',{password:$('#p').value});boot()}catch(e){$('#e').textContent=e.status===429||e.status===403?e.message:'Wrong password'}})}
 await seedDisplay();loadTz();view=getView();$('#hdr').hidden=false;hdrSig='';hdrPoll();await refreshSites();hdrReveal();clearInterval(siPoll);siPoll=setInterval(refreshSites,10000);route();pollFollowups();
}
/* the box keeps its display choices (so a restore brings them back); a device that has chosen otherwise keeps its own */
const dispT={};function saveDisplay(k,v){clearTimeout(dispT[k]);dispT[k]=setTimeout(()=>{api('display',{[k]:v}).catch(()=>{})},500)}
async function seedDisplay(){try{const d=await api('display');
 if(d.view&&lsGet('mb-view')===null)lsSet('mb-view',d.view);if(d.hist&&lsGet('mb-hist')===null)lsSet('mb-hist',d.hist);
 if(d.cammode&&lsGet('mb-cammode')===null){lsSet('mb-cammode',d.cammode);camMode=d.cammode==='live'?'live':'pics'}
 if(d.gwin&&lsGet('mb-gw')===null){lsSet('mb-gw',d.gwin);grWin=0}if(d.gpanel&&lsGet('mb-gp')===null)lsSet('mb-gp',d.gpanel);
 if(d.dw&&lsGet('mb-dw')===null)setDw(d.dw)}catch(e){}}
function route(){ if(location.hash==='#/settings/watched'){location.hash='#/settings/advanced';return} if(location.hash!=='#/settings/servers')window._ret=null; if(location.hash.startsWith('#/settings')){closeStream();renderSettings()}else if(location.hash==='#/setup/review'){closeStream();renderReview()}else if(location.hash==='#/setup'){closeStream();renderSetup()}else if(location.hash==='#/welcome'){closeStream();renderWelcome()}else if(location.hash==='#/map'){closeStream();renderMap()}else if(location.hash.startsWith('#/logs')){closeStream();renderLogs()}else{openStream()} }
addEventListener('hashchange',route);

/* ---------- live status ---------- */
function openStream(){
 if(es)return; render();
 if(SITE){const site=SITE;let stop=false,tm=null;es={close(){stop=true;clearTimeout(tm)}};
  const poll=async()=>{try{const j=await api('status');if(stop||SITE!==site)return;live=true;lastEvent=Date.now();snap=j;const sg=statusSig(JSON.stringify(j));if(sg!==lastJson){lastJson=sg;render()}else tick()}
   catch(e){if(stop||SITE!==site)return;live=false;if(e.status===401&&!e.data.unreachable){closeStream();return boot()}const s=((siCfg||{}).sites||[]).find(x=>x.id===site);remoteDown(s?s.name:'That site',e.message)}
   if(!stop)tm=setTimeout(poll,3000)};poll();return}
 es=new EventSource('/api/stream');
 es.onopen=()=>{live=true;api('health').then(h=>{if(h.version&&window.__v&&h.version!==window.__v)location.reload()}).catch(()=>{})};
 es.onmessage=ev=>{live=true;lastEvent=Date.now();const j=statusSig(ev.data);
  snap=JSON.parse(ev.data); if(j!==lastJson){lastJson=j;render()}else tick()};
 es.onerror=()=>{live=false;tick();api('state').catch(e=>{if(e.status===401){closeStream();boot()}})};
}
/* main screen: 'summary' (one tile per group) or 'detail' (every check on the page). Kept per device, because a phone and an iPad can want different ones. */
function getView(){try{return localStorage.getItem('mb-view')==='detail'?'detail':'summary'}catch(e){return 'summary'}}
const HWIN=[[3600,'1 hour','hour'],[86400,'1 day','day'],[604800,'1 week','week'],[2592000,'1 month','30 days']];
function getHWin(){try{const v=+localStorage.getItem('mb-hist');return HWIN.some(x=>x[0]===v)?v:2592000}catch(e){return 2592000}}
function setHWin(v){try{localStorage.setItem('mb-hist',v)}catch(e){};saveDisplay('hist',v);for(const k in hist)delete hist[k];renderSettings()}
function setView(v){view=v==='detail'?'detail':'summary';try{localStorage.setItem('mb-view',view)}catch(e){}saveDisplay('view',view);
 if(location.hash.startsWith('#/settings'))renderSettings();else{lastTouch=0;render()}}
const dotc=st=>`<span class="dot ${esc(st)}" aria-hidden=true></span>`;
const openN=new Set();
function toggleN(id){if(openN.has(id))openN.delete(id);else openN.add(id);lastTouch=0;render()}
/* Every check view. One line per item. Anything with several parts folds into a roll-up line ("40 checks · all good")
   that opens on tap, and opens by itself when a part is not healthy, so a problem (failed or degraded) is never hidden; a check that cannot be answered (unknown) is counted in the roll-up but does not force it open.
   Folds nest: an aggregate (Internet, DNS) holds its children, and a device groups its own checks by kind (Disks, Volumes...). */
function kindOf(c){const l=c.label||'',t=c.target||'';
 if(/^Disk/i.test(l))return'Disks'; if(/^Volume \/ shared folder/i.test(l))return'Shared folders';
 if(/^Volume/i.test(l)||t==='volume')return'Volumes'; if(/^Storage pool/i.test(l))return'Storage pools';
 if(/^RAID/i.test(l))return'RAID groups'; if(/^Interface/i.test(l)||t==='interface')return'Network ports';
 if(t==='device')return'Devices'; if(t==='tunnel')return'VPN tunnels'; return null}
/* what an aggregate shows nested under it: its own children, plus the plain checks that depend on it
   (public DNS and the web check depend on "Internet"). A child that already belongs to another aggregate stays there. */
function membersOf(n){const all=Object.values(snap.nodes),owned=new Set(all.flatMap(x=>x.kind==='aggregate'?(x.children||[]):[]));
 const own=(n.children||[]).map(id=>snap.nodes[id]).filter(Boolean);
 return own.concat(all.filter(x=>x.kind!=='aggregate'&&!owned.has(x.id)&&x.group===n.group&&(x.dependsOn||[]).includes(n.id)))}
const ds=(n,st)=>n.muted&&st!=='healthy'&&st!=='pending'?'expected':st;   // expected down shows grey; the observed state stays in the data
const padOf=d=>d?` style="padding-left:${d*20}px"`:'';
function line(go,st,name,dt,d,note){dt=dt||'';const nt=note?' note':'';   // note: fine, but worth a line (a busy CPU): the text turns amber, the light stays green
 return (dt.length>34||name.length+dt.length>34)?`<button class="rw two${nt}${d?' sub1':''}"${padOf(d)} onclick="${go}">${dotc(st)}<span class=tx><span class=nm>${esc(name)}</span><span class=dt>${esc(dt)}</span></span></button>`
  :`<button class="rw${nt}${d?' sub1':''}"${padOf(d)} onclick="${go}">${dotc(st)}<span class=nm>${esc(name)}</span><span class=dt>${esc(dt)}</span></button>`}
function fold(key,st,name,states,inner,d,bold,unit){
 const good=states.filter(x=>x==='healthy'||x==='pending'||x==='expected').length, bad=states.length-good, open=openN.has(key)||states.some(x=>x==='failed'||x==='degraded');   // a check still waiting for its first answer is not a problem, and neither is one that simply cannot be checked (it opens when tapped, but is not forced open)
 const roll=bad?`${good} of ${states.length} good · ${bad} need a look`:`${states.length} ${unit||'checks'} · all good`;
 const nm=bold?`<b>${esc(name)}</b>`:esc(name),two=name.length+roll.length>34;      // a long name gets its own line so it is not cut off
 return `<button class="rw${two?' two':''}${d?' sub1':''}" aria-expanded=${open}${padOf(d)} onclick="toggleN('${esc(key)}')">${dotc(st)}${two?`<span class=tx><span class=nm>${nm}</span><span class=dt>${esc(roll)}</span></span>`:`<span class=nm>${nm}</span><span class=dt>${esc(roll)}</span>`}<span class=cv aria-hidden=true>›</span></button>${open?inner():''}`}
/* A paired site on the main screen: one line with its name and how the link is; tapping it shows the site's internet address and the address this box connects to
   (one line when they are the same, as when the site's router forwards the port or the line is double NAT). */
let siRemote=null;   /* /api/site-links of the site whose tab is open (null on this box's own tab) */
function siteInfo(n){const c=SITE?siRemote:siCfg;if(!c||!/^(site|managed-by)-/.test(n.id))return null;
 const s=(c.sites||[]).find(x=>'site-'+x.id===n.id),m=s?null:(c.managers||[]).find(x=>'managed-by-'+x.id===n.id);if(!s&&!m)return null;
 const wan=(s||m).wan||'',via=s?String(s.address||''):String(m.addr||''),host=via.replace(/:\d+$/,''),lines=[];
 const pr=(s||m).probe||{},lt=v=>v===true?'healthy':v===false?'failed':'expected',cs=s?(s.link&&s.link.state?(s.link.state==='linked'?'healthy':'failed'):'expected'):(n.state==='healthy'?'healthy':n.state==='failed'?'failed':'expected');   /* each light: that address answers a ping from here (the box itself: the link) */
 if(wan&&host&&wan===host)lines.push(['Internet address',wan+' (this box connects here too)',cs]);
 else{lines.push(['Internet address',wan||'not shared yet',lt(pr.wan)]);if(via)lines.push(['Connects to',via,cs])}
 if((s||m).gw)lines.push(['Gateway',(s||m).gw,lt(pr.gw)]);
 return {name:s?s.name:(m.name||'Other site')+' (managed by)',lines}}
function siteFold(n,i,d,inf){const st=ds(n,n.state),open=openN.has(n.id)||st==='failed'||st==='degraded',dt=n.detail||'',two=inf.name.length+dt.length>34;
 const inner=inf.lines.map(l=>line('void(0)',l[2],l[0],l[1],d+1)).join('');
 return `<button class="rw${two?' two':''}${d?' sub1':''}" aria-expanded=${open}${padOf(d)} onclick="toggleN('${esc(n.id)}')">${dotc(st)}${two?`<span class=tx><span class=nm>${esc(inf.name)}</span><span class=dt>${esc(dt)}</span></span>`:`<span class=nm>${esc(inf.name)}</span><span class=dt>${esc(dt)}</span>`}<span class=cv aria-hidden=true>›</span></button>${open?inner:''}`}
function rowsOf(n,i,d){d=d||0;
 const go=`openDrawer(${i},'${esc(n.id)}')`, cs=n.checks||[];
 {const inf=siteInfo(n);if(inf)return siteFold(n,i,d,inf)}
 if(n.kind==='aggregate'){const kids=membersOf(n);
  if(kids.length>1)return fold(n.id,ds(n,n.state),n.name,kids.map(k=>ds(k,k.state)),()=>kids.map(k=>rowsOf(k,i,d+1)).join(''),d,true)}
 if(cs.length<2)return line(go,ds(n,n.state),n.name,n.detail||(cs[0]&&cs[0].detail)||n.label,d,n.notice&&ds(n,n.state)==='healthy');
 const row=c=>line(go,ds(n,c.state),c.label||c.target||c.type,c.detail,d+2,c.notice), counts={};
 for(const c of cs){const k=kindOf(c);if(k)counts[k]=(counts[k]||0)+1}
 return fold(n.id,ds(n,n.state),n.name,cs.map(c=>ds(n,c.state)),()=>{const done=new Set();let out='';
  for(const c of cs){const k=kindOf(c);
   if(k&&counts[k]>=3){if(done.has(k))continue;done.add(k);const g=cs.filter(x=>kindOf(x)===k);
    out+=fold(n.id+'/'+k,g.some(x=>ds(n,x.state)!=='healthy'&&ds(n,x.state)!=='pending'&&ds(n,x.state)!=='expected')?'degraded':'healthy',k,g.map(x=>ds(n,x.state)),()=>g.map(row).join(''),d+1)}
   else out+=line(go,ds(n,c.state),c.label||c.target||c.type,c.detail,d+1)}
  return out},d,true)}
/* Services that belong to an environment (Portainer containers) are grouped under it: one fold per environment, opening to short service
   names, with a stack of several containers folded once more. A problem opens its fold by itself like every other fold. */
function envGroups(ns){
 const svcs=ns.filter(n=>n.service&&n.service.env&&n.kind!=='aggregate'),envs={};
 for(const n of svcs)(envs[n.service.env]=envs[n.service.env]||{env:n.service.env,svcs:[],node:null}).svcs.push(n);
 const taken=new Set(svcs.map(n=>n.id));
 for(const g of Object.values(envs)){g.node=ns.find(x=>!x.service&&g.svcs.some(s=>(s.dependsOn||[]).includes(x.id)))||null;if(g.node)taken.add(g.node.id)}
 return{groups:Object.values(envs).sort((a,b)=>a.env.localeCompare(b.env)),taken}}
const worstState=sts=>sts.reduce((w,s)=>(SRANK[s]||0)>(SRANK[w]||0)?s:w,'healthy');
/* the green light already says running and healthy, so a service line keeps only what adds something: how long it has been up, or what is wrong */
const tidy=s=>String(s||'').replace(/^running\s*(·\s*)?/i,'').replace(/^\((.*)\)$/,'$1').replace(/\s*·?\s*\bhealthy$/i,m=>/unhealthy$/i.test(m)?m:'').replace(/^healthy$/i,'').trim();
function svcLine(n,i,d){const title=n.service.title||n.service.container||n.name,det=tidy(n.detail||(n.checks[0]&&n.checks[0].detail)||n.label);
 return line(`openDrawer(${i},'${esc(n.id)}')`,ds(n,n.state),title,det,d)}
function envFold(g,i){
 const byTitle=(a,b)=>(a.service.title||a.name).localeCompare(b.service.title||b.name),sts=g.svcs.map(n=>ds(n,n.state));
 const stacks={};for(const n of g.svcs)if(n.service.stack)(stacks[n.service.stack]=stacks[n.service.stack]||[]).push(n);
 const inner=()=>{let out=g.node?line(`openDrawer(${i},'${esc(g.node.id)}')`,ds(g.node,g.node.state),'Portainer environment',tidy(g.node.detail||g.node.label),1):'';const done=new Set();
  for(const n of g.svcs.slice().sort(byTitle)){const st=n.service.stack;
   if(st&&stacks[st].length>1){if(done.has(st))continue;done.add(st);const m=stacks[st].slice().sort(byTitle);
    out+=fold('env/'+g.env+'/'+st,worstState(m.map(x=>ds(x,x.state))),pretty(st),m.map(x=>ds(x,x.state)),()=>m.map(x=>svcLine(x,i,2)).join(''),1,false,'services')}
   else out+=svcLine(n,i,1)}
  return out};
 return fold('env/'+g.env,worstState(sts.concat(g.node?[ds(g.node,g.node.state)]:[])),g.env,sts,inner,0,true,'services')}
function cardRows(c){
 const ns=c.nodes.map(id=>snap.nodes[id]).filter(Boolean), kids=new Set(ns.flatMap(n=>{if(n.kind!=='aggregate')return [];const m=membersOf(n);return m.length>1?m.map(x=>x.id):[]}));
 const eg=envGroups(ns.filter(n=>!kids.has(n.id)));
 const loose0=ns.filter(n=>!kids.has(n.id)&&!eg.taken.has(n.id)),secs={};
 for(const n of loose0){const k=secOf(n);if(k)(secs[k.key]=secs[k.key]||{key:k.key,name:k.name,unit:k.unit,nodes:[]}).nodes.push(n)}
 const sections=Object.values(secs).filter(x=>x.nodes.length>=3),inSec=new Set(sections.flatMap(x=>x.nodes.map(n=>n.id)));
 return{loose:loose0.filter(n=>!inSec.has(n.id)),groups:eg.groups,sections}}
/* a card with many alike items (every camera, every switch and access point, every VPN tunnel) folds them under one heading per source; a problem opens it by itself */
const SEC={'unifi-protect/camera':['UniFi Protect cameras','cameras'],'scrypted/camera':['Scrypted cameras','cameras'],'unifi-network/device':['UniFi switches and access points','devices'],'unifi-network/tunnel':['UniFi VPN tunnels','tunnels'],'unifi-network/temperature':['UniFi temperatures','temperatures'],'unifi-protect/drive':['UniFi Protect drives','drives']};
function secOf(n){const cs=n.checks||[];if(n.kind==='aggregate'||cs.length!==1)return null;const k=cs[0].type+'/'+cs[0].target,v=SEC[k];return v?{key:'sec/'+k,name:v[0],unit:v[1]}:null}
const secFold=(x,i)=>{const nodes=x.nodes.slice().sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true})),sts=nodes.map(n=>ds(n,n.state));
 return fold(x.key,worstState(sts),x.name,sts,()=>nodes.map(n=>rowsOf(n,i,1)).join(''),0,true,x.unit)}
const CI={servers:'M4 5h16v6H4z M4 13h16v6H4z M8 8h.01 M8 16h.01',network:'M12 20v-6 M4 10a12 12 0 0 1 16 0 M7 13a8 8 0 0 1 10 0 M12 20h.01',internet:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18',power:'M13 2L4 14h7l-1 8 9-12h-7z',cameras:'M3 7h12v10H3z M15 11l6-3v8l-6-3',services:'M12 3l9 5-9 5-9-5z M3 13l9 5 9-5',sites:'M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11z M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z'};
function cIco(n){const d=CI[String(n).toLowerCase()];return d?`<span class=cico aria-hidden=true><svg width=20 height=20 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2 stroke-linecap=round stroke-linejoin=round><path d="${d}"/></svg></span>`:''}
/* the 24 h bar on each card: the worst state of its checks, hour by hour (asked for from the box, kept a minute) */
const strips={},sk=c=>SITE+'|'+c.name;   /* kept per site: the same card name on two sites must never share a bar */
function stripHtml(c){const d=strips[sk(c)]&&strips[sk(c)].d;if(!BARSHOW.length||!d||!d.buckets.some(x=>x))return '';
 return d.buckets.map((x,k)=>`<i class="${x||'none'}" title="${x?esc(LABELS[x]||x):'No record yet'}, ${24-k} h ago"></i>`).join('')}
const LABELS={healthy:'Healthy',degraded:'Degraded',failed:'Down',unknown:'Unknown'};
/* A bar that could not be fetched is asked for again within a few seconds (it used to wait the full minute, so one dropped request left a card bare), and what was drawn stays until a good answer replaces it. */
function loadStrips(){if(!snap)return;const now=Date.now();
 snap.cards.forEach(c=>{const k=sk(c),o=strips[k],ids=c.nodes||[];if(!ids.length||(o&&now-o.at<(o.bad?4000:60000)))return;strips[k]={at:now,d:o&&o.d,bad:o&&o.bad};
  api('history?strip='+encodeURIComponent(ids.join(','))).then(d=>{if(!d||!Array.isArray(d.buckets))throw new Error('no bar');strips[k]={at:Date.now(),d};document.querySelectorAll('.strip').forEach(e=>{if(e.dataset.c===k){const h=stripHtml(c);if(e.innerHTML!==h)e.innerHTML=h}})}).catch(()=>{const cur=strips[k];strips[k]={at:Date.now(),d:cur&&cur.d,bad:1}})})}
/* tap a slice of a card's bar: what was not healthy in that hour (when each thing changed; the box does not record why) */
let tsOpen=false;
const TST={failed:'Down',degraded:'Degraded',unknown:'Could not be checked'};
/* times are shown in the time zone of the site being viewed (Settings, This box); until one is set, in this device's */
let BOXTZ='';const tzo=()=>BOXTZ?{timeZone:BOXTZ}:{};
let BARSHOW=['failed','degraded','unknown'];   /* which states the bars may show: a display choice per site, set in Settings, History */
async function loadTz(){try{BOXTZ=(await api('timezone')).timezone||''}catch(e){BOXTZ=''}
 try{BARSHOW=(await api('barshow')).show}catch(e){BARSHOW=['failed','degraded','unknown']}for(const k in strips)delete strips[k];if(snap)loadStrips()}
/* an ISO time from the box (always UTC) shown in the site's own time zone, such as 'Oct 19, 1:36 AM CDT' */
const lt=iso=>{const d=new Date(iso);return isNaN(d)?String(iso||''):d.toLocaleString([],Object.assign({month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'},tzo()))};
const tfmt=t=>new Date(t*1000).toLocaleTimeString([],Object.assign({hour:'numeric',minute:'2-digit'},tzo()));
function tdur(s){s=Math.round(s);return s<60?'under a minute':s<3600?Math.round(s/60)+' min':(s/3600).toFixed(1).replace('.0','')+' h'}
function closeTrouble(){const o=$('#tsheet');if(o)o.remove();tsOpen=false}
async function stripTap(ev,i){const c=snap&&snap.cards[i],d=c&&strips[sk(c)]&&strips[sk(c)].d;if(!d)return;
 const r=ev.currentTarget.getBoundingClientRect(),n=d.buckets.length,k=Math.max(0,Math.min(n-1,Math.floor((ev.clientX-r.left)/r.width*n))),step=(d.now-d.since)/n,lo=Math.floor(d.since+k*step),hi=Math.floor(d.since+(k+1)*step);
 closeTrouble();tsOpen=true;const o=document.createElement('div');o.id='tsheet';o.setAttribute('role','dialog');o.setAttribute('aria-label','What happened');document.body.appendChild(o);
 const head=`<h3>${esc(c.name)}, ${esc(new Date(lo*1000).toLocaleDateString([],Object.assign({weekday:'short'},tzo())))} ${tfmt(lo)} to ${tfmt(hi)}</h3>`,foot=`<button class="btn" onclick="closeTrouble()">Close</button>`;
 o.innerHTML=head+'<p class=sub>Loading…</p>'+foot;
 try{const t=await api('history?trouble='+encodeURIComponent((c.nodes||[]).join(','))+'&from='+lo+'&to='+hi);if(!$('#tsheet'))return;
  const nm=id=>(snap.nodes&&snap.nodes[id]&&snap.nodes[id].name)||id,items=t.items||[];
  const body=!d.buckets[k]?'<p class=sub>No record for this hour yet.</p>':items.length?`<div class=rows>${items.map(x=>`<div class=tr><span class="dot ${esc(x.state)}"></span><div><b>${esc(nm(x.node))}</b><span class=sub>${esc(TST[x.state]||x.state)} · ${tdur(x.to-x.from)} · ${tfmt(x.from)} to ${tfmt(x.to)}</span>${x.why?`<span class=sub style="display:block">${esc(x.why)}</span>`:''}</div></div>`).join('')}</div>${t.more?`<p class=note>And ${t.more} more.</p>`:''}<p class=note>Each line says what the check reported when it started. Older entries, from before this was kept, only say when.</p>`:'<p class=sub>Nothing was wrong in this hour.</p>';
  o.innerHTML=head+body+foot}catch(e){if($('#tsheet'))o.innerHTML=head+'<p class=sub>Could not load that hour.</p>'+foot}}
addEventListener('pointerdown',e=>{if(tsOpen&&!e.target.closest('#tsheet,.strip'))closeTrouble()},true);
addEventListener('keydown',e=>{if(e.key==='Escape'&&tsOpen)closeTrouble()});
function detailCard(c,i){
 const r=cardRows(c),rows=r.loose.map(n=>rowsOf(n,i)).join('')+r.sections.map(x=>secFold(x,i)).join('')+r.groups.map(g=>envFold(g,i)).join('');
 return `<div class="card det"><button class=hd onclick="openDrawer(${i})"><span class=t>${cIco(c.name)}${esc(c.name)}</span>${chip(c.state,c.label)}</button><div class=strip data-c="${esc(sk(c))}" aria-label="Last 24 hours, tap for what happened" onclick="stripTap(event,${i})">${stripHtml(c)}</div><div class=rows>${rows}</div></div>`}
/* cards go into side-by-side columns by their FOLDED size, so opening a fold never moves a card to another column */
function colsFor(){const w=($('#m')&&$('#m').clientWidth)||innerWidth;return Math.max(1,Math.min(3,Math.floor((w+16)/356)))}
function denseGrid(items){const n=colsFor(),cols=Array.from({length:n},()=>({h:0,html:''}));
 for(const it of items){const c=cols.reduce((a,b)=>b.h<a.h?b:a);c.html+=it.html;c.h+=it.w}
 return cols.map(c=>`<div class=col>${c.html}</div>`).join('')}
let lastCols=0;addEventListener('resize',()=>{if(snap&&view==='detail'&&colsFor()!==lastCols&&!location.hash.startsWith('#/settings')){lastTouch=0;render()}});
/* what makes a status update worth redrawing: everything except the clock and each check's round-trip time,
   which changes on every poll and would otherwise rebuild the page every few seconds */
function statusSig(raw){return raw.replace(/"generatedAt":"[^"]*"/,'').replace(/"ms":[0-9.]+/g,'"ms":0')}
/* a redraw replaces the side panel, which stops a finger-scroll (and its momentum) dead on iPad, so while the
   panel is being touched or is still gliding the redraw waits until it has been still for a moment */
for(const t of['touchstart','touchmove','scroll','wheel'])document.addEventListener(t,()=>{lastTouch=Date.now()},{capture:true,passive:true});
function busyScrolling(){return !!(drawer||svcOpen)&&Date.now()-lastTouch<700}
function closeStream(){if(es){es.close();es=null}snap=null;lastJson=''}
setInterval(()=>{if(es)tick()},5000);
function tick(){const u=$('#upd');if(!u)return;
 u.textContent=!snap?'':(!live||Date.now()-lastEvent>40000)?'Live updates paused. Reconnecting…':'Updated '+ago(Date.now()-lastEvent)}

/* any page other than the main screen takes the whole window: the side panel (which now lives outside the page that is rebuilt) is closed first */
function mpage(){if(drawer||svcOpen||(($('#dr')||{}).firstChild))closeDrawer();return $('#m')}
/* the last word of the headline takes the state colour: 'Everything is <fine>' */
function headHtml(t){t=String(t||'');const i=t.trimEnd().lastIndexOf(' ');return i<0?'<em>'+esc(t)+'</em>':esc(t.slice(0,i+1))+'<em>'+esc(t.slice(i+1))+'</em>'}
function tilesHtml(){const ns=Object.values(snap.nodes||{}).filter(n=>n.kind!=='aggregate'&&!n.muted),ok=ns.filter(n=>n.state==='healthy').length,bad=snap.attention.filter(a=>!/^(site|managed-by)-/.test(a.id)).length,sites=1+(siCfg?siCfg.sites.length:0);
 if(!ns.length)return '';const t=(n,l,c)=>`<div class=tile><b style="color:${c}">${n}</b><span>${l}</span></div>`;
 return `<div class=tiles>${t(ok,ok===1?'check healthy':'checks healthy','#34D399')}${t(bad,bad===1?'thing needs attention':'things need attention',bad?'var(--acc)':'var(--sub)')}${t(sites,sites===1?'site watched':'sites watched','var(--ink)')}</div>`}
function render(){if(!SITE&&snap&&snap.banner){locBanner=snap.banner}renderHeader();
 if(!es)return;
 if(busyScrolling()){clearTimeout(deferred);deferred=setTimeout(render,Math.max(60,750-(Date.now()-lastTouch)));return}
 const d0=document.querySelector('.drawer');if(d0)drawerTop=d0.scrollTop;   // the page is rebuilt below; remember where the side panel was
 delete $('#m').dataset.set;if(!snap){$('#m').innerHTML='<p class=sub>Loading…</p>';return}
 document.body.dataset.s=snap.banner.status;
 const b=snap.banner;
 const att=snap.attention.map(a=>`<div class=item onclick="openDrawer('${esc(a.group).replace(/'/g,'')}','${esc((a.ids||[a.id])[0])}')">
   ${chip(a.state,a.label)}<div class=grow><b>${esc(a.name)}</b><div class=sub>${a.check?esc(a.check)+': ':''}${esc(a.detail)}${a.affects.length?` · ${a.ids?'Affecting':'Also affecting'} ${esc(a.affects.slice(0,4).join(', '))}${a.affects.length>4?' and '+(a.affects.length-4)+' more':''}`:''}</div></div>
   <small>${since(a.label,a.since)}</small><button class="btn sm" onclick="event.stopPropagation();checkNow(${esc(JSON.stringify(a.ids||a.id))})">Check now</button></div>`).join('');
 const sumCard=(c,i)=>`<button class=card onclick="openDrawer(${i})"><div class=r><span class=t>${cIco(c.name)}${esc(c.name)}</span>${chip(c.state,c.label)}</div>
   <div class=big>${esc(c.big)}</div><div class=strip data-c="${esc(sk(c))}" aria-label="Last 24 hours, tap for what happened" onclick="event.stopPropagation();stripTap(event,${i})">${stripHtml(c)}</div><div class=sub>${esc(c.line)}</div></button>`;
 const cards=view==='detail'?(lastCols=colsFor(),denseGrid(snap.cards.map((c,i)=>{const r=cardRows(c);return{html:detailCard(c,i),w:2+r.loose.length+r.sections.length+r.groups.length}}))):snap.cards.map(sumCard).join('');
 $('#m').innerHTML=`<div class=top><div class=row>${snap.demo?`<span class=ribbon>DEMO: ${esc(snap.demo)}</span>`:''}<div class=seg role=group aria-label="Main screen view"><button aria-pressed=${view==='summary'} onclick="setView('summary')">Summarized</button><button aria-pressed=${view==='detail'} onclick="setView('detail')">Detailed</button></div><small id=upd></small></div></div>
  <h1 class=head>${headHtml(b.headline)}</h1><p class=lede>${esc(b.subline)}</p>${tilesHtml()}
  ${snap.configError?`<div class=err>The saved monitoring settings have a problem, so only the built-in checks are running: ${esc(snap.configError)}</div>`:''}
  ${att?`<div class=eyebrow>Needs attention</div>${att}`:''}
  <div class="grid${view==='detail'?' dense':''}">${cards||'<div class=box>No checks are set up yet. Open Settings to add some.</div>'}</div><div id=gr></div><p class=vfoot>MonitorBox ${hdrInfo.ver?'v'+esc(hdrInfo.ver):''}</p>`;
 if(!grLoaded){grLoaded=1;loadGraphCfg().then(()=>{drawGraphs();pollGraphs();pollBusiest()})}else drawGraphs();
 pollBusiest();
 loadStrips();tick(); if(svcOpen)drawServices();else if(drawer)drawDrawer();
}
/* ---------- throughput graphs ---------- */
let grCfg=[],grData=null,grLoaded=0,grWin=0,grPick=null;
const GW=[[60,'1 min'],[300,'5 min'],[900,'15 min'],[3600,'1 hour']];
async function loadGraphCfg(){try{grCfg=(await api('graphs')).graphs||[]}catch(e){}}
function fmtBps(v){v=+v||0;return v>=999.5e6?(v>=1e10?Math.round(v/1e9)+'':(v/1e9).toFixed(2).replace(/\.?0+$/,''))+' Gbit/s':v>=999.5e3?(v/1e6).toFixed(v>=9.95e6?0:1)+' Mbit/s':v>=1e3?Math.round(v/1e3)+' kbit/s':Math.round(v)+' bit/s'}
function niceMax(v){if(v<=0)return 1000;const p=Math.pow(10,Math.floor(Math.log10(v))),m=v/p;return (m<=1?1:m<=2?2:m<=5?5:10)*p}
function agoText(n){n=Math.round(n);return n>=3600?Math.round(n/3600)+' h ago':n>=90?Math.round(n/60)+' min ago':n+' s ago'}
/* the top of the graph is what the link is rated for (2.5 Gbit/s, 10 Gbit/s), so a quiet link reads as quiet; it grows only if traffic ever passes the rating */
function graphSvg(pts,sec,now,speedMbps,h){const W=600,H=h||110;if(!pts.length)return '';const top=Math.max(...pts.map(p=>Math.max(p[1],p[2]))),mx=speedMbps?Math.max(speedMbps*1e6,top):niceMax(top),span=Math.max(20,Math.min(sec,now-pts[0][0])),t0=now-span;
 const X=t=>((t-t0)/span*W).toFixed(1),line=i=>pts.map(p=>`${X(p[0])},${(H-p[i]/mx*(H-6)-3).toFixed(1)}`).join(' ');
 const ax=`display:flex;flex-direction:column;justify-content:space-between;height:${H}px;text-align:right;font-size:12px;color:var(--sub);white-space:nowrap`;
 return `<div style="display:flex;gap:8px"><div style="${ax}"><span>${fmtBps(mx)}</span><span>${fmtBps(mx/2)}</span><span>0</span></div><div style="flex:1;min-width:0"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role=img aria-label="traffic graph" style="width:100%;height:${H}px;display:block"><line x1=0 x2=${W} y1=3 y2=3 stroke="rgba(255,255,255,.08)"/><line x1=0 x2=${W} y1=${H/2} y2=${H/2} stroke="rgba(255,255,255,.08)"/><line x1=0 x2=${W} y1=${H-3} y2=${H-3} stroke="rgba(255,255,255,.14)"/><polygon fill="rgba(52,211,153,.12)" points="${X(pts[0][0])},${H} ${line(1)} ${X(pts[pts.length-1][0])},${H}"/><polyline fill=none stroke="#34d399" stroke-width=2.5 stroke-linejoin=round vector-effect="non-scaling-stroke" points="${line(1)}"/><polyline fill=none stroke="#60a5fa" stroke-width=2.5 stroke-linejoin=round vector-effect="non-scaling-stroke" points="${line(2)}"/></svg></div></div>
  <div class=sub style="display:flex;justify-content:space-between;font-size:12px;margin-left:calc(4.6em + 8px)"><span>${agoText(span)}</span><span>live</span></div>`}
function drawGraphs(){const el=$('#gr');if(!el)return;if(!grWin)grWin=+lsGet('mb-gw')||300;if(!grCfg.length){el.innerHTML='';return}
 const d=(grData&&grData.graphs)||[],byId=new Map(d.map(g=>[g.id,g]));
 el.innerHTML=`<div class=eyebrow style="display:flex;align-items:center;justify-content:space-between;gap:.6rem;flex-wrap:wrap">Traffic<span class=seg role=group aria-label="Graph window">${GW.map(x=>`<button aria-pressed=${grWin===x[0]} onclick="setGw(${x[0]})">${x[1]}</button>`).join('')}</span></div>
  <div class=grid>${grCfg.map((c,ix)=>{if(c.kind==='busiest')return busiestCard(c,ix);const g=byId.get(c.id),p=g&&g.points||[],l=p[p.length-1];
   return `<div class=box data-gp="${ix}" style="cursor:pointer" title="Tap for a longer history" onclick="openGraphPanel(${ix})"><div class=r style="justify-content:space-between;gap:.8rem;flex-wrap:wrap;margin-bottom:.4rem"><b>${esc(c.title)}</b><small style="margin-left:.8rem"><span style="color:#34d399">↓ ${l?fmtBps(l[1]):'…'}</span> &nbsp;<span style="color:#60a5fa">↑ ${l?fmtBps(l[2]):'…'}</span></small></div>
    ${g&&g.error&&!p.length?`<div class=sub>${esc(g.error)}</div>`:p.length?graphSvg(p,grData.seconds,grData.now,c.maxMbps||g.speedMbps):'<div class=sub>Waiting for the first readings…</div>'}</div>`}).join('')}</div>`}
/* Busiest client: a graph you add in Settings → Graphs. Who is chattiest on the wired LAN right now (the box keeps the name steady when things are slow). Tap "where does it go?" for the likely destinations. */
let bzData=null,bzPanel=null,flPanel=null;
const hasBusiest=()=>grCfg.some(g=>g.kind==='busiest');
let bzBusy=0;
async function pollBusiest(){if(!hasBusiest()||document.hidden||bzBusy)return;if(!grWin)grWin=+lsGet('mb-gw')||300;bzBusy=1;try{bzData=await api('lan/busiest?seconds='+grWin);drawBusiest()}catch(e){}bzBusy=0}
setInterval(pollBusiest,1000);
function drawBusiest(){drawGraphs()}
function busiestCard(c,ix){const d=bzData,L=d&&d.leader,p=(d&&d.points)||[],open=`data-gp="${ix}" style="cursor:pointer" title="Tap to see where its traffic goes" onclick="openGraphPanel(${ix})"`;
 if(!d||!d.available)return `<div class=box id=bz ${open}><b>${esc(c.title)}</b><div class=sub>${d?'Nothing to show yet. This needs a UniFi network connection and a minute or so of readings.':'Waiting for the first readings…'}</div></div>`;
 return `<div class=box id=bz ${open}><div class=r style="justify-content:space-between;gap:.8rem;flex-wrap:wrap;margin-bottom:.4rem"><b>${L?esc(L.name):'The network is quiet'}</b>${L?`<small style="margin-left:.8rem"><span style="color:#34d399">↓ ${fmtBps(L.down)}</span> &nbsp;<span style="color:#60a5fa">↑ ${fmtBps(L.up)}</span></small>`:''}</div>
   <div class=sub style="margin-bottom:.3rem">${esc(c.title)}${L?' · '+esc(L.where):''}</div>
   ${p.length?graphSvg(p,d.seconds,d.now,0):''}</div>`}
function segOn(b){for(const x of b.parentNode.children)x.setAttribute('aria-pressed',x===b?'true':'false')}   /* the tapped time lights up where it is: the page is not redrawn, so nothing flashes or moves (Safari threw a redrawn page to the top) */
function setGw(n){grWin=n;lsSet('mb-gw',n);saveDisplay('gwin',n);pollGraphs();pollBusiest()}
/* tapping a graph opens the side panel with a longer stretch (15 minutes unless Settings, Graphs says otherwise). The box keeps the last hour, so that is the most any window can be. */
const GPW=[[300,'5 min'],[900,'15 min'],[1800,'30 min'],[3600,'1 hour']];
let grPanel=null,grPData=null;   /* grPanel: which graph (its place in the list) the panel shows */
function getGp(){const v=+lsGet('mb-gp');return [60,300,900,1800,3600].includes(v)?v:900}
function setGp(n){lsSet('mb-gp',n);saveDisplay('gpanel',n);grPData=null;bzPanel=null;flPanel=null;if(grPanel!==null){drawGraphPanel();pollGraphPanel()}}
function openGraphPanel(i){closeDrawer();grPanel=i;grPData=null;bzPanel=null;flPanel=null;drawGraphPanel();pollGraphPanel()}
function gpWide(){setDw(wideNow()?0:innerWidth);saveDisplay('dw',dw);drawGraphPanel()}
async function pollGraphPanel(){if(grPanel===null||document.hidden)return;const w=getGp(),c0=grCfg[grPanel];pollFlows(c0,w);if(c0&&c0.kind==='busiest')return pollBusiestPanel(c0,w);try{const d=await api('graphs/data?seconds='+w);if(grPanel===null||w!==getGp())return;grPData=d;drawGraphPanel()}catch(e){}}
setInterval(pollGraphPanel,1000);
/* the Busiest client panel: the leader's graph, then where its traffic goes (worked out every 5 s, not every second) */
async function pollBusiestPanel(c,w){try{const d=await api('lan/busiest?seconds='+w);if(grPanel===null||w!==getGp()||grCfg[grPanel]!==c)return;bzPanel=d;drawGraphPanel()}catch(e){}}
/* the list under every graph in the side panel: where its traffic goes and how much, biggest first, other devices on the LAN and the internet together. Asked every 5 s, not every second. */
async function pollFlows(c,w){if(!c)return;const key=c.id+'|'+w;if(flPanel&&flPanel.key===key&&Date.now()-flPanel.at<5000)return;
 const g=flPanel&&flPanel.key===key?flPanel:(flPanel={key,at:0,data:null});g.at=Date.now();
 try{const r=await api('lan/flows?graph='+encodeURIComponent(c.id)+'&win='+w);if(flPanel===g&&grPanel!==null){g.data=r;drawGraphPanel()}}catch(e){if(flPanel===g){g.data={error:'Could not work it out ('+e.message+')',flows:[]};drawGraphPanel()}}}
function flowsHtml(c,w){const g=flPanel&&flPanel.key===c.id+'|'+w?flPanel:null,d=g&&g.data;
 let h='<h3 style="margin:1rem 0 .3rem">Where its traffic goes</h3>';
 if(!d)return h+'<div class=sub>Working it out…</div>';
 if(d.error)return h+`<div class=sub>${esc(d.error)}</div>`;
 const rows=(d.flows||[]).map(f=>`<div class=r style="justify-content:space-between;gap:.6rem;align-items:baseline;padding:.15rem 0"><span>${esc(f.label)} <span class=sub style="margin-left:.4rem">${f.scope==='internet'?'via the gateway':f.scope==='unmatched'?(d.young?'still working out where it goes':'the rest of its traffic'):f.seen?'local · seen by the gateway':'local · '+(f.confidence==='likely'?'<b>likely</b>':'possible')+' · '+f.match+'% match'}</span></span><small style="white-space:nowrap">${f.scope==='local'&&!f.seen?'up to ':''}<span style="color:#34d399">↓ ${fmtBps(f.down_bps)}</span> &nbsp;<span style="color:#60a5fa">↑ ${fmtBps(f.up_bps)}</span></small></div>`).join('');
 const young=d.young?`<div class=sub style="margin:.2rem 0 .4rem">MonitorBox only started reading this about ${d.history<90?'a minute':Math.round(d.history/60)+' minutes'} ago, which is less than the ${(GPW.find(x=>x[0]===w)||[0,Math.round(w/60)+' min'])[1]} shown. Matches appear after a few minutes of readings.</div>`:'';
 return h+young+(rows||`<div class=sub>${esc(d.why||'Nothing stands out.')}</div>`)+`<div class=sub style="opacity:.75;margin-top:.4rem">Biggest first, averaged over the last ${(GPW.find(x=>x[0]===w)||[0,Math.round(w/60)+' min'])[1]}. Conversations the gateway logged are named exactly (averaged over the window, counted as each flow reports in). Other local flows are an estimate from how traffic rises and falls on ${d.read||'the'} switch ports, not a record of conversations, and their rates are the most each could be (several can share the same traffic); internet traffic is counted by the gateway, wifi included. Traffic that never reaches the gateway is not in its log.${d.unread&&d.unread.length?' No readings yet from '+esc(d.unread.join(', '))+'.':''}</div>`}
function gpShell(){if(!document.querySelector('.drawer.gp'))$('#dr').innerHTML=`<div class=scrim onclick=closeDrawer()></div><aside class="drawer gp" aria-label="Traffic history"><div class=dgrip onpointerdown=gripDown(event) title="Drag to make this panel wider or narrower"></div><div id=gp-in></div></aside>`}
function drawBusiestPanel(c){const w=getGp(),d=bzPanel&&bzPanel.seconds===w?bzPanel:null,L=d&&d.leader,p=(d&&d.points)||[];gpShell();
 $('#gp-in').innerHTML=`<div class=row style="justify-content:space-between"><h2 style="margin:0">${esc(c.title)}</h2><span><button class="btn sm" onclick=gpWide()>${wideNow()?'Narrower':'Wider'}</button> <button class="btn sm" onclick=closeDrawer()>Close</button></span></div>
  <div class=seg role=group aria-label="Panel window" style="margin:.6rem 0">${GPW.map(x=>`<button aria-pressed=${w===x[0]} onclick="setGp(${x[0]})">${x[1]}</button>`).join('')}</div>
  ${!d?'<div class=sub>Waiting for the readings…</div>':`<div class=r style="justify-content:space-between;gap:.8rem;flex-wrap:wrap"><b>${L?esc(L.name):'The network is quiet'}</b>${L?`<small><span style="color:#34d399">↓ ${fmtBps(L.down)}</span> &nbsp;<span style="color:#60a5fa">↑ ${fmtBps(L.up)}</span></small>`:''}</div>${L?`<div class=sub style="margin-bottom:.4rem">${esc(L.where)}</div>`:''}${L?`<div class=row style="gap:.6rem;align-items:center;margin:0 0 .6rem"><button class="btn sm" onclick="bzHide()">Hide this client</button><span class=sub>from this card only</span></div>`:''}
  ${p.length?graphSvg(p,w,d.now,0,220):''}${(d.before||[]).length?`<div class=sub>Before that: ${d.before.map(b=>esc(b.name)+' ('+agoText(b.ago)+')').join(', ')}</div>`:''}`}
  ${flowsHtml(c,w)}`}
function drawGraphPanel(){const c=grCfg[grPanel];if(!c){closeDrawer();return}
 if(c.kind==='busiest')return drawBusiestPanel(c);
 const w=getGp(),g=grPData&&grPData.seconds===w?(grPData.graphs||[]).find(x=>x.id===c.id):null,p=g&&g.points||[],l=p[p.length-1];
 if(!document.querySelector('.drawer.gp'))$('#dr').innerHTML=`<div class=scrim onclick=closeDrawer()></div><aside class="drawer gp" aria-label="Traffic history"><div class=dgrip onpointerdown=gripDown(event) title="Drag to make this panel wider or narrower"></div><div id=gp-in></div></aside>`;
 const st=i=>{if(!p.length)return['…','…'];let s=0,m=0;for(const q of p){s+=q[i];if(q[i]>m)m=q[i]}return[fmtBps(s/p.length),fmtBps(m)]};
 const row=(lab,col,i)=>{const s=st(i);return `<tr><td style="color:${col}">${lab}</td><td>${l?fmtBps(l[i]):'…'}</td><td>${s[0]}</td><td>${s[1]}</td></tr>`};
 $('#gp-in').innerHTML=`<div class=row style="justify-content:space-between"><h2 style="margin:0">${esc(c.title)}</h2><span><button class="btn sm" onclick=gpWide()>${wideNow()?'Narrower':'Wider'}</button> <button class="btn sm" onclick=closeDrawer()>Close</button></span></div>
  <div class=seg role=group aria-label="Panel window" style="margin:.6rem 0">${GPW.map(x=>`<button aria-pressed=${w===x[0]} onclick="setGp(${x[0]})">${x[1]}</button>`).join('')}</div>
  ${g&&g.error&&!p.length?`<div class=sub>${esc(g.error)}</div>`:p.length?graphSvg(p,w,grPData.now,c.maxMbps||g.speedMbps,220):'<div class=sub>Waiting for the readings…</div>'}
  <table class=gpt style="width:100%;margin-top:.8rem;font-size:14px;border-collapse:collapse"><tr class=sub><th></th><th align=left>Now</th><th align=left>Average</th><th align=left>Peak</th></tr>${row('↓ In','#34d399',1)}${row('↑ Out','#60a5fa',2)}</table>
  ${flowsHtml(c,w)}
  <p class=sub>The last ${(GPW.find(x=>x[0]===w)||[0,w/60+' min'])[1]} of readings. The box keeps one hour, so that is the longest this can show.</p>`}
async function pollGraphs(){if(!$('#gr')||!grCfg.length||document.hidden)return;if(!grWin)grWin=+lsGet('mb-gw')||300;try{grData=await api('graphs/data?seconds='+grWin);drawGraphs()}catch(e){}}
setInterval(pollGraphs,1000);
/* ---------- the network map: the gateway at the top, what hangs off each switch below it, and how busy each link is ---------- */
let mapTimer=null,mapOpen=new Set(),mapPeer=null,mapLast=null;
const PW=[[300,'5 min'],[900,'15 min'],[3600,'1 hour']];
function peerRow(a,ml){return `<div class=sub${ml?' style="margin-left:1.6rem"':''}>${a.confidence==='likely'?'<b>likely</b>':'possible'} · ${a.kind==='flood'?esc(a.label)+' ('+esc((a.ports||[]).join(', '))+')':(a.direction==='from'?'sends to ':'receives from ')+esc(a.label)} · ${Math.round(a.r*100)}% match</div>`}
function peersHtml(p,fn){fn=fn||'mapPeers';const d=p.data;if(!d)return '<div class=sub style="margin-left:1.6rem">Working it out…</div>';
 if(d.error)return `<div class=sub style="margin-left:1.6rem">${esc(d.error)}</div>`;
 const wins=PW.map(([w,t])=>w===p.win?`<b>${t}</b>`:`<a href="#" style="color:inherit" onclick="${fn}('${esc(p.node)}','${esc(p.port)}',${w});return false">${t}</a>`).join(' · ');
 const rows=(d.answer||[]).map(a=>peerRow(a,1)).join('');
 return `<div style="margin:.2rem 0 .4rem 1.6rem;border-left:2px solid #2dd4bf55;padding-left:.6rem"><div class=sub>Where this port's traffic most likely goes, last ${wins}</div>${rows||`<div class=sub>${esc(d.why||'Nothing stands out.')}</div>`}
  <div class=sub style="opacity:.75">An estimate from how traffic rises and falls on ${d.read} ports, not a record of conversations.${d.unread&&d.unread.length?' No readings yet from '+esc(d.unread.join(', '))+'.':''}</div></div>`}
async function mapPeers(node,port,win){if(!win&&mapPeer&&mapPeer.node===node&&mapPeer.port===port){mapPeer=null;if(mapLast)drawMap(mapLast);return}
 mapPeer={node,port,win:win||(mapPeer&&mapPeer.win)||900,data:null};if(mapLast)drawMap(mapLast);await loadPeers()}
async function loadPeers(){const p=mapPeer;if(!p)return;let d;try{d=await api('lan/peers?node='+encodeURIComponent(p.node)+'&port='+encodeURIComponent(p.port)+'&win='+p.win)}catch(e){d={error:'Could not work it out ('+e.message+')'}}
 if(mapPeer===p){p.data=d;if(mapLast)drawMap(mapLast)}}
const pwBox=m=>m.nodes.length?`<div class=box><label class=row style="min-height:44px"><input type=checkbox ${m.portwatch&&m.portwatch.on?'checked':''} onchange="pwOn(this.checked)"> <span>Watch for rising port errors</span></label><p class=sub style="margin:.2rem 0 0">On by default when a switch can be read. MonitorBox learns what is normal for each switch port and shows a yellow heads-up (never red) when a port's errors, packet drops or link drops climb well above that. It needs about half an hour of readings first. Untick "alert" on a port to keep watching it but never be told about it.${m.portwatch&&m.portwatch.on&&m.portwatch.ports?` Watching ${m.portwatch.ports} ports (the full list is on the Port errors page).`:''}</p></div>`:'';
async function pwOn(on){try{await api('portwatch',{on})}catch(e){alert(e.message)}await mapLoad()}
async function pwKnown(a,known){try{await api('portwatch',{keys:a.dataset.k.split('\t'),known})}catch(e){alert(e.message)}await mapLoad()}
function mapTog(d){const k=d.dataset.n;if(d.open)mapOpen.add(k);else mapOpen.delete(k)}
const spd=m=>!m?'':m>=1000?(m/1000)+' GbE':m+' Mbit';
/* ---------- the Logs page: its own page; new lines follow you at the top and never move the page once you have scrolled ---------- */
let lgTimer=null,lgItems=[],lgHeld=[],lgOpen=new Set(),lgF={level:'auto',source:'',q:''},lgDebug={on:false,until:0},lgSources=[],lgMenu=false,lgQT=null,lgSeq=0;
const lgQs=(extra)=>'logs?'+new URLSearchParams(Object.assign({level:lgF.level,source:lgF.source,q:lgF.q},extra)).toString();
const lgAtTop=()=>(window.scrollY||document.documentElement.scrollTop||0)<60;
const lgBusy=()=>{const a=document.activeElement,sel=window.getSelection&&window.getSelection();return lgOpen.size>0||(a&&a.id==='lg-q')||!!(sel&&String(sel).length>0&&sel.anchorNode&&$('#lg-list')&&$('#lg-list').contains(sel.anchorNode))};
async function lgStat(){const e=$('#lgstat');if(!e)return;try{const j=await api('logs?limit=1&level=error');const c=j.counts||{};
 e.textContent=c.error?c.error+' error'+(c.error==1?'':'s')+' in the last day.':c.warning?c.warning+' warning'+(c.warning==1?'':'s')+' in the last day.':'All quiet in the last day.'}catch(x){e.textContent=''}}
function renderLogs(){clearInterval(lgTimer);document.body.dataset.s='green';lgItems=[];lgHeld=[];lgOpen=new Set();lgMenu=false;const hq=new URLSearchParams(location.hash.split('?')[1]||'');lgF={level:['auto','warning','error','debug'].includes(hq.get('level'))?hq.get('level'):'auto',source:hq.get('source')||'',q:''};
 mpage().innerHTML=`<div class=top><h1 style="margin:0;font-size:28px">Logs</h1><div class=row><button class="btn sm" onclick="location.hash='#/settings/advanced'">← Advanced</button><button class="btn sm" id=lg-mb aria-label="Log options" onclick="lgToggleMenu()">⋯</button></div></div>
 <div id=lg-menu class=box hidden></div><div id=lg-banner></div>
 <div class=lg-bar><select id=lg-lvl aria-label="Level" onchange="lgFilter()"><option value=auto>All</option><option value=warning>Warnings and errors</option><option value=error>Errors only</option><option value=debug>All, with older debug lines</option></select>
  <select id=lg-src aria-label="Source" onchange="lgFilter()"><option value="">Every source</option></select>
  <input id=lg-q type=search placeholder="Search" aria-label="Search" oninput="lgSearchSoon()"></div>
 <div id=lg-nw><button id=lg-new class="btn pri" hidden onclick="lgShowHeld()"></button></div>
 <div id=lg-list><p class=sub>Loading…</p></div>`;
 $('#lg-lvl').value=lgF.level;lgLoad();lgTimer=setInterval(lgTick,3000);window.addEventListener('scroll',lgScroll,{passive:true})}
function lgScroll(){if(!location.hash.startsWith('#/logs')){window.removeEventListener('scroll',lgScroll);return}if(lgHeld.length&&lgAtTop()&&!lgBusy())lgShowHeld()}
function lgFilter(){lgF.level=$('#lg-lvl').value;lgF.source=$('#lg-src').value;if(document.activeElement&&document.activeElement.tagName==='SELECT')document.activeElement.blur();lgLoad()}
function lgSearchSoon(){clearTimeout(lgQT);lgQT=setTimeout(()=>{lgF.q=($('#lg-q')||{}).value||'';lgLoad()},350)}
async function lgLoad(){const my=++lgSeq;let j;try{j=await api(lgQs({limit:300}))}catch(e){const l=$('#lg-list');if(l)l.innerHTML='<p class=sub>Could not read the logs ('+esc(e.message)+'). That MonitorBox may be running an older version.</p>';return}
 if(my!==lgSeq||!location.hash.startsWith('#/logs'))return;lgItems=j.entries||[];lgHeld=[];lgOpen=new Set();lgMeta(j);lgDraw();window.scrollTo(0,0)}
function lgLevels(){const s=$('#lg-lvl');if(!s)return;const o=lgDebug.on?[['auto','All'],['info','All except debug'],['warning','Warnings and errors'],['error','Errors only']]:[['auto','All'],['warning','Warnings and errors'],['error','Errors only'],['debug','All, with older debug lines']];const sig=o.map(x=>x[0]).join();if(s.dataset.sig===sig)return;s.dataset.sig=sig;s.innerHTML=o.map(x=>`<option value=${x[0]}>${x[1]}</option>`).join('');if(!o.some(x=>x[0]===lgF.level)){lgF.level='auto';lgLoad()}s.value=lgF.level}
function lgMeta(j){if(j.debug)lgDebug=j.debug;lgLevels();if(j.sources){lgSources=j.sources;const s=$('#lg-src');if(s){const keep=lgF.source;s.innerHTML='<option value="">Every source</option>'+lgSources.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');s.value=keep}}
 const b=$('#lg-banner');if(b)b.innerHTML=lgDebug.on?`<div class=box style="border-color:#FBBF24"><b>Debug logging is on</b> until ${esc(new Date(lgDebug.until*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}))}. It records more detail and switches itself off after 24 hours. <button class="btn sm" onclick="lgSetDebug(false)">Turn off</button></div>`:'';
 const m=$('#lg-menu');if(m&&!m.hidden)lgMenuDraw()}
async function lgTick(){if(!location.hash.startsWith('#/logs')){clearInterval(lgTimer);return}if(document.hidden||!lgItems)return;const newest=Math.max(lgItems.length?lgItems[0].id:0,lgHeld.length?lgHeld[0].id:0),my=lgSeq;let j;
 try{j=await api(lgQs({since:newest,limit:300}))}catch(e){return}if(my!==lgSeq)return;lgMeta(j);const add=(j.entries||[]).filter(e=>e.id>newest);if(!add.length)return;
 lgHeld=add.concat(lgHeld);if(lgAtTop()&&!lgBusy())lgShowHeld();else lgPill()}
function lgPill(){const b=$('#lg-new');if(!b)return;b.hidden=!lgHeld.length;b.textContent=lgHeld.length+' new entr'+(lgHeld.length==1?'y':'ies')+' ↑'}
function lgShowHeld(){if(!lgHeld.length)return;lgItems=lgHeld.concat(lgItems).slice(0,1000);lgHeld=[];lgDraw();lgPill();if(!lgAtTop())window.scrollTo(0,0)}
function lgToggle(id){lgOpen.has(id)?lgOpen.delete(id):lgOpen.add(id);lgDraw()}
function lgOnly(src){lgF.source=src;lgOpen=new Set();const m=$('#lg-src');if(m)m.value=src;lgLoad()}
function lgDraw(){const L=$('#lg-list');if(!L)return;if(!lgItems.length){L.innerHTML='<p class=sub>Nothing to show'+(lgF.q||lgF.source||lgF.level!=='auto'?' with these filters':' yet')+'.</p>';lgPill();return}
 let day='',h='';for(const e of lgItems){const d=e.time.slice(0,10);if(d!==day){day=d;h+=`<div class=lg-day>${esc(new Date(d+'T12:00:00').toLocaleDateString([],{weekday:'short',month:'short',day:'numeric'}))}</div>`}
  const open=lgOpen.has(e.id);h+=`<div class="lg-l${open?' open':''}" data-id="${e.id}" onclick="lgToggle(${e.id})"><span class=lg-t>${esc(e.time.slice(11))}</span><span class="lg-lv ${esc(e.level)}">${esc(e.level)}</span><span class=lg-s>${esc(e.source)} <i class=lg-c>${open?'▾':'▸'}</i></span><div class=lg-x>${esc(e.text)}</div>${open?`<div class=lg-d>${esc(new Date(e.time).toLocaleString([],{weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit'}))} · ${esc(e.level)} · ${esc(e.source)} · entry ${e.id}<br><button class="btn sm" onclick="event.stopPropagation();lgOnly('${esc(e.source)}')">Only ${esc(e.source)}</button></div>`:''}</div>`}
 L.innerHTML=h;lgPill()}
function lgToggleMenu(){const m=$('#lg-menu');if(!m)return;m.hidden=!m.hidden;if(!m.hidden)lgMenuDraw()}
function lgMenuDraw(){const m=$('#lg-menu');m.innerHTML=`<div class=row><a class=btn href="${U('logs/download')}" download>Download logs</a><button class=btn onclick="lgCopy()">Copy last 100 lines</button></div>
 <label class=sub style="display:flex;align-items:center;gap:.5rem;min-height:44px;margin-top:.4rem"><input type=checkbox ${lgDebug.on?'checked':''} onchange="lgSetDebug(this.checked)">Debug logging${lgDebug.on?'':' (off)'}</label>
 <p class=sub style="margin:0">Debug adds detail, such as timing of every round and why a check could not be read. It switches itself off after 24 hours and what it wrote ages out on its own. Passwords and tokens are never written.</p><span id=lg-cm class=sub></span>`}
async function lgSetDebug(on){try{const j=await api('logs/debug',{on:!!on});lgMeta(j);lgLoad()}catch(e){const c=$('#lg-cm');if(c)c.textContent=e.message}}
async function lgCopy(){const t=lgItems.slice(0,100).map(e=>e.time+' '+e.level.toUpperCase()+' '+e.source+' '+e.text).join('\n');let ok=false;try{await navigator.clipboard.writeText(t);ok=true}catch(x){}
 const c=$('#lg-cm');if(!c)return;if(ok)c.textContent='Copied.';else{c.innerHTML=`<textarea id=lg-tx readonly rows=8 style="width:100%">${esc(t)}</textarea>`;const x=$('#lg-tx');x.focus();x.select()}}
async function renderMap(){mapOpen=new Set();mapPeer=null;document.body.dataset.s='green';clearInterval(mapTimer);closeDrawer();
 mpage().innerHTML=`<div class=top><div class=row><h1 style="margin:0;font-size:28px">Network map</h1></div><button class="btn sm" onclick="location.hash='#/settings/advanced'">← Advanced</button></div><p class=sub id=mapmsg>Reading the switches…</p><div id=mapout></div>`;
 await mapLoad();mapTimer=setInterval(()=>{if(location.hash!=='#/map'){clearInterval(mapTimer);return}mapLoad()},10000)}
async function mapLoad(){let m;try{m=await api('lan/map')}catch(e){const g=$('#mapmsg');if(g)g.textContent='Could not read the switches ('+e.message+'). It may be running an older version.';return}
 if(!$('#mapout'))return;$('#mapmsg').textContent='';drawMap(m);if(mapPeer)loadPeers()}
function drawMap(m){const o=$('#mapout');if(!o)return;mapLast=m;
 const kids={};for(const n of m.nodes)(kids[n.parent||'']=kids[n.parent||'']||[]).push(n);
 const rate=(d,u)=>d==null&&u==null?'no traffic figures':`↓ ${fmtBps(d)} ↑ ${fmtBps(u)}`,pwTxt=w=>!w?'':w.known?' · <span class=sub>not alerting</span>':w.rising.length?` · <b style="color:#FBBF24">${w.rising.map(k=>({errors:'errors',drops:'packet drops',flaps:'link drops'})[k]+' rising (about '+(w.perHour[k]||0).toLocaleString()+' an hour'+(w.split&&w.split[k]?': '+w.split[k].rx.toLocaleString()+' receive, '+w.split[k].tx.toLocaleString()+' transmit':'')+')').join(' and ')}${w.traffic?', carrying about '+fmtBps(w.traffic.avgBps)+' (peak '+fmtBps(w.traffic.peakBps)+')':''}${pwFar(w)}</b>`:w.learning?' · <span class=sub>learning what is normal</span>'+pwQuiet(w):pwQuiet(w),
  pwFar=w=>{const k=w.other&&w.rising.find(x=>x!=='flaps');return k?` · other end (${esc(w.other.label)}): ${w.other.state==='figures'?(w.other.split[k]||{rx:0,tx:0}).rx.toLocaleString()+' receive, '+(w.other.split[k]||{rx:0,tx:0}).tx.toLocaleString()+' transmit an hour':w.other.state==='learning'?'still learning':'no counters'}`:''},
  pwKnownLink=(w,keys)=>w&&keys&&keys.length?` · <label style="white-space:nowrap"><input type=checkbox ${w.known?'':'checked'} data-k="${esc(keys.join('\t'))}" onchange="pwKnown(this,!this.checked)"> alert</label>`:'',
  warn=(e,dr)=>(e?` · <span style="color:#FBBF24">${e.toLocaleString()} errors</span>`:'')+(dr?` · ${dr.toLocaleString()} packet drops`:'');
 const row=(n,depth,path=[])=>{const l=n.link,ports=n.ports||[];if(path.includes(n.id))return '';
  const head=`<div class=r style="gap:.5rem;flex-wrap:wrap"><span class="dot ${esc(n.state)}"></span><b>${esc(n.name)}</b><small class=sub>${esc(n.model||'')}${n.stateWord&&n.stateWord!=='connected'?' · '+esc(n.stateWord):''}</small></div>`;
  const link=l?`<div class=sub>${esc(spd(l.speedMbps))} to ${esc(l.to)}${l.port?` (port ${esc(l.port)} to ${esc(l.parentPort||'?')})`:''} · ${rate(l.down,l.up_bps)}${warn(l.errors,l.drops)}${pwTxt(l.watch)}${pwKnownLink(l.watch,l.watchKeys)}${l.up?'':' · <b>link down</b>'}</div>`:'';
  const wifi=n.kind==='ap'?`<div class=sub>${n.wifi||0} wifi client${n.wifi==1?'':'s'}</div>`:'';
  const pl=ports.length?`<details data-n="${esc(n.id)}"${mapOpen.has(n.id)?' open':''} ontoggle="mapTog(this)"><summary class=sub>${ports.length} port${ports.length==1?'':'s'} in use</summary>${ports.map(p=>{const on=mapPeer&&mapPeer.node===n.id&&mapPeer.port===p.port;return `<div class=sub style="margin-left:.8rem">Port ${esc(p.port)} · <b>${esc(p.name||'nothing named')}</b> · ${esc(spd(p.speedMbps))} · ${rate(p.down,p.up_bps)}${warn(p.errors,p.drops)}${pwTxt(p.watch)}${pwKnownLink(p.watch,p.watchKeys)}${p.keys&&p.keys.length?` · <a href="#" style="color:inherit" onclick="mapPeers('${esc(n.id)}','${esc(p.port)}');return false">${on?'hide':'where does it go?'}</a>`:''}</div>${on?peersHtml(mapPeer):''}`}).join('')}</details>`:'';
  return `<div class=mnode style="margin-left:${depth?14:0}px">${head}${link}${wifi}${pl}${(kids[n.id]||[]).map(c=>row(c,depth+1,path.concat(n.id))).join('')}</div>`};
 const roots=m.nodes.filter(n=>!n.parent||!m.nodes.some(x=>x.id===n.parent));
 o.innerHTML=(m.nodes.length?`<div class=box>${roots.map(n=>row(n,0)).join('')}</div><p class=sub>${m.counts.devices} devices · ${m.counts.ports==null?'':m.counts.ports+' switch port'+(m.counts.ports==1?'':'s')+' in use · '}${m.counts.wired} Ethernet clients · ${m.counts.wifi} Wi-Fi clients. Reminder: an uplink between switches counts as 2 ports and 0 clients. ↓ is traffic going to the device, ↑ is traffic from it, read from the switches' own counters about every 10 seconds. Packet drops here are usually congestion, not a fault. Errors are the better sign of a bad cable.</p>`:'')+pwBox(m)+(m.notes||[]).map(t=>`<p class=sub>${esc(t)}</p>`).join('')}
/* Settings → Alerts. The webhook address is a secret: the screen never gets it back, only whether it is set and where it points. */
let alCfg=null,alOpen=false;
async function loadSiteCfg(){try{siCfg=await api('sites')}catch(e){}}
function siAgo(t){if(!t)return 'never';const s=Math.max(0,Math.round(Date.now()/1000-t));return s<90?s+' s ago':s<5400?Math.round(s/60)+' min ago':Math.round(s/3600)+' h ago'}
async function siteSettings(){const o=$('#siset');if(!o)return;await loadSiteCfg();const c=siCfg;if(!c){o.innerHTML='<p class=sub>Could not load.</p>';return}
 const inp='spellcheck=false autocomplete=off autocapitalize=off autocorrect=off style="min-width:0;box-sizing:border-box"';
 o.innerHTML=`<h3 style="margin:0 0 .3rem">Name of this site</h3>
  <p class=sub style="margin:0 0 .4rem">Shown on the site tabs, for example <b>Bay Harbor</b> or <b>Tidewater</b>. Give each site a short name before pairing${c.name?'':'. Until you do, the tabs show the computer name ('+esc(c.nameDefault)+')'}.</p>
  <div class=row><input id=si-name value="${esc(c.name)}" placeholder="Name this site" maxlength=60 ${inp}><button class="btn" onclick="siName()">Save</button><span id=si-nm></span></div>
  ${(c.sites.length||c.managers.length)?(c.ownWan&&c.ownWan.state==='ok'?`<p class=sub style="margin:.5rem 0 0">This site's internet address: <b>${esc(c.ownWan.ip)}</b> (${c.ownWan.source==='unifi'?'from the UniFi gateway':'from a public address page'}). It is shared with the paired sites so they can tell whether this site's internet is down.</p>`:c.ownWan?`<p class=sub style="margin:.5rem 0 0"><b>This site's internet address is not shared.</b> ${esc(c.ownWan.why)}. It is looked at again every minute.</p>`:''):''}
  <h3 style="margin:1.2rem 0 .3rem">Sites managed from here</h3>
  ${c.sites.length?c.sites.map(s=>{const l=s.link||{};const st=l.state==='linked'?`<span class=sub>Reachable · running MonitorBox ${esc(l.version||'')}</span>`:l.state==='refused'?`<b>${esc(l.error)}</b>`:`<span class=sub>Can\'t reach it right now · ${esc(l.error||'checking…')}${l.lastSeen?' · last heard '+siAgo(l.lastSeen):''}</span>`;
   return `<div class=row><span><b>${esc(s.name)}</b> <small class=sub>${esc(s.address)}</small><br>${st}<br><small class=sub>Internet address: ${s.wan?esc(s.wan):'not shared yet'}</small>${l.state==='linked'&&l.nameSet===false?`<br><b>Remote site does not have its sitename set.</b> <button class="btn sm" onclick="siRemoteName('${esc(s.id)}')">Set it now</button> <small class=sub>It will be called ${esc(s.name)}.</small>`:''}</span><button class="btn sm" onclick="siRename('${esc(s.id)}','${esc(s.name).replace(/'/g,'')}')">Rename</button><button class="btn sm" onclick="siRemove('${esc(s.id)}')">Remove</button></div>`}).join(''):'<p class=sub>No other sites yet.</p>'}
  <h3 style="margin:1rem 0 .3rem">Add a site</h3>
  <p class=sub style="margin-top:0">On the other MonitorBox, open Settings → Sites and press <b>Let a main MonitorBox manage this one</b>. It shows a code. Enter that site's address and the code here. The address is either its internet address with the site port (this box uses ${c.listen.port}; use the number set on that one), or its address on your own network.</p>
  <div class=row><input id=si-addr placeholder="tidewater.example.com:${c.listen.port}" ${inp} style="flex:1 1 14rem"><input id=si-code placeholder="ABCDE-ABCDE-ABCDE-ABCDE-ABCDE" ${inp} style="flex:2 1 16rem"><button class="btn pri" onclick="siAdd()">Add site</button></div><p id=si-msg class=sub></p>
  <h3 style="margin:1.2rem 0 .3rem">Let a main MonitorBox manage this one</h3>
  ${c.managers.length?c.managers.map(m=>`<div class=row><span><b>Managed by ${esc(m.name)}</b><br><small class=sub>Internet address: ${m.wan?esc(m.wan):'not shared yet'}</small></span><button class="btn sm" onclick="siCut('${esc(m.id)}')">Stop being managed by it</button></div>`).join(''):'<p class=sub style="margin-top:0">No main MonitorBox manages this one.</p>'}
  <p class=sub>This opens a separate <b>site port</b> on this box (port <b>${c.listen.port}</b>). If the main MonitorBox is at another site, forward only port ${c.listen.port} on your router. Everything on it is encrypted and needs the key created when you pair, so nothing is shown without it.</p>
  <div class=row><label>Site port <input id=si-port type=number min=1024 max=65535 value="${c.listen.port}" style="width:6.5rem"></label><label class=row><input type=checkbox id=si-on ${c.listen.enabled?'checked':''} onchange="siListen()"> Site port on</label>${c.listen.enabled&&!c.listening?'<b>Port ${c.listen.port} couldn\'t be opened. Pick another one.</b>':''}</div>
  ${c.pairing?`<div class=box style="margin:.6rem 0"><p style="margin:0 0 .3rem">Enter this code on the main MonitorBox. It works once and expires in about ${Math.ceil(c.pairing.expiresIn/60)} minutes.</p><p style="margin:0;font-size:1.3rem;font-family:monospace;overflow-wrap:anywhere">${esc(c.pairing.code)}</p><button class="btn sm" style="margin-top:.5rem" onclick="siPair(false)">Cancel</button></div>`
  :`<div class=row style="margin-top:.5rem"><button class="btn pri" onclick="siPair(true)">Let a main MonitorBox manage this one</button></div>`}`;
 clearTimeout(siTimer);if(c.pairing)siTimer=setTimeout(()=>{if($('#siset'))siteSettings()},20000)}
/* passkeys: the browser's own sign-in with Face ID, Touch ID or a PIN. The box never sees anything secret, only a signature. */
const b64uToBuf=s=>{s=s.replace(/-/g,'+').replace(/_/g,'/');s+='='.repeat((4-s.length%4)%4);const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u.buffer};
const bufToB64u=b=>{const u=new Uint8Array(b);let s='';for(const c of u)s+=String.fromCharCode(c);return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')};
async function passkeySignIn(){const e=$('#e');e.textContent='';try{
 if(!window.PublicKeyCredential)throw new Error('This browser cannot use passkeys here.');
 const o=await api('passkeys/login/options',{}),k=o.publicKey;
 const cred=await navigator.credentials.get({publicKey:{challenge:b64uToBuf(k.challenge),rpId:k.rpId,timeout:k.timeout,userVerification:k.userVerification,allowCredentials:[]}});
 const r=cred.response;
 await api('passkeys/login/finish',{handle:o.handle,credential:{id:cred.id,rawId:bufToB64u(cred.rawId),response:{clientDataJSON:bufToB64u(r.clientDataJSON),authenticatorData:bufToB64u(r.authenticatorData),signature:bufToB64u(r.signature)}}});boot()}
 catch(x){e.textContent=x.name==='NotAllowedError'?'The passkey was cancelled.':x.message}}
async function passkeyAdd(){const m=$('#pk-msg');m.textContent='';try{
 if(!window.PublicKeyCredential)throw new Error('This browser cannot use passkeys here.');
 const name=await askText('Name this passkey','For example the device it lives on, such as "Jeff\'s iPad".','');if(name===null)return;
 const o=await api('passkeys/register/options',{}),k=o.publicKey;
 const cred=await navigator.credentials.create({publicKey:{...k,challenge:b64uToBuf(k.challenge),user:{...k.user,id:b64uToBuf(k.user.id)},excludeCredentials:(k.excludeCredentials||[]).map(c=>({...c,id:b64uToBuf(c.id)}))}});
 const r=cred.response;
 await api('passkeys/register/finish',{handle:o.handle,name,credential:{id:cred.id,rawId:bufToB64u(cred.rawId),response:{clientDataJSON:bufToB64u(r.clientDataJSON),attestationObject:bufToB64u(r.attestationObject)}}});
 securitySettings()}catch(x){m.textContent=x.name==='NotAllowedError'?'The passkey was cancelled.':x.message}}
async function passkeyRemove(id,name){if(!await askYes('Remove the passkey "'+name+'"? That device can no longer sign in with it.'))return;try{await api('passkeys/remove',{id});securitySettings()}catch(x){$('#pk-msg').textContent=x.message}}
async function signOutOthers(){const n=(await api('security')).signedIn-1;if(!await askYes('Sign out every other device? '+(n>0?n+' other device'+(n==1?'':'s')+' will have to sign in again.':'No other device is signed in right now.')+' This one stays signed in.'))return;try{const r=await api('signout-others',{});$('#pk-msg').textContent=r.signedOut?('Signed out '+r.signedOut+' other device'+(r.signedOut==1?'':'s')+'.'):'No other devices were signed in.'}catch(x){$('#pk-msg').textContent=x.message}}
async function passkeyOnlySave(on){try{await api('security',{internetNeedsPasskey:on});securitySettings()}catch(x){$('#pk-msg').textContent=x.message;securitySettings()}}
async function securitySettings(){const o=$('#secset');if(!o)return;let c;try{c=await api('security')}catch(e){o.innerHTML='<p class=sub>Could not load.</p>';return}
 const y=c.you||{};
 o.innerHTML=`<h3 style="margin:0 0 .3rem">Proxy address</h3>
  <p class=sub style="margin:0 0 .4rem">The address of the machine running your proxy, for example <b>192.168.77.9</b>. Only visits that arrive from this address are treated as coming through the proxy. Separate several with commas.</p>
  <div class=row><input id=sec-px value="${esc((c.trustedProxies||[]).join(', '))}" placeholder="192.168.77.9" spellcheck=false autocomplete=off autocapitalize=off style="min-width:0;flex:1 1 14rem"></div>
  <h3 style="margin:1rem 0 .3rem">Public name</h3>
  <p class=sub style="margin:0 0 .4rem">The name you type to reach MonitorBox from outside, for example <b>monitorbox.example.com</b>. When it is set, visits through the proxy under any other name are refused. Leave it empty to allow any.</p>
  <div class=row><input id=sec-host value="${esc(c.publicHost||'')}" placeholder="monitorbox.example.com" spellcheck=false autocomplete=off autocapitalize=off style="min-width:0;flex:1 1 14rem"></div>
  <div class=row style="margin-top:.6rem"><button class="btn pri" onclick="securitySave()">Save</button><span id=sec-msg class=sub></span></div>
  <h3 style="margin:1.4rem 0 .3rem">Passkeys</h3>
  <p class=sub style="margin:0 0 .4rem">A passkey signs you in with Face ID, Touch ID or your device PIN, with no password to type or steal. Add one while you are on the device you want to use, and while you are visiting by your public HTTPS name${c.publicHost?' (<b>https://'+esc(c.publicHost)+'</b>)':''}. Each device needs its own, or a passkey kept in your cloud keychain follows you to your other devices.</p>
  ${(c.passkeys||[]).length?c.passkeys.map(k=>`<div class=row style="margin:.4rem 0"><span style="flex:1"><b>${esc(k.name)}</b> <small class=sub>added ${esc(new Date(k.created*1000).toLocaleDateString())} · ${k.lastUsed?'last used '+esc(new Date(k.lastUsed*1000).toLocaleDateString()):'not used yet'}</small></span><button class="btn sm" onclick="passkeyRemove('${esc(k.id)}','${esc(k.name).replace(/'/g,'')}')">Remove</button></div>`).join(''):'<p class=sub>No passkeys yet.</p>'}
  <div class=row style="margin-top:.4rem"><button class="btn pri" onclick="passkeyAdd()">Add a passkey on this device</button></div>
  <label class=row style="margin-top:.8rem;gap:.5rem;align-items:flex-start"><input type=checkbox ${c.internetNeedsPasskey?'checked':''} ${(c.passkeys||[]).length?'':'disabled'} onchange="passkeyOnlySave(this.checked)"> <span>From outside my home network, require a passkey. The password then works only on your home network.${(c.passkeys||[]).length?'':' (Add a passkey first.)'}</span></label>
  <h3 style="margin:1.4rem 0 .3rem">If you lose a device</h3>
  <p class=sub style="margin:0 0 .4rem">From your home network, sign in with your password, remove that device's passkey above, then sign out every other device here. Anything the lost device was still signed in to stops working. Your backups keep your passkeys, so a restore brings them back.</p>
  <div class=row><button class="btn" onclick="api('logout',{}).then(boot)">Sign out this device</button><button class="btn" onclick="signOutOthers()">Sign out every other device</button></div>
  <p id=pk-msg class=sub></p>
  <p class=sub style="margin-top:1rem">This visit: ${y.viaProxy?'came through the proxy from <b>'+esc(y.ip)+'</b>'+(y.https?' over HTTPS':' (not HTTPS)'):'came directly from <b>'+esc(y.ip)+'</b>'}.</p>
  <p class=sub>After five wrong passwords from one address, sign-in from it pauses for a minute, then longer with each further wrong try. If you set a public name by mistake, open MonitorBox by its address on your home network to fix it.</p>`}
async function securitySave(){const m=$('#sec-msg');m.textContent='Saving…';try{await api('security',{trustedProxies:$('#sec-px').value.split(/[,\s]+/).filter(Boolean),publicHost:$('#sec-host').value});m.textContent='Saved.';securitySettings()}catch(e){m.textContent=e.message}}
async function siName(){try{siCfg=await api('sites/name',{name:$('#si-name').value});$('#si-nm').textContent='Saved.';refreshSites()}catch(e){$('#si-nm').textContent=e.message}}
async function siListen(){try{siCfg=await api('sites/listen',{enabled:$('#si-on').checked,port:parseInt($('#si-port').value,10)});siteSettings()}catch(e){await siteSettings();const m=$('#si-msg');if(m)m.textContent=e.message}}
async function siPair(on){try{if(on){const n=($('#si-name').value||'').trim();if(n)await api('sites/name',{name:n})}if(on)await api('sites/listen',{enabled:true,port:parseInt($('#si-port').value,10)});siCfg=await api(on?'sites/pair/start':'sites/pair/stop',{});siteSettings()}catch(e){await siteSettings();const m=$('#si-msg');if(m)m.textContent=e.message}}
async function siAdd(){const m=$('#si-msg');m.textContent='Pairing…';try{const n=($('#si-name').value||'').trim();if(n)await api('sites/name',{name:n});siCfg=await api('sites/add',{address:$('#si-addr').value,code:$('#si-code').value});await siteSettings();$('#si-msg').textContent='Paired.'}catch(e){m.textContent=e.message}}
async function siRemove(id){if(!await askYes('Stop managing this site from here? It keeps running on its own.'))return;try{siCfg=await api('sites/remove',{id});siteSettings()}catch(e){alert(e.message)}}
async function siRemoteName(id){try{siCfg=await api('sites/remote-name',{id});siteSettings()}catch(e){alert(e.message)}}
async function siRename(id,cur){const n=await askText('Name for this site','',cur);if(!n)return;try{siCfg=await api('sites/rename',{id,name:n});siteSettings()}catch(e){alert(e.message)}}
async function siCut(id){if(!await askYes('Stop being managed by this MonitorBox? It will no longer be able to see or change this one.'))return;try{siCfg=await api('sites/manager/remove',{id});siteSettings()}catch(e){alert(e.message)}}
async function loadAlertCfg(){try{alCfg=await api('alerts')}catch(e){}}
async function alertSettings(){const o=$('#alset');if(!o)return;await loadAlertCfg();const c=alCfg;if(!c){o.innerHTML='<p class=sub>Could not load.</p>';return}
 const l=c.last,ha=c.homeAssistant,em=c.email,ready=ha.connected||ha.set||em.set;
 o.innerHTML=`<h3 style="margin:0 0 .3rem">1. Connect Home Assistant</h3>
  ${ha.connected?`<div class=row><span>Connected to <b>${esc(ha.url)}</b>${ha.kind==='token'?' <small>(with a token)</small>':''}</span><button class="btn sm" onclick="alertDisconnect()">Disconnect</button></div>
   ${ha.needsSignIn?`<div class=box style="margin:.6rem 0"><b>Home Assistant no longer accepts MonitorBox's sign-in.</b> <button class="btn pri sm" onclick="alertConnect(${JSON.stringify(ha.url).replace(/"/g,'&quot;')})">Connect again</button></div>`:''}
   <h3 style="margin:1rem 0 .3rem">Send alerts to</h3><div id=al-devs><p class=sub>Asking Home Assistant…</p></div>`
  :`<p class=sub style="margin-top:0">First, in Home Assistant, make a user just for MonitorBox: <b>Settings → People → Users → Add user</b>. Leave <b>Administrator</b> off and turn on <b>Can only log in from the local network</b>. Then enter your Home Assistant's address here.</p>
   <div class=row><input id=al-ha type=text spellcheck=false autocomplete=off autocapitalize=off autocorrect=off placeholder="http://192.168.77.9:8123" style="flex:1 1 16rem;min-width:0;max-width:100%;box-sizing:border-box"><button class="btn pri" onclick="alertConnect()">Connect</button></div>
   <p class=sub style="margin-top:.6rem">Home Assistant opens its own sign-in page. Sign in as the MonitorBox user and approve. MonitorBox never sees the password; it keeps a sign-in you can remove from that user's profile at any time. MonitorBox only ever sends notifications to your phones and tablets.</p>`}
  <details style="margin-top:.8rem" ontoggle="alOpen=this.open"${alOpen||(ha.set&&!ha.connected)?' open':''}><summary class=sub>Other ways to connect</summary>
   <h3 style="margin:.8rem 0 .3rem">A token instead of the sign-in page</h3>
   <p class=sub style="margin-top:0">In Home Assistant, sign in as the MonitorBox user, open its profile → Security → Long-lived access tokens → Create token, and paste it here.</p>
   <div class=row><input id=al-tu type=text spellcheck=false autocomplete=off autocapitalize=off autocorrect=off placeholder="http://192.168.77.9:8123" value="${esc(ha.url||'')}" style="flex:1 1 12rem;min-width:0;box-sizing:border-box"><input id=al-tt type=text spellcheck=false autocomplete=off autocapitalize=off autocorrect=off placeholder="Paste the token" style="flex:2 1 14rem;min-width:0;box-sizing:border-box"><button class="btn" onclick="alertToken()">Use token</button></div>
   <h3 style="margin:1rem 0 .3rem">A webhook (no account)</h3>
   <p class=sub style="margin-top:0">An automation in Home Assistant that starts from a <b>Webhook</b> trigger decides who is notified. Used only while Home Assistant is not connected above. Home Assistant answers "OK" to any webhook address, so check a typo with the test.</p>
   <div class=row><input id=al-hook type=text spellcheck=false autocomplete=off autocapitalize=off autocorrect=off value="${esc(ha.webhook)}" placeholder="http://192.168.77.9:8123/api/webhook/…" style="flex:1 1 18rem;min-width:0;max-width:100%;box-sizing:border-box">
   <button class="btn" onclick="alertHook()">Save address</button>${ha.set?'<button class="btn" onclick="alertHook(true)">Remove</button>':''}</div>
  </details>
  <h3 style="margin:1.2rem 0 .3rem">2. Email (optional, as well as or instead of Home Assistant)</h3>
  <p class=sub style="margin-top:0">Plain email through any mail server. For <b>Gmail</b>, press the Gmail button, use your full Gmail address as the user, and an <b>app password</b> (Google account → Security → 2-Step Verification → App passwords), not your normal password. The password is stored on this box only.</p>
  <div class=row><button class="btn sm" onclick="alertMailPreset()">Gmail</button></div>
  <div class=fm style="margin-top:.4rem">
   <div class=fld><label for=em-host>Mail server</label><input id=em-host type=text spellcheck=false autocomplete=off autocapitalize=off value="${esc(em.host)}" placeholder="smtp.gmail.com"></div>
   <div class=fld><label for=em-port>Port</label><input id=em-port type=text inputmode=numeric autocomplete=off value="${esc(em.port)}"></div>
   <div class=fld><label for=em-sec>Security</label><select id=em-sec><option value=starttls ${em.security==='starttls'?'selected':''}>STARTTLS (usually port 587)</option><option value=ssl ${em.security==='ssl'?'selected':''}>SSL (usually port 465)</option><option value=none ${em.security==='none'?'selected':''}>None (a mail server on your own network)</option></select></div>
   <div class=fld><label for=em-user>User</label><input id=em-user type=text spellcheck=false autocomplete=off autocapitalize=off value="${esc(em.user)}" placeholder="you@gmail.com"></div>
   <div class=fld><label for=em-pw>Password${em.passwordSet?' <span style="color:var(--acc)">· saved, shown as dots</span>':''}</label><input id=em-pw type=password autocomplete=new-password data-lpignore=true data-1p-ignore data-bwignore name="mb-em-pw-x" placeholder="${em.passwordSet?'Leave empty to keep it':'App password'}"></div>
   <div class=fld><label for=em-from>From</label><input id=em-from type=text spellcheck=false autocomplete=off autocapitalize=off value="${esc(em.from)}" placeholder="you@gmail.com"></div>
   <div class=fld><label for=em-to>Send alerts to</label><input id=em-to type=text spellcheck=false autocomplete=off autocapitalize=off value="${esc(em.to.join(', '))}" placeholder="you@gmail.com, partner@example.com"></div></div>
  <div class=row style="margin-top:.6rem"><button class="btn pri" onclick="alertMailSave()">Save email</button>${em.host||em.to.length?'<button class="btn" onclick="alertMailClear()">Remove email</button>':''}<span id=em-msg></span></div>
  <h3 style="margin:1.2rem 0 .3rem">3. Try it</h3>
  <div class=row><button class="btn pri" onclick="alertTest(this)" ${ready?'':'disabled'}>Send a test alert</button><span id=al-msg></span></div>
  <p class=sub style="margin-top:.6rem">${l?(l.ok?'Last message delivered':'<b>Last message could not be delivered:</b> '+esc(l.error||''))+' · '+esc(l.what)+' · '+esc(lt(l.at)):'Nothing sent yet.'}${c.waiting?' · '+c.waiting+' waiting to be delivered (MonitorBox keeps trying for half an hour)':''}</p>
  <h3 style="margin:1.2rem 0 .3rem">4. Turn alerts on</h3>
  <label class=row><input type=checkbox id=al-on ${c.enabled?'checked':''} ${ready?'':'disabled'} onchange="alertSave()"> Send alerts${ready?'':' <small>(connect Home Assistant or set up email first)</small>'}</label>
  <h3 style="margin:1.2rem 0 .3rem">Details</h3>
  <div class=row><label>Name of this site <input id=al-site value="${esc(c.site)}" placeholder="${esc(c.siteDefault)}" maxlength=60></label>
  <label>Wait <input id=al-delay type=number min=0 max=3600 value="${c.delaySeconds}" style="width:6rem"> seconds before alerting</label>
  <button class="btn" onclick="alertSave()">Save</button></div>
  <h3 style="margin:1.2rem 0 .3rem">What sends an alert</h3>
  <div class=row>${[['down','Down'],['degraded','Degraded'],['unknown','Unknown'],['restored','Restored']].map(([k,t])=>`<label class=row style="min-height:44px"><input type=checkbox id=al-t-${k} ${c.triggers[k]?'checked':''} onchange="alertSave()"> ${t}</label>`).join('')}</div>
  <p class=sub style="margin-top:0">Unknown means MonitorBox could not look (for example the UPS host or a provider is out of reach), which is not the same as down. A UPS running on battery always alerts.</p>`;
 if(ha.connected)alertDevices()}
async function alertDevices(){const o=$('#al-devs');if(!o)return;let r;try{r=await api('alerts/ha/devices')}catch(e){o.innerHTML='<p class=sub>'+esc(e.message)+'</p>';return}
 if(r.error){o.innerHTML=`<p class=sub><b>${esc(r.error)}</b></p><div class=row>${r.needsSignIn?`<button class="btn pri sm" onclick="alertConnect(alCfg.homeAssistant.url)">Connect again</button>`:''}<button class="btn sm" onclick="alertDevices()">Try again</button></div>`;return}
 o.innerHTML=(r.devices.length?r.devices.map(d=>`<label class=row><input type=checkbox data-dev="${esc(d.id)}" ${d.on?'checked':''} onchange="alertDevSave()"> ${esc(d.name)} <small class=sub>${esc(d.id)}</small></label>`).join(''):'<p class=sub>Home Assistant knows no phones or tablets yet. Install the Home Assistant app on one, sign in to this Home Assistant, then press Refresh.</p>')+
  `<div class=row style="margin-top:.4rem"><button class="btn sm" onclick="alertDevices()">Refresh</button><small id=al-dm class=sub></small></div>`}
async function alertDevSave(){const ids=[...document.querySelectorAll('#al-devs input[data-dev]')].filter(x=>x.checked).map(x=>x.dataset.dev);try{alCfg=await api('alerts/ha/devices',{devices:ids});const m=$('#al-dm');if(m)m.textContent=ids.length?'Saved.':'Nothing ticked: no alert will be sent.'}catch(e){const m=$('#al-dm');if(m)m.textContent=e.message}}
async function alertConnect(url){const v=(url||($('#al-ha')||{}).value||'').trim();if(!v){$('#al-msg').textContent='Enter your Home Assistant address first.';return}
 try{const r=await api('alerts/ha/begin',{url:v});location.href=r.url}catch(e){const m=$('#al-msg');if(m)m.textContent=e.message;else alert(e.message)}}
async function alertDisconnect(){if(!await askYes('Disconnect Home Assistant? Alerts stop unless a webhook is saved.'))return;try{alCfg=await api('alerts/ha/disconnect',{});alertSettings()}catch(e){alert(e.message)}}
async function alertToken(){const u=$('#al-tu').value.trim(),t=$('#al-tt').value.trim();if(!u||!t){$('#al-msg').textContent='Enter the address and paste the token.';return}
 try{alCfg=await api('alerts/ha/token',{url:u,token:t});await alertSettings();const n=$('#al-msg');if(n)n.textContent='Connected.'}catch(e){$('#al-msg').textContent=e.message}}
function alertMailPreset(){$('#em-host').value='smtp.gmail.com';$('#em-port').value='587';$('#em-sec').value='starttls';const u=$('#em-user');if(!u.value)u.focus()}
async function alertMailSave(){const v=id=>$('#'+id).value.trim(),m=$('#em-msg'),pw=$('#em-pw').value,e={host:v('em-host'),port:v('em-port'),security:$('#em-sec').value,user:v('em-user'),from:v('em-from'),to:v('em-to')};
 if(pw)e.password=pw;
 try{alCfg=await api('alerts',{email:e});await alertSettings();const n=$('#em-msg');if(n)n.textContent='Saved. Send a test alert to check it.'}catch(x){if(m)m.textContent=x.message}}
async function alertMailClear(){if(!await askYes('Remove the email settings, including the saved password?'))return;try{alCfg=await api('alerts',{email:{clear:true}});await alertSettings();const n=$('#em-msg');if(n)n.textContent='Removed.'}catch(x){$('#em-msg').textContent=x.message}}
async function alertSave(){const m=$('#al-msg');try{alCfg=await api('alerts',{enabled:$('#al-on').checked,site:$('#al-site').value,delaySeconds:parseInt($('#al-delay').value,10),triggers:Object.fromEntries(['down','degraded','unknown','restored'].map(k=>[k,$('#al-t-'+k).checked]))});alertSettings();const n=$('#al-msg');if(n)n.textContent='Saved.'}catch(e){if(m)m.textContent=e.message;await alertSettings();const n=$('#al-msg');if(n)n.textContent=e.message}}
async function alertHook(clear){const v=clear?'':$('#al-hook').value.trim();if(!clear&&!v){$('#al-msg').textContent='Paste the webhook address first.';return}if(clear&&!await askYes('Remove the webhook address?'))return;
 try{if(clear)await api('alerts',{homeAssistant:{webhook:''}});else await api('alerts',{homeAssistant:{webhook:v}});await alertSettings();const n=$('#al-msg');if(n)n.textContent=clear?'Removed.':'Saved. Send a test alert to check it.'}catch(e){$('#al-msg').textContent=e.message}}
async function alertTest(b){b.disabled=true;$('#al-msg').textContent='Sending…';try{const th=$('#al-hook'),typed=th?(th.value||'').trim():'';if(typed&&alCfg&&!alCfg.homeAssistant.connected&&typed!==alCfg.homeAssistant.webhook)await api('alerts',{homeAssistant:{webhook:typed}});const r=await api('alerts/test',{});await alertSettings();const n=$('#al-msg');if(n)n.textContent=r.message}catch(e){await alertSettings();const n=$('#al-msg');if(n)n.textContent=e.message}}
/* Settings → Graphs: what to draw. Each change is saved at once. */
async function saveGraphs(list){const r=await api('graphs',{graphs:list});grCfg=r.graphs;grData=null}
/* the Power page: one heading per UPS; a system ticked under one is no longer offered under another */
async function powerSettings(){const o=$('#pwset');if(!o)return;let d;try{d=await api('power')}catch(e){o.innerHTML=`<p class=sub>${esc(e.message)}</p>`;return}
 if(!(d.ups||[]).length){o.innerHTML='<p class=sub>No battery backup is being watched yet. Add one under Settings → Servers (Battery backup), then come back.</p>';return}
 const free=d.systems.filter(x=>!x.ups);
 const row=(x,u)=>`<label class=row style="gap:.6rem;align-items:center;margin:.35rem 0"><input type=checkbox checked onchange="powerPut('${esc(x.id)}','')"><span>${esc(x.name)} <span class=sub>· ${esc(x.group)}${x.from==='guess'?' · <b>best guess</b>':''}</span>${x.why?`<span class=sub style="display:block">${esc(x.why)}</span>`:''}</span></label>`;
 o.innerHTML=d.ups.map(u=>{const mine=d.systems.filter(x=>x.ups===u.id);
  return `<h3 style="margin:1rem 0 .2rem">${esc(u.name)}</h3><p class=sub style="margin:0">${mine.length?'Keeps these running:':'No systems are on it yet.'}</p>${mine.map(x=>row(x,u)).join('')}`}).join('')
  +(free.length?`<h3 style="margin:1.2rem 0 .2rem">Not on a backup yet</h3><p class=sub style="margin:0">Pick a backup for any that are on one. Leave the rest alone: systems at other sites, or anything with no battery backup.</p>`
   +free.map(x=>`<div class=row style="gap:.6rem;align-items:center;margin:.35rem 0;flex-wrap:wrap"><span style="flex:1 1 14rem">${esc(x.name)} <span class=sub>· ${esc(x.group)}</span>${x.why?`<span class=sub style="display:block">${esc(x.why)}</span>`:''}</span><select aria-label="Backup for ${esc(x.name)}" onchange="powerPut('${esc(x.id)}',this.value)"><option value="">none</option>${d.ups.map(u=>`<option value="${esc(u.id)}">${esc(u.name)}</option>`).join('')}</select></div>`).join(''):'')
  +((d.follows||[]).length?`<p class=sub style="margin-top:1.2rem">These follow the machine they run on, so there is nothing to tick: ${d.follows.map(f=>esc(f.name)+' (on '+esc(f.host)+')').join(', ')}.</p>`:'')+((d.notes||[]).length?`<p class=sub>${d.notes.map(esc).join('<br>')}</p>`:'')+'<div id=powmsg class=sub></div>'}
async function powerPut(system,ups){const m=$('#powmsg');if(m)m.textContent='Saving…';try{await api('power',{system,ups:ups||null});await powerSettings()}catch(e){if(m)m.textContent=e.message}}
async function graphSettings(){const o=$('#grset');if(!o)return;await loadGraphCfg();let conns=[],nodes=[];try{conns=((await api('config/connections')).connections||[]).filter(c=>c.module==='snmp');nodes=(await api('config/monitoring')).monitoring.nodes||[]}catch(e){}
 const name=id=>{const c=conns.find(c=>c.id===id)||{},n=nodes.find(n=>(n.checks||[]).some(k=>k.connection===id));return (n&&n.name)||c.name||id};     // the name the main screen uses, not the connection's internal id
 o.innerHTML=(grCfg.length?grCfg.map((g,i)=>`<div class=devrow><div class=grow><b>${esc(g.title)}</b><div class=sub>${g.kind==='busiest'?'The chattiest device right now (wired, or wifi through the gateway), and where its traffic goes':esc(name(g.connection))+' · '+esc(g.interface)+' · graph tops out at '+(g.maxMbps?fmtBps(g.maxMbps*1e6)+' (you set this)':'the port\'s own speed')}</div></div>
   <button class="btn sm" aria-label="Move up" onclick="graphMove(${i},-1)" ${i?'':'disabled'}>↑</button><button class="btn sm" aria-label="Move down" onclick="graphMove(${i},1)" ${i<grCfg.length-1?'':'disabled'}>↓</button>
   <button class="btn sm" onclick="graphRename(${i})">Rename</button>${g.kind==='busiest'?'':`<button class="btn sm" onclick="graphTop(${i})">Top speed</button>`}<button class="btn sm" onclick="graphRemove(${i})">Remove</button></div>${g.kind==='busiest'?bzFilters(g,i):''}`).join(''):'<p class=sub>No graphs yet.</p>')+
  (hasBusiest()?'':`<h3 style="margin:1rem 0 .3rem">Add a graph</h3><div class=devrow><div class=grow><b>Busiest client</b><div class=sub>Names the chattiest device on your network (wifi included) and, with one tap, where its traffic is going. Needs a UniFi network connection.</div></div><button class="btn sm pri" onclick="graphAddBusiest()">Add</button></div>`)+
  (conns.length?`<h3 style="margin:1rem 0 .3rem">Add a port graph</h3><div class=row><select id=gp-conn aria-label="Server">${conns.map(c=>`<option value="${esc(c.id)}">${esc(name(c.id))}</option>`).join('')}</select><button class="btn" onclick="graphLook()">Show its ports</button></div><div id=gp-list style="margin-top:.6rem"></div>`
   :'<p class=sub style="margin-top:1rem">Port graphs need a system that can report its network traffic (SNMP). Add one first under Settings → Servers.</p>')}
async function graphLook(){const o=$('#gp-list'),cid=$('#gp-conn').value;o.innerHTML='<p class=sub>Asking the system for its ports…</p>';
 try{const [r,w]=await Promise.all([api('detect',{connection:cid}),api('graphs/wan',{connection:cid}).catch(()=>({ports:[]}))]);
  const wan=new Map((w.ports||[]).map(p=>[p.ifname,p]));       // the gateway's own words for which port is the WAN
  grPick={cid,list:(r.interfaces||[]).map(x=>({...x,wan:wan.get(x.name)||null})).sort((a,b)=>(b.wan?1:0)-(a.wan?1:0))};
  o.innerHTML=grPick.list.length?grPick.list.map((x,i)=>`<div class=devrow><div class=grow><b>${esc(x.name)}</b>${x.wan?` <span class=chip style="background:rgba(96,165,250,.18);color:#93C5FD">${esc(x.wan.label||'WAN')}</span>`:''}<div class=sub>${x.wan&&x.wan.ip?esc(x.wan.ip)+' · ':''}${esc(x.status)}${x.speedMbps?', '+(x.speedMbps>=1000?x.speedMbps/1000+' Gbit/s':x.speedMbps+' Mbit/s'):''}</div></div>
    ${grCfg.some(g=>g.connection===cid&&g.interface===x.name)?'<span class=sub>on the main screen</span>':`<button class="btn sm pri" onclick="graphAdd(${i})">Add</button>`}</div>`).join(''):'<p class=sub>That system didn\'t list any ports.</p>'}catch(e){o.textContent=e.message}}
async function graphAdd(i){const x=grPick.list[i],t=await askText('Name for this graph','',x.wan?'WAN '+x.name:x.name);if(t===null)return;
 let top=null;if(x.wan){const v=await askText('Speed of your internet connection','This port is your internet connection. What speed does your plan give you, in Mbit/s? The port itself may be rated higher than your plan. Leave it empty to use the port\'s own speed.',x.wan.speedMbps||'');if(v===null)return;const n=parseInt(v,10);if(n>0)top=n}
 try{await saveGraphs([...grCfg,{connection:grPick.cid,interface:x.name,title:t.trim()||x.name,...(top?{maxMbps:top}:{})}]);await graphSettings();$('#gp-conn').value=grPick.cid;graphLook()}catch(e){alert(e.message)}}
/* the Busiest client card's filters: who it may show. They change only what the card shows. */
function bzFilters(g,i){const f=g.filter||{},ex=f.exclude||[],tick=(k,t)=>`<label class=row style="gap:.5rem;align-items:center;margin:.25rem 0"><input type=checkbox ${f[k]===false?'':'checked'} onchange="bzFilter(${i},'${k}',this.checked)"> ${t}</label>`;
 return `<div style="margin:-.2rem 0 1rem 0"><div class=sub style="margin:.2rem 0">Choose which devices this card may show. This only changes the card. Health, alerts and the other graphs are not affected.</div>
  ${tick('wired','Wired devices')}${tick('wifi','Wi-Fi devices (and anything else only your UniFi gateway can see)')}${tick('servers','Servers you monitor')}${tick('cameras','Cameras')}${tick('iot','IoT devices (anything on a network or Wi-Fi with IoT in its name)')}
  <label class=row style="gap:.5rem;align-items:center;margin:.25rem 0"><input type=checkbox ${f.blacklistOn===false?'':'checked'} onchange="bzFilter(${i},'blacklistOn',this.checked)"> Hide devices that match this list</label>
  <input type=text maxlength=500 value="${esc(f.blacklist||'')}" placeholder="Names, IP addresses, MAC addresses or makers, separated by commas" style="width:100%;box-sizing:border-box" onchange="bzList(${i},this.value)">
  <div class=sub style="margin:.2rem 0">Part of a name or a maker (such as Ring or Sonos) is enough. For a MAC address, the last six digits are enough, such as dd:ee:ff. An IP address can be whole, or the start of a range ending in a dot, such as 192.168.7.</div>
  <label class=row style="gap:.5rem;align-items:center;margin:.25rem 0">Don't show devices using less than <input type=number min=0.01 step=any value="${f.floorMbps||1}" style="width:5.5rem" onchange="bzFloor(${i},this.value)"> Mbit/s</label>
  <div class=sub style="margin:.2rem 0">${ex.length?'Hidden from this card:':'Nothing is hidden. To hide a device, open the card and tap "Hide this client".'}</div>
  ${ex.map((x,k)=>`<div class=row style="gap:.6rem;align-items:center;margin:.2rem 0"><span style="flex:1">${esc(x.name||x.mac||x.id)}${x.mac?` <span class=sub>${esc(x.mac)}</span>`:''}</span><button class="btn sm" onclick="bzUnhide(${i},${k})">Show again</button></div>`).join('')}</div>`}
async function bzSave(i,fn){try{await loadGraphCfg();/* the saved list, not what this page remembers: another device may have changed it */await saveGraphs(grCfg.map(g=>{if(g.kind!=='busiest')return g;const f={...(g.filter||{})};fn(f);return {...g,filter:f}}));bzData=null;graphSettings();pollBusiest()}catch(e){alert(e.message);graphSettings()}}
function bzFilter(i,key,on){bzSave(i,f=>{f[key]=!!on})}
function bzList(i,v){bzSave(i,f=>{f.blacklist=v.trim()})}
function bzFloor(i,v){const n=parseFloat(v);if(!(n>0)){alert('Enter a number of Mbit/s, such as 1 or 0.5.');graphSettings();return}bzSave(i,f=>{f.floorMbps=n})}
function bzUnhide(i,k){bzSave(i,f=>{f.exclude=(f.exclude||[]).filter((_,j)=>j!==k)})}
async function bzHide(){const L=bzPanel&&bzPanel.leader,i=grCfg.findIndex(g=>g.kind==='busiest');if(!L||i<0)return;
 if(!await askYes('Stop showing "'+L.name+'" on the Busiest client card? Health, alerts and the other graphs are not affected. Settings → Graphs brings it back.'))return;
 try{await loadGraphCfg();await saveGraphs(grCfg.map(g=>g.kind!=='busiest'?g:{...g,filter:{...(g.filter||{}),exclude:[...((g.filter||{}).exclude||[]),L.mac?{mac:L.mac,name:L.name}:{id:L.id,name:L.name}]}}));bzData=null;bzPanel=null;pollBusiest();pollGraphPanel()}catch(e){alert(e.message)}}
async function graphAddBusiest(){try{await saveGraphs([...grCfg,{kind:'busiest',title:'Busiest client'}]);bzData=null;graphSettings();pollBusiest()}catch(e){alert(e.message)}}
async function graphRemove(i){if(!await askYes('Take "'+grCfg[i].title+'" off the main screen?'))return;try{await saveGraphs(grCfg.filter((_,k)=>k!==i));graphSettings()}catch(e){alert(e.message)}}
async function graphRename(i){const t=await askText('New name','',grCfg[i].title);if(t===null||!t.trim())return;try{await saveGraphs(grCfg.map((g,k)=>k===i?{...g,title:t.trim()}:g));graphSettings()}catch(e){alert(e.message)}}
async function graphTop(i){const g=grCfg[i],t=await askText('Where the graph tops out','In Mbit/s, for example 1000, 2500 or 10000. Use the speed you pay for or expect. Leave it empty to use the port\'s own speed.',g.maxMbps||'');if(t===null)return;
 const n=t.trim()===''?null:parseInt(t,10);if(n!==null&&(!(n>0)||String(n)!==t.trim())){alert('Enter a whole number of Mbit/s, such as 2500.');return}
 try{await saveGraphs(grCfg.map((x,k)=>{if(k!==i)return x;const y={...x};if(n===null)delete y.maxMbps;else y.maxMbps=n;return y}));graphSettings()}catch(e){alert(e.message)}}
async function graphMove(i,d){const l=[...grCfg],j=i+d;if(j<0||j>=l.length)return;[l[i],l[j]]=[l[j],l[i]];try{await saveGraphs(l);graphSettings()}catch(e){alert(e.message)}}
async function checkNow(id){try{for(const one of [].concat(id))await api('check-now',{id:one})}catch(e){}}     // a source that does not answer stands for several items: check each

/* ---------- drill-down drawer ---------- */
function dropGp(){if(grPanel!==null){grPanel=null;grPData=null;const d=$('#dr');if(d)d.innerHTML=''}}
function openDrawer(ref,focus){
 dropGp();
 const i=typeof ref==='number'?ref:snap.cards.findIndex(c=>c.name===ref);
 if(isSvcCard(snap.cards[i])){openServices(focus);return}
 svcOpen=false; drawer={i:Math.max(0,i),focus:focus||null}; drawerTop=0;
 if(isCamCard(snap.cards[i])){loadCams();startCams()}else stopCams();
 drawDrawer()}
function closeDrawer(){stopCams();stopAllLive();grPanel=null;grPData=null;drawer=null;svcOpen=false;drawerTop=0;drawerSig='';svcTop='';svcPrev=[];const d=$('#dr');if(d)d.innerHTML=''}
/* ---------- cameras: a picture of each camera, from any camera source (UniFi Protect now, Scrypted later) ---------- */
let cams=null,camT=0,camTimer=null;
const lsGet=k=>{try{return localStorage.getItem(k)}catch(e){return null}},lsSet=(k,v)=>{try{localStorage.setItem(k,v)}catch(e){}};
/* the side panel can be dragged wider (or made as wide as the screen) and the camera pictures grow with it */
let dw=+lsGet('mb-dw')||0;function setDw(px){dw=px;if(px)document.documentElement.style.setProperty('--dw',px+'px');else document.documentElement.style.removeProperty('--dw');lsSet('mb-dw',px||'')}
if(dw)setDw(dw);
const wideNow=()=>dw>=innerWidth-40;
function drawerWide(){setDw(wideNow()?0:innerWidth);saveDisplay('dw',dw);drawDrawer()}
function gripDown(ev){ev.preventDefault();const g=ev.target;g.setPointerCapture(ev.pointerId);
 const mv=e=>{setDw(Math.round(Math.max(360,Math.min(innerWidth,innerWidth-e.clientX))));saveDisplay('dw',dw)};
 const up=()=>{g.removeEventListener('pointermove',mv);g.removeEventListener('pointerup',up);g.removeEventListener('pointercancel',up);if(grPanel!==null)drawGraphPanel();else drawDrawer()};
 g.addEventListener('pointermove',mv);g.addEventListener('pointerup',up);g.addEventListener('pointercancel',up)}
const camBig=new Set();const camKey=c=>c.connection+'|'+c.id;
/* ---- live video. Scrypted makes the WebRTC connection with this page; MonitorBox only carries the setup messages (one shared channel for every camera,
   because a browser allows only about six connections to this box). The video itself goes straight from Scrypted to this page. ---- */
let camMode=lsGet('mb-cammode')==='live'?'live':'pics';
const CAMQ=['light','balanced','sharp'];let camQ=CAMQ.includes(lsGet('mb-camq'))?lsGet('mb-camq'):'balanced';   // how big a picture live video asks Scrypted for
const camLive=new Set(),lv=new Map(),bySid=new Map();let hub=null,hubWait=null,liveQ=[],liveQT=null;

function wantLive(c,i){const k=camKey(c);if(!c.liveVia)return false;const st=lv.get(k);if(st&&st.status==='failed')return false;
 return camLive.has(k)||camMode==='live'}
/* what the relays have carried, for when live video misbehaves: shown in a box, so nothing needs typing into the address bar */
let liveDet='';
async function liveDetails(){try{const j=async u=>{const r=await fetch(u);if(!r.ok)throw new Error(u+' answered '+r.status);return r.json()},a=await j('/api/live/relays'),b=SITE?await j(U('live/relays')):null;
 const f=x=>(x||[]).map(v=>`${v.view}: in ${v.packetsIn} (${Math.round(v.bytesIn/1024)} KB), out ${v.packetsOut} (${Math.round(v.bytesOut/1024)} KB), dropped ${v.dropped}, ${v.linked?'linked':'not linked'}${v.target?'':', no target'}, ${v.seconds}s`).join('\n')||'none';
 liveDet='This box: '+a.liveViews+' live views\n'+f(a.mainBox)+(b?'\n\nThe other site: '+b.liveViews+' live views\n'+f(b.siteBox):'')}catch(e){liveDet='Could not read the live details: '+e.message}
 drawDrawer()}      // shown in the panel, not in an alert: an alert freezes the page and the videos stop
function setCamMode(m){camMode=m==='live'?'live':'pics';lsSet('mb-cammode',camMode);saveDisplay('cammode',camMode);camLive.clear();for(const [k,st] of lv)if(st.status==='failed')lv.delete(k);drawDrawer()}
function camGoLive(k,ev){ev.stopPropagation();const st=lv.get(k);if(st&&st.status==='failed'){lv.delete(k);camLive.add(k)}else if(camLive.has(k)||st)camLive.delete(k);else camLive.add(k);drawDrawer()}
function livePost(path,body){return fetch(U(path.replace(/^\/api\//,'')),{method:'POST',headers:{'Content-Type':'application/json','X-MB':'1'},body:JSON.stringify(body)}).then(r=>r.json().then(j=>{if(!r.ok)throw new Error(j.error||'failed');return j}))}
function ensureHub(){
 if(hub&&hub.readyState===1)return Promise.resolve();if(hubWait)return hubWait;
 if(typeof RTCPeerConnection==='undefined'||typeof EventSource==='undefined')return Promise.reject(new Error('this browser cannot play live video'));
 hub=null;const id='p'+Math.random().toString(36).slice(2)+Date.now().toString(36);
 hubWait=new Promise((ok,bad)=>{const es=new EventSource(U('live/events?client=')+id);hub=es;hub.__id=id;
  es.onopen=()=>{hubWait=null;ok()};
  es.onmessage=e=>{try{liveMsg(JSON.parse(e.data))}catch(x){}};
  es.onerror=()=>{es.close();if(hub===es)hub=null;const wasWaiting=!!hubWait;hubWait=null;liveAllFail('The live connection to MonitorBox was lost');if(wasWaiting)bad(new Error('could not open the live connection'))}});
 return hubWait}
function liveAllFail(msg){for(const [k,st] of lv)if(st.status!=='failed')liveFail(k,st,msg,false);drawDrawer()}
function liveFail(k,st,msg,draw=true){st.status='failed';st.msg=msg;teardown(st);if(st.sid)bySid.delete(st.sid);if(draw)drawDrawer()}
function teardown(st){clearTimeout(st.timer);clearTimeout(st.frameTimer);if(st.pc){try{for(const r of st.pc.getReceivers())r.track&&r.track.stop()}catch(e){}try{st.pc.close()}catch(e){}st.pc=null}st.stream=null}
function startLive(c){const k=camKey(c);if(lv.has(k))return;const st={status:'connecting',msg:'Connecting…',chain:Promise.resolve(),stream:null,pc:null,sid:null};lv.set(k,st);
 st.timer=setTimeout(()=>{if(st.status==='connecting')liveFail(k,st,'Live video did not start in time (is the camera reachable from Scrypted?)')},35000);
 ensureHub().then(()=>livePost('/api/live/open',{client:hub.__id,connection:c.liveVia.connection,id:c.liveVia.id,options:cameraOptions()})).then(r=>{
  if(lv.get(k)!==st){livePost('/api/live/close',{session:r.session}).catch(()=>{});return}st.sid=r.session;bySid.set(r.session,k);for(const m of early.splice(0))liveMsg(m)})
 .catch(e=>{if(lv.get(k)===st&&st.status!=='failed')liveFail(k,st,String(e.message||e).slice(0,160))})}
function stopLive(k){const st=lv.get(k);if(!st)return;lv.delete(k);if(st.sid){bySid.delete(st.sid);livePost('/api/live/close',{session:st.sid}).catch(()=>{})}teardown(st)}
function stopAllLive(){for(const k of [...lv.keys()])stopLive(k);camLive.clear();liveQ=[];if(hub){hub.close();hub=null;hubWait=null}}
function syncLive(){if(!cams||!drawer||!isCamCard(snap.cards[drawer.i])||document.hidden)return;
 const want=new Set();cams.cameras.forEach((c,i)=>{if(wantLive(c,i))want.add(camKey(c))});
 for(const k of [...lv.keys()]){const st=lv.get(k);if(st.status!=='failed'&&!want.has(k))stopLive(k)}
 for(const c of cams.cameras)if(want.has(camKey(c))&&!lv.has(camKey(c))&&!liveQ.includes(c))liveQ.push(c);
 if(!liveQT&&liveQ.length)liveQT=setInterval(()=>{const c=liveQ.shift();if(c&&!lv.has(camKey(c)))startLive(c);if(!liveQ.length){clearInterval(liveQT);liveQT=null}},350)}   // one at a time, so Scrypted is not asked for everything at once
function attachVideos(){document.querySelectorAll('.cam video[data-vk]').forEach(v=>{if(!v._mbf){v._mbf=1;v.addEventListener('playing',()=>{const q=lv.get(v.dataset.vk);if(q&&!q.frame){q.frame=true;clearTimeout(q.frameTimer);if(q.status==='live')q.msg='Live';drawDrawer()}})}   /* 'Live' means a picture is on screen, not only that the connection is up */
  const st=lv.get(v.dataset.vk);if(st&&st.stream&&v.srcObject!==st.stream){v.srcObject=st.stream;v.play().catch(()=>{})}})}
function tileSize(){const e=document.querySelector('.cam .ph'),w=e&&e.clientWidth>100?e.clientWidth:640,h=e&&e.clientHeight>60?e.clientHeight:Math.round(w*9/16);return{devicePixelRatio:devicePixelRatio,width:w,height:h}}
function setCamQ(q){camQ=CAMQ.includes(q)?q:'balanced';lsSet('mb-camq',camQ);for(const k of [...lv.keys()])stopLive(k);liveQ=[];drawDrawer()}      // a new quality means new streams
function qualitySize(){return camQ==='light'?{devicePixelRatio:1,width:640,height:360}:camQ==='sharp'?{devicePixelRatio:devicePixelRatio,width:screen.width,height:screen.height}:tileSize()}
function cameraOptions(){return{userAgent:navigator.userAgent,capabilities:{audio:RTCRtpReceiver.getCapabilities?.('audio')||{},video:RTCRtpReceiver.getCapabilities?.('video')||{}},screen:qualitySize()}}
const early=[];   // setup messages can arrive before the answer to 'open' has told us which camera the session belongs to: hold them until it has
function liveMsg(m){const k=bySid.get(m.session),st=k&&lv.get(k);if(!st){if(early.length<200)early.push(m);return}const x=m.message||{};
 if(x.type==='call')liveCall(k,st,x);
 else if(x.type==='ready'){if(st.status==='connecting')st.msg='Starting the picture…';drawDrawer()}
 else if(x.type==='error')liveFail(k,st,x.error||'Live video failed')
 else if(x.type==='closed'){if(st.status==='failed')return;const again=st.status==='live';lv.delete(k);bySid.delete(m.session);teardown(st);if(!again)lv.set(k,{status:'failed',msg:x.reason==='setup failed'?'Live video could not start':'Live video ended',chain:Promise.resolve()});drawDrawer();if(again)syncLive()}}   // a view that ran its time limit simply starts again
function liveReply(st,msg){st.chain=st.chain.then(()=>livePost('/api/live/input',{session:st.sid,message:msg})).catch(()=>{})}
function livePeer(k,st,setup){if(st.pc)return st.pc;const pc=st.pc=new RTCPeerConnection(setup.configuration);st.stream=new MediaStream();
 pc.ontrack=e=>{for(const t of (e.streams[0]?e.streams[0].getTracks():[e.track]))if(!st.stream.getTracks().includes(t))st.stream.addTrack(t);attachVideos()};
 pc.oniceconnectionstatechange=()=>{const s=pc.iceConnectionState;if(s==='connected'||s==='completed'){clearTimeout(st.timer);st.status='live';st.msg=st.frame?'Live':'Waiting for the picture…';if(!st.frame&&!st.frameTimer)st.frameTimer=setTimeout(()=>{if(!st.frame&&lv.get(k)===st)liveFail(k,st,'The connection is up but no picture has arrived')},20000);drawDrawer()}
  else if(s==='failed'||s==='closed')liveFail(k,st,'The live connection was lost');else if(s==='disconnected'){st.msg='Reconnecting…';drawDrawer()}};
 if(setup.audio)pc.addTransceiver('audio',setup.audio);if(setup.video)pc.addTransceiver('video',setup.video);return pc}
function iceDone(pc){if(pc.iceGatheringState==='complete')return Promise.resolve();return new Promise(ok=>{const f=()=>{if(pc.iceGatheringState==='complete'){pc.removeEventListener('icegatheringstatechange',f);ok()}};pc.addEventListener('icegatheringstatechange',f)})}
async function liveCall(k,st,msg){const reply=(value,error)=>liveReply(st,{type:'result',callId:msg.callId,value,error});
 try{const [first,second]=msg.args||[];
  const pc=livePeer(k,st,msg.method==='createLocalDescription'?(second||{}):{});
  if(msg.method==='createLocalDescription'){
   pc.onicecandidate=e=>{if(e.candidate&&msg.trickle)liveReply(st,{type:'candidate',callId:msg.callId,candidate:e.candidate.toJSON?e.candidate.toJSON():e.candidate})};
   let d=first==='offer'?await pc.createOffer({offerToReceiveAudio:!!(second&&second.audio),offerToReceiveVideo:!!(second&&second.video)}):await pc.createAnswer();
   await pc.setLocalDescription(d);if(!msg.trickle)await iceDone(pc);d=pc.localDescription||d;reply({type:d.type,sdp:d.sdp})}
  else if(msg.method==='setRemoteDescription'){await pc.setRemoteDescription(first);reply(null)}
  else if(msg.method==='addIceCandidate'){await pc.addIceCandidate(first);reply(null)}
  else throw new Error('unsupported live setup step')}
 catch(e){reply(null,String(e.message||e).slice(0,200))}}
document.addEventListener('visibilitychange',()=>{if(!drawer||!isCamCard(snap.cards[drawer.i]))return;if(document.hidden){for(const k of [...lv.keys()])stopLive(k);liveQ=[]}else syncLive()});
function camTap(k,el){camBig.has(k)?camBig.delete(k):camBig.add(k);el.classList.toggle('big')}
const isCamCard=c=>!!c&&c.name==='Cameras';
const CAMWORD={healthy:'OK',degraded:'Degraded',failed:'Offline',unknown:'Unknown'};
function loadCams(){fetch(U('cameras')).then(r=>r.json()).then(j=>{cams=j;camT=Date.now();if(drawer&&isCamCard(snap.cards[drawer.i]))drawDrawer()}).catch(()=>{})}
/* pictures: each camera's picture is asked for again about a second after the last one arrived, a few at a time. No connection is kept open
   (a browser only allows about six to this box, so one open stream per camera left most cameras blank). */
const CAM_EVERY=1000,CAM_PARALLEL=3;let camBusy=0;
function loadPic(img){img.__busy=1;camBusy++;
 fetch(img.dataset.src+'&t='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw 0;return r.blob()}).then(b=>{const u=URL.createObjectURL(b),old=img.__url;img.src=u;img.__url=u;if(old)URL.revokeObjectURL(old);img.parentNode.classList.remove('none')}).catch(()=>{}).finally(()=>{img.__busy=0;img.__due=Date.now()+CAM_EVERY;camBusy--})}
function pollPics(){if(document.hidden||!drawer||!isCamCard(snap.cards[drawer.i]))return;
 const due=[...document.querySelectorAll('.cam:not(.islive) img')].filter(i=>!i.__busy&&(i.__due||0)<=Date.now()).sort((a,b)=>(a.__due||0)-(b.__due||0));
 for(const i of due){if(camBusy>=CAM_PARALLEL)break;loadPic(i)}}
function startCams(){stopCams();camTimer=setInterval(pollPics,250)}
function stopCams(){if(camTimer){clearInterval(camTimer);camTimer=null}}
const camUrl=c=>U('camera-snapshot?conn=')+encodeURIComponent(c.connection)+'&id='+encodeURIComponent(c.id);
function camSection(){
 if(!cams)return '<p class=sub>Loading the cameras…</p>';
 const errs=(cams.errors||[]).map(e=>`<p class=sub>Could not ask ${esc(e.connection)}: ${esc(e.error)}</p>`).join('');
 if(!cams.cameras.length)return errs||'<p class=sub>No cameras reported yet.</p>';
 const anyLive=cams.cameras.some(c=>c.liveVia);
 const ctl=`<div class=camctl><span class=seg><button aria-pressed=${camMode==='pics'} onclick="setCamMode('pics')">Snapshots</button><button aria-pressed=${camMode==='live'} onclick="setCamMode('live')">Live</button></span>${camMode==='live'?`<span class=seg title="Picture quality of live video">${[['light','Light'],['balanced','Balanced'],['sharp','Sharp']].map(([q,n])=>`<button aria-pressed=${camQ===q} onclick="setCamQ('${q}')">${n}</button>`).join('')}</span><button class="btn sm" onclick="liveDetails()">Live details</button>`:''}<small>${camMode==='live'?(anyLive?'Live video from Scrypted; other cameras show snapshots':'Live video needs Scrypted (none of these cameras has it)'):'A new snapshot about every second'}</small></div>${liveDet?`<pre class=sub style="white-space:pre-wrap;margin:.4rem 0">${esc(liveDet)}</pre><div class=row><button class="btn sm" onclick="liveDetails()">Refresh</button><button class="btn sm" onclick="liveDet='';drawDrawer()">Hide</button></div>`:''}`;
 return errs+ctl+`<div class=camgrid>${cams.cameras.map(c=>{const k=camKey(c),st=lv.get(k),on=st&&st.status!=='failed';return `<figure class="cam${c.state==='failed'?' off':''}${camBig.has(k)?' big':''}${on?' islive':''}" onclick="camTap(decodeURIComponent('${encodeURIComponent(k)}'),this)">
  <div class=ph>${c.snapshot?`<img alt="${esc(c.name)}" data-src="${esc(camUrl(c))}" src="${esc(camUrl(c))}&t=${camT}" onerror="this.parentNode.classList.add('none')">`:''}${on?`<video data-vk="${esc(k)}" playsinline muted autoplay></video><span class="ls${st.status==='live'?' ok':''}">${esc(st.msg)}</span>`:''}<span class=nop>No picture</span></div>
  <figcaption><b>${esc(c.name)}</b> ${chip(c.state,CAMWORD[c.state]||c.state)}<div class=sub>${esc(c.detail)}</div>${st&&st.status==='failed'?`<div class=sub>Live video unavailable: ${esc(st.msg)}</div>`:''}${c.liveVia&&c.snapshot&&(camMode==='pics'||(st&&st.status==='failed'))?`<button class="btn sm gl" onclick="camGoLive(decodeURIComponent('${encodeURIComponent(k)}'),event)">${on||camLive.has(k)&&!(st&&st.status==='failed')?'Stop live':st&&st.status==='failed'?'Try live again':'Go live'}</button>`:''}</figcaption></figure>`}).join('')}</div>`}
/* everything under a node's name: history, causes, checks, buttons. The side panel and the services list share it. */
/* the Port errors item page (#295): switch it on or off, see which ports are rising, and choose per port whether it alerts */
let pwPage=null,pwAt=0,pwOpen=new Set();
function pwTog(d){if(d.open)pwOpen.add(d.dataset.o);else pwOpen.delete(d.dataset.o)}
function pwFetch(now){if(!now&&Date.now()-pwAt<5000)return;pwAt=Date.now();api('portwatch').then(d=>{pwPage=d}).catch(()=>{})}
async function pwSwitch(on){try{await api('portwatch',{on})}catch(e){alert(e.message)}pwFetch(true)}
async function pwGone(el){try{await api('portwatch',{keys:[el.dataset.k],gone:true})}catch(e){alert(e.message)}pwFetch(true)}
async function pwAlert(el){try{await api('portwatch',{keys:[el.dataset.k],known:!el.checked})}catch(e){alert(e.message);el.checked=!el.checked}pwFetch(true)}
const pwKinds={errors:'errors',drops:'packet drops',flaps:'link drops'};
function pwSpan(m){m=Math.max(0,Math.round(m||0));if(m<60)return m+' min';const h=Math.floor(m/60),r=m%60;if(h<24)return h+' h'+(r?' '+r+' min':'');const d=Math.floor(h/24),hh=h%24;return d+(d==1?' day':' days')+(hh?' '+hh+' h':'')}
/* errors and drops that stay below the alert line: shown, in plain grey, so a link that is busy-but-fine can still be seen */
function pwPct(x){const p=x*100;return p>=0.0001?Number(p.toPrecision(2)).toString()+'%':'under 0.0001%'}
function pwQuiet(w){const per=(w&&w.perHour)||{},sh=(w&&w.shares)||{},parts=['errors','drops'].filter(k=>per[k]).map(k=>per[k].toLocaleString()+' '+(k==='errors'?'errors':'packet drops')+' an hour'+(sh[k]!=null?' ('+pwPct(sh[k])+' of packets)':''));
 return parts.length?` · <span class=sub>${parts.join(', ')}, below the alert line</span>`:''}
function pwRow(r){return `<label class=row style="min-height:44px"><input type=checkbox ${r.alert?'checked':''} data-k="${esc(r.key)}" onchange="pwAlert(this)"> <span>${esc(r.label)}${r.kinds&&r.kinds.length?' · '+r.kinds.map(k=>pwKinds[k]+' rising'+(r.perHour&&r.perHour[k]?' (about '+r.perHour[k].toLocaleString()+' an hour)':'')).join(', '):''} · <span class=sub>Alert on this port</span></span></label>`}
function pwSection(){pwFetch();const d=pwPage;if(!d)return '<p class=sub>Loading the ports…</p>';
 return `<p class=sub style="margin-top:8px">${d.on?(d.ready?`Watching ${d.ports} port${d.ports==1?'':'s'}. `:'Working out which ports the map shows. '):'Not watching. '}<a href="#/map">Open the network map</a></p>`+
  ((d.watched||[]).length?`<details data-o="ports" ontoggle="pwTog(this)"${pwOpen.has('ports')?' open':''} style="margin-top:4px"><summary class=sub>Which ports</summary><div class=sub style="margin-top:4px">${d.watched.map(w=>esc(w.label)+' · '+pwSpan(w.minutes)+' of readings'+(w.resets?` · its counter went backwards ${w.resets} time${w.resets==1?'':'s'} (${esc(w.resetKind)}${w.resetFrom!=null?', from '+Number(w.resetFrom).toLocaleString()+' down to '+Number(w.resetTo).toLocaleString():''}, last ${w.resetAgoMin} min ago)`:'')).join('<br>')}</div></details>`:'')+
  ((d.others&&d.others.count)?`<details data-o="others" ontoggle="pwTog(this)"${pwOpen.has('others')?' open':''} style="margin-top:4px"><summary class=sub>${d.others.count} other interfaces are read but not counted (no link)</summary><div class=sub style="margin-top:4px">${(d.others.where||[]).map(g=>esc(g.from)+' ('+esc(g.id)+'): '+g.count+', last read '+g.lastAgoMin+' min ago').join('<br>')}<br><br>${d.others.names.map(esc).join('<br>')}${d.others.count>d.others.names.length?'<br>…':''}</div></details>`:'')+
  ((d.suspect||[]).length?`<div class=sub style="margin-top:6px">${d.suspect.map(g=>esc(g.from)+' ('+esc(g.id)+'): read as a separate device: '+esc(g.why)).join('<br>')}${(d.others&&d.others.unifiNames||[]).length?'<br>UniFi calls its devices: '+d.others.unifiNames.map(esc).join(', ')+'.':''}</div>`:'')+
  ((d.down||[]).length?`<div class=sub style="margin-top:6px"><b>Links down</b></div>${d.down.map(r=>`<div class=row style="min-height:44px"><span>${esc(r.label)} · link is down (was up)</span><button class="btn sm" data-k="${esc(r.key)}" onclick="pwGone(this)">Not coming back</button></div>`).join('')}`:'')+
  (d.rising.length?`<div class=sub style="margin-top:6px"><b>Rising now</b></div>${d.rising.map(pwRow).join('')}`:(d.on?'<p class=sub>No port is rising.</p>':''))+
  ((d.quiet||[]).length?`<div class=sub style="margin-top:6px"><b>Below the alert line</b></div>${d.quiet.map(r=>`<div class=row style="min-height:44px"><span>${esc(r.label)}${pwQuiet(r)}${r.learning?' · <span class=sub>still learning</span>':''}</span></div>`).join('')}`:'')+
  (d.off.length?`<div class=sub style="margin-top:6px"><b>Not alerting</b></div>${d.off.map(pwRow).join('')}`:'')}
const nmOf=id=>snap.nodes[id]?snap.nodes[id].name:id;
function nodeInner(n){const nm=nmOf,one=!!(n.service&&!n.service.synthetic&&n.checks.filter(c=>c.web).length===1);return `   <div class=hist data-n="${esc(n.id)}">${histHtml(n.id)}</div>
   ${n.detail?`<div class=sub>${esc(n.detail)}</div>`:''}
   ${n.since&&n.state!=='healthy'&&n.state!=='pending'?`<small>${since(n.label,n.since)}</small>`:''}
   ${n.affectedBy.length?`<div class=sub>Affected by ${esc(n.affectedBy.map(nm).join(', '))}. That is the cause to fix first.</div>`:''}
   ${n.affects.length?`<div class=sub>Also affecting ${esc(n.affects.map(nm).join(', '))}</div>`:''}
   ${n.dependsOn.length?`<small>Depends on ${esc(n.dependsOn.map(nm).join(', '))}</small>`:''}
   ${n.checks.length?`<ul class=checks>${n.checks.map(c=>`<li>${chip(c.state,c.state==='healthy'?'OK':c.state==='degraded'?'Degraded':c.state==='failed'?'Failed':c.state==='unknown'?'Unknown':'…')}<span>${c.type==='ports'?'Port counters':esc(c.type)+' '+esc(c.label||c.target)}</span><span${c.notice?' class=note':''}>${esc(c.detail)}${c.ms!=null?' · '+c.ms+' ms':''}</span>${c.web?`<button class="btn sm" onclick="editCheckUrl('${esc(n.id)}','${esc(c.id)}')">${one?'Change address':'Edit monitored address'}</button>`:''}</li>`).join('')}</ul>`:''}
   ${n.id==='port-errors'?pwSection():''}
   <div class=row style="margin-top:8px"><button class="btn sm" onclick="checkNow('${esc(n.id)}')">Check now</button>${n.id==='port-errors'?`<button class="btn sm" onclick="pwSwitch(${!(pwPage&&pwPage.on)})">${pwPage&&pwPage.on?'Disable':'Enable'}</button>`:''}<button class="btn sm" onclick="renameNode('${esc(n.id)}')">Rename</button>${((n.service?!n.service.synthetic:(!n.builtin&&n.kind!=='aggregate'&&n.id!=='port-errors'))&&!one)?`<button class="btn sm" onclick="setLink('${esc(n.id)}')">${(n.service?n.service.url:n.link)?'Change opened link':'Set opened link'}</button>`:''}${!n.service&&safeUrl(n.link)?`<a class="btn sm" href="${esc(n.link)}" target=_blank rel="noopener noreferrer">Open ↗</a>`:''}${n.kind==='aggregate'||n.builtin||n.id==='port-errors'?'':`<button class="btn sm" onclick="editMonitoring('${esc(n.id)}')">Edit monitoring</button>`}${n.kind==='aggregate'||n.id==='port-errors'?'':`<button class="btn sm" onclick="setExpected('${esc(n.id)}',${!n.expected})">${n.expected?'Clear expected down':'Mark expected down'}</button>`}${n.builtin||n.id==='port-errors'?'':`<button class="btn sm" onclick="setCritical(['${esc(n.id)}'],${!n.critical})">${n.critical?'Clear critical':'Mark critical'}</button>`}${n.builtin||n.id==='port-errors'?'':`<button class="btn sm" onclick="stopWatching('${esc(n.id)}')">Stop watching</button>`}
    ${n.canWake?`<button class="btn sm" onclick="wake('${esc(n.id)}')" ${(snap.wakes&&snap.wakes[n.id]&&['sending','waiting'].includes(snap.wakes[n.id].state))?'disabled':''}>Wake</button>`:''}</div>
   ${snap.wakes&&snap.wakes[n.id]?`<div class=sub style="margin-top:6px">${esc(snap.wakes[n.id].detail)}</div>`:''}`}
/* make a's children look like b's, changing only what differs: a new response time changes one piece of text, the camera pictures are never rebuilt */
function morphKids(a,b){const ac=[...a.childNodes],bc=[...b.childNodes];
 for(let i=0;i<bc.length;i++){
  if(i>=ac.length){a.appendChild(bc[i].cloneNode(true));continue}
  const x=ac[i],y=bc[i];
  if(x.nodeType!==y.nodeType||x.nodeName!==y.nodeName){a.replaceChild(y.cloneNode(true),x);continue}
  if(x.nodeType!==1){if(x.nodeValue!==y.nodeValue)x.nodeValue=y.nodeValue;continue}
  for(const at of [...x.attributes])if(!y.hasAttribute(at.name)&&!(x.nodeName==='IMG'&&at.name==='src'&&x.dataset.src===y.dataset.src))x.removeAttribute(at.name);
  const same=x.nodeName==='IMG'&&x.dataset.src===y.dataset.src;       // the same picture or live stream keeps playing: its src is the timer's to change
  for(const at of y.attributes)if(!(same&&at.name==='src')&&x.getAttribute(at.name)!==at.value)x.setAttribute(at.name,at.value);
  morphKids(x,y)}
 while(a.childNodes.length>bc.length)a.removeChild(a.lastChild)}
function drawDrawer(){
 const card=snap&&snap.cards[drawer.i]; if(!card){closeDrawer();return}
 const nm=id=>snap.nodes[id]?snap.nodes[id].name:id;
 const nodes=card.nodes.map(id=>snap.nodes[id]).sort((a,b)=>(a.id===drawer.focus?-1:0)-(b.id===drawer.focus?-1:0));
 const old=document.querySelector('.drawer'),keep=old?old.scrollTop:drawerTop;
 const inner=`<div class=dgrip onpointerdown=gripDown(event) title="Drag to make this panel wider or narrower"></div>
  <div class=row style="justify-content:space-between"><h2 style="margin:0">${esc(card.name)}</h2><span><button class="btn sm" onclick=drawerWide()>${wideNow()?'Narrower':'Wider'}</button> <button class="btn sm" onclick=closeDrawer()>Close</button></span></div>
  <p class=sub>${chip(card.state,card.label)} ${esc(card.big)} · ${esc(card.line)}</p>
  <div class=row><button class="btn sm pri" onclick="checkNow()">Check everything now</button></div>
  ${isCamCard(card)?camSection():''}
  ${nodes.map(n=>`<div class=node><div class=row style="justify-content:space-between"><b>${esc(n.name)}${n.critical?' <small>(critical)</small>':''}</b>${chip(n.muted&&n.state!=='healthy'?'expected':n.state,n.muted&&n.state==='failed'?n.label:(n.muted&&n.state!=='healthy'&&n.state!=='pending'?'Expected down':n.label))}</div>
${nodeInner(n)}</div>`).join('')}`;
 const html=`<div class=scrim onclick=closeDrawer()></div><aside class=drawer>${inner}</aside>`;
 if(old&&drawerSig===html){if(isCamCard(card))syncLive();return}      // nothing changed: leave the panel alone
 drawerSig=html;
 if(old){const t=document.createElement('div');t.innerHTML=inner;morphKids(old,t)}else $('#dr').innerHTML=html;      // new numbers go into the same panel element: it is never swapped for another, so it cannot blink or lose its place
 const nw=document.querySelector('.drawer');if(nw){nw.scrollTop=keep;requestAnimationFrame(()=>{nw.scrollTop=keep})}
 loadHist(nodes.map(n=>n.id));if(isCamCard(card)){attachVideos();syncLive()}}
/* ---------- services directory: what runs where, with the app's icon and a link that opens it in a new window ---------- */
const svcStacks=new Set(),svcNodes=new Set();
const pretty=s=>{const x=String(s).replace(/[-_.]+/g,' ').trim();return x.slice(0,1).toUpperCase()+x.slice(1)};   // the same tidy-up the Portainer module gives container names, so a stack looks like its containers
const isSvcCard=c=>!!c&&c.nodes.some(id=>snap.nodes[id]&&snap.nodes[id].service);
function toggleSvcNode(id){if(svcNodes.has(id))svcNodes.delete(id);else svcNodes.add(id);drawServices()}
function toggleStack(k){if(svcStacks.has(k))svcStacks.delete(k);else svcStacks.add(k);drawServices()}
function openServices(focus){dropGp();drawer=null;svcOpen=true;drawerTop=0;if(focus)svcNodes.add(focus);drawServices()}
const SRANK={failed:3,degraded:2,unknown:1,pending:1,expected:0,healthy:0};
const worstOf=ns=>ns.reduce((w,n)=>(SRANK[ds(n,n.state)]||0)>(SRANK[w]||0)?ds(n,n.state):w,'healthy');
const initials=t=>(String(t).match(/[A-Za-z0-9]+/g)||['?']).slice(0,2).map(w=>w[0].toUpperCase()).join('');
const safeUrl=u=>/^https?:\/\//i.test(u||'')?u:'';
/* A pure grouping step: servers (by environment) -> rows, where containers of one multi-container stack fold into a single stack row. */
function svcGroups(nodes){
 const envs={};
 for(const n of nodes){const sv=n.service;if(!sv)continue;(envs[sv.env||'Other']=envs[sv.env||'Other']||[]).push(n)}
 return Object.keys(envs).sort((a,b)=>a.localeCompare(b)).map(env=>{
  const list=envs[env].sort((a,b)=>(a.service.title||a.name).localeCompare(b.service.title||b.name)),stacks={};
  for(const n of list)if(n.service.stack)(stacks[n.service.stack]=stacks[n.service.stack]||[]).push(n);
  const rows=[],done=new Set();
  for(const n of list){const st=n.service.stack;
   if(st&&stacks[st].length>1){if(!done.has(st)){done.add(st);rows.push({stack:st,key:env+'|'+st,members:stacks[st]})}}
   else rows.push({node:n})}
  return{env,rows}})}
/* Which bundled icon fits a service. The image name is the best clue ("plexinc/pms-docker" says nothing, but the container is called "plex"),
   so the image, container, title and stack names are tried in turn: exact names first, then any word of a name ("homebridge-homebridge-1"). */
function loadIcons(){if(ICONS!==null)return;ICONS=false;fetch('/icons/index.json').then(r=>r.json()).then(j=>{ICONS={set:new Set(j.icons),al:j.aliases||{}};if(svcOpen)drawServices()}).catch(()=>{})}
function iconSlug(...cands){if(!ICONS)return '';
 const cs=cands.filter(Boolean).map(c=>String(c).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'')).filter(Boolean),ok=s=>{s=ICONS.al[s]||s;return ICONS.set.has(s)?s:ICONS.set.has(s.replace(/-/g,''))?s.replace(/-/g,''):''};
 for(const c of cs){const s=ok(c);if(s)return s}
 for(const c of cs)for(const w of c.split('-')){if(w.length<3)continue;const s=ok(w);if(s)return s}
 return ''}
const svcSlug=sv=>iconSlug(sv.icon,sv.container,sv.title,sv.stack);
function svcIcon(sv,slug){const t=sv.title||sv.container||'?';slug=slug===undefined?svcSlug(sv):slug;
 const ini=`<span class=ini ${slug?'style="display:none"':''}>${esc(initials(t))}</span>`;
 return slug?`<img src="/icons/${slug}.svg" alt="" width=40 height=40 onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">${ini}`:ini}
function svcTile(sv){const u=safeUrl(sv.url);return u?`<a class=ico href="${esc(u)}" target=_blank rel="noopener noreferrer" aria-label="Open ${esc(sv.title||sv.container)}" onclick="event.stopPropagation()">${svcIcon(sv)}</a>`:`<span class=ico>${svcIcon(sv)}</span>`}
function svcRow(n,sub){const sv=n.service||{},u=safeUrl(sv.url),open=svcNodes.has(n.id),title=sv.title||sv.container||n.name;
 return `<div class="svcrow${sub?' sub2':''}${open?' on':''}" data-n="${esc(n.id)}">${n.service?svcTile(sv):`<span class=ico>${esc(initials(title))}</span>`}<div class="grow" style="cursor:pointer" role=button aria-expanded=${open} onclick="toggleSvcNode('${esc(n.id)}')"><b>${esc(title)}</b>
  <div class=sub>${dotc(ds(n,n.state))} ${esc(n.service&&!n.service.synthetic?tidy(n.detail||n.label):n.detail||n.label)}</div></div>
  ${u?`<a class="btn sm open" href="${esc(u)}" target=_blank rel="noopener noreferrer" aria-label="Open ${esc(title)} in a new window">↗</a>`:''}</div>`
  +(open?`<div class="node inl${sub?' sub2':''}">${nodeInner(n)}</div>`:'')}
/* Replace only the rows that changed, so icons and scroll position stay put while status updates arrive */
function patchList(el,html,prev){const tmp=document.createElement('div');tmp.innerHTML=html;const nw=[...tmp.children],sig=nw.map(x=>x.outerHTML);
 if(prev.length!==nw.length||el.children.length!==nw.length){el.innerHTML=html;return sig}
 nw.forEach((c,i)=>{if(sig[i]!==prev[i])el.children[i].replaceWith(c)});return sig}
function drawServices(){
 if(!snap){return}
 loadIcons();
 const all=Object.values(snap.nodes),nodes=all.filter(n=>n.service&&n.kind!=='aggregate'),groups=svcGroups(nodes),eg=envGroups(all),envNode={};
 for(const g of eg.groups)envNode[g.env]=g.node;
 const loose=snap.cards.filter(isSvcCard).flatMap(c=>cardRows(c).loose).filter(n=>!eg.taken.has(n.id)&&!n.service);
 const old=document.querySelector('.drawer'),keep=old?old.scrollTop:drawerTop;
 const body=groups.map(g=>`<div class=svcenv>${esc(g.env)}${g.env!=='Other'?` <button class="btn sm" style="float:right;text-transform:none;letter-spacing:0" onclick="removeEnv(decodeURIComponent('${encodeURIComponent(g.env)}'))">Remove all</button>`:''}</div>`+(envNode[g.env]?svcRow(Object.assign({},envNode[g.env],{service:{title:'Portainer environment',icon:'portainer',synthetic:true}}),false):'')+g.rows.map(r=>{
  if(r.node)return svcRow(r.node,false);
  const open=svcStacks.has(r.key),w=worstOf(r.members),slug=iconSlug(r.stack)||r.members.map(svcSlug).find(Boolean)||'';
  return `<div class=svcrow data-stack="${esc(r.key)}" style="cursor:pointer" onclick="toggleStack(decodeURIComponent('${encodeURIComponent(r.key)}'))" role=button aria-expanded=${open}><span class=ico>${svcIcon({title:pretty(r.stack)},slug)}</span>
   <div class=grow><b>${esc(pretty(r.stack))}</b><div class=sub>${dotc(w)} ${r.members.length} services · ${open?'tap to fold':'tap to open'}</div></div><span aria-hidden=true>${open?'▾':'▸'}</span></div>`
   +(open?r.members.map(n=>svcRow(n,true)).join(''):'')}).join('')).join('')
  +(loose.length?`<div class=svcenv>Other</div>`+loose.map(n=>svcRow(n,false)).join(''):'');
 const cs=snap.cards.filter(isSvcCard);
 const top=`<div class=row style="justify-content:space-between"><h2 style="margin:0">Services</h2><button class="btn sm" onclick=closeDrawer()>Close</button></div>
  <p class=sub>${cs.map(c=>`${chip(c.state,c.label)} ${esc(c.big)} · ${esc(c.line)}`).join('<br>')}</p>
  <div class=row><button class="btn sm pri" onclick="checkNow()">Check everything now</button></div>
  <p class=sub>Tap an icon or ↗ to open a service in a new window. Tap a row for its checks and history.</p>`;
 let aside=old&&old.classList.contains('svc')?old:null;
 if(!aside){$('#dr').innerHTML=`<div class=scrim onclick=closeDrawer()></div><aside class="drawer svc"><div id=svctop></div><div id=svcbody></div></aside>`;aside=document.querySelector('.drawer');svcTop='';svcPrev=[]}
 if(top!==svcTop){aside.querySelector('#svctop').innerHTML=top;svcTop=top}
 svcPrev=patchList(aside.querySelector('#svcbody'),body||'<p class=sub>No services yet. Connect Portainer under Settings > Servers.</p>',svcPrev);
 if(aside!==old){aside.scrollTop=keep;requestAnimationFrame(()=>{aside.scrollTop=keep})}
 loadHist([...svcNodes].filter(id=>snap.nodes[id]))}

const hist={};
function histHtml(id){const h=hist[id]&&hist[id].d;if(!h||!h.segments.length)return '';
 const w=getHWin(),lab=HWIN.find(x=>x[0]===w)[2],t0=h.since,span=Math.max(h.now-t0,1),first=h.segments[0][0];
 const bar=h.segments.map(([a,b,st])=>`<i class="${st}" style="left:${((a-t0)/span*100).toFixed(2)}%;width:${Math.max((b-a)/span*100,.4).toFixed(2)}%"></i>`).join('');
 const av=h.availability==null?'No up or down time recorded yet':h.availability+'% available',o=h.outages,short=first-t0>span*.05?' (history starts here)':'';
 return `<div class=hbar title="Last ${lab}">${bar}</div><small>Last ${lab}: ${av}${o?' · '+o+' outage'+(o>1?'s':''):''}${short}</small>`}
function loadHist(ids){const now=Date.now();
 ids.forEach(id=>{const c=hist[id];if(c&&now-c.at<(c.d&&c.d.segments.length?60000:3000))return;hist[id]={at:now,d:c&&c.d};
  api('history?node='+encodeURIComponent(id)+'&seconds='+getHWin()).then(d=>{hist[id]={at:Date.now(),d};document.querySelectorAll('.hist').forEach(e=>{if(e.dataset.n===id){const h=histHtml(id);if(e.innerHTML!==h)e.innerHTML=h}})}).catch(()=>{})})}

async function detect(){const o=$('#detout'),m=$('#detmsg');let cid=$('#detid').value.trim();o.innerHTML='';m.textContent='Asking…';
 try{const r=await api('detect',{connection:cid});cid=r.connection||cid;$('#detid').value=cid;m.textContent='';if(window._inline&&r.sysName)setupAutoName(window._inline.host,r.sysName);
  if(!(r.suggest||[]).length){o.textContent='Nothing found.';return}
  const l=r.suggest,any=l.some(x=>x.watching);window._det={cid,r,list:l,showSys:false,msg:'',sel:new Set(l.map((x,i)=>i).filter(i=>any?l[i].watching:(!l[i].system&&l[i].batch!=='Network interfaces'&&l[i].default!==false)))};drawList()}catch(e){m.textContent=e.message}}
/* what the device reports right now, beside each tick, so the right interface or volume is easy to pick */
function liveNote(s,r){const l=String(s.label||'');
 const i=(r.interfaces||[]).find(x=>l==='Interface '+x.name);if(i)return i.status+(i.speedMbps?', '+i.speedMbps+' Mbit/s':'');
 const v=(r.volumes||[]).find(x=>l==='Volume '+x.name||l==='Volume / shared folder '+x.name);if(v)return (v.usedPercent==null?'':v.usedPercent+'% used, ')+(v.size||'');return ''}
function drawList(){const d=window._det,o=$('#detout'),r=d.r,list=d.list;
 const info=[...(r.interfaces||[]).map(x=>'Interface '+x.name+': '+x.status+(x.speedMbps?', '+x.speedMbps+' Mbit/s':'')),
  ...(r.volumes||[]).map(x=>'Volume '+x.name+': '+(x.usedPercent==null?'?':x.usedPercent+'% used')+', '+x.size),
  ...(r.ups||[]).map(x=>'UPS '+x.name+(x.description?' ('+x.description+')':'')),
  ...Object.entries(r.tables||{}).flatMap(([k,a])=>a.map(x=>k+' '+x.name+': status '+x.status))];
 const nsys=list.filter(s=>s.system).length,vis=(s,i)=>!s.system||d.showSys||d.sel.has(i);
 const rows=idxs=>{let last=null,h='';
  idxs.forEach(i=>{const s=list[i];if(!vis(s,i))return;
   if(s.batch&&s.batch!==last){last=s.batch;const ids=idxs.filter(j=>list[j].batch===s.batch&&vis(list[j],j)),on=ids.filter(j=>d.sel.has(j)).length;
    h+=`<div class=row style="margin:.9rem 0 .2rem;justify-content:space-between"><b>${esc(s.batch)} <small>${on} of ${ids.length}</small></b>${ids.length>1?`<span><button class="btn sm" onclick="pickBatch('${esc(s.batch)}',true)">All</button> <button class="btn sm" onclick="pickBatch('${esc(s.batch)}',false)">None</button></span>`:''}</div>`}
   h+=`<label class=row style="margin:0;padding:.55rem 0;gap:.7rem;cursor:pointer;min-height:44px"><input type=checkbox style="width:22px;height:22px;flex:none" ${d.sel.has(i)?'checked':''} onchange="pickTick(${i},this.checked)"><span style="flex:1">${esc(s.label)}${liveNote(s,r)?` <small>· ${esc(liveNote(s,r))}</small>`:''}</span>${s.watching?'<small>watching</small>':''}</label>`});return h};
 /* Things that belong to an environment (Portainer) are listed under it: every environment first, collapsed, ticked as a whole. */
 const envs=[...new Set(list.filter(s=>s.env).map(s=>s.env))],loose=list.map((s,i)=>i).filter(i=>!list[i].env);
 d.open=d.open||new Set();
 let html='';
 if(envs.length){const head=envs.map(e=>list.findIndex(s=>s.env===e&&s.check==='environment')),onE=head.filter(i=>i>=0&&d.sel.has(i)).length;
  html+=`<div class=row style="margin:.9rem 0 .2rem"><b>Environments <small>${onE} of ${envs.length}</small></b></div>`;
  envs.forEach((e,k)=>{const hi=head[k],inner=list.map((s,i)=>i).filter(i=>list[i].env===e&&i!==hi),isOpen=d.open.has(e),
    svc=inner.filter(i=>list[i].check!=='environment'),on=new Set(svc.filter(i=>d.sel.has(i)).map(i=>list[i].node)).size,tot=new Set(svc.map(i=>list[i].node)).size,ticked=hi>=0?d.sel.has(hi):on>0;
   html+=`<div class=envrow data-env="${esc(e)}"><div class=row style="margin:0;padding:.35rem 0;gap:.7rem;min-height:48px"><input type=checkbox style="width:22px;height:22px;flex:none" aria-label="Watch ${esc(e)}" ${ticked?'checked':''} onchange="pickEnv(decodeURIComponent('${encodeURIComponent(e)}'),this.checked)">
     <button class=btn style="flex:1;text-align:left;display:flex;justify-content:space-between;gap:.7rem" aria-expanded=${isOpen} onclick="pickOpen(decodeURIComponent('${encodeURIComponent(e)}'))"><span><b>${esc(e)}</b> <small>${on} of ${tot} services</small></span><span aria-hidden=true>${isOpen?'▾':'▸'}</span></button></div>
    ${isOpen?`<div style="margin-left:2.2rem">${rows(inner)}</div>`:''}</div>`})}
 html+=rows(loose);
 const add=list.filter((s,i)=>d.sel.has(i)&&!s.watching).length,rm=list.filter((s,i)=>!d.sel.has(i)&&s.watching).length;
 o.innerHTML='<p class=sub style="margin:0 0 .5rem">Tick what should appear on the main screen, then Apply. Network interfaces start unticked because most devices have many you will not care about.</p>'+html
  +(nsys?`<div class=row style="margin:.8rem 0"><button class="btn sm" onclick="window._det.showSys=!window._det.showSys;drawList()">${d.showSys?'Hide':'Show'} ${nsys} system items</button></div>`:'')
  +`<div class=row style="position:sticky;bottom:0;padding:.7rem 0;background:var(--bg,#0b1a1d);gap:.7rem;align-items:center"><button id=pickapply class="btn${window._inline?' pri':''}" ${add||rm||window._inline?'':'disabled'} onclick="pickApply()">${window._inline&&!(add||rm)?'Done':'Apply'}${add||rm?' ('+[add?'+'+add:'',rm?'\u2212'+rm:''].filter(Boolean).join(' ')+')':''}</button><span id=pickmsg class=sub>${d.msg?esc(d.msg):''}</span></div>`
  +'<p class=sub style="margin:.8rem 0 .2rem">Current values</p><pre class=sub style="white-space:pre-wrap;margin:0">'+esc(info.join('\n'))+'</pre>'}
function pickOpen(e){const d=window._det;d.open.has(e)?d.open.delete(e):d.open.add(e);drawList()}
function pickEnv(e,on){const d=window._det;d.msg='';d.list.forEach((x,i)=>{if(x.env!==e)return;if(!on)d.sel.delete(i);else if(x.check==='environment'||(x.default!==false&&!x.system))d.sel.add(i)});drawList()}
function pickTick(i,on){const d=window._det;d.msg='';on?d.sel.add(i):d.sel.delete(i);drawList()}
function pickBatch(name,on){const d=window._det;d.msg='';d.list.forEach((x,i)=>{if(x.batch===name&&(!x.system||d.showSys||d.sel.has(i)))on?d.sel.add(i):d.sel.delete(i)});drawList()}
async function pickApply(){const d=window._det,btn=$('#pickapply');btn.disabled=true;
 const add=d.list.filter((s,i)=>d.sel.has(i)&&!s.watching),rm=d.list.filter((s,i)=>!d.sel.has(i)&&s.watching);
 if(window._inline&&!add.length&&!rm.length)return inlineClose();
 try{if(add.length){await api('watch',{connection:d.cid,items:add.map(item)});add.forEach(x=>x.watching=true)}
  if(rm.length){await api('unwatch',{connection:d.cid,items:rm.map(item)});rm.forEach(x=>x.watching=false)}
  await syncCfg();d.msg='Saved: '+add.length+' added, '+rm.length+' removed.';if(window._inline)return inlineClose();drawList()}
 catch(e){alert(e.message);drawList()}}
const item=s=>{const o={label:s.label,check:s.check,params:s.params,node:s.node,group:s.group,rule:s.rule};for(const k of['type','url','expect','insecure','service','requires'])if(s[k]!==undefined)o[k]=s[k];return o};
/* the revision counters and JSON editors live on different Settings pages, so each one is only touched when it is on screen */
const setRev=r=>{for(const id of['#rev','#crev']){const e=$(id);if(e)e.textContent=r}};
async function syncCfg(){const cur=await api('config/monitoring');setRev(cur.revision);const e=$('#cfg');if(e)e.value=JSON.stringify(cur.monitoring,null,2)}
/* Edit monitoring: one in-page editor for a system's own monitoring settings. For now the grace period: failures in a row, then seconds.
   An empty box uses this site's setting (Settings, Alerts), which is 2 failures and 60 seconds until it has been changed. More settings can join here later. */
async function editMonitoring(id){let r,mon;try{r=await api('config/monitoring');mon=r.monitoring}catch(e){alert(e.message);return}
 const nd=(mon.nodes||[]).find(x=>x.id===id),df=mon.confirm||{},dn=df.failures??2,ds=df.seconds??60;
 const hk=nd&&(nd.checks||[]).find(k=>k.type==='module'&&(k.check==='temperature'||k.check==='drive')),heat=hk?{def:hk.check==='drive'?55:80,cur:(hk.params||{}).max_c}:null,
  disks=nd?(nd.checks||[]).filter(k=>k.type==='module'&&k.check==='row'&&(k.params||{}).preset==='qnap-disk'):[];   /* a NAS's disks: one limit each */   /* a device or drive temperature check also has its warning limit here */
 if(!nd){alert('This system has no settings of its own to change.');return}
 const o=document.createElement('div');o.id='medit';o.setAttribute('role','dialog');o.setAttribute('aria-modal','true');
 o.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;justify-content:center;padding:10vh 16px 16px;overflow:auto';
 const v=x=>x==null?'':String(x);
 o.innerHTML=`<div style="background:var(--bg);border:1px solid var(--line);border-radius:16px;padding:1.1rem;width:100%;max-width:560px;box-shadow:0 20px 60px rgba(0,0,0,.5)"><h3 style="margin:0 0 .3rem">Edit monitoring: ${esc(nd.name||id)}</h3>
  <p class=sub style="margin:0 0 .6rem">Call this <b>Down</b> only after it has failed this many checks in a row and for at least this many seconds. An empty box uses this site's setting (now ${dn} in a row and ${ds} s).</p>
  <div class=fld><label class=sub>Failures in a row (1 to 20)<input id=me-n type=number min=1 max=20 step=1 inputmode=numeric placeholder="${dn}" value="${esc(v(nd.confirmFailures))}"></label></div>
  <div class=fld><label class=sub>Seconds it must keep failing (0 to 3600)<input id=me-s type=number min=0 max=3600 step=1 inputmode=numeric placeholder="${ds}" value="${esc(v(nd.confirmSeconds))}"></label></div>
  ${heat?`<div class=fld><label class=sub>Warn when hotter than (°C, 20 to 150; empty uses ${heat.def})<input id=me-t type=number min=20 max=150 step=1 inputmode=numeric placeholder="${heat.def}" value="${esc(v(heat.cur))}"></label></div>`:''}
  ${disks.length?`<details${disks.length<=4?' open':''}><summary class=sub>Disk temperature limits (${disks.length})</summary><p class=sub style="margin:.3rem 0">Warn when a disk is hotter than this (°C, 20 to 150). Empty uses the built-in limit: 55 for a hard drive, 70 for an SSD.</p>
   ${disks.map((k,i)=>`<div class=fld><label class=sub>${esc(k.label||(k.params||{}).name||k.id)}<input class=me-d data-c="${esc(k.id)}" data-was="${esc(v((k.params||{}).max_c))}" type=number min=20 max=150 step=1 inputmode=numeric placeholder="auto" value="${esc(v((k.params||{}).max_c))}"></label></div>`).join('')}</details>`:''}
  <p id=me-msg class=sub></p><div class=row style="margin-top:.6rem"><button class="btn pri big" id=me-ok>Save</button><button class="btn big" id=me-no>Cancel</button></div></div>`;
 const done=()=>o.remove();o.querySelector('#me-no').onclick=done;
 o.addEventListener('keydown',e=>{if(e.key==='Escape')done()});o.addEventListener('click',e=>{if(e.target===o)done()});
 o.querySelector('#me-ok').onclick=async()=>{const m=o.querySelector('#me-msg'),a=o.querySelector('#me-n').value.trim(),b=o.querySelector('#me-s').value.trim();
  const num=x=>x===''?null:Number(x);if([a,b].some(x=>Number.isNaN(num(x)))){m.textContent='Please enter whole numbers, or leave a box empty.';return}
  const tv=o.querySelector('#me-t'),ds=[...o.querySelectorAll('.me-d')];if((tv&&Number.isNaN(num(tv.value.trim())))||ds.some(d=>Number.isNaN(num(d.value.trim())))){m.textContent='Please enter a number of degrees, or leave it empty.';return}
  try{await api('confirm',{id,failures:num(a),seconds:num(b)});if(tv)await api('limit',{id,max_c:num(tv.value.trim())});
   for(const d of ds)if(d.value.trim()!==d.dataset.was)await api('limit',{id,check:d.dataset.c,max_c:num(d.value.trim())});done()}catch(e){m.textContent=e.message}};
 document.body.appendChild(o);o.querySelector('#me-n').focus()}
async function setCritical(ids,on){try{await api('critical',{ids,critical:on});if(window.sv&&sv.mon&&$('#devs')){const keep=keepNow();await loadServers(keep)}}catch(e){alert(e.message)}}
const critBox=(ids,label)=>{const ns=(sv.mon.nodes||[]).filter(n=>ids.includes(n.id));return ns.length?`<label class=row style="min-height:44px"><input type=checkbox ${ns.every(n=>n.critical)?'checked':''} onchange="setCritical(${esc(JSON.stringify(ids))},this.checked)"> ${esc(label)}</label>`:''};
async function setExpected(id,on){try{await api('expected',{id,expected:on})}catch(e){alert(e.message)}}
async function stopWatching(id){const n=snap.nodes[id];if(!n)return;const grp=n.kind==='aggregate'&&(n.children||[]).length;
 if(!await askYes(grp?'Remove '+n.name+' and the '+n.children.length+' system'+(n.children.length==1?'':'s')+' inside it? Their checks are removed. Connection settings stay.':'Stop watching '+n.name+'? Its checks are removed. The server and its connection settings stay, so you can pick it again later.'))return;
 try{await api('stopwatching',grp?{id,children:true}:{id})}catch(e){alert(e.message)}}
async function removeEnv(env){const g=svcGroups(Object.values(snap.nodes).filter(n=>n.service&&n.kind!=='aggregate')).find(x=>x.env===env);if(!g)return;
 const eg=envGroups(Object.values(snap.nodes)).groups.find(x=>x.env===env),ids=[...(eg&&eg.node?[eg.node.id]:[]),...g.rows.flatMap(r=>r.node?[r.node.id]:r.members.map(n=>n.id))];
 if(!await askYes('Remove everything listed under '+env+' ('+ids.length+' systems)? Their checks are removed. Connection settings stay, so you can pick them again later.'))return;
 try{for(const id of ids)await api('stopwatching',{id})}catch(e){alert(e.message)}}
/* A text box in the page instead of the browser's pop-up (which some browsers, iPad Safari included, can silently refuse). Resolves to the text, or null on Cancel. */
/* a yes/no box in the page (a browser await askYes() is silently suppressed by iPad Safari, which made buttons look dead); same buttons as askText */
function askYes(msg,ok){return new Promise(res=>{
 const o=document.createElement('div');o.id='ask';o.setAttribute('role','dialog');o.setAttribute('aria-modal','true');
 o.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;justify-content:center;padding:12vh 16px 16px';
 o.innerHTML=`<div style="background:var(--bg);border:1px solid var(--line);border-radius:16px;padding:1.1rem;width:100%;max-width:560px;box-shadow:0 20px 60px rgba(0,0,0,.5)"><p style="margin:0 0 .9rem">${esc(msg)}</p><div class=row style="justify-content:flex-end"><button class=btn id=ask-no>Cancel</button><button class="btn pri" id=ask-ok>${esc(ok||'OK')}</button></div></div>`;
 const done=v=>{o.remove();res(v)};
 o.querySelector('#ask-ok').onclick=()=>done(true);o.querySelector('#ask-no').onclick=()=>done(false);
 o.addEventListener('keydown',e=>{if(e.key==='Enter')done(true);else if(e.key==='Escape')done(false)});
 o.addEventListener('click',e=>{if(e.target===o)done(false)});
 document.body.appendChild(o);o.querySelector('#ask-ok').focus()})}
/* a confirm with several answers: the choices are [text, value] pairs; Cancel gives null */
function askChoice(msg,choices){return new Promise(res=>{
 const o=document.createElement('div');o.id='ask';o.setAttribute('role','dialog');o.setAttribute('aria-modal','true');
 o.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;justify-content:center;padding:12vh 16px 16px';
 o.innerHTML=`<div style="background:var(--bg);border:1px solid var(--line);border-radius:16px;padding:1.1rem;width:100%;max-width:560px;box-shadow:0 20px 60px rgba(0,0,0,.5)"><p style="margin:0 0 .9rem;overflow-wrap:anywhere">${esc(msg)}</p><div style="display:flex;flex-direction:column;gap:.5rem">${choices.map((c,i)=>`<button class=btn data-i=${i}>${esc(c[0])}</button>`).join('')}<button class=btn id=ask-no>Cancel</button></div></div>`;
 const done=v=>{o.remove();res(v)};
 o.querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>done(choices[+b.dataset.i][1]));o.querySelector('#ask-no').onclick=()=>done(null);
 o.addEventListener('keydown',e=>{if(e.key==='Escape')done(null)});o.addEventListener('click',e=>{if(e.target===o)done(null)});
 document.body.appendChild(o);o.querySelector('#ask-no').focus()})}
/* and a notice box in the page instead of alert() */
window.alert=function(msg){return new Promise(res=>{
 const o=document.createElement('div');o.id='ask';o.setAttribute('role','alertdialog');o.setAttribute('aria-modal','true');
 o.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;justify-content:center;padding:12vh 16px 16px';
 o.innerHTML=`<div style="background:var(--bg);border:1px solid var(--line);border-radius:16px;padding:1.1rem;width:100%;max-width:560px;box-shadow:0 20px 60px rgba(0,0,0,.5)"><p style="margin:0 0 .9rem;overflow-wrap:anywhere">${esc(String(msg))}</p><div class=row style="justify-content:flex-end"><button class="btn pri" id=ask-ok>OK</button></div></div>`;
 const done=()=>{o.remove();res()};o.querySelector('#ask-ok').onclick=done;
 o.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key==='Escape')done()});o.addEventListener('click',e=>{if(e.target===o)done()});
 document.body.appendChild(o);o.querySelector('#ask-ok').focus()})};
function askText(title,hint,value){return new Promise(res=>{
 const o=document.createElement('div');o.id='ask';o.setAttribute('role','dialog');o.setAttribute('aria-modal','true');
 o.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.6);display:flex;align-items:flex-start;justify-content:center;padding:12vh 16px 16px';
 o.innerHTML=`<div style="background:var(--bg);border:1px solid var(--line);border-radius:16px;padding:1.1rem;width:100%;max-width:560px;box-shadow:0 20px 60px rgba(0,0,0,.5)"><h3 style="margin:0 0 .3rem">${esc(title)}</h3>${hint?`<p class=sub style="margin:0 0 .6rem">${esc(hint)}</p>`:''}<div class=fld><input id=ask-in type=text autocomplete=off autocapitalize=off autocorrect=off spellcheck=false value="${esc(value||'')}"></div><div class=row style="margin-top:.8rem"><button class="btn pri big" id=ask-ok>Save</button><button class="btn big" id=ask-no>Cancel</button></div></div>`;
 const done=v=>{o.remove();res(v)},i=o.querySelector('#ask-in');
 o.querySelector('#ask-ok').onclick=()=>done(i.value);o.querySelector('#ask-no').onclick=()=>done(null);
 o.addEventListener('keydown',e=>{if(e.key==='Enter')done(i.value);else if(e.key==='Escape')done(null)});
 o.addEventListener('click',e=>{if(e.target===o)done(null)});
 document.body.appendChild(o);i.focus();i.select()})}
async function renameNode(id){const n=snap.nodes[id],nm=await askText('New name for this system','',n?n.name:'');if(nm===null||!nm.trim()||(n&&nm.trim()===n.name))return;
 try{await api('rename',{id,name:nm.trim()})}catch(e){alert(e.message)}}
async function editCheckUrl(id,cid){const n=snap.nodes[id],c=n&&n.checks.find(x=>x.id===cid),one=!!(n&&n.service&&!n.service.synthetic&&n.checks.filter(x=>x.web).length===1),
 u=await askText(one?'Address of this service':'Web address to check',one?'MonitorBox watches this page and the row opens it. For example http://192.168.1.5/admin/':'For example http://192.168.1.5/admin/',c?c.target:'');if(u===null||(c&&u.trim()===c.target))return;
 try{await api('check-url',{id,check:cid,url:u.trim()});if(one)await api('service-link',{id,url:u.trim()})}catch(e){alert(e.message)}}
async function setLink(id){const n=snap.nodes[id],u=await askText('Address to open for this service','For example http://192.168.1.9:8123. Leave it empty to remove the link.',(n&&((n.service&&n.service.url)||n.link))||'');if(u===null)return;
 try{await api('service-link',{id,url:u.trim()})}catch(e){alert(e.message)}}
async function wake(id){try{await api('wake',{id})}catch(e){alert(e.message)}}

/* ---------- new box: password first, then start fresh or restore a backup ---------- */
function welcome(){
 try{sessionStorage.removeItem('mb-sx')}catch(e){}            // servers looked at on an earlier install are not part of this one
 mpage().innerHTML=`<h1 class=head style="font-size:44px">Welcome to MonitorBox</h1><div class=box><p>Choose an admin password.</p>
  <form id=f class=row><input id=p type=password placeholder="Password (8+ characters)" autocomplete=new-password><button class="btn pri">Create</button></form><p id=e></p></div>`;
 $('#f').onsubmit=async ev=>{ev.preventDefault();try{const pw=$('#p').value;await api('setup',{password:pw});await api('login',{password:pw});location.hash='#/welcome';boot()}catch(e){$('#e').textContent=e.message}}}
const CHANNELS=[['stable','Stable','Tested releases. The right choice for most people.'],['beta','Beta','Upcoming releases a little early, for people who like to try things.'],['dev','Dev','The newest changes as soon as they are built. They may be rough.']];
async function setChannel(v){const m=$('#chmsg');m.textContent='Saving…';try{await api('channel',{channel:v});m.textContent='✓ Updates follow the '+v+' channel.'}catch(e){m.textContent=e.message}}
async function welcomeChannel(){const o=$('#wch');if(!o)return;let cur='dev';try{cur=(await api('health')).channel||'dev'}catch(e){}
 o.innerHTML=CHANNELS.map(([k,t,d])=>`<label class=row style="gap:.7rem;padding:.45rem 0;min-height:44px;cursor:pointer"><input type=radio name=wch style="width:22px;height:22px;flex:none" ${k===cur?'checked':''} onchange="setChannel('${k}')"><span><b>${t}</b> <span class=sub>${d}</span></span></label>`).join('')+'<p class=sub id=chmsg style="margin:.3rem 0 0">You can change this later under Settings, Updates. A restored backup brings back its own choice.</p>'}
function renderWelcome(){document.body.dataset.s='green';
 mpage().innerHTML=`<h1 class=head style="font-size:44px">How do you want to begin?</h1><div class=box><h3 style="margin-top:0">What do you call this site?</h3><p class=sub style="margin:0 0 .4rem">Used in alerts and on the site tabs, for example <b>Bay Harbor</b>. You can change it later under Settings, Sites.</p><div class=row><input id=w-name placeholder="Site name" maxlength=60 style="min-height:44px;font-size:16px"></div></div><div class=box><h3 style="margin-top:0">Which updates should this box follow?</h3><div id=wch></div></div><div class=box>
  <div class=row><button class="btn pri big" onclick="welcomeStart()">Start fresh</button><label class="btn big">Restore a backup<input id=w-file type=file accept=.tgz,.gz style="display:none" onchange="welcomeRestore(this)"></label></div>
  <p class=sub id=e>Start fresh looks around your network and helps you add what it finds. Restore brings back the settings and history from a backup file you saved earlier; the password you just chose stays.</p></div>`;welcomeChannel();api('sites').then(c=>{const i=$('#w-name');if(i&&!i.value)i.placeholder=c.nameDefault||'Site name'}).catch(()=>{})}
async function welcomeStart(){const n=($('#w-name').value||'').trim();if(n){try{await api('sites/name',{name:n})}catch(e){$('#e').textContent=e.message;return}}location.hash='#/setup'}
async function welcomeRestore(inp){const f=inp.files[0];if(!f)return;const m=$('#e');m.textContent='Checking the backup…';
 try{const r=await fetch(U('backups/upload'),{method:'POST',headers:{'X-MB':'1'},body:f}),j=await r.json();if(!r.ok)throw new Error(j.error||'That file did not work.');
  const x=await api('restore',{name:j.name});m.textContent=x.message||'Restoring…';$('#m').textContent='Restoring…';location.hash='';setTimeout(boot,5000)}catch(e){m.textContent=e.message}}
/* ---------- first-run setup: look at this box and its network, then hand over to the Servers page for logins ---------- */
let box=null,setupConns=[],setupMon=null,scans={},openCards=new Set();
const hostKey=h=>String(h||'').trim().toLowerCase();
const ck=h=>String(h||'').replace(/[^a-z0-9]/gi,'_');
function savedHosts(){try{return JSON.parse(sessionStorage.getItem('mb-sx')||'[]')}catch(e){return []}}
function saveHosts(l){try{sessionStorage.setItem('mb-sx',JSON.stringify(l))}catch(e){}}
function watchedOf(cid){let n=0;((setupMon&&setupMon.nodes)||[]).forEach(x=>(x.checks||[]).forEach(k=>{if(k.connection===cid)n++}));return n}
let setupRev=0;
async function loadSetupData(){const r=await Promise.all([api('config/connections'),api('config/monitoring')]);setupConns=r[0].connections||[];setupRev=r[0].revision;setupMon=r[1].monitoring||{nodes:[]}}
const okChip='<span class=chip style="background:rgba(52,211,153,.16);color:#6EE7B7">';
/* every server starts with its own system and a reachability check (ping, or a TCP port when it does not answer pings); what is picked later joins it */
async function setupEnsure(host,name){try{await api('server',{name,host})}catch(e){}await loadSetupData()}
function setupServers(){const out=[{host:box.ip,name:box.hostname,own:true}],seen=new Set([hostKey(box.ip),hostKey(box.gateway)]);
 for(const c of setupConns){const h=hostOf(c);if(h&&!seen.has(h)){seen.add(h);const sv=savedHosts().find(x=>hostKey(x.host)===h),sid=sysOf(h),nd=sid&&((setupMon.nodes||[]).find(n=>n.id===sid)||{}).name;out.push({host:h,name:(sv&&hostKey(sv.name)!==h&&sv.name)||nd||c.name||h})}}
 for(const x of savedHosts()){const h=hostKey(x.host);if(h&&!seen.has(h)){seen.add(h);out.push({host:h,name:x.name||h})}}
 return out}
const scanOf=s=>s.own?box:scans[s.host];
function connOf(host,module){return setupConns.find(c=>c.module===module&&hostOf(c)===hostKey(host))}
function webOf(host){let u=null;((setupMon&&setupMon.nodes)||[]).forEach(n=>(n.checks||[]).forEach(k=>{if(k.type==='http'&&k.url){try{if(new URL(k.url).hostname.toLowerCase()===hostKey(host))u=k.url}catch(e){}}}));return u}
function sysOf(host){const ids=new Set(setupConns.filter(c=>hostOf(c)===hostKey(host)).map(c=>c.id));const nodes=(setupMon&&setupMon.nodes)||[];
 const n=nodes.find(n=>(n.checks||[]).some(k=>ids.has(k.connection)))||nodes.find(n=>(n.checks||[]).some(k=>hostKey(k.target)===hostKey(host)&&['ping','tcp'].includes(k.type)));return n?n.id:null}
function wakeOf(host){return ((setupMon&&setupMon.nodes)||[]).find(n=>n.wake&&(n.checks||[]).some(k=>hostKey(k.target)===hostKey(host)))}
async function renderSetup(){document.body.dataset.s='green';window._ret=null;window._inline=null;
 mpage().innerHTML=`<div class=top><div class=row><button class=btn onclick="location.hash=''">← Skip</button><h1 style="margin:0;font-size:28px">Set up</h1></div></div><p class=sub id=boxmsg>Looking at this box and your network…</p><div id=boxout></div>`;
 try{box=await api('thisbox');await setupEnsure(box.ip,box.hostname)}catch(e){$('#boxmsg').textContent=e.message;return}
 $('#boxmsg').textContent='';drawSetup();
 if(window._focus){const f=$('#card-'+ck(window._focus));window._focus=null;if(f)f.scrollIntoView({block:'start'})}
 for(const s of setupServers())if(!s.own&&!scans[s.host])setupLook(s.host,s.name,true)}
/* rows of one server: what its scan found, what is already connected, and the cascade (Protect follows a UniFi Network login) */
function setupRowHtml(s,x){const h=s.host,c=connOf(h,x.module),n=c?watchedOf(c.id):0,nm=encodeURIComponent(s.name),sl='slot-'+ck(h)+'-'+x.module;
 if(x.module==='web'){const w=webOf(h);if(!x.found&&!w)return '';
  return `<div class=devrow><div class=grow><b>Web page</b> ${w?okChip+'watching</span>':okChip+'found</span>'}<div class=sub>${esc(w||x.url||'')}</div></div>${w?'':`<button class="btn sm pri" onclick="setupWatchWeb('${esc(h)}',decodeURIComponent('${nm}'),'${esc(x.url)}',this)">Watch it</button>`}</div>`}
 if(x.module==='portainer'&&!c&&!x.found&&x.note&&setupConns.some(k=>k.module==='portainer'))return `<div class=devrow><div class=grow><b>${esc(x.label)}</b> <span class=sub>agent</span><div class=sub>This box runs a Portainer agent, managed by the Portainer server you added. Its containers are already covered there.</div></div></div>`;
 if(!c&&!x.found)return x.note&&!x.optional?`<div class=devrow><div class=grow><b>${esc(x.label)}</b> <span class=sub>not seen</span><div class=sub>${esc(x.note)}</div></div></div>`:'';
 const net=x.module==='unifi-protect'&&!c?connOf(h,'unifi-network'):null;
 const state=c?okChip+'set up</span> <span class=sub>'+n+' thing'+(n==1?'':'s')+' watched</span>':okChip+'found</span>';
 return `<div class=devrow><div class=grow><b>${esc(x.label)}</b> ${state}${x.note&&!c?`<div class=sub>${esc(x.note)}</div>`:''}</div>
  ${net?`<button class="btn sm pri" onclick="setupSameLogin('${esc(net.id)}',this)">Add with the same login</button>`:''}
  <button class="btn sm${c||net?'':' pri'}" onclick="inlineOpen('${x.module}','${esc(h)}',null,'${sl}')">${c?'Edit':'Set up'}</button></div><div id="${sl}"></div>`}
async function setupWatchWeb(host,name,url,btn){btn.disabled=true;btn.textContent='Adding…';
 try{await api('web-page',{name:name+' web page',url,system:sysOf(host)||undefined,insecure:url.startsWith('https://')});await loadSetupData();drawSetup()}catch(e){btn.disabled=false;btn.textContent='Watch it';alert(e.message)}}
function setupCardHtml(s){const sc=scanOf(s),h=s.host,k=ck(h),nm=encodeURIComponent(s.name);
 if(!sc||sc.loading)return `<div class=box><b>${esc(s.name)}</b> <span class=sub>${esc(h)}</span><div class=sub>Looking…</div></div>`;
 if(sc.error)return `<div class=box><b>${esc(s.name)}</b> <span class=sub>${esc(h)}</span><div class=sub>${esc(sc.error)}</div></div>`;
 const conns=setupConns.filter(c=>hostOf(c)===hostKey(h)),mods=new Set(sc.services.map(x=>x.module)),
  extra=conns.filter(c=>!mods.has(c.module)).map(c=>({module:c.module,label:(SVC[c.module]||{long:c.module}).long,found:true,optional:true})),
  rows=[...sc.services,...extra],pending=rows.filter(x=>x.found&&(x.module==='web'?!webOf(h):!connOf(h,x.module))).length,doneN=conns.length,
  I=window._inline,editing=!!(I&&hostKey(I.host)===hostKey(h)),collapsed=pending===0&&doneN>0&&!openCards.has(h)&&!editing;
 const head=`<div class=fm><div class=fld><label for=${s.own?'bx-name':'nm-'+k}>Name on the main screen</label><input id=${s.own?'bx-name':'nm-'+k} type=text autocomplete=off value="${esc(s.name)}" onchange="setupRename('${esc(h)}',this.value)"></div></div>`;
 if(collapsed)return `<div class=box><div class=row style="justify-content:space-between"><span><b>${esc(s.name)}</b> <span class=sub>${esc(h)} · ${conns.map(c=>esc((SVC[c.module]||{label:c.module}).label)).join(' · ')}</span> ${okChip}done</span></span><button class="btn sm" onclick="openCards.add('${esc(h)}');drawSetup()">Edit</button></div></div>`;
 const wk=wakeOf(h),wrow=sc.mac||wk?`<div class=devrow><div class=grow><b>Wake on LAN</b> ${wk?okChip+'set up</span>':`<span class=sub>MAC ${esc(sc.mac)} seen on your network</span>`}</div><button class="btn sm" onclick="inlineOpen('wake','${esc(h)}',decodeURIComponent('${nm}'),'slot-${k}-wake','${esc(sc.mac||'')}')">${wk?'Edit':'Set up'}</button></div><div id="slot-${k}-wake"></div>`:'';
 const more=Object.keys(SVC).filter(m=>!conns.some(c=>c.module===m)&&!rows.some(r=>r.module===m&&r.found)).map(m=>`<option value="${m}">${esc(SVC[m].long)}</option>`).join('');
 return `<div class=box data-h="${esc(h)}"><div class=row style="justify-content:space-between"><span><b>${esc(s.name)}</b> <span class=sub>${esc(h)}</span></span>${doneN&&!pending&&!editing?`<button class="btn sm" onclick="openCards.delete('${esc(h)}');drawSetup()">Collapse</button>`:''}</div>${head}
  ${rows.map(x=>setupRowHtml(s,x)).join('')}${wrow}
  <div class=row style="margin-top:.7rem;gap:.5rem;flex-wrap:wrap"><span class=sub>Add by hand:</span><button class="btn sm" onclick="setupManual('ping','${esc(h)}',decodeURIComponent('${nm}'))">Ping an address</button><button class="btn sm" onclick="setupManual('web','${esc(h)}',decodeURIComponent('${nm}'))">Watch a web page</button>
   <select onchange="setupMore(this,'${esc(h)}',decodeURIComponent('${nm}'))" aria-label="Another kind of connection"><option value="">Another kind of connection…</option>${more}</select></div><div id="slot-m-${k}"></div><div id="slot-x-${k}"></div></div>`}
let netOpen=false;
function drawSetup(){const b=box,o=$('#boxout');if(!o)return;
 const ied=$('#ied');if(ied)ied.remove();
 const gwDone=b.gateway&&connOf(b.gateway,'unifi-network'),protectRow=gwDone&&!connOf(b.gateway,'unifi-protect')?`<div class=devrow><div class=grow><b>UniFi Protect (cameras)</b><div class=sub>The same console usually runs Protect too.</div></div><button class="btn sm pri" onclick="setupSameLogin('${esc(gwDone.id)}',this)">Add with the same login</button></div>`:'';
 const gwUnifi=b.gatewayUnifi?`<div class=devrow><div class=grow><b>UniFi gateway</b> ${gwDone?okChip+'set up</span>':okChip+'found</span>'}
   <div class=sub>Your gateway ${esc(b.gateway)} is a UniFi console. Add it for devices, health and VPN tunnels; Protect (cameras) is offered right after.</div></div>
   <button class="btn sm${gwDone?'':' pri'}" onclick="inlineOpen('unifi-network','${esc(b.gateway)}','UniFi gateway','slot-gw')">${gwDone?'Edit':'Set up'}</button></div><div id=slot-gw></div>${protectRow}`:'';
 const net=[...(b.gateway?[`<label class=row style="padding:.5rem 0;gap:.7rem;min-height:44px"><input type=checkbox style="width:22px;height:22px" id=nw-gw checked><span>Gateway <b>${esc(b.gateway)}</b> <small>the router everything goes through</small></span></label>`]:[]),
  ...b.dns.map(d=>`<label class=row style="padding:.5rem 0;gap:.7rem;min-height:44px"><input type=checkbox style="width:22px;height:22px" class=nw-dns value="${esc(d)}" checked><span>DNS server <b>${esc(d)}</b> <small>handed out by your network</small></span></label>`)].join('');
 const watched=((setupMon&&setupMon.nodes)||[]).some(n=>n.id==='gateway'||/^dns-/.test(n.id)),done=watched&&(!b.gatewayUnifi||!!gwDone),
  editingGw=!!(window._inline&&window._inline.slot==='slot-gw'),folded=done&&!netOpen&&!editingGw;
 const netBox=folded?`<div class=box><div class=row style="justify-content:space-between"><span><b>Your network</b> <span class=sub>${b.gateway?'Gateway '+esc(b.gateway)+' · ':''}${b.dns.length} DNS${b.gatewayUnifi?' · UniFi':''}</span> ${okChip}done</span></span><button class="btn sm" onclick="netOpen=true;drawSetup()">Edit</button></div>${protectRow}</div>`
  :`<div class=box>${gwUnifi}${net?`<p class=sub style="margin-top:.5rem">Tick what MonitorBox should keep an eye on.</p>${net}<div class=row style="margin-top:.6rem"><button class="btn pri big" id=nw-go onclick="setupNetwork()">Watch these</button>${done?'<button class="btn big" onclick="netOpen=false;drawSetup()">Close</button>':''}<span id=nw-msg class=sub></span></div>`:'<p class=sub>No gateway or DNS servers were found from here. You can add them later under Settings.</p>'}</div>`;
 o.innerHTML=`<p class=sub style="margin-top:0">Each part opens its settings in place: press <b>Set up</b> or <b>Edit</b>, fill it in, test it, tick what to watch, and apply. Nothing leaves this page.</p>
  <h3>Your network</h3>${netBox}
  <h3>Your servers</h3>${setupServers().map(x=>`<div id=card-${ck(x.host)}>${setupCardHtml(x)}</div>`).join('')}
  <div id=fu></div>
  <h3>Add another server</h3>
  <div class=box id=sx-form><div class=row style="gap:.6rem"><input id=sx-host type=text autocomplete=off autocapitalize=off spellcheck=false placeholder="Add a server: its name or address, like 192.168.1.13" style="flex:1;min-width:12rem" onkeydown="if(event.key==='Enter')setupAddServer()"><button class="btn pri" onclick="setupAddServer()">Add</button></div><div class=sub id=sx-msg style="margin-top:.4rem">MonitorBox looks at what it offers, then lists it above.</div></div>
  <div class=row style="margin:1rem 0"><button class="btn pri big" onclick="location.hash='#/setup/review'">Save and finish</button></div>`;
 if(ied&&window._inline){const sl=$('#'+window._inline.slot);if(sl)sl.appendChild(ied)}
 loadFollowups()}
async function setupLook(host,name,quiet){scans[host]={loading:true};
 try{scans[host]=await Promise.race([api('thisbox?host='+encodeURIComponent(host)),new Promise((_,j)=>setTimeout(()=>j(new Error('it took too long to answer')),30000))])}catch(e){scans[host]={error:'Could not look at it: '+e.message,services:[]}}
 if(scans[host].hostname){const l=savedHosts().map(x=>hostKey(x.host)===hostKey(host)&&(!x.name||hostKey(x.name)===hostKey(host))?{host:x.host,name:scans[host].hostname}:x);saveHosts(l)}
 if(!quiet){const l=savedHosts().filter(x=>hostKey(x.host)!==hostKey(host));l.push({name,host});saveHosts(l)}
 if(!quiet&&!scans[host].error){const nm=(savedHosts().find(x=>hostKey(x.host)===hostKey(host))||{}).name||host;await setupEnsure(host,nm)}
 if(location.hash==='#/setup'&&$('#boxout'))drawSetup()}
async function setupAddServer(host,name){const typed=!host;host=hostKey(host||$('#sx-host').value);const m=$('#sx-msg');
 if(!host){if(m)m.textContent='Type a name or an address.';return}
 if(host===hostKey(box.ip)){if(m)m.textContent='That is this box, already above.';return}
 name=name||host;const l=savedHosts().filter(x=>hostKey(x.host)!==host);l.push({name,host});saveHosts(l);
 if(typed&&m)m.textContent='Looking…';scans[host]={loading:true};drawSetup();await setupLook(host,name)}
async function setupNetwork(){const m=$('#nw-msg'),btn=$('#nw-go');btn.disabled=true;m.textContent='Saving…';
 try{const r=await api('network',{gateway:$('#nw-gw')&&$('#nw-gw').checked?box.gateway:null,dns:[...document.querySelectorAll('.nw-dns:checked')].map(x=>x.value)});
  m.textContent=r.added.length?'✓ Now watching '+r.added.length+' thing'+(r.added.length==1?'':'s')+'.':'Already watching these.';await loadSetupData();netOpen=false;if(!(window._inline&&window._inline.slot==='slot-gw'))drawSetup()}
 catch(e){m.textContent=e.message}btn.disabled=false}
async function setupSameLogin(netId,btn){btn.disabled=true;btn.textContent='Adding…';
 try{const r=await api('followups/add',{id:'protect:'+netId});await loadSetupData();drawSetup();const m=$('#sx-msg');if(m)m.textContent='✓ '+r.message}catch(e){btn.disabled=false;btn.textContent='Add with the same login';alert(e.message)}}
/* the in-place editor: the same forms and pick list the Servers page uses, shown under the row that was pressed */
/* a server added by address is named after what it calls itself, once SNMP has answered, unless a name was already typed */
function setupAutoName(host,n){if(hostKey(host)===hostKey(box.ip))return;const inp=$('#nm-'+ck(host)),cur=hostKey(inp?inp.value:((savedHosts().find(x=>hostKey(x.host)===hostKey(host))||{}).name)||host);
 if(cur!==hostKey(host)||!n)return;setupRename(host,n);if(inp)inp.value=n}
/* a typed name is kept everywhere the server is saved: the cards, its connections (their name wins when something is added later) and its system on the main screen */
async function setupRename(host,v){v=String(v||'').trim();if(!v)return;const h=hostKey(host);await loadSetupData();
 if(h===hostKey(box.ip))box.hostname=v;
 saveHosts(savedHosts().map(x=>hostKey(x.host)===h?{host:x.host,name:v}:x));
 try{const mine=setupConns.filter(c=>hostOf(c)===h&&c.name!==v);
  if(mine.length)await api('config/connections',{revision:setupRev,connections:setupConns.map(c=>mine.includes(c)?{...c,name:v}:c)});
  const sid=sysOf(host);if(sid)await api('rename',{id:sid,name:v});
  await loadSetupData()}catch(e){alert(e.message)}}
async function inlineOpen(module,host,name,slot,mac){await inlineClose(true);
 const own=hostKey(host)===hostKey(box.ip),inp=$('#'+(own?'bx-name':'nm-'+ck(host)));name=String((inp&&inp.value)||name||(own?box.hostname:host)).trim();
 const el=$('#'+slot);if(!el)return;window._inline={host,name,module,slot,opening:true};window._ret=null;
 el.innerHTML='<div id=ied class=ied><div id=devs></div><input id=detid type=hidden><span id=detmsg class=sub></span><div id=detout></div></div>';
 window._wiz={name,host:own?box.ip:host,svc:module,mac:mac||''};
 try{await loadServers();const ex=module==='wake'?null:sv.conns.find(c=>c.module===module&&hostOf(c)===hostKey(own?box.ip:host));if(ex)svcForm(module,ex.id)}
 finally{if(window._inline)window._inline.opening=false}
 const e2=$('#'+slot);if(e2)e2.scrollIntoView({block:'nearest',behavior:'smooth'});drawSetup()}
async function inlineClose(quiet){const I=window._inline;window._inline=null;window._det=null;
 if(I){const el=$('#'+I.slot);if(el)el.innerHTML=''}
 if(quiet)return;if(location.hash==='#/setup'){try{await loadSetupData()}catch(e){}drawSetup()}}
function setupMore(sel,host,name){const m=sel.value;sel.value='';if(m)inlineOpen(m,host,name,'slot-x-'+ck(host))}
function setupManual(kind,host,name){const el=$('#slot-m-'+ck(host));if(!el)return;
 el.innerHTML=`<div class=fm style="margin-top:.5rem"><div class=fld><label>${kind==='ping'?'Name':'Name of the page'}</label><input id=mn-name type=text autocomplete=off value="${esc(kind==='ping'?name+' ping':name+' web page')}"></div>
  <div class=fld><label>${kind==='ping'?'Address to ping':'Page address (http:// or https://)'}</label><input id=mn-target type=text autocomplete=off autocapitalize=off spellcheck=false value="${esc(kind==='ping'?host:'http://'+host+'/')}"></div></div>
  <div class=row><button class="btn pri" onclick="setupManualAdd('${kind}','${esc(host)}')">Add</button><button class="btn" onclick="$('#slot-m-${ck(host)}').innerHTML=''">Cancel</button><span class=sub id=mn-msg></span></div>`}
async function setupManualAdd(kind,host){const name=$('#mn-name').value.trim(),t=$('#mn-target').value.trim(),m=$('#mn-msg');m.textContent='Adding…';
 try{if(kind==='ping')await api('ping',{name,target:t});else await api('web-page',{name,url:t,insecure:t.startsWith('https://')});
  await loadSetupData();drawSetup();const e=$('#sx-msg');if(e)e.textContent='✓ Added '+name+'.'}catch(e){m.textContent=e.message}}
/* last page: what will be watched, read-only. Edit goes back to the setup page; Save and launch opens the main screen. */
async function renderReview(){document.body.dataset.s='green';window._ret=null;window._inline=null;
 mpage().innerHTML=`<div class=top><div class=row><h1 style="margin:0;font-size:28px">Summary</h1></div></div><p class=sub id=rvmsg>Loading…</p><div id=rvout></div>`;
 try{if(!box)box=await api('thisbox');await loadSetupData()}catch(e){$('#rvmsg').textContent=e.message;return}
 $('#rvmsg').textContent='';drawReview()}
function drawReview(){const o=$('#rvout');if(!o)return;
 const card=s=>{const h=s.host,conns=setupConns.filter(c=>hostOf(c)===hostKey(h)),wk=wakeOf(h);
  const lines=conns.map(c=>{const n=watchedOf(c.id);return `<div class=sub>${esc((SVC[c.module]||{long:c.module}).long)} · ${n} thing${n==1?'':'s'} watched</div>`}).join('')+(wk?'<div class=sub>Wake on LAN</div>':'');
  return `<div class=box><b>${esc(s.name)}</b> <span class=sub>${esc(h)}</span>${lines||'<div class=sub>Nothing connected yet. It is still pinged if you added a check by hand.</div>'}</div>`};
 const netNodes=((setupMon&&setupMon.nodes)||[]).filter(n=>n.group==='Network'||n.group==='DNS'),total=((setupMon&&setupMon.nodes)||[]).length;
 o.innerHTML=`<p class=sub style="margin-top:0">${total} thing${total==1?'':'s'} on the main screen. Everything here can be changed later under Settings.</p>
  <h3>Your servers</h3>${setupServers().map(card).join('')}
  ${netNodes.length?`<h3>Your network</h3><div class=box>${netNodes.filter(n=>n.kind!=='aggregate').map(n=>`<div class=sub>${esc(n.name)}</div>`).join('')}</div>`:''}
  <div class=row style="margin:1rem 0"><button class="btn big" onclick="location.hash='#/setup'">Edit</button><button class="btn pri big" onclick="location.hash=''">Save and launch</button></div>`}

/* ---------- "more found": proposals that follow from what is already connected (UniFi Network -> Protect, a server answering on Scrypted's port) ---------- */
async function loadFollowups(n){const o=$('#fu');if(!o)return;let r;try{r=await api('followups')}catch(e){return}
 if(!$('#fu'))return;fuN=(r.suggestions||[]).length;const l=fuFilter(r.suggestions||[]);window._fu=l;if(r.pending&&(n||0)<8)setTimeout(()=>loadFollowups((n||0)+1),3000);
 const notes=(r.notes||[]).map(t=>`<p class=sub>${esc(t)}</p>`).join('');
 o.innerHTML=notes+(l.length?`<h3>Found more you can add</h3><div class=box>${l.map((x,i)=>`<div class=devrow><div class=grow><b>${esc(x.title)}</b><div class=sub>${esc(x.why)}</div></div><button class="btn sm pri" onclick="takeFollowup(${i},this)">${x.how==='add'||x.how==='webpage'?'Add':x.how==='items'||x.how==='snmp-switches'?'Add all':x.how==='server'?'Add server':'Set up'}</button><button class="btn sm" onclick="dismissFollowup(${i})">Not now</button></div>`).join('')}<p class=sub id=fumsg>${esc(window._fumsg||'')}</p></div>`:(window._fumsg?`<div class=box><p class=sub id=fumsg style="margin:0">✓ ${esc(window._fumsg)}</p></div>`:''))}
let fuN=0;
/* on the Set up page the cards already show Scrypted, UniFi and Protect for every server they list, so only new servers are offered here */
function fuFilter(l){if(location.hash!=='#/setup'||!box)return l;const have=new Set(setupServers().map(x=>hostKey(x.host)));if(box.gateway)have.add(hostKey(box.gateway));
 const srv=new Set(l.filter(x=>x.kind==='server').map(x=>hostKey(x.host)));return l.filter(x=>!have.has(hostKey(x.host))&&(x.kind==='server'||!srv.has(hostKey(x.host))))}
async function pollFollowups(){try{const r=await api('followups');const n=(r.suggestions||[]).length;if(n!==fuN){fuN=n;if(snap&&!location.hash)render()}}catch(e){}}
setInterval(pollFollowups,600000);
async function dismissFollowup(i){try{await api('followups/dismiss',{id:window._fu[i].id});window._fumsg='';await loadFollowups()}catch(e){alert(e.message)}}
async function takeFollowup(i,b){const x=window._fu[i],m=$('#fumsg');
 if(location.hash==='#/setup'&&box&&!['add','webpage','items','snmp-switches'].includes(x.how)){setupAddServer(x.host,x.name||x.host);return}
 if(!['add','webpage','items','snmp-switches'].includes(x.how)){window._wiz={name:x.host,host:x.host,svc:x.kind};location.hash='#/settings/servers';return}
 b.disabled=true;m.textContent='Adding…';
 try{const r=await api('followups/add',{id:x.id});window._fumsg=r.message;await loadFollowups()}catch(e){m.textContent=e.message;b.disabled=false}}

/* ---------- settings ---------- */
/* Settings used to ask for seven things one after another, and forced a fresh look at the update server, on every tap into a settings page.
   Now: everything is asked for at once, kept for 20 s (any change made through the app clears it), the update server is only asked on the
   Updates page, and a slow answer from an earlier tap can never paint over a later one. */
async function settingsData(fresh){const k=SITE;
 if(!fresh&&SXC&&SXC.k===k&&Date.now()-SXC.at<20000)return SXC.d;
 let bad=null;const need=p=>p.catch(e=>{bad=bad||e;return null});     // signed out: every request says so; the page then goes to sign-in, as before
 const [s,v,mon,conn,ab,bk,al,si,tz]=await Promise.all([apiq('state').catch(()=>null),need(apiq('versions')),
  need(apiq('config/monitoring')),need(apiq('config/connections')),apiq('about').catch(()=>null),apiq('backups').catch(e=>({error:e.message,backups:[]})),
  apiq('alerts').catch(()=>null),apiq('sites').catch(()=>null),apiq('timezone').catch(()=>null)]);
 if(!s)return {s:null};if(bad)throw bad;
 if(tz)BOXTZ=tz.timezone||'';
 const d={s,v,mon,conn,ab,bk,al,si};if(s)SXC={k,at:Date.now(),d};return d}
async function renderSettings(){
 document.body.dataset.s='green';const tok=++rsTok,onUpd=location.hash.startsWith('#/settings/updates');
 if(!(!onUpd&&SXC&&SXC.k===SITE&&Date.now()-SXC.at<20000)&&!$('#m').dataset.set&&mpage())mpage().innerHTML='<p class=sub style="padding:1.2rem 0">Loading settings…</p>';   /* something on screen at once, so a second tap is not needed */
 const D=await settingsData(onUpd);       /* the Updates page never reuses a stale answer: what is waiting can change at any moment */if(tok!==rsTok)return;
 const {s,v,mon,conn,ab,bk}=D;if(!s)return boot();LASTV=JSON.stringify(v);$('#m').dataset.set='1';if(D.al)alCfg=D.al;if(D.si)siCfg=D.si;if(onUpd){hdrPoll();if(Date.now()-UPDCHK>30000){UPDCHK=Date.now();     /* the page is up at once with what is known; the look at the update server follows and refreshes it */
  api('check',{}).then(()=>api('versions')).then(nv=>{if(tok!==rsTok||!location.hash.startsWith('#/settings/updates'))return;
   const same=o=>JSON.stringify(Object.assign({},o,{checkedAt:0}));
   if(same(nv)!==same(JSON.parse(LASTV||'{}')))renderSettings();            /* the look found something new: draw it */
   else{const c=$('#chk');if(c&&nv.checkedAt)c.textContent='Checked '+lt(nv.checkedAt)}}).catch(()=>{})}}   /* nothing new: only the time changes, in place */
 const up=ab?(ab.uptimeSeconds<3600?Math.round(ab.uptimeSeconds/60)+' min':Math.round(ab.uptimeSeconds/3600)+' h'):'';
 const about=ab?`<h3>This box</h3><div class=box><div>Memory in use: <b>${ab.containerMb!=null?ab.containerMb+' MB':(ab.processesTotalMb!=null?ab.processesTotalMb+' MB':'unknown')}</b>
   <small>${ab.containerMb!=null?'container, not counting file cache':'MonitorBox processes'}</small></div>
   <small>MonitorBox ${ab.appMb} MB · launcher ${ab.launcherMb} MB · ${ab.moduleProcesses} module${ab.moduleProcesses==1?'':'s'} ${ab.modulesMb} MB · running ${up}</small></div>`:'';
 const row=(label,kind,id,c,desc)=>{ if(!c)return '';
  const opts=[`<option value=latest ${c.pin=='latest'?'selected':''}>Latest${c.latest?' ('+esc(c.latest)+')':''}</option>`]
   .concat(c.options.map(o=>`<option value="${esc(o.version)}" ${c.pin==o.version?'selected':''}>${esc(o.version)}${c.failed.includes(o.version)?' (failed to start)':''}${o.version==c.running?' (running)':''}</option>`)).join('');
  return `<div class=box data-sw="${esc(kind==='app'?'app':id)}"><div class=row><b>${esc(label)}</b><small>${kind==='module'?esc(id)+' · ':''}${c.running?'running '+esc(c.running):'not installed'}</small></div>
   ${desc?`<div class=sub>${desc}</div>`:''}${(c.changed||[]).length?`<details class=sub style="margin-top:.4rem"><summary>What changed</summary>${(c.highlights||[]).length?`<p style="margin:.4rem 0 .2rem">Highlights from ${c.changed.length} versions</p>${c.highlights.map(x=>`<div style="margin-top:.2rem">${esc(x.text)}</div>`).join('')}<details style="margin-top:.5rem"><summary>Show everything</summary>`:''}${c.changed.map(x=>`<div style="margin-top:.4rem"><b>${esc(x.version)}</b>${x.changes.map(t=>`<div>${esc(t)}</div>`).join('')}</div>`).join('')}${(c.highlights||[]).length?'</details>':''}</details>`:''}<div class=row style="margin-top:.5rem"><select onchange="pick('${kind}','${esc(id||'')}',this.value)">${opts}</select>
   ${c.needsApply?`<button class="btn" onclick="act('apply',{kind:'${kind}',id:'${esc(id||'')}'})">${c.running?(c.target==c.latest&&c.pin=='latest'?'Update to ':'Switch to '):'Install '}${esc(c.target)}</button>`:'<small>Up to date</small>'}
   ${kind==='module'&&(c.running||c.installed)?`<button class="btn sm" onclick="uninstallModule('${esc(id)}','${esc(label)}',${+c.uses||0})">Uninstall</button>`:''}</div>
   ${c.pinMissing?'<div><small>That version isn\'t available in this channel.</small></div>':''}
   ${kind==='module'&&c.repoOn===false&&!c.repoGone?'<div><small>Its repository is switched off, so no updates are offered. It keeps running.</small></div>':''}
   ${kind==='module'&&c.repoGone?'<div><small>Its repository is no longer in the list, so no updates are offered. It keeps running.</small></div>':''}
   ${kind==='module'?(c.alsoIn||[]).map(r=>{const rp=(v.repos||[]).find(x=>x.id===r);return `<div class=row style="margin-top:.4rem"><small>${esc(rp?rp.name:r)} offers the same build.</small><button class="btn sm" onclick="act('repos/adopt',{module:'${esc(id)}',id:'${esc(r)}'})">Update from ${esc(rp?rp.name:r)} instead</button></div>`}).join(''):''}</div>`};
 const swList=(()=>{const info={};s.modules.forEach(m=>info[m.id]=m);const ids=[...new Set([...s.modules.map(m=>m.id),...Object.keys(v.modules)])];
  const one=id=>{const m=info[id]||{id},c=v.modules[id];const title=(m.card&&m.card.title)||id,txt=m.id&&m.running===false?'Not running: '+esc(m.error):esc((m.card&&m.card.text)||(m.running?'running':''));
   return c?row(title,'module',id,c,txt):`<div class=box data-sw="${esc(id)}"><b>${esc(title)}</b> <small>${esc(id)} ${esc(m.version||'')}</small><div class=sub>${txt}</div>${info[id]?`<div class=row style="margin-top:.5rem"><button class="btn sm" onclick="uninstallModule('${esc(id)}','${esc(title)}',0)">Uninstall</button></div>`:''}</div>`};
  const repos=v.repos||[];
  if(repos.length<2)return ids.map(one).sort().join('')||'<div class=box>No modules installed yet.</div>';
  /* more than one repository: the modules sit under the repository they come from, the default first */
  const by={};ids.forEach(id=>{const c=v.modules[id],r=c?c.repo:'';(by[r]=by[r]||[]).push(id)});
  const head=(t,n)=>`<h4 class=sub style="margin:1rem 0 .3rem">${t} <small>(${n})</small></h4>`;
  const sect=repos.map(r=>head(esc(r.name)+(r.default?' · default':'')+(r.enabled?'':' · switched off'),(by[r.id]||[]).length)
   +(r.error?`<div class=box><small>Can't reach this repository right now. Nothing is marked failed.</small></div>`:'')
   +((by[r.id]||[]).map(one).sort().join('')||'<div class=box><small>Nothing installed or offered from here.</small></div>'));
  const known=new Set(repos.map(r=>r.id)),lost=Object.keys(by).filter(r=>!known.has(r)).flatMap(r=>by[r]);
  return sect.join('')+(lost.length?head('Removed repository',lost.length)+lost.map(one).sort().join(''):'')})();
 const repoBox=(v.repos||[]).length?`<h3>Repositories</h3><div class=box><p class=sub style="margin-top:0">Where MonitorBox looks for software. The first one is built in. Switching one off stops checking it; what is installed from it keeps running.</p>
  ${(window._rv=v.repos,'')}${v.repos.map(r=>`<div class=row style="margin:.4rem 0"><label class=row style="gap:.6rem;flex:1">${r.default?'':`<input type=checkbox ${r.enabled?'checked':''} onchange="repoOn('${esc(r.id)}',this.checked)">`}<span>${esc(r.name)}${r.default?' <small>· built in</small>':''}${r.error?`<small style="display:block">Can't reach it right now.</small>`:''}</span></label>
   ${r.default?'':`<button class="btn sm" onclick="repoRemove('${esc(r.id)}','${esc(r.name)}')">Remove</button>`}</div>`).join('')}
  <div class=row style="margin-top:.6rem"><input id=repoin placeholder="owner/name on GitHub" autocapitalize=off autocorrect=off spellcheck=false style="flex:1;min-width:12rem"><button class=btn onclick="repoAdd()">Add repository</button></div>
  <p id=repomsg class=sub></p></div>`:'';
 const kb=n=>n>1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB';
 const bkRow=b=>`<div class=row style="margin:.5rem 0"><span>${esc(lt(b.created))} · ${esc(b.kind==='config'?'settings':b.kind)} · ${esc(b.name.includes('-uploaded-')?'uploaded':b.label)}${b.appVersion?' · MonitorBox '+esc(b.appVersion):''} · ${kb(b.size)}</span>
   <a class="btn sm" href="${U('backups/download?name=')}${encodeURIComponent(b.name)}">Download</a>
   ${bk.canRestore?`<button class="btn sm" onclick="restoreBk('${esc(b.name)}')">Restore</button>`:''}
   <button class="btn sm" onclick="delBk('${esc(b.name)}')">Delete</button></div>`;
 const bkLast=bk.last?`<div class=box>Last restore: ${esc(bk.last.result)}</div>`:'';
 const backupsHtml=`<h3>Backups</h3>${bkLast}<div class=box><p class=sub style="margin-top:0">A <b>settings</b> backup (your settings and admin password) is made every night. A <b>full</b> backup, which also includes the installed MonitorBox version and modules, is made every week. Both are stored on this box, so <b>download one and keep it somewhere else</b>. A backup file contains your passwords and tokens, so keep it private.</p>
   ${bk.error?`<div>${esc(bk.error)}</div>`:''}
   <div class=row><button class="btn" onclick="backupNow('config')">Back up settings now</button><button class="btn" onclick="backupNow('full')">Full backup now</button>
   <label class="btn">Upload a backup<input type=file accept=.tgz,.gz style="display:none" onchange="uploadBk(this)"></label></div>
   ${bk.backups.length?bk.backups.map(bkRow).join(''):'<p><small>No backups yet. The first one is made about a minute after the box starts.</small></p>'}</div>`;
 const img=v.image&&v.image.outdated?`<div class=box><b>The container image needs updating.</b> This box is running image ${esc(v.image.have)}; this release was built for ${esc(v.image.wants)}. Everything keeps working, but some updates may not install until the image is re-pulled. Pull the new image and restart the container; your settings and data are kept.</div>`:'';
 const last=v.last&&v.last.result!='ok'?`<div class=box>Last install: ${esc(v.last.version)} — ${esc(v.last.result)}</div>`:'';
 const nPending=((v.app&&v.app.needsApply&&v.app.target&&!v.app.failed.includes(v.app.target))?1:0)+Object.values(v.modules||{}).filter(modWaiting).length;
 const linked=((siCfg&&siCfg.sites)||[]).filter(x=>(x.link||{}).state==='linked'),remoteWaiting=linked.some(x=>hdrSites[x.id]&&hdrSites[x.id].pend);rowSig=remoteWaitingNow();
 const checkSites=(SITE===''&&linked.length)?`<button class=btn id=chkall onclick="checkAllSites(this)">Check all sites</button>`:'';
 const updBtn=nPending>0?`<button class="btn pri" id=upall onclick="updateAll(this)">Update</button>`:'';        /* this box has something waiting */
 const sitesBtn=(SITE===''&&linked.length&&remoteWaiting)?`<button class="btn pri" id=upsites onclick="updateSites(this)">Update all sites</button>`:'';        /* a linked site has something waiting */
 const sec=(location.hash.split('/')[2]||''),nServers=new Set((conn.connections||[]).map(hostOf).filter(Boolean)).size,nNodes=((mon.monitoring||{}).nodes||[]).length,
  upd=!!(v.app&&v.app.needsApply)||Object.values(v.modules||{}).some(modWaiting),lastBk=bk.backups&&bk.backups[0];
 const SECS=[['display','Display','How the main screen looks on this device',`${view==='detail'?'Detailed':'Summarized'} · history ${HWIN.find(x=>x[0]===getHWin())[1]}`],
  ['history','History','What was not healthy, and when; which states the bars show','Last 30 days kept'],
  ['servers','Servers','The machines MonitorBox watches, and how it reaches them',`${nServers} server${nServers==1?'':'s'}`],
  ['power','Power','Which battery backup keeps what running','One alert when the power goes, not one per server'],
  ['graphs','Graphs','Which traffic graphs to show, and how much time they cover',`${grCfg.length} graph${grCfg.length==1?'':'s'}`],
  ['alerts','Alerts','Who is told when something goes down, and how long to wait first',alCfg?(alCfg.enabled?'On · Home Assistant':'Off'):''],
  ...(SITE?[]:[['sites','Sites','Other MonitorBoxes, managed from here or managing this one',siCfg?(siCfg.sites.length?siCfg.sites.length+' site'+(siCfg.sites.length==1?'':'s'):siCfg.managers.length?'Managed by '+siCfg.managers.map(m=>m.name).join(', '):'None'):'']]),
  ...(SITE?[]:[['security','Sign-in and security','How MonitorBox is reached from outside, and who may try','']]),
  ['backups','Backups','Nightly backups, download, restore',lastBk?'Last: '+lt(lastBk.created):'No backups yet'],
  ['updates','Updates and versions','Channel, installed versions, modules',upd?'Update available':'Up to date'],
  ['box','This box','Time zone, memory use, restart, factory reset, sign out',ab?(ab.containerMb!=null?ab.containerMb:ab.processesTotalMb)+' MB in use':''],
  ['advanced','Advanced','Troubleshooting tools and the JSON editors','Logs, network map, performance, switch report, flows']];
 const PARTS={display:`<h3>Main screen</h3><div class=box><p class=sub style="margin-top:0">How the main screen looks on <b>this device</b>. <b>Summarized</b> shows one tile for each group (Servers, Network and so on). <b>Detailed</b> lists every check. You can also switch from the main screen itself.</p>
   <div class=seg role=group aria-label="Main screen view"><button aria-pressed=${view==='summary'} onclick="setView('summary')">Summarized</button><button aria-pressed=${view==='detail'} onclick="setView('detail')">Detailed</button></div>
   <p class=sub style="margin-bottom:.4rem">How far back the history bar in each side panel reaches, on <b>this device</b>. MonitorBox keeps 30 days whichever you pick.</p>
   <div class=seg role=group aria-label="History length">${HWIN.map(x=>`<button aria-pressed=${getHWin()===x[0]} onclick="setHWin(${x[0]})">${x[1]}</button>`).join('')}</div></div>
  `,history:`<h3>History</h3><div class=box><p class=sub style="margin-top:0">Every stretch when something was not healthy, for <b>this site</b>, newest first. MonitorBox keeps 30 days. It records <b>when</b> something changed, not why.</p>
   <div class=seg role=group aria-label="Range" id=hp-range>${[['1','1 day'],['7','1 week'],['30','All (30 days)']].map(x=>`<button data-d="${x[0]}" aria-pressed=${x[0]==='1'} onclick="hpRange('${x[0]}')">${x[1]}</button>`).join('')}</div>
   <div class=row style="margin-top:.5rem"><label class=sub>From <input type=date id=hp-from></label><label class=sub>To <input type=date id=hp-to></label><button class=btn onclick="hpCustom()">Show</button></div>
   <div class=row id=hp-st>${[['failed','Down'],['degraded','Degraded'],['unknown','Unknown']].map(x=>`<label class=sub style="display:flex;align-items:center;gap:.4rem;min-height:44px"><input type=checkbox checked data-st="${x[0]}" onchange="hpLoad()">${x[1]}</label>`).join('')}<label class=sub style="display:flex;align-items:center;gap:.4rem;min-height:44px" title="A failure or warning that cleared before the confirmation time set in Settings → Alerts. The main screen and your alerts never showed these."><input type=checkbox id=hp-brief onchange="hpLoad()">Show brief blips</label></div></div>
  <div class=box id=hp-list><p class=sub>Loading…</p></div>
  <div class=box><p class=sub style="margin-top:0"><b>Clear history</b> forgets everything recorded for this site and starts again from how things are now. The bars and this list start empty. A backup you already took still holds the old history.</p>
   <div class=row><button class=btn onclick="hpClear()">Clear history…</button></div></div>
  
  <h3>Colours in the history bars</h3><div class=box><p class=sub style="margin-top:0">Choose which states the small bars on the main screen may colour in, for <b>this site</b>. Nothing is erased, so ticking a state again brings it back. With <b>Down</b> or <b>Degraded</b> unticked, those stretches look healthy. With <b>Unknown</b> unticked, they show as no record. With nothing ticked, the bars are hidden. Tapping a slice lists only what the bar shows.</p>
   <div class=row id=bs-row>${[['failed','Down'],['degraded','Degraded'],['unknown','Unknown']].map(x=>`<label class=sub style="display:flex;align-items:center;gap:.4rem;min-height:44px"><input type=checkbox data-bs="${x[0]}" onchange="saveBarShow()">${x[1]}</label>`).join('')}</div><p id=bs-msg class=sub></p></div>
  `,servers:`<h3>Servers</h3><div class=box><p class=sub style="margin-top:0">Every machine MonitorBox watches. Open one to see what is watched on it and how MonitorBox reaches it (SNMP, UniFi, battery backup, Wake on LAN and so on). Passwords are saved, and never shown again.</p>
   <div id=devs><p class=sub>Loading…</p></div>
</div>
  <input id=detid type=hidden><span id=detmsg class=sub></span><div id=detout></div>
  `,security:`<h3>Sign-in and security</h3><div class=box><p class=sub style="margin-top:0">Use this if you open MonitorBox through a reverse proxy such as Caddy, so the box can tell a real visitor from the proxy itself. Without it, every outside visit looks like it came from the proxy.</p><div id=secset><p class=sub>Loading…</p></div></div>
  `,sites:`<h3>Sites</h3><div class=box><p class=sub style="margin-top:0">Each site runs its own MonitorBox, so it keeps watching and sending alerts even if the others go offline. One MonitorBox, the main one, can be paired with the others to show them and manage their settings. The main one can change the others. The others cannot change the main one.</p><div id=siset><p class=sub>Loading…</p></div></div>
  `,alerts:`<h3>Alerts</h3><div class=box><p class=sub style="margin-top:0">MonitorBox sends a message when something has been <b>down</b> or <b>degraded</b> for about a minute, and another when it recovers. It stays quiet about anything marked expected down, about things that are down only because something they depend on is down (you get one message for the cause), and about things it cannot check.</p><div id=alset><p class=sub>Loading…</p></div></div>
  
  <h3>Confirm a failure first</h3><div class=box><p class=sub style="margin-top:0">MonitorBox calls something <b>Down</b> only after it has failed this many checks in a row <b>and</b> for at least this many seconds. Until then it keeps its last state and shows a heads-up line; nothing reaches the history or your alerts. The standard is 2 checks and 60 seconds. Enter 1 and 0 for no wait. A longer wait means a real outage shows later. To set it for one system only, open that system and tap <b>Edit monitoring</b>; its own setting wins over this.</p>
   <div class=row><label class=sub>Failures in a row <input id=cf-n type=number min=1 max=20 step=1 inputmode=numeric style="width:5rem"></label><label class=sub>Seconds <input id=cf-s type=number min=0 max=3600 step=1 inputmode=numeric style="width:6rem"></label><button class=btn onclick="saveConfirm()">Save</button></div><p id=cf-msg class=sub></p></div>
  `,power:`<h3>Power</h3><div class=box><p class=sub style="margin-top:0">Which battery backup (UPS) keeps each system running. If a backup switches to battery and the systems on it then go down, you get one alert for the backup instead of one for every system. MonitorBox ticks a system for you only when the backup itself says that system is plugged into it. Tick or untick to correct that. A system can be on one backup at a time.</p>
   <div id=pwset><p class=sub>Loading…</p></div></div>
  `,graphs:`<h3>Graphs</h3><div class=box><p class=sub style="margin-top:0">Live traffic graphs for the main screen. Each one follows a single network port on one of your systems, updating every second while the main screen is open and every ten seconds otherwise. The box remembers the last hour, so that is the furthest back a graph can look.</p><div id=grset><p class=sub>Loading…</p></div></div>
  <h3>Traffic graphs</h3><div class=box><p class=sub style="margin-top:0">How much time the traffic graphs show on <b>this device</b>: on the main screen, and in the panel that opens when you tap one. The box keeps the last hour of readings, so an hour is the most for either.</p>
   <p class=sub style="margin-bottom:.4rem">Main screen</p>
   <div class=seg role=group aria-label="Main screen graph window">${GW.map(x=>`<button aria-pressed=${(grWin||+lsGet('mb-gw')||300)===x[0]} onclick="setGw(${x[0]});segOn(this)">${x[1]}</button>`).join('')}</div>
   <p class=sub style="margin-bottom:.4rem">When you tap a graph</p>
   <div class=seg role=group aria-label="Panel graph window">${GPW.map(x=>`<button aria-pressed=${getGp()===x[0]} onclick="setGp(${x[0]});segOn(this)">${x[1]}</button>`).join('')}</div></div>
  `,backups:backupsHtml,updates:`<h3>Updates</h3>${img}<div class=box>
   <div class=row><select id=ch onchange="act('channel',{channel:this.value})">${['dev','beta','stable'].map(c=>`<option ${c==v.channel?'selected':''}>${c}</option>`).join('')}</select>
   <button class=btn onclick="checkUpdates(this)">Check now</button>${checkSites}${updBtn}${sitesBtn}<small id=chk>${v.checkedAt?'Checked '+esc(lt(v.checkedAt)):''}</small></div><div id=upsitesout class=sub></div>
   <div class=sub style="margin-top:.4rem">Channel: <b>dev</b> is the newest and least tested, <b>beta</b> is in between, <b>stable</b> changes least.</div>
   <label class=row style="margin-top:.6rem"><input type=checkbox ${v.settings.autoCheck?'checked':''} onchange="setting({autoCheck:this.checked})"> Check for updates automatically</label>
   <label class=row><input type=checkbox ${v.settings.autoUpdate?'checked':''} onchange="setting({autoUpdate:this.checked})"> Install updates automatically (only for items set to Latest on the ${esc(v.channel)} channel below)</label></div>
  ${v.checkError?`<div class=box>${esc(v.checkError)}</div>`:''}
  ${repoBox}<h3>Installed software</h3>${last}${row('MonitorBox','app','',v.app)}${swList}
  `,box:`${about}<h3>Time zone</h3><div class=box><p class=sub style="margin-top:0">The time zone of <b>this site</b>. Times on the screens, and anything the box writes itself, follow it. Each site has its own. The first time you open this page it uses your device's time zone. You can change it here at any time.</p>
   <div class=row><select id=tz-sel aria-label="Time zone" style="max-width:100%"></select><button class=btn onclick="saveTz()">Save</button></div><p id=tz-msg class=sub></p></div>
  <h3>Restart and reset</h3><div class=box><p class=sub style="margin-top:0"><b>Restart MonitorBox</b> starts it again. This takes a few seconds and your settings stay.</p>
   <div class=row><button class=btn onclick="restartApp()">Restart MonitorBox</button></div></div>
  <div class=box><p class=sub style="margin-top:0"><b>Factory reset</b> deletes your settings, password, history and installed modules, then starts MonitorBox from the setup screen. Your backups are kept, and the modules are downloaded again fresh, so a backup can bring everything back.</p>
   <div class=row><button class="btn" onclick="factoryReset()">Factory reset…</button></div></div>
  <div class=row><button class=btn onclick="api('logout',{}).then(boot)">Sign out</button></div><p id=msg></p>`,advanced:`<h3>Advanced</h3><p class=sub style="margin-top:0">Troubleshooting tools, and the raw editors behind the settings screens. You don\'t need anything here day to day. To change one system\'s settings, open that system and tap <b>Edit monitoring</b> instead.</p>
  <p class=sub style="margin:.2rem 0 0"><i>Here there be dragons.</i></p>
  <h3>Logs</h3><div class=box><p class=sub style="margin-top:0">What MonitorBox did and saw: checks changing state, alerts, modules, backups, sign-ins. <span id=lgstat></span></p>
   <div class=row><button class=btn onclick="location.hash='#/logs'">Open the logs</button></div></div>
  <h3>Network map</h3><div class=box><p class=sub style="margin-top:0">A map of your network: the devices MonitorBox can see and how they connect.</p>
   <div class=row><button class=btn onclick="location.hash='#/map'">Open the network map</button></div></div>
  <h3>Performance</h3><div class=box><p class=sub style="margin-top:0">How long this site takes to answer, and where its memory goes. On the Tidewater tab it includes the link from here.</p>
   <div class=row><button class=btn onclick="perfRun()">Measure this site</button> <button class=btn id=perfcopy hidden onclick="perfCopy()">Copy</button></div><div id=perfout></div></div>
  <h3>Switch report</h3><div class=box><p class=sub style="margin-top:0">Asks each UniFi login and SNMP device what it reports about its ports, speeds, traffic and neighbours. It only reads. Passwords and keys are never included and device addresses are shortened. Copy it to share, so the network map can be built from what your switches really report.</p>
   <div class=row><button class=btn onclick="lanRun()">Ask the switches</button> <button class=btn id=lancopy hidden onclick="lanCopy()">Copy</button></div><div id=lanout></div></div>
  <h3>Flows look</h3><div class=box><p class=sub style="margin-top:0">Asks your UniFi gateway the questions behind its Insights, Flows page and shows how it answers: which requests it accepts and what the answers look like. It reads only (one of the questions is a search of the flow list, which changes nothing). Passwords are never included, public addresses are hidden and MAC addresses are shortened, but look it over before you share it: it can include the names of sites and devices.</p>
   <div class=row><button class=btn onclick="flowRun()">Ask the gateway</button> <button class=btn id=flowcopy hidden onclick="flowCopy()">Copy</button></div><div id=flowout></div></div>
  <h3>Preview the screens</h3><div class=box><p class=sub style="margin-top:0">Shows pretend data on the main screen. Nothing real changes, and it resets when MonitorBox restarts.</p>
   <div class=row>${['green','headsup','yellow','down','blue','red'].map(n=>`<button class=btn onclick="demo('${n}')">${n}</button>`).join('')}<button class=btn onclick="demo(null)">Back to real data</button></div></div>
  <h3>Monitoring (JSON)</h3><div class=box><p class=sub style="margin-top:0">Every system and check, as JSON text. Saving checks it first and changes nothing if something is wrong.
   Revision <b id=rev>${mon.revision}</b>.</p>
   <textarea id=cfg spellcheck=false>${esc(JSON.stringify(mon.monitoring,null,2))}</textarea>
   <div class=row style="margin-top:.6rem"><button class="btn pri" onclick="saveMon()">Save</button><span id=monmsg></span></div></div>
  <h3>Connections (JSON)</h3><div class=box><p class=sub style="margin-top:0">Every saved connection, as JSON text. Revision <b id=crev>${conn.revision}</b>. Passwords and keys show as dots and stay as they are unless you type a new one.</p>
   <textarea id=ccfg spellcheck=false>${esc(JSON.stringify(conn.connections,null,2))}</textarea>
   <div class=row style="margin-top:.6rem"><button class="btn pri" onclick="saveConn()">Save</button><span id=cmsg></span></div></div>`};
 const cur=SECS.find(x=>x[0]===sec);
 if(!cur){mpage().innerHTML=`<div class=top><div class=row><button class=btn onclick="location.hash=''">← Back</button><h1 style="margin:0;font-size:28px">Settings</h1></div><small>MonitorBox ${esc(v.version)}${v.imageVersion?' · image '+esc(v.imageVersion)+(v.image&&v.image.outdated?' (update available)':''):''} · channel ${esc(v.channel)}</small></div>
  ${last}<div class=hubg>${SECS.map(x=>`<button class="hub" onclick="location.hash='#/settings/${x[0]}'"><b>${x[1]}</b><span class=sub>${esc(x[2])}</span><small>${esc(x[3])}</small></button>`).join('')}</div>
  <div class=row style="margin-top:1rem"><button class=btn onclick="api('logout',{}).then(boot)">Sign out</button></div><p id=msg></p>`;return}
 mpage().innerHTML=`<div class=top><div class=row><button class=btn onclick="location.hash='#/settings'">← Settings</button><h1 style="margin:0;font-size:28px">${cur[1]}</h1></div><small>MonitorBox ${esc(v.version)}${v.imageVersion?' · image '+esc(v.imageVersion)+(v.image&&v.image.outdated?' (update available)':''):''} · channel ${esc(v.channel)}</small></div>
  ${sec==='servers'&&window._ret?`<div class=box style="display:flex;align-items:center;gap:.8rem;flex-wrap:wrap"><span>You are setting up your box.</span><button class="btn pri" onclick="const r=window._ret;window._ret=null;location.hash=r">← Back to ${window._ret==='#/setup/review'?'the review':'Set up'}</button></div>`:''}${PARTS[sec].replace(/<h3>(Main screen|Servers)<\/h3>/,'')}<p id=msg></p>`;if(sec==='history'){hpRange('1');loadBarShow()}if(sec==='box')loadTzBox();if(sec==='servers')loadServers();if(sec==='graphs')graphSettings();if(sec==='power')powerSettings();if(sec==='alerts'){alertSettings();loadConfirm()}if(sec==='sites')siteSettings();if(sec==='security')securitySettings();if(sec==='advanced')lgStat()}
/* the history page: stretches that were not healthy, in a range, filtered by state */
let hpFrom=0,hpTo=0;
function zoneEpoch(y,m,d,h,mi,s){const g=Date.UTC(y,m-1,d,h,mi,s);if(!BOXTZ)return Math.floor(new Date(y,m-1,d,h,mi,s).getTime()/1000);
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:BOXTZ,hourCycle:'h23',year:'numeric',month:'numeric',day:'numeric',hour:'numeric',minute:'numeric',second:'numeric'}).formatToParts(new Date(g)).map(x=>[x.type,+x.value]));
 const off=Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute,p.second)-g;return Math.floor((g-off)/1000)}
async function hpRange(d){await loadTz();document.querySelectorAll('#hp-range button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.d===d));
 hpTo=Math.floor(Date.now()/1000);hpFrom=hpTo-(+d)*86400;hpLoad()}
function hpCustom(){const a=$('#hp-from').value,b=$('#hp-to').value;if(!a||!b){$('#hp-list').innerHTML='<p class=sub>Pick both dates.</p>';return}
 const A=a.split('-').map(Number),B=b.split('-').map(Number);hpFrom=zoneEpoch(A[0],A[1],A[2],0,0,0);hpTo=zoneEpoch(B[0],B[1],B[2],23,59,59);
 if(hpTo<hpFrom){$('#hp-list').innerHTML='<p class=sub>The end date is before the start date.</p>';return}
 document.querySelectorAll('#hp-range button').forEach(x=>x.setAttribute('aria-pressed',false));hpLoad()}
async function hpLoad(){const L=$('#hp-list');if(!L)return;const st=[...document.querySelectorAll('#hp-st input')].filter(i=>i.checked).map(i=>i.dataset.st);
 if(!st.length){L.innerHTML='<p class=sub>Tick at least one of Down, Degraded and Unknown.</p>';return}
 try{const t=await api('history?events=1&from='+hpFrom+'&to='+hpTo+'&states='+st.join(',')+(($('#hp-brief')||{}).checked?'&brief=1':''));if(!$('#hp-list'))return;
  const nm=id=>(t.names&&t.names[id])||id,items=t.items||[];
  const dt=x=>new Date(x*1000).toLocaleDateString([],Object.assign({month:'short',day:'numeric'},tzo()))+' '+tfmt(x);
  L.innerHTML=items.length?`<div class=rows>${items.map(x=>`<div class=tr><span class="dot ${esc(x.state)}"></span><div><b>${esc(nm(x.node))}</b><span class=sub>${esc(TST[x.state]||x.state)}${x.brief?' (brief, not shown on screen)':''} · ${tdur(x.to-x.from)} · ${dt(x.from)} to ${dt(x.to)}</span>${x.why?`<span class=sub>${esc(x.why)}</span>`:''}</div></div>`).join('')}</div>${t.more?`<p class=note>Showing the newest ${items.length}; ${t.more} older ones are not listed. Narrow the range to see them.</p>`:''}`:'<p class=sub>Nothing in that range. Good.</p>'}
 catch(e){L.innerHTML='<p class=sub>Could not load the history.</p>'}}
async function hpClear(){if(!await askYes('Clear all history for this site? This cannot be undone (an older backup would still hold it).'))return;
 try{await api('history/clear',{});for(const k in strips)delete strips[k];hpLoad();$('#msg').textContent='History cleared.'}catch(e){$('#msg').textContent=e.message}}
let cfRev=-1,cfMon=null;
async function loadBarShow(){await loadTz();document.querySelectorAll('#bs-row input').forEach(i=>{i.checked=BARSHOW.includes(i.dataset.bs)})}
async function saveBarShow(){const m=$('#bs-msg'),v=[...document.querySelectorAll('#bs-row input')].filter(i=>i.checked).map(i=>i.dataset.bs);
 try{BARSHOW=(await api('barshow',{show:v})).show;for(const k in strips)delete strips[k];m.textContent=v.length?'Saved.':'Saved. The bars are hidden.'}catch(e){m.textContent=e.message}}
function tzList(){let l=[];try{l=Intl.supportedValuesOf('timeZone')}catch(e){}
 if(!l.length)l=['America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Phoenix','America/Anchorage','Pacific/Honolulu','Europe/London','Europe/Paris','Europe/Berlin','Asia/Tokyo','Australia/Sydney','UTC'];
 if(!l.includes('UTC'))l.push('UTC');return l}
async function loadTzBox(){const sel=$('#tz-sel'),m=$('#tz-msg');if(!sel)return;let dev='UTC';try{dev=Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC'}catch(e){}
 await loadTz();let cur=BOXTZ,first=!cur;if(first)cur=dev;
 const l=tzList();if(!l.includes(cur))l.unshift(cur);
 sel.innerHTML=l.map(z=>`<option${z===cur?' selected':''}>${esc(z)}</option>`).join('');
 if(first){try{await api('timezone',{timezone:cur});BOXTZ=cur;m.textContent="Set to this device's time zone ("+cur+'). Change it above if the site is somewhere else.'}catch(e){m.textContent='This site has no time zone yet, and could not take '+cur+': '+e.message}}}
async function saveTz(){const m=$('#tz-msg'),z=$('#tz-sel').value;try{await api('timezone',{timezone:z});BOXTZ=z;m.textContent='Saved. Times now follow '+z+'.'}catch(e){m.textContent=e.message}}
async function loadConfirm(){try{const r=await api('config/monitoring');cfRev=r.revision;cfMon=r.monitoring;const c=cfMon.confirm||{};$('#cf-n').value=c.failures??2;$('#cf-s').value=c.seconds??60}catch(e){}}
async function saveConfirm(){const m=$('#cf-msg');if(!cfMon){m.textContent='Not loaded yet.';return}
 const f=parseInt($('#cf-n').value,10),sec=Number($('#cf-s').value);
 if(!(f>=1&&f<=20)||!(sec>=0&&sec<=3600)){m.textContent='Failures must be 1 to 20 and seconds 0 to 3600.';return}
 const mon=Object.assign({},cfMon);if(f===2&&sec===60)delete mon.confirm;else mon.confirm={failures:f,seconds:sec};
 try{const r=await api('config/monitoring',{revision:cfRev,monitoring:mon});cfRev=r.revision;cfMon=mon;m.textContent='Saved.'}catch(e){m.textContent=e.message}}
async function saveMon(){const m=$('#monmsg');let obj;try{obj=JSON.parse($('#cfg').value)}catch(e){m.textContent='That isn\'t valid JSON: '+e.message;return}
 try{const r=await api('config/monitoring',{revision:+$('#rev').textContent,monitoring:obj});setRev(r.revision);m.textContent='Saved. Revision '+r.revision+'.'}
 catch(e){m.innerHTML=esc(e.message)+((e.data&&e.data.errors)?'<ul>'+e.data.errors.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'')}}
/* a backup runs in one piece on the box, so there is no honest percentage: a moving bar and a plain line say that something is happening */
async function backupNow(kind){const row=document.querySelector('button[onclick^="backupNow("]'),bar=row&&row.parentNode,btns=bar?[...bar.querySelectorAll('button,label')]:[];
 btns.forEach(b=>{b.disabled=true;b.style.opacity='.5';b.style.pointerEvents='none'});
 let note=null;if(bar){note=document.createElement('div');note.id='bkbusy';note.className='box';note.setAttribute('role','status');
  note.innerHTML='<div>Making the backup… '+(kind==='full'?'A full backup can take about half a minute.':'This takes a few seconds.')+'</div><div class=busybar><i></i></div>';bar.parentNode.insertBefore(note,bar.nextSibling)}
 try{await api('backups',{kind});renderSettings()}catch(e){if(note)note.remove();btns.forEach(b=>{b.disabled=false;b.style.opacity='';b.style.pointerEvents=''});const m=$('#msg');if(m)m.textContent=e.message;else alert(e.message)}}
async function delBk(name){if(!await askYes('Delete this backup? This cannot be undone.'))return;try{await api('backups/delete',{name});renderSettings()}catch(e){$('#msg').textContent=e.message}}
async function restoreBk(name){if(!await askYes('Replace your current settings with this backup? A copy of what you have now is saved first, so you can go back.'))return;await act('restore',{name})}
async function uploadBk(inp){const f=inp.files[0];if(!f)return;$('#msg').textContent='Uploading the backup…';
 try{const r=await fetch(U('backups/upload'),{method:'POST',headers:{'X-MB':'1'},body:f});const j=await r.json();
  if(!r.ok)throw new Error(j.error||'The upload failed.');renderSettings()}catch(e){$('#msg').textContent=e.message}}
async function saveConn(){const m=$('#cmsg');let obj;try{obj=JSON.parse($('#ccfg').value)}catch(e){m.textContent='That isn\'t valid JSON: '+e.message;return}
 try{const r=await api('config/connections',{revision:+$('#crev').textContent,connections:obj});setRev(r.revision);m.textContent='Saved. Revision '+r.revision+'.'}
 catch(e){m.innerHTML=esc(e.message)+((e.data&&e.data.errors)?'<ul>'+e.data.errors.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'')}}

/* ---------- servers: one page per machine, with its services (SNMP, battery backup, UniFi, Wake on LAN) ---------- */
const MASKCH='••••••••';
const v3=c=>c.version!=='2c';
const SVC={
 snmp:{label:'SNMP',long:'SNMP (health, disks, network ports)',help:'MonitorBox asks the server questions over SNMP. It only reads, it never changes anything.',fields:[
  {k:'version',l:'SNMP version',t:'select',o:[['3','v3 (a user and passwords)'],['2c','v2c (a community word)']],d:'3',re:1},
  {k:'community',l:'Community',t:'password',show:c=>!v3(c)},
  {k:'user',l:'User',show:v3},
  {k:'auth',l:'Login method',t:'select',o:[['sha','SHA'],['sha256','SHA-256'],['sha512','SHA-512'],['sha224','SHA-224'],['sha384','SHA-384'],['md5','MD5'],['','None']],d:'sha',show:v3,re:1},
  {k:'authPassword',l:'Password',t:'password',show:c=>v3(c)&&!!c.auth},
  {k:'priv',l:'Privacy (encryption)',t:'select',o:[['aes','AES'],['des','DES'],['','None']],d:'aes',show:c=>v3(c)&&!!c.auth,re:1},
  {k:'privPassword',l:'Privacy password',t:'password',show:c=>v3(c)&&!!c.auth&&!!c.priv},
  {k:'port',l:'Port',t:'number',ph:'161 (the usual)'}]},
 nut:{label:'Battery backup',long:'Battery backup (NUT)',help:'Reads a UPS from a NUT server (upsd). Read-only: MonitorBox never shuts anything down.',fields:[
  {k:'port',l:'Port',t:'number',ph:'3493 (the usual)'},{k:'username',l:'User (only if the server asks for one)'},{k:'password',l:'Password',t:'password'}]},
 'unifi-network':{label:'UniFi Network',long:'UniFi Network controller',help:'Reads devices, health and VPN tunnels with a read-only account. Create a local user that can only view.',fields:[
  {k:'username',l:'User'},{k:'password',l:'Password',t:'password'},{k:'site',l:'Site',ph:'default'},
  {k:'verify_tls',l:'Check the controller\'s certificate (leave off for a self-signed one)',t:'check'}]},
 'unifi-protect':{label:'UniFi Protect',long:'UniFi Protect (cameras)',help:'Reads camera health, recording and recorder storage with a read-only account. In UniFi OS, create a local user that can only view Protect. It cannot record, move or change anything.',fields:[
  {k:'username',l:'User'},{k:'password',l:'Password',t:'password'},
  {k:'verify_tls',l:'Check the console\'s certificate (leave off for a self-signed one)',t:'check'}]},
 scrypted:{label:'Scrypted',long:'Scrypted (camera hub)',help:'Reads whether Scrypted is up and which cameras it shows, and takes pictures, with a read-only account. In Scrypted, make a user that is not an admin and give it only the Camera and VideoCamera interfaces of the cameras. Needs the newer MonitorBox image (it includes Node).',fields:[
  {k:'username',l:'User'},{k:'password',l:'Password',t:'password'},{k:'port',l:'Port',t:'number',ph:'10443 (the usual)'},
  {k:'exclude',l:'Leave out these cameras',ph:'names, separated by commas'},
  {k:'verify_tls',l:'Check the certificate (leave off for Scrypted\'s own self-signed one)',t:'check'}]},
 portainer:{label:'Portainer',long:'Portainer (containers)',help:'Reads every environment the Portainer server manages, and their containers, with an access token (in Portainer: My account, Access tokens). Read-only: MonitorBox only ever sends GET requests. Give it its own non-admin user that can see only what it needs.',fields:[
  {k:'token',l:'Access token',t:'password'},{k:'port',l:'Port',t:'number',ph:'9443 (the usual), or 9000 for plain http'},
  {k:'http',l:'Portainer uses plain http (port 9000)',t:'check'},{k:'verify_tls',l:'Check the certificate (leave off for Portainer\'s own self-signed one)',t:'check'}]}};
let sv=null;
const slug=t=>(t||'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
const hostOf=c=>String(c.host||c.base_url||'').replace(/^\w+:\/\//,'').split(/[\/:]/)[0].toLowerCase();
const connHost=(c,h)=>{if(c.base_url){const m=String(c.base_url).match(/^(\w+:\/\/)?([^\/:]+)(.*)$/);return (m&&m[1]||'')+h+(m&&m[3]||'')}return h};
const nodesFor=id=>(sv.mon.nodes||[]).filter(n=>(n.checks||[]).some(k=>k.connection===id));
const watchedBy=id=>(sv.mon.nodes||[]).reduce((n,x)=>n+(x.checks||[]).filter(k=>k.connection===id).length,0);
function servers(){const m=new Map(),get=(k,h)=>{if(!m.has(k))m.set(k,{key:k,host:h,conns:[],nodes:[]});return m.get(k)};
 sv.conns.forEach(c=>{const h=hostOf(c);get(h||'conn:'+c.id,h).conns.push(c)});
 (sv.mon.nodes||[]).forEach(n=>{if(n.kind==='aggregate')return;const ks=n.checks||[];
  let x=[...m.values()].find(x=>ks.some(k=>x.conns.some(c=>c.id===k.connection)||(x.host&&k.target&&String(k.target).toLowerCase()===x.host&&['ping','tcp'].includes(k.type))));
  if(!x&&n.wake){const h=String((ks.find(k=>k.target)||{}).target||'').toLowerCase();x=get(h||'node:'+n.id,h)}
  if(x)x.nodes.push(n)});
 return [...m.values()].map(x=>{const snmp=new Set(x.conns.filter(c=>c.module==='snmp').map(c=>c.id));
  x.sys=x.nodes.find(n=>(n.checks||[]).some(k=>snmp.has(k.connection)))||x.nodes.find(n=>(n.checks||[]).some(k=>x.host&&String(k.target||'').toLowerCase()===x.host&&['ping','tcp'].includes(k.type)))||null;
  x.wake=(x.nodes.find(n=>n.wake)||{}).wake||null;
  x.name=(x.sys&&x.sys.name)||(x.conns.find(c=>c.name)||{}).name||(x.nodes[0]&&x.nodes[0].name)||(x.conns[0]&&x.conns[0].id)||x.host;
  x.watched=x.conns.reduce((n,c)=>n+watchedBy(c.id),0);return x})}
const curServer=()=>sv.draft?{key:'draft',host:sv.draft.host,name:sv.draft.name,conns:[],nodes:[],sys:null,wake:null,watched:0,draft:true}:servers().find(x=>x.key===sv.key);
async function loadServers(keep){try{const [c,m]=await Promise.all([api('config/connections'),api('config/monitoring')]);
  sv={conns:c.connections,rev:c.revision,mon:m.monitoring,page:keep?keep.page:'list',key:keep?keep.key:null,draft:keep?keep.draft:null,form:null,wake:null,test:null};
  if(sv.page==='server'&&!curServer())sv.page='list';
  if(window._wiz&&window._wiz.svc==='web'){window._wiz=null;sv.page='list';drawSv();newWebPage();return}
  if(window._wiz){const w=window._wiz;window._wiz=null;const have=servers().find(x=>x.host&&x.host===w.host.toLowerCase());
   if(have){sv.page='server';sv.key=have.key}else{sv.draft={name:w.name,host:w.host};sv.page='server';sv.key=null}
   drawSv();if(w.svc==='wake'){wakeForm();if(w.mac&&!sv.wake.macs)sv.wake.macs=w.mac;drawSv()}else if(SVC[w.svc]&&!(curServer().conns||[]).some(c=>c.module===w.svc))svcForm(w.svc);return}
  if($('#ccfg'))$('#ccfg').value=JSON.stringify(c.connections,null,2);setRev(c.revision);
  drawSv()}catch(e){if($('#devs'))$('#devs').textContent=e.message}}
const keepNow=()=>({page:sv.page,key:sv.key,draft:sv.draft});
function drawSv(){if(!$('#devs')||!sv)return;const I=window._inline;if(I&&!sv.form&&!sv.wake){if(I.opening)return;if(I.picking){$('#devs').innerHTML='';return}return inlineClose()}
 if(sv.form)return drawSvcForm();if(sv.wake)return drawWakeForm();if(sv.page==='server'&&sv.draft)return drawServer();if(sv.page==='server'){sv.open=sv.key;sv.page='list'}drawServerList()}
const chips=x=>[...x.conns.map(c=>(SVC[c.module]||{label:c.module}).label),...(x.wake?['Wake on LAN']:[])].map(t=>`<span class=chip style="background:rgba(255,255,255,.1);color:var(--sub);margin-right:6px">${esc(t)}</span>`).join('');
function drawServerList(){const l=servers();$('#devs').innerHTML=(l.length?l.map(x=>{const op=sv.open===x.key;return `<div class="devrow srv${op?' open':''}" data-key="${esc(x.key)}"><div class=grow><b style="font-size:18px">${esc(x.name)}</b>
   <div class=sub>${esc(x.host||'no address')} · ${x.watched} thing${x.watched==1?'':'s'} watched</div><div style="margin-top:6px">${chips(x)}</div></div>
   <button class="btn sm" onclick="${op?'closeServer()':`openServer('${esc(x.key)}')`}">${op?'Close':'Open'}</button>${op?`<div class=srvbody style="flex-basis:100%">${serverBody(x)}</div>`:''}</div>`}).join(''):'<p class=sub>No servers yet. Add one to start watching it.</p>')
  +`<div class=row style="margin-top:1.2rem;padding-top:1rem;border-top:1px solid rgba(255,255,255,.14)"><button class="btn pri" onclick="newServer()">Add a server</button><button class="btn" onclick="newWebPage()">Add a web page</button><button class="btn" onclick="rescanAll()">Rescan all servers</button></div><p class=sub style="margin:.4rem 0 0">Rescan looks at every server again for things you are not watching yet.</p><div id=fu></div>`;loadFollowups()}
/* a rescan is the Set up scan: forget what was seen, then open Set up, which looks again (the box itself every time) */
function rememberServers(l){const have=savedHosts(),h=have.map(x=>hostKey(x.host));       // Set up lists servers it has been told about, so tell it
 for(const x of l)if(x.host&&!h.includes(hostKey(x.host)))have.push({host:x.host,name:x.name});saveHosts(have)}
function rescanAll(){rememberServers(servers());for(const k of Object.keys(scans))delete scans[k];window._focus=null;location.hash='#/setup'}
function rescanServer(host){rememberServers(servers().filter(x=>hostKey(x.host)===hostKey(host)));delete scans[hostKey(host)];window._focus=hostKey(host);location.hash='#/setup'}
function closeServer(){sv.open=null;drawSv()}
/* Watch a web page by hand: a server's admin console, a login page, anything that is not a container. It joins a system (which then shows an Open link) or becomes one. */
async function newWebPage(){let nodes=[];try{nodes=((await api('config/monitoring')).monitoring.nodes||[]).filter(n=>n.kind!=='aggregate')}catch(e){}
 const groups=['Services','Servers','Network','Internet','Power','Cameras'];
 $('#devs').innerHTML=`<h3 style="margin:.2rem 0">Add a web page</h3><p class=sub style="margin:0">MonitorBox opens the page every minute or so. Add it to a system (a server's admin page, say) or let it be a system of its own.</p>
  <div class=fm><div class=fld><label for=w-name>Name</label><input id=w-name type=text autocomplete=off placeholder="Granite admin"></div>
   <div class=fld><label for=w-url>Address</label><input id=w-url type=text autocomplete=off autocapitalize=off spellcheck=false placeholder="https://192.168.1.13/"></div>
   <div class=fld><label for=w-sys>Add it to</label><select id=w-sys onchange="$('#w-grp').parentNode.style.display=this.value?'none':''"><option value="">A new system</option>${nodes.map(n=>`<option value="${esc(n.id)}">${esc(n.name)}</option>`).join('')}</select></div>
   <div class=fld><label for=w-grp>Show it under</label><select id=w-grp>${groups.map(g=>`<option>${g}</option>`).join('')}</select></div></div>
  <details style="margin:.6rem 0"><summary class=sub>More options</summary><div class=fm style="margin-top:.5rem">
   <div class=fld><label for=w-link>Link to open <span class=sub>· if different from the address</span></label><input id=w-link type=text autocomplete=off autocapitalize=off spellcheck=false></div>
   <div class=fld><label for=w-text>Page must contain <span class=sub>· text</span></label><input id=w-text type=text autocomplete=off></div>
   <div class=fld><label for=w-exp>Expected status codes <span class=sub>· for example 200, 401</span></label><input id=w-exp type=text autocomplete=off placeholder="any 200 to 399"></div>
   <label class=row style="gap:10px"><input id=w-ins type=checkbox style="width:22px;height:22px"> Trust this device's own certificate (usual for admin pages on your own network)</label></div></details>
  <div class=row><button class="btn pri big" onclick="saveWebPage()">Add</button><button class="btn big" onclick="drawSv()">Cancel</button></div><div id=devmsg style="margin-top:.6rem"></div>`}
async function saveWebPage(){const v=id=>$('#'+id).value.trim(),sys=v('w-sys'),m=$('#devmsg');
 const body={name:v('w-name'),url:v('w-url'),system:sys||undefined,group:v('w-grp'),link:v('w-link')||undefined,contains:v('w-text')||undefined,
  expect:v('w-exp')?v('w-exp').split(/[ ,]+/).filter(Boolean):undefined,insecure:$('#w-ins').checked};
 if(!body.name||!body.url){m.textContent='Enter a name and an address.';return}
 try{await api('web-page',body);m.textContent='Added.';setTimeout(()=>{drawSv()},600)}catch(e){m.textContent=e.message}}
function openServer(key){sv.open=key;sv.key=key;sv.page='list';sv.draft=null;drawSv()}
function newServer(){$('#devs').innerHTML=`<h3 style="margin:.2rem 0">Add a server</h3><p class=sub style="margin:0">Give it a name and an address, then choose how MonitorBox reaches it.</p>
  <div class=fm><div class=fld><label for=n-name>Name</label><input id=n-name type=text autocomplete=off placeholder="Monitor"></div>
   <div class=fld><label for=n-host>Address</label><input id=n-host type=text autocomplete=off autocapitalize=off spellcheck=false placeholder="192.168.1.10"></div></div>
  <div class=row><button class="btn pri big" onclick="startServer()">Next</button><button class="btn big" onclick="drawSv()">Cancel</button></div><div id=devmsg style="margin-top:.6rem"></div>`}
function startServer(){const name=$('#n-name').value.trim(),host=$('#n-host').value.trim();
 if(!name||!host){$('#devmsg').textContent='Enter a name and an address.';return}
 if(servers().some(x=>x.host&&x.host===host.toLowerCase())){$('#devmsg').textContent='That address is already a server. Open it from the list.';return}
 sv.draft={name,host};sv.page='server';drawSv()}
function serverBody(x){
 const have=new Set(x.conns.map(c=>c.module));
 const svcRow=c=>{const t=SVC[c.module],n=watchedBy(c.id);return `<div class=devrow><div class=grow><b>${esc(t?t.long:c.module)}</b><div class=sub>${n} thing${n==1?'':'s'} watched</div>${c.module==='portainer'?critBox(x.nodes.filter(nd=>(nd.checks||[]).some(k=>k.connection===c.id&&k.check==='environment')).map(nd=>nd.id),'Critical: if Portainer is down here, the whole box goes red'):''}</div>
   <button class="btn sm" onclick="pickFor('${esc(c.id)}')">Pick what to watch</button><button class="btn sm" onclick="svcForm('${esc(c.module)}','${esc(c.id)}')">Edit</button></div>`};
 const wakeRow=x.wake?`<div class=devrow><div class=grow><b>Wake on LAN</b><div class=sub>${esc(x.wake.macs.join(', '))}</div></div><button class="btn sm" onclick="wakeForm()">Edit</button></div>`:'';
 const add=Object.keys(SVC).filter(k=>!have.has(k)).map(k=>`<button class="btn" onclick="svcForm('${k}')">${esc(SVC[k].long)}</button>`).concat(x.wake?[]:[`<button class="btn" onclick="wakeForm()">Wake on LAN</button>`]).join('');
 return `  ${x.draft?'<p class=sub>Not saved yet. It is saved when you add its first service below.</p>':''}
  <div class=fm><div class=fld><label for=s-name>Name <span class=sub>· also what the main screen calls it</span></label><input id=s-name type=text autocomplete=off value="${esc(x.name)}"></div>
   <div class=fld><label for=s-host>Address</label><input id=s-host type=text autocomplete=off autocapitalize=off spellcheck=false value="${esc(x.host)}"></div></div>
  ${x.draft?'':'<div class=row><button class="btn" onclick="saveBasics()">Save name and address</button></div>'}
  ${(!x.draft&&x.sys)?critBox([x.sys.id],'Critical: if this server is down, the whole box goes red'):''}
  <h3 style="margin:1rem 0 .2rem">Services</h3>${x.conns.map(svcRow).join('')}${wakeRow}${(!x.conns.length&&!x.wake)?'<p class=sub>Nothing set up yet.</p>':''}
  <div class=row style="margin-top:.8rem"><b>Add:</b>${add}</div>
  ${x.draft?'':`<div class=row style="margin-top:1rem"><button class="btn" onclick="rescanServer('${esc(x.host)}')">Rescan this server</button><button class="btn" onclick="removeServer()">Remove this server</button></div>`}<div id=devmsg style="margin-top:.6rem"></div>`}
function drawServer(){const x=curServer();$('#devs').innerHTML=`<div class=row><button class="btn sm" onclick="sv.page='list';sv.draft=null;drawSv()">‹ All servers</button></div>`+serverBody(x)}
function basics(){const x=curServer(),name=($('#s-name')||{}).value,host=($('#s-host')||{}).value;return {name:(name||x.name).trim(),host:(host||x.host).trim()}}
const showErr=(err,id)=>{$(id||'#devmsg').innerHTML=esc(err.message)+((err.data&&err.data.errors)?'<ul>'+err.data.errors.map(e=>'<li>'+esc(e)+'</li>').join('')+'</ul>':'')};
async function saveBasics(){const x=curServer(),b=basics(),m=$('#devmsg');
 if(!b.name||!b.host){m.textContent='Enter a name and an address.';return}
 m.textContent='Saving…';
 try{const moved=b.host.toLowerCase()!==x.host.toLowerCase();
  const list=sv.conns.map(c=>x.conns.includes(c)?{...c,name:b.name,...(!moved?{}:c.base_url?{base_url:connHost(c,b.host)}:{host:b.host})}:c);
  if(x.conns.length)await api('config/connections',{revision:sv.rev,connections:list});
  const cur=await api('config/monitoring'),old=x.host.toLowerCase();let changed=false;
  const sys=(cur.monitoring.nodes||[]).find(n=>x.sys&&n.id===x.sys.id);
  if(sys&&sys.name!==b.name){sys.name=b.name;changed=true}
  if(b.host.toLowerCase()!==old)(cur.monitoring.nodes||[]).forEach(n=>(n.checks||[]).forEach(k=>{if(k.target&&String(k.target).toLowerCase()===old){k.target=b.host;changed=true}}));
  if(changed)await api('config/monitoring',{revision:cur.revision,monitoring:cur.monitoring});
  const keep=keepNow();keep.key=b.host.toLowerCase()||keep.key;await loadServers(keep);try{await syncCfg()}catch(_){}}
 catch(err){showErr(err)}}
function svcForm(type,id){const t=SVC[type],x=curServer(),o=id?sv.conns.find(c=>c.id===id):null,c={...(o||{module:type})};
 t.fields.forEach(f=>{if(c[f.k]===undefined&&f.k==='version'&&!o)c[f.k]=f.d;if(c[f.k]===undefined&&f.k==='version'&&o)c[f.k]=f.d;if(!o&&f.d!==undefined&&c[f.k]===undefined)c[f.k]=f.d});
 sv.form={type,c,orig:o||{},isNew:!o};sv.test=null;drawSvc()}
const drawSvcForm=()=>drawSvc();
function drawSvc(){const e=sv.form,t=SVC[e.type],x=curServer();
 $('#devs').innerHTML=`<div class=row><button class="btn sm" onclick="sv.form=null;sv.test=null;drawSv()">‹ ${esc(x.name)}</button></div>
  <h3 style="margin:.6rem 0 .2rem">${e.isNew?'Add':'Edit'}: ${esc(t.long)}</h3><p class=sub style="margin:0">${esc(t.help)}</p>
  <p class=sub style="margin:.3rem 0 0">For ${esc(x.name)} · ${esc(x.host)}</p>
  <div class=fm>${t.fields.filter(f=>!f.show||f.show(e.c)).map(fieldHtml).join('')}</div>
  <div class=row><button class="btn big" id=devtestbtn onclick="devTest()">Test connection</button></div><div id=devtest>${testHtml()}</div>
  <div class=row style="margin-top:.8rem"><button class="btn pri big" onclick="svcSave(true)">Save, then pick what to watch</button>
   <button class="btn big" onclick="sv.form=null;sv.test=null;drawSv()">Cancel</button>${e.isNew?'':'<button class="btn big" style="margin-left:auto" onclick="svcRemove()">Remove this service</button>'}</div><div id=devmsg style="margin-top:.6rem"></div>`}
const fieldHtml=f=>{const e=sv.form,v=e.c[f.k];let inp;
 if(f.t==='select')inp=`<select id="f-${f.k}" onchange="devSet('${f.k}',this.value,${f.re?1:0})">${f.o.map(([val,lab])=>`<option value="${esc(val)}" ${String(v??'')===val?'selected':''}>${esc(lab)}</option>`).join('')}</select>`;
 else if(f.t==='check')return `<label class=row style="flex:1 1 100%;min-height:44px"><input type=checkbox ${v?'checked':''} onchange="devSet('${f.k}',this.checked,0)"> ${esc(f.l)}</label>`;
 else inp=`<input id="f-${f.k}" type=text ${f.t==='password'?'class=pw data-lpignore=true data-1p-ignore data-bwignore name="mb-'+f.k+'-x"':''} ${f.t==='number'?'inputmode=numeric':''} autocomplete=off autocapitalize=off spellcheck=false value="${esc(v??'')}" placeholder="${esc(f.ph||'')}" oninput="devSet('${f.k}',this.value,0)">`;
 return `<div class=fld><label for="f-${f.k}">${esc(f.l)}${f.t==='password'&&v===MASKCH?' <span style="color:var(--acc)">· saved, shown as dots</span>':''}</label>${inp}</div>`};
function devSet(k,v,re){sv.form.c[k]=v;sv.test=null;if(re)drawSvc()}
function testHtml(){const r=sv.test;if(!r)return '';if(r==='busy')return '<p class=sub>Trying…</p>';
 if(r.ok)return `<div class=okbox><b style="color:#6EE7B7">✓ It answered in ${r.seconds} s</b>${r.found.length?'<div class=sub style="margin-top:6px">Found: '+r.found.map(f=>esc(f.label)+' '+f.count).join(' · ')+'</div>':''}</div>`;
 return `<div class=badbox><b style="color:#FCA5A5">${esc(r.error)}</b>${r.detail?`<details><summary class=sub style="min-height:36px;display:flex;align-items:center">Technical detail</summary><small>${esc(r.detail)}</small></details>`:''}</div>`}
function cleanConn(){const e=sv.form,t=SVC[e.type],x=curServer(),c={...e.orig,module:e.type};
 for(const f of t.fields){const shown=!f.show||f.show(e.c);let v=e.c[f.k];delete c[f.k];
  if(!shown||v===''||v===undefined||v===false)continue;
  if(f.t==='number'){v=parseInt(v,10);if(isNaN(v))continue}
  c[f.k]=v}
 const b=basics();c.name=b.name;delete c.host;delete c.base_url;
 if(!e.isNew&&b.host.toLowerCase()===x.host.toLowerCase()){if(e.orig.base_url!==undefined)c.base_url=e.orig.base_url;if(e.orig.host!==undefined)c.host=e.orig.host}   // address untouched: keep exactly what was saved (scheme, port)
 else if(e.orig.base_url)c.base_url=connHost(e.orig,b.host);else c.host=b.host;
 if(e.isNew){let base=slug(b.name+'-'+e.type),id=base,n=2;while(sv.conns.some(y=>y.id===id))id=base+'-'+n++;c.id=id}else c.id=e.orig.id;return c}
async function devTest(){sv.test='busy';$('#devtest').innerHTML=testHtml();$('#devtestbtn').disabled=true;
 try{sv.test=await api('connections/test',{connection:cleanConn()})}catch(err){sv.test={ok:false,error:err.message}}
 if($('#devtest')){$('#devtest').innerHTML=testHtml();$('#devtestbtn').disabled=false}}
async function svcSave(thenPick){const e=sv.form,m=$('#devmsg'),c=cleanConn();if(window._inline&&thenPick)window._inline.picking=true;
 const list=e.isNew?[...sv.conns,c]:sv.conns.map(x=>x.id===e.orig.id?c:x);m.textContent='Saving…';
 try{await api('config/connections',{revision:sv.rev,connections:list});
  if(c.module==='portainer'&&!e.isNew)await dropGoneEnvs(c.id);
  const keep={page:'server',key:hostOf(c)||sv.key,draft:null};await loadServers(keep);try{await syncCfg()}catch(_){}
  if(thenPick)pickFor(c.id)}
 catch(err){showErr(err)}}
/* saving a Portainer connection re-reads its environments: whatever was watched under one that is gone (renamed, deleted) is offered for removal right then */
async function dropGoneEnvs(cid){
 try{const r=await api('detect',{connection:cid}),have=new Set((r.environments||[]).map(x=>x.name));if(!have.size)return;
  const mine=(sv.mon.nodes||[]).filter(n=>n.kind!=='aggregate'&&(n.checks||[]).some(k=>k.connection===cid)),envOf=n=>(n.service&&n.service.env)||(((n.checks||[]).find(k=>k.connection===cid&&k.check==='environment')||{}).params||{}).name;
  const stale=mine.filter(n=>{const v=envOf(n);return v&&!have.has(v)}),names=[...new Set(stale.map(envOf))];
  if(!stale.length)return;
  if(!await askYes('Portainer no longer has '+(names.length==1?'an environment called ':'environments called ')+names.map(x=>"'"+x+"'").join(', ')+' (it has: '+[...have].join(', ')+'). Stop watching the '+stale.length+' thing'+(stale.length==1?'':'s')+' under '+(names.length==1?'it':'them')+'?'))return;
  for(const n of stale)await api('stopwatching',{id:n.id})}catch(_){}}   // a failed look never removes anything
async function svcRemove(){const e=sv.form,n=watchedBy(e.orig.id);
 if(!await askYes(n?`Remove this service? The ${n} thing${n==1?'':'s'} watched through it ${n==1?'is':'are'} removed too. You can set it up again afterwards.`:'Remove this service?'))return;
 try{await api('config/connection/remove',{id:e.orig.id});await loadServers({page:'server',key:sv.key,draft:null});try{await syncCfg()}catch(_){}}catch(err){showErr(err)}}
async function removeServer(){const x=curServer(),k=x.nodes.length;
 if(!await askYes(`Remove ${x.name}? Its ${k?k+' watched system'+(k==1?'':'s')+' and all their checks, its ':''}connection settings${x.wake?' and wake settings':''} are deleted.`))return;
 try{for(const n of x.nodes)await api('stopwatching',{id:n.id});          // its checks go first; a connection that is still in use cannot be removed
  const ids=new Set(x.conns.map(c=>c.id));
  for(const id of ids)await api('config/connection/remove',{id});
  await loadServers();try{await syncCfg()}catch(_){}}catch(err){showErr(err);await loadServers()}}
function pickFor(id){$('#detid').value=id;detect();$('#detout').scrollIntoView({behavior:'smooth',block:'start'})}
/* wake settings belong to the server's system (the one that holds its checks); one is made if the server has none yet */
function wakeForm(){const x=curServer(),w=x.wake||{};
 sv.wake={macs:(w.macs||[]).join('\n'),broadcast:w.broadcast||'',timeout:w.timeout===undefined?'':String(w.timeout),isNew:!x.wake};drawSv()}
function drawWakeForm(){const e=sv.wake,x=curServer();$('#devs').innerHTML=`<div class=row><button class="btn sm" onclick="sv.wake=null;drawSv()">‹ ${esc(x.name)}</button></div>
  <h3 style="margin:.6rem 0 .2rem">Wake on LAN: ${esc(x.name)}</h3><p class=sub style="margin:0">Lets the Wake button on its page switch it on while it sleeps. MonitorBox sends the wake signal, then watches for it to come up.</p>
  <div class=fm><div class=fld style="flex-basis:100%"><label for=w-macs>MAC addresses, one per line (a machine with two network cards can list both)</label>
   <textarea id=w-macs rows=3 spellcheck=false autocapitalize=off style="min-height:90px;font-size:17px" oninput="sv.wake.macs=this.value" placeholder="aa:bb:cc:dd:ee:ff">${esc(e.macs)}</textarea></div>
   <div class=fld><label for=w-bc>Broadcast address (optional)</label><input id=w-bc type=text inputmode=decimal autocomplete=off value="${esc(e.broadcast)}" placeholder="255.255.255.255 (the usual)" oninput="sv.wake.broadcast=this.value"></div>
   <div class=fld><label for=w-to>Give up after, seconds (optional)</label><input id=w-to type=text inputmode=numeric autocomplete=off value="${esc(e.timeout)}" placeholder="120 (the usual)" oninput="sv.wake.timeout=this.value"></div></div>
  <div class=row><button class="btn pri big" onclick="saveWake()">Save</button><button class="btn big" onclick="sv.wake=null;drawSv()">Cancel</button>
   ${e.isNew?'':'<button class="btn big" style="margin-left:auto" onclick="saveWake(true)">Remove wake settings</button>'}</div><div id=wakemsg style="margin-top:.6rem"></div>`}
async function saveWake(remove){const e=sv.wake,x=curServer(),m=$('#wakemsg');
 if(remove&&!await askYes('Remove the wake settings for '+x.name+'? Its MAC addresses will be forgotten.'))return;m.textContent='Saving…';
 try{const cur=await api('config/monitoring'),nodes=cur.monitoring.nodes||(cur.monitoring.nodes=[]);
  let n=nodes.find(y=>x.nodes.some(z=>z.id===y.id&&(z.wake||(x.sys&&z.id===x.sys.id))));
  if(!n&&x.sys)n=nodes.find(y=>y.id===x.sys.id);
  if(remove){if(n)delete n.wake}
  else{if(!n){if(!x.host){throw new Error('This server needs an address first.')}
    let base=slug(x.name)||'server',id=base,k=2;while(nodes.some(y=>y.id===id))id=base+'-'+k++;
    n={id,name:x.name,group:'Servers',rule:'primary',checks:[{id:'ping',type:'ping',target:x.host}]};nodes.push(n)}
   const w={...(n.wake||{})};w.macs=e.macs.split(/[\s,;]+/).filter(Boolean).map(v=>{const f=v.replace(/[:.\-]/g,'').toLowerCase();return /^[0-9a-f]{12}$/.test(f)?f.match(/../g).join(':'):v});
   const bc=e.broadcast.trim();if(bc)w.broadcast=bc;else delete w.broadcast;
   const to=e.timeout.trim();if(to){const v=parseInt(to,10);if(isNaN(v)){m.textContent='The time to give up must be a number of seconds.';return}w.timeout=v}else delete w.timeout;n.wake=w}
  await api('config/monitoring',{revision:cur.revision,monitoring:cur.monitoring});
  await loadServers({page:'server',key:sv.draft?(sv.draft.host||'').toLowerCase():sv.key,draft:null});try{await syncCfg()}catch(_){}}
 catch(err){showErr(err,'#wakemsg')}}
async function demo(n){try{await api('demo',{scenario:n});location.hash=''}catch(e){$('#msg').textContent=e.message}}
async function checkUpdates(b){b.disabled=true;$('#chk').textContent='Checking…';
 try{const v=await api('check',{});hdrPoll();const n=(v.app&&v.app.needsApply?1:0)+Object.values(v.modules).filter(modWaiting).length;
  await renderSettings();$('#chk').textContent=v.checkError?v.checkError:(n?n+' update'+(n>1?'s':'')+' available':'Checked just now: everything is up to date')}
 catch(e){$('#chk').textContent=e.message;b.disabled=false}}
async function checkAllSites(b){b.disabled=true;const ids=((siCfg&&siCfg.sites)||[]).filter(x=>(x.link||{}).state==='linked');$('#chk').textContent='Checking…';
 const rs=await Promise.allSettled([api('check',{})].concat(ids.map(x=>api('site/'+x.id+'/check',{}))));await hdrPoll();
 try{await renderSettings()}catch(e){}
 const bad=ids.filter((x,i)=>rs[i+1].status==='rejected').map(x=>x.name||'A site'),c=$('#chk');
 if(c)c.textContent=rs[0].status==='rejected'?String(rs[0].reason&&rs[0].reason.message||'Could not check'):bad.length?'Checked just now. No answer from '+bad.join(', '):'Checked just now'}
async function repoAdd(){const t=($('#repoin').value||'').trim();if(!t)return;
 if(!await askYes('Add '+t+'? Modules from a repository run on this box and can see the passwords and keys you give them. Only add repositories you trust.','Add'))return;
 const m=$('#repomsg');m.textContent='Adding…';try{await api('repos/add',{repo:t});renderSettings()}catch(e){m.textContent=e.message}}
async function repoOn(id,on){try{await api('repos/enable',{id,enabled:on});renderSettings()}catch(e){$('#msg').textContent=e.message}}
const BKCH=[['Uninstall, no backup','none'],['Back up settings first, then uninstall','config'],['Full backup first, then uninstall','full']];
const plural=(n,w)=>n+' '+w+(n==1?'':'s');
async function repoRemove(id,name){const r=(window._rv||[]).find(x=>x.id===id)||{installed:[],uses:{}};
 if(!r.installed.length){if(!await askYes('Remove '+name+' from the list?'))return;try{await api('repos/remove',{id});renderSettings()}catch(e){$('#repomsg').textContent=e.message}return}
 const n=Object.values(r.uses||{}).reduce((a,b)=>a+b,0);
 const b=await askChoice('Removing '+name+' also uninstalls '+r.installed.join(', ')+(n?' and deletes the '+plural(n,'connection')+' that use'+(n==1?'s':'')+' them, with their settings (passwords and keys)':'')+'. Back up first?',BKCH);
 if(b===null)return;const m=$('#repomsg');m.textContent='Working…';try{const x=await api('repos/remove',{id,uninstall:true,backup:b});await renderSettings();$('#msg').textContent=x.message}catch(e){m.textContent=e.message}}
async function uninstallModule(id,title,n){
 const b=await askChoice('Uninstall '+title+'? '+(n?'This also deletes the '+plural(n,'connection')+' that use'+(n==1?'s':'')+' it, with their settings (passwords and keys) and the checks that came from them.':'No saved connection uses it.')+' Back up first?',BKCH);
 if(b===null)return;try{const x=await api('modules/uninstall',{id,backup:b});await renderSettings();$('#msg').textContent=x.message}catch(e){$('#msg').textContent=e.message}}
async function pick(kind,id,pin){try{await api('select',{kind,id,pin});renderSettings()}catch(e){$('#msg').textContent=e.message}}
async function setting(b){try{await api('settings',b)}catch(e){$('#msg').textContent=e.message}}
function sitesLines(d){const w={asking:'asked…',restarting:'installing, restarting',done:'done',failed:'did not update',waiting:'next',working:'installing here'};
 return (d.sites||[]).map(r=>`<div><b>${esc(r.name)}</b>: ${esc(w[r.state]||r.state)}${r.message?' · '+esc(r.message):''}</div>`).join('')+(d.local?`<div><b>This box</b>: ${esc(w[d.local.state]||d.local.state)}${d.local.message?' · '+esc(d.local.message):''}</div>`:'')}
async function updateSites(btn){btn.disabled=true;const out=$('#upsitesout');
 const restart=()=>{$('#m').textContent='Restarting…';setTimeout(boot,4000)};         /* this box updated itself: wait for it, then reload the page, as for any other App update */
 try{await api('sites/update-all',{})}catch(e){if(out)out.textContent=e.message||'Could not start.';btn.disabled=false;return}
 for(let i=0;i<150;i++){let d;try{d=await api('sites/update-all')}catch(e){restart();return}      /* it stopped answering after it started: it is restarting */
  const o=$('#upsitesout');if(!o)return;o.innerHTML=sitesLines(d);if(d.local&&d.local.state==='restarting'){restart();return}if(!d.running)break;await new Promise(r=>setTimeout(r,2000))}
 const b=$('#upsites');if(b)b.disabled=false}
async function updateAll(btn){btn.disabled=true;btn.textContent='Updating…';await act('apply-all',{});btn.disabled=false}
async function restartApp(){if(!await askYes('Restart MonitorBox now?'))return;await act('app/restart',{})}
async function factoryReset(){const t=await askText('Reset MonitorBox','This deletes your settings, password, history and installed modules. Your backups are kept, and the modules are downloaded again. Type RESET to continue.','');if(t===null)return;try{sessionStorage.removeItem('mb-sx')}catch(e){}await act('factory-reset',{confirm:t})}
async function act(p,b){try{const r=await api(p,b||{});$('#msg').textContent=r.message||'Done';
 if(r.restarting){$('#m').textContent='Restarting…';setTimeout(boot,4000)}else renderSettings()}catch(e){$('#msg').textContent=e.message}}
boot();
</script></html>"""
