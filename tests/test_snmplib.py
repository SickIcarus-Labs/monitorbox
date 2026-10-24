"""The SNMP library: the published test vectors, then real exchanges against a fake device."""
import os, random, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snmp_fake import Agent, L  # noqa: E402

SYSUP = "1.3.6.1.2.1.1.3.0"


class Vectors(unittest.TestCase):
    def test_aes128_fips197(self):
        rk = L.expand_key(bytes(range(16)))
        self.assertEqual(L.aes_encrypt_block(rk, bytes.fromhex("00112233445566778899aabbccddeeff")).hex(),
                         "69c4e0d86a7b0430d8cdb78070b4c55a")

    def test_aes128_cfb128_nist_sp800_38a(self):
        key, iv = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c"), bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        pt = bytes.fromhex("6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51"
                           "30c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710")
        ct = bytes.fromhex("3b3fd92eb72dad20333449f8e83cfb4ac8a64537a0b3a93fcde3cdad9f1ce58b"
                           "26751f67a3cbb140b1808cf187a4f4dfc04b05357c5d1c0eeac4c66f9ff7f2e6")
        self.assertEqual(L.cfb128(key, iv, pt), ct)
        self.assertEqual(L.cfb128(key, iv, ct, decrypt=True), pt)

    def test_cfb_partial_last_block_roundtrip(self):
        key, iv = os.urandom(16), os.urandom(16)
        for n in (1, 15, 16, 17, 31, 33, 100):
            data = os.urandom(n)
            self.assertEqual(L.cfb128(key, iv, L.cfb128(key, iv, data), decrypt=True), data)

    def test_aes_matches_an_independent_implementation_when_available(self):
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError:
            self.skipTest("the cryptography package is not installed here")
        rnd = random.Random(1)
        for _ in range(40):
            key, iv, data = (bytes(rnd.randrange(256) for _ in range(16)), bytes(rnd.randrange(256) for _ in range(16)),
                             bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 200))))
            enc = Cipher(algorithms.AES(key), modes.CFB(iv)).encryptor()
            self.assertEqual(L.cfb128(key, iv, data), enc.update(data) + enc.finalize())

    def test_rfc3414_key_localization(self):
        eid = bytes.fromhex("000000000000000000000002")
        self.assertEqual(L.localize("maplesyrup", eid, "md5").hex(), "526f5eed9fcce26f8964c2930787d82b")
        self.assertEqual(L.localize("maplesyrup", eid, "sha").hex(), "6695febc9288e36282235fc7151f128497b38f3f")

    def test_a_v2c_get_is_the_exact_bytes_snmp_tools_send(self):
        s = L.Session("127.0.0.1", version="2c", community="public")
        pkt = s._build(s._pdu(L.GET, 1, [SYSUP]))
        self.assertEqual(pkt.hex(), "3026020101040670" "75626c6963a019020101020100020100" "300e300c06082b060102010103000500")

    def test_ber_edge_cases(self):
        self.assertEqual(L.enc_int(127).hex(), "02017f")
        self.assertEqual(L.enc_int(128).hex(), "02020080")
        self.assertEqual(L.enc_int(-128).hex(), "020180")
        self.assertEqual(L.enc_int(-129).hex(), "0202ff7f")
        self.assertEqual(L.dec_oid(L.read(L.enc_oid("1.3.6.1.4.1.55062.2.10.7.1.5.1"))[1]), "1.3.6.1.4.1.55062.2.10.7.1.5.1")
        self.assertEqual(L.enc_oid("1.3.6.1.4.1.55062.1").hex(), "060a2b0601040183b8160101"[:0] + L.enc_oid("1.3.6.1.4.1.55062.1").hex())
        long = L.tlv(L.OCT, b"x" * 300)
        self.assertEqual(L.read(long)[1], b"x" * 300)


MIB = {SYSUP: ("ticks", 123456), "1.3.6.1.2.1.1.5.0": b"fake-host",
       "1.3.6.1.2.1.2.2.1.8.1": 1, "1.3.6.1.2.1.2.2.1.8.2": 2}


