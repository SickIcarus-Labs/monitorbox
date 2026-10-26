// Scrypted module: is Scrypted up, can it see the cameras, and a picture from each (read-only).
//
//   check    {"check": "server"}                        Scrypted answers and this account can see cameras
//            {"check": "cameras", "params": {"names"}}  every camera Scrypted reports (or just those named)
//            {"check": "camera",  "params": {"name"}}   one camera
//            connection: {host or base_url, port (default 10443), username, password, verify_tls (default false), exclude: "name, name"}
//   cameras  {"connection"} -> the source-neutral camera list (id, name, model, state, detail, recording, lastSeen, motion, source, snapshot, live)
//   snapshot {"connection", "id"} -> {"mime": "image/jpeg", "data": base64}
//   discover {"connection"} -> cameras and ready-made checks; fails with a plain reason if this account cannot see or photograph the cameras
//
//   live_open  {"connection", "id", "session", "options"}  start live video (WebRTC) for one camera; answers at once, then sends unasked
//   live_input {"session", "message"}                       lines {"event":"live","session","message"} that the browser answers with live_input
//   live_close {"session"}
//
// READ-ONLY. The only things this file ever asks Scrypted to do: log in, list its devices, read a device's name, type, interfaces and online
// flag, take one picture (takePicture + convert to JPEG), and, for a live view the person asked for, a WebRTC signaling session with that one
// camera (RTCSignalingChannel.startRTCSignalingSession, ended with endSession). The video itself flows between Scrypted and the browser, never
// through MonitorBox. It never sets anything and never calls a device method that changes state. A Scrypted that cannot be reached, or a login that is refused, is Unknown, never Failed.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const VERSION = JSON.parse(fs.readFileSync(path.join(here, 'manifest.json'), 'utf8')).version;
const CAMERA_TYPES = ['Camera', 'Doorbell'];
const MAX_PICTURE = 3_000_000;
const sessions = new Map();          // one connection per Scrypted login, shared by every check

class ScryptedProblem extends Error {}

function timed(label, promise, ms) {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new ScryptedProblem(`${label} timed out`)), ms); })])
    .finally(() => clearTimeout(timer));
}

async function loadClient() {
  // MB_SCRYPTED_CLIENT lets the tests stand in a fake Scrypted; in real use it is the official client library shipped with the module
  const where = process.env.MB_SCRYPTED_CLIENT;
  const mod = await import(where ? pathToFileURL(where).href : '@scrypted/client');
  return mod.connectScryptedClient || mod.default?.connectScryptedClient;
}

function baseUrl(conn) {
  const raw = conn.base_url || conn.host;
  if (!raw) throw new ScryptedProblem("this connection has no 'host' or 'base_url'");
  if (!conn.username || !conn.password) throw new ScryptedProblem("this connection needs a 'username' and 'password' (a Scrypted user that can only see the cameras)");
  if (String(raw).includes('://')) return String(raw).replace(/\/+$/, '');
  return `https://${raw}:${conn.port || 10443}`;
}

