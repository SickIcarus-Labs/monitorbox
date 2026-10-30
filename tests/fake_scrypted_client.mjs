// A stand-in for @scrypted/client in tests. It follows exactly the calls the old, working MonitorBox 3 bridge made, reads its world from the
// JSON file named by MB_FAKE_SCRYPTED, and appends every call it receives to MB_FAKE_SCRYPTED_LOG, so a test can prove only reads happen.
import fs from 'node:fs';

const world = () => JSON.parse(fs.readFileSync(process.env.MB_FAKE_SCRYPTED, 'utf8'));
const log = what => fs.appendFileSync(process.env.MB_FAKE_SCRYPTED_LOG, what + '\n');

export async function connectScryptedClient({ baseUrl, pluginId, username, password }) {
  const w = world();
  log(`connect ${baseUrl} ${pluginId} tls=${process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0' ? 'unchecked' : 'checked'}`);   // what certificate checking was in force while connecting
  if (w.down) throw new Error('connect ECONNREFUSED');
  if (username !== w.username || password !== w.password) throw new Error('Request failed with status code 401');
  const device = d => ({
    name: d.name, type: d.type, interfaces: d.interfaces, nativeId: d.nativeId, online: d.online, info: d.info,
    async takePicture() {
      log(`takePicture ${d.id}`);
      if (world().devices.find(x => x.id === d.id).pictureFails) throw new Error('Permission denied: takePicture');
      return { bytes: Buffer.from(d.bytes || 'FAKE-JPEG') };
    },
    // what real Scrypted does for a live view: it asks the browser (through the session object) for a WebRTC offer, then answers it
    async startRTCSignalingSession(session) {
      log(`startRTC ${d.id}`);
      if (world().rtcFails) throw new Error('Permission denied: startRTCSignalingSession');
      const setup = { audio: { direction: 'recvonly' }, video: { direction: 'recvonly' }, configuration: { iceServers: [] } };
      const offer = await session.createLocalDescription('offer', setup, async c => log(`candidate ${c ? 'x' : 'end'}`));
      log(`offer ${offer?.type} ${String(offer?.sdp || '').length}`);
      session.setRemoteDescription({ type: 'answer', sdp: 'v=0\r\n' }, setup).then(() => log('answered'), e => log(`answer-rejected ${String(e.message).slice(0, 40)}`));
      return { endSession: async () => log(`endSession ${d.id}`) };
    },
    getVideoStream() { log('FORBIDDEN getVideoStream'); throw new Error('must not be called'); },
    setOnline() { log('FORBIDDEN set'); },
  });
  return {
    serverVersion: w.version || '0.147.0',
    systemManager: {
      getSystemState() { log('getSystemState'); return Object.fromEntries(world().devices.filter(d => !d.hidden).map(d => [d.id, {}])); },
      getDeviceById(id) { const d = world().devices.find(x => x.id === id && !x.hidden); return d ? device(d) : undefined; },   // read live, like Scrypted
    },
    mediaManager: {
      async convertMediaObjectToBuffer(obj, mime) { log(`convert ${mime}`); return obj.bytes; },
    },
    disconnect() {},
  };
}