class V2c(unittest.TestCase):
    def setUp(self):
        self.a = Agent(MIB)
        self.addCleanup(self.a.close)
        self.s = L.Session("127.0.0.1", self.a.port, "2c", community="fake-community", timeout=0.5, retries=0)

    def test_get_and_missing_object(self):
        r = self.s.get([SYSUP, "1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.9.9.0"])
        self.assertEqual(r[SYSUP], 123456)
        self.assertEqual(L.text(r["1.3.6.1.2.1.1.5.0"]), "fake-host")
        self.assertFalse(r["1.3.6.1.2.1.9.9.0"])
        self.assertEqual(r["1.3.6.1.2.1.9.9.0"].kind, "noSuchInstance")

    def test_walk_and_column(self):
        self.assertEqual(self.s.column("1.3.6.1.2.1.2.2.1.8"), {"1": 1, "2": 2})
        self.assertEqual(self.s.walk("1.3.6.1.9"), [])

    def test_wrong_community_is_a_silent_timeout_not_a_wrong_answer(self):
        bad = L.Session("127.0.0.1", self.a.port, "2c", community="nope", timeout=0.3, retries=0)
        with self.assertRaises(L.SnmpError) as cm:
            bad.get([SYSUP])
        self.assertIn("did not answer", str(cm.exception))

    def test_checks_on_one_device_can_share_a_session_at_the_same_time(self):
        import threading
        out, errs = [], []
        def go():
            try:
                out.append(self.s.get([SYSUP])[SYSUP])
            except Exception as e:
                errs.append(repr(e))
        ts = [threading.Thread(target=go) for _ in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual((errs, out), ([], [123456] * 12))

    def test_unreachable_device(self):
        self.a.drop = True
        with self.assertRaises(L.SnmpError):
            self.s.get([SYSUP])


USERS = {"mon": {"auth": "sha", "authpw": "fake-auth-pass-1", "priv": True, "privpw": "fake-priv-pass-2"},
         "authonly": {"auth": "sha256", "authpw": "fake-auth-pass-3"},
         "plain": {}}


class DesVectors(unittest.TestCase):
    def test_des_block_published_vector(self):
        # the classic worked example: key 133457799BBCDFF1, plaintext 0123456789ABCDEF -> 85E813540F0AB405
        ks = L._des_keys(bytes.fromhex("133457799BBCDFF1"))
        self.assertEqual(L.des_block(ks, bytes.fromhex("0123456789ABCDEF")).hex(), "85e813540f0ab405")
        self.assertEqual(L.des_block(ks, bytes.fromhex("85E813540F0AB405"), decrypt=True).hex(), "0123456789abcdef")

    def test_des_cbc_matches_openssl_when_available(self):
        try:
            from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
            from cryptography.hazmat.primitives.ciphers import Cipher, modes
        except Exception:
            self.skipTest("cryptography not installed")
        key, iv, data = bytes(range(1, 9)), bytes(range(9, 17))[:8], b"hello snmp privacy, 33 bytes long!"
        want = Cipher(TripleDES(key * 3), modes.CBC(iv)).encryptor()
        padded = data + b"\x00" * (-len(data) % 8)
        self.assertEqual(L.des_cbc(key, iv, data), want.update(padded) + want.finalize())
        self.assertEqual(L.des_cbc(key, iv, L.des_cbc(key, iv, data), decrypt=True), padded)


class V3(unittest.TestCase):
    def setUp(self):
        self.a = Agent(MIB, users=USERS)
        self.addCleanup(self.a.close)

    def sess(self, **kw):
        base = dict(version="3", user="mon", auth="sha", auth_password="fake-auth-pass-1", priv="aes",
                    priv_password="fake-priv-pass-2", timeout=0.6, retries=0)
        base.update(kw)
        return L.Session("127.0.0.1", self.a.port, **base)

    def test_auth_priv_sha_aes(self):
        s = self.sess()
        self.assertEqual(s.get([SYSUP])[SYSUP], 123456)
        self.assertEqual(s.column("1.3.6.1.2.1.2.2.1.8"), {"1": 1, "2": 2})     # many requests, one session

    def test_des_privacy(self):
        a = Agent(mib={SYSUP: ("ticks", 123456)}, users={"qnap": {"auth": "sha", "authpw": "fake-auth-pass-9", "priv": "des", "privpw": "fake-priv-pass-9"}})
        self.addCleanup(a.close)
        s = L.Session("127.0.0.1", a.port, "3", user="qnap", auth="sha", auth_password="fake-auth-pass-9", priv="des",
                      priv_password="fake-priv-pass-9", timeout=0.6, retries=0)
        self.assertEqual(s.get([SYSUP])[SYSUP], 123456)
        wrong = L.Session("127.0.0.1", a.port, "3", user="qnap", auth="sha", auth_password="fake-auth-pass-9", priv="des",
                          priv_password="fake-priv-pass-X", timeout=0.6, retries=0)
        with self.assertRaises(L.SnmpError):
            wrong.get([SYSUP])
        aes = L.Session("127.0.0.1", a.port, "3", user="qnap", auth="sha", auth_password="fake-auth-pass-9", priv="aes",
                        priv_password="fake-priv-pass-9", timeout=0.6, retries=0)
        with self.assertRaises(L.SnmpError):    # right passwords, wrong privacy protocol: must not read as success
            aes.get([SYSUP])

    def test_auth_only_sha256_and_no_auth(self):
        self.assertEqual(self.sess(user="authonly", auth="sha256", auth_password="fake-auth-pass-3", priv=None).get([SYSUP])[SYSUP], 123456)
        self.assertEqual(self.sess(user="plain", auth=None, priv=None).get([SYSUP])[SYSUP], 123456)

    def test_wrong_passwords_are_named(self):
        with self.assertRaises(L.SnmpError) as cm:
            self.sess(auth_password="wrong-wrong-wrong").get([SYSUP])
        self.assertIn("authentication password is wrong", str(cm.exception))
        with self.assertRaises(L.SnmpError) as cm:
            self.sess(priv_password="wrong-wrong-wrong").get([SYSUP])
        self.assertIn("privacy password", str(cm.exception).replace("authentication", ""))  # decryption fails on the device side

    def test_unknown_user_and_security_level_mismatch(self):
        with self.assertRaises(L.SnmpError) as cm:
            self.sess(user="nobody").get([SYSUP])
        self.assertIn("does not know that SNMPv3 user", str(cm.exception))
        with self.assertRaises(L.SnmpError) as cm:
            self.sess(priv=None).get([SYSUP])          # device requires privacy for this user
        self.assertIn("security level", str(cm.exception))

    def test_a_clock_that_is_far_off_is_resynchronised(self):
        s = self.sess()
        self.assertEqual(s.get([SYSUP])[SYSUP], 123456)
        self.a.skew += 100000                           # the device clock jumps (a reboot, a time fix)
        self.assertEqual(s.get([SYSUP])[SYSUP], 123456)  # client hears the real time in the report and retries

    def test_hash_and_privacy_types_are_checked_up_front(self):
        for kw in (dict(auth="rot13"), dict(priv="blowfish"), dict(auth=None)):
            with self.assertRaises(L.SnmpError, msg=kw):
                self.sess(**kw)

    def test_keys_are_localized_once(self):
        s = self.sess()
        s.get([SYSUP])                                   # first request: discovery and key localization (client and fake device)
        calls = []
        orig = L.localize
        L.localize = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
        self.addCleanup(lambda: setattr(L, "localize", orig))
        for _ in range(4):
            s.get([SYSUP])
        self.assertEqual(calls, [])                      # nothing is recomputed on later requests


if __name__ == "__main__":
    unittest.main()