async function connect(conn) {
  const url = baseUrl(conn);
  const key = JSON.stringify([url, conn.username, conn.password, !!conn.verify_tls]);
  const have = sessions.get(key);
  if (have?.sdk) return have.sdk;
  if (have?.pending) return have.pending;
  if (have?.failedAt && Date.now() - have.failedAt < 60000 && have.refused)           // a refused login is not retried for a minute (no lock-outs)
    throw new ScryptedProblem(`${have.refused} (not retrying for a minute, so the account is not locked out)`);
  if (!conn.verify_tls) process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';              // a self-signed certificate is normal on Scrypted; only this module process is affected
  const entry = { pending: null };
  entry.pending = (async () => {
    const connectScryptedClient = await loadClient();
    const log = console.log; console.log = () => {};                                  // the client library is chatty and stdout is our protocol
    try {
      const sdk = await timed('connecting to Scrypted', connectScryptedClient({
        baseUrl: url, pluginId: '@scrypted/core', username: conn.username, password: conn.password, clientName: 'MonitorBox', local: false,
      }), (conn.timeout || 10) * 1000);
      sdk.onClose = () => { sessions.delete(key); };
      sessions.set(key, { sdk });
      return sdk;
    } catch (e) {
      const msg = String(e?.message || e);
      sessions.set(key, { failedAt: Date.now(), refused: /401|403|unauthor|forbidden|invalid|denied|credential/i.test(msg) ? `Scrypted refused the user name or password (${msg.slice(0, 80)})` : null });
      throw new ScryptedProblem(/401|403|unauthor|forbidden|invalid|denied|credential/i.test(msg) ? `Scrypted refused the user name or password (${msg.slice(0, 80)})` : `cannot reach Scrypted at ${url} (${msg.slice(0, 120)})`);
    } finally { console.log = log; }
  })();
  sessions.set(key, entry);
  return entry.pending;
}

function excluded(conn) {
  return new Set(String(conn.exclude || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean));
}

function cameraDevices(sdk, conn) {
  const skip = excluded(conn);
  const out = [];
  for (const id of Object.keys(sdk.systemManager.getSystemState())) {
    const d = sdk.systemManager.getDeviceById(id);
    if (d && CAMERA_TYPES.includes(d.type) && !skip.has(String(d.name).toLowerCase())) out.push({ id, d });
  }
  return out.sort((a, b) => String(a.d.name).localeCompare(String(b.d.name), undefined, { sensitivity: 'base' }));
}

function describeCamera({ id, d }) {
  const online = d.online === true ? true : d.online === false ? false : null;          // only a real false is Offline
  const live = (d.interfaces || []).includes('RTCSignalingChannel');
  const model = d.info?.model || d.type;
  const state = online === false ? 'failed' : 'healthy';
  const detail = [model, online === false ? 'offline in Scrypted' : 'online'].filter(Boolean).join(' · ');
  return { id: String(id), name: String(d.name), model, state, detail, recording: null, lastSeen: null, motion: false, source: 'scrypted', snapshot: online !== false, live };
}

async function picture(sdk, id) {
  const d = sdk.systemManager.getDeviceById(id);
  if (!d || !CAMERA_TYPES.includes(d.type)) throw new ScryptedProblem('that is not a camera Scrypted shows this account');
  if (typeof d.takePicture !== 'function') throw new ScryptedProblem('this account cannot take pictures from that camera (give it the Camera interface in Scrypted)');
  const media = await timed('taking a picture', d.takePicture(), 15000);
  const buf = await timed('reading the picture', sdk.mediaManager.convertMediaObjectToBuffer(media, 'image/jpeg'), 15000);
  if (!buf || buf.length > MAX_PICTURE) throw new ScryptedProblem('the picture was empty or larger than expected');
  return Buffer.from(buf);
}

// ---- checks (pure on a list of described cameras)
function checkServer(sdk, cams) {
  if (!cams.length) return { state: 'degraded', detail: `Scrypted ${sdk.serverVersion || ''} answers, but this account can see no cameras (in Scrypted, give it the Camera and VideoCamera interfaces of the cameras)`.replace('  ', ' ') };
  return { state: 'healthy', detail: `Scrypted ${sdk.serverVersion || ''} · ${cams.length} camera${cams.length === 1 ? '' : 's'}`.replace('  ', ' ') };
}

function checkCameras(cams, names) {
  const want = new Set((names || []).map(n => String(n).toLowerCase()));
  const rows = want.size ? cams.filter(c => want.has(c.name.toLowerCase())) : cams;
  if (!rows.length) return { state: 'unknown', detail: 'Scrypted shows this account no cameras' };
  const bad = rows.filter(c => c.state === 'failed').map(c => c.name);
  const detail = `${rows.length - bad.length} of ${rows.length} cameras online` + (bad.length ? ` · offline: ${bad.join(', ')}` : '');
  return { state: bad.length ? 'failed' : 'healthy', detail };
}

function checkCamera(cams, name) {
  if (!name) return { state: 'unknown', detail: "this check needs a camera 'name'. Use Re-detect." };
  const c = cams.find(x => x.name.toLowerCase() === String(name).toLowerCase());
  if (!c) return { state: 'unknown', detail: `Scrypted shows this account no camera called '${name}' any more (it shows: ${cams.map(x => x.name).join(', ') || 'none'}). Use Re-detect.` };
  return { state: c.state, detail: c.detail };
}

async function runCheck(kind, params, conn) {
  try {
    const sdk = await connect(conn);
    const cams = cameraDevices(sdk, conn).map(describeCamera);
    if (kind === 'server') return checkServer(sdk, cams);
    if (kind === 'cameras') return checkCameras(cams, params.names);
    if (kind === 'camera') return checkCamera(cams, params.name);
    return { state: 'unknown', detail: `unknown Scrypted check '${kind}' (known: server, cameras, camera)` };
  } catch (e) {
    return { state: 'unknown', detail: String(e.message || e) };           // Scrypted could not be asked: Unknown, never Failed
  }
}

async function discover(conn) {
  const sdk = await connect(conn);
  const found = cameraDevices(sdk, conn);
  if (!found.length)
    throw new ScryptedProblem('connected, but this account can see no cameras. In Scrypted, open the user and give it the Camera and VideoCamera interfaces of each camera');
  try { await picture(sdk, found[0].id); }
  catch (e) { throw new ScryptedProblem(`connected and can see ${found.length} cameras, but taking a picture from ${found[0].d.name} failed (${String(e.message || e).slice(0, 120)}). Check this account's access to the cameras in Scrypted`); }
  const cams = found.map(describeCamera);
  const suggest = [
    { label: 'Scrypted', check: 'server', params: {}, batch: 'Overview', node: 'Scrypted', group: 'Cameras', rule: 'primary' },
    // every camera is its own item, so one that is off shows as Down by name (the all-cameras summary is no longer offered: the cameras say it themselves)
    ...cams.map(c => ({ label: `Camera ${c.name}`, check: 'camera', params: { name: c.name }, batch: 'Cameras', node: `Camera ${c.name}`, group: 'Cameras', rule: 'primary' })),
  ];
  return { cameras: cams, suggest };
}

// ---- live video: Scrypted asks the BROWSER (through the App) to create its WebRTC offer/answer; the browser answers; media flows browser <-> Scrypted
const MAX_LIVE = 10, SETUP_MS = 30000, LIFETIME_MS = 10 * 60 * 1000;
const lives = new Map();             // session id -> { close(reason), input(message) }
function emit(session, message) { send({ event: 'live', session, message }); }

async function liveOpen(a) {
  const conn = a.connection || {}, id = String(a.id || ''), sid = String(a.session || '');
  if (!/^[A-Za-z0-9_-]{8,64}$/.test(sid)) throw new ScryptedProblem('bad live session id');
  if (lives.has(sid)) throw new ScryptedProblem('that live session is already open');
  if (lives.size >= MAX_LIVE) throw new ScryptedProblem(`too many live views are open (${MAX_LIVE})`);
  const sdk = await connect(conn);
  const found = cameraDevices(sdk, conn).find(x => x.id === id);
  if (!found) throw new ScryptedProblem('Scrypted shows this account no such camera');
  const d = found.d;
  if (!(d.interfaces || []).includes('RTCSignalingChannel') || typeof d.startRTCSignalingSession !== 'function')
    throw new ScryptedProblem('this account cannot start live video from that camera. In Scrypted, give the user the RTCSignalingChannel interface of the cameras (view only); if that is already done, this camera has no live video');
  const options = a.options && typeof a.options === 'object' ? a.options : {};
  const pending = new Map(), senders = new Map();
  let seq = 0, control = null, closed = false, setupTimer = null, lifeTimer = null;
  const close = async reason => {
    if (closed) return;
    closed = true; clearTimeout(setupTimer); clearTimeout(lifeTimer); lives.delete(sid);
    for (const w of pending.values()) w.reject(new Error(reason || 'live view closed'));
    pending.clear(); senders.clear();
    try { await control?.endSession(); } catch {}
    emit(sid, { type: 'closed', reason: reason || 'ended' });
  };
  const callBrowser = (method, args = [], sender) => new Promise((resolve, reject) => {
    if (closed) return reject(new Error('live view closed'));
    const callId = String(++seq);
    pending.set(callId, { resolve, reject });
    if (sender) senders.set(callId, sender);
    emit(sid, { type: 'call', callId, method, args, trickle: Boolean(sender) });
  });
  const session = {
    __json_disable_serialization: true, __proxy_props: { options }, options,
    getOptions: async () => options,
    createLocalDescription: (type, setup, sendIceCandidate) => callBrowser('createLocalDescription', [type, setup], sendIceCandidate),
    setRemoteDescription: (description, setup) => callBrowser('setRemoteDescription', [description, setup]),
    addIceCandidate: candidate => callBrowser('addIceCandidate', [candidate]),
  };
  lives.set(sid, {
    close,
    async input(m) {
      if (m?.type === 'result') {
        const w = pending.get(String(m.callId));
        if (!w) return;
        pending.delete(String(m.callId));
        m.error ? w.reject(new Error(String(m.error).slice(0, 200))) : w.resolve(m.value);
      } else if (m?.type === 'candidate') {
        const snd = senders.get(String(m.callId));
        if (snd) await snd(m.candidate).catch(() => {});
      }
    },
  });
  setupTimer = setTimeout(() => { emit(sid, { type: 'error', error: 'live video setup timed out' }); close('setup timed out'); }, SETUP_MS);
  (async () => {
    try {
      control = await d.startRTCSignalingSession(session);
      if (closed) { try { await control?.endSession(); } catch {} return; }
      clearTimeout(setupTimer);
      emit(sid, { type: 'ready' });
      lifeTimer = setTimeout(() => close('time limit reached'), LIFETIME_MS);
    } catch (e) {
      emit(sid, { type: 'error', error: String(e?.message || e).slice(0, 200) });
      close('setup failed');
    }
  })();
  return { started: true };
}

async function handle(req) {
  const m = req.method, a = req.params || {};
  if (m === 'hello') return { module: 'scrypted', version: VERSION };
  if (m === 'describe') return { title: 'Scrypted', text: 'Reads camera status and pictures from Scrypted, read-only', status: 'healthy' };
  if (m === 'check') return runCheck(a.check || 'server', a.params || {}, a.connection || {});
  if (m === 'cameras') { const c = a.connection || {}; const sdk = await connect(c); return { cameras: cameraDevices(sdk, c).map(describeCamera) }; }
  if (m === 'snapshot') {
    const c = a.connection || {};
    const buf = await picture(await connect(c), String(a.id || ''));
    return { mime: 'image/jpeg', data: buf.toString('base64') };
  }
  if (m === 'discover') return discover(a.connection || {});
  if (m === 'live_open') return liveOpen(a);
  if (m === 'live_input') { await lives.get(String(a.session || ''))?.input(a.message); return {}; }
  if (m === 'live_close') { await lives.get(String(a.session || ''))?.close('closed by the viewer'); return {}; }
  throw new Error(`unknown method ${m}`);
}

function send(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }

readline.createInterface({ input: process.stdin }).on('line', line => {
  let req;
  try { req = JSON.parse(line); } catch { return; }
  handle(req).then(
    result => send({ id: req.id, result }),
    e => {
      const msg = String(e?.message || e);
      send(req.method === 'check' ? { id: req.id, result: { state: 'unknown', detail: msg } } : { id: req.id, error: msg });
    });
});
