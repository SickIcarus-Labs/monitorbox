"""The persistent header (0.53.0): on every page once signed in, with the mark, site tabs that scroll sideways,
the bell, the version and Settings. Skipped where Playwright/Chromium is not installed."""
import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_snmp_e2e as T
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

class Header(T.SnmpE2E):
    test_monitoring_follows_a_volume_when_the_indexes_move_and_re_detect_shows_it = None
    test_the_editor_masks_the_community_and_keeps_it_on_save = None

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_header_is_on_every_page_hidden_when_signed_out_and_the_mark_goes_home(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            self.assertFalse(pg.is_visible("#hdr"), "no header on the sign-in page")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter")
            pg.wait_for_selector("#hdr .bar")
            for page in ("#/settings", "#/settings/servers", "#/settings/alerts"):
                pg.goto(f"http://127.0.0.1:{self.port}/{page}"); pg.wait_for_selector("#hdr .bar")
                self.assertTrue(pg.is_visible("#hdr .home") and pg.is_visible("#hdr button[aria-label=Settings]"), page)
            pg.wait_for_function("document.querySelector('#hdr .ver').innerText.startsWith('v')")
            pg.click("#hdr .home"); pg.wait_for_function("location.hash===''")
            pg.click("#hdr button[aria-label=Settings]"); pg.wait_for_function("location.hash==='#/settings'")
            pg.click("#hdr .ver"); pg.wait_for_function("location.hash==='#/settings/updates'")
            self.assertEqual(errs, []); b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_bell_lists_what_is_new_and_closes_on_escape_and_outside_tap(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.click("#bellbtn"); pg.wait_for_selector("#bell")
            self.assertIn("Nothing new", pg.inner_text("#bell"))
            pg.keyboard.press("Escape"); self.assertEqual(pg.locator("#bell").count(), 0)
            pg.click("#bellbtn"); pg.wait_for_selector("#bell"); pg.click("h1, main", position={"x": 5, "y": 5}, force=True)
            self.assertEqual(pg.locator("#bell").count(), 0)
            # iPad Safari sends no click for a tap on plain background, only pointer events: that alone must close it
            pg.click("#bellbtn"); pg.wait_for_selector("#bell")
            pg.evaluate("document.querySelector('#m').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
            self.assertEqual(pg.locator("#bell").count(), 0, "a tap anywhere away closes the bell")
            pg.click("#bellbtn"); pg.wait_for_selector("#bell"); pg.click("#bell h3")      # inside the bell it stays open
            self.assertEqual(pg.locator("#bell").count(), 1)
            pg.keyboard.press("Escape")
            # an item: fake a find and an update, the badge counts both and a tap goes to the right page
            pg.evaluate("hdrSites['']={ver:'',fu:[{title:'Plex'}],pend:{target:'9.9.9',what:'MonitorBox itself'}};renderHeader()")
            self.assertEqual(pg.inner_text("#hdr .badge").strip(), "2")
            pg.click("#bellbtn"); pg.click("#bell .nitem:nth-child(3)")
            pg.wait_for_function("location.hash==='#/settings/updates'")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_bell_says_an_automatic_update_happened_and_tapping_it_clears_it(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.evaluate("hdrSites['']={ver:'',fu:[],pend:null,auto:[{id:'module:widget-probe:0.4.2',text:'widget-probe updated itself from 0.4.1 to 0.4.2.'}]};hdrSig='';renderHeader()")
            self.assertEqual(pg.inner_text("#hdr .badge").strip(), "1")
            pg.click("#bellbtn"); self.assertIn("widget-probe updated itself from 0.4.1 to 0.4.2.", pg.inner_text("#bell"))
            pg.click("#bell .nitem")
            pg.wait_for_function("location.hash==='#/settings/updates'")
            self.assertEqual(pg.locator("#hdr .badge").count(), 0, "tapping the note clears it from the bell")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_update_all_sites_button_starts_the_sites_and_shows_each_ones_progress(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            self.assertEqual(pg.locator("#upsites").count(), 0, "no linked site, no button")
            pg.evaluate("""()=>{window._posted=[];window._waiting=false;let n=0;const f=window.fetch;
              window.fetch=(u,o)=>{u=String(u);
                if(u.endsWith('/api/sites')&&!(o&&o.method))return f(u,o).then(async r=>{const j=await r.json();j.sites=[{id:'tb',name:'Cabin',address:'x',link:{state:'linked'}}];return new Response(JSON.stringify(j))});
                if(u.endsWith('/api/site/tb/versions'))return Promise.resolve(new Response(JSON.stringify(window._waiting?{version:'1.0.0',app:{needsApply:true,target:'9.9.9',failed:[]},modules:{}}:{version:'1.0.0',app:{needsApply:false,failed:[]},modules:{}})));
                if(u.endsWith('/api/sites/update-all')){
                  if(o&&o.method==='POST'){window._posted.push(u);return Promise.resolve(new Response(JSON.stringify({running:true,sites:[],local:null})))}
                  n++;const st=n<2?'asking':'restarting';return Promise.resolve(new Response(JSON.stringify({running:n<2,sites:[{id:'tb',name:'Cabin',state:st,message:''}],local:{state:n<2?'waiting':'done',message:''}})))}
                return f(u,o)};
              loadSiteCfg().then(()=>route())}""")
            pg.wait_for_selector("[data-sw=app]"); pg.wait_for_timeout(500)
            self.assertEqual(pg.locator("#upsites").count(), 0, "a site is linked but no update is waiting at any site: no button")
            pg.evaluate("window._waiting=true;hdrPoll().then(()=>route())")
            pg.wait_for_selector("#upsites")
            self.assertEqual(pg.inner_text("#upsites"), "Update all sites")
            pg.click("#upsites")
            pg.wait_for_function("document.querySelector('#upsitesout').innerText.includes('Cabin: installing, restarting')", timeout=15000)
            self.assertEqual(len(pg.evaluate("window._posted")), 1, "pressed once, asked once")
            self.assertIn("This box: done", pg.inner_text("#upsitesout"))
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_update_all_sites_restarts_the_page_when_this_box_says_it_is_restarting(self):
        """Regression: this box installed its own update, went away, and the page just said it was restarting and stayed there until reloaded by hand."""
        self.restart_case("answers-restarting")

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_update_all_sites_restarts_the_page_when_this_box_stops_answering(self):
        self.restart_case("stops-answering")

    def restart_case(self, how):
        if True:
            c = self.start(); self.configure(c, [], [])
            with sync_playwright() as p:
                b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
                pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
                pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
                pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
                pg.evaluate("""how=>{window._booted=0;const ob=window.boot;window.boot=()=>{window._booted++};
                  const f=window.fetch;window._waiting=true;
                  window.fetch=(u,o)=>{u=String(u);
                    if(u.endsWith('/api/sites')&&!(o&&o.method))return f(u,o).then(async r=>{const j=await r.json();j.sites=[{id:'tb',name:'Cabin',address:'x',link:{state:'linked'}}];return new Response(JSON.stringify(j))});
                    if(u.endsWith('/api/site/tb/versions'))return Promise.resolve(new Response(JSON.stringify(window._waiting?{version:'1.0.0',app:{needsApply:true,target:'9.9.9',failed:[]},modules:{}}:{version:'1.0.0',app:{needsApply:false,failed:[]},modules:{}})));
                    if(u.endsWith('/api/sites/update-all')){
                      if(o&&o.method==='POST')return Promise.resolve(new Response(JSON.stringify({running:true,sites:[],local:null})));
                      if(how==='stops-answering')return Promise.reject(new Error('network'));
                      return Promise.resolve(new Response(JSON.stringify({running:true,sites:[{id:'tb',name:'Cabin',state:'asking',message:''}],local:{state:'restarting',message:'Installing App 9.9.9…'}})))}
                    return f(u,o)};
                  loadSiteCfg().then(()=>hdrPoll()).then(()=>route())}""", how)
                pg.wait_for_selector("#upsites")
                pg.click("#upsites")
                pg.wait_for_function("document.querySelector('#m').innerText.includes('Restarting')", timeout=15000)
                pg.wait_for_function("window._booted>=1", timeout=15000)       # and it comes back by loading the page again
                b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_check_all_sites_checks_this_box_and_every_linked_site_and_names_one_that_does_not_answer(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            self.assertEqual(pg.locator("#chkall").count(), 0, "no linked site, no button")
            pg.evaluate("""()=>{window._checks=[];const f=window.fetch;
              window.fetch=(u,o)=>{u=String(u);
                if(u.endsWith('/api/sites')&&!(o&&o.method))return f(u,o).then(async r=>{const j=await r.json();j.sites=[{id:'tb',name:'Cabin',address:'x',link:{state:'linked'}},{id:'bt',name:'Boat',address:'y',link:{state:'linked'}}];return new Response(JSON.stringify(j))});
                if(u.endsWith('/api/site/bt/check')){window._checks.push('bt');return Promise.resolve(new Response(JSON.stringify({error:'down'}),{status:502}))}
                if(u.endsWith('/api/site/tb/check')){window._checks.push('tb');return Promise.resolve(new Response(JSON.stringify({})))}
                if(u.endsWith('/api/check')){window._checks.push('here')}
                return f(u,o)};
              loadSiteCfg().then(()=>route())}""")
            pg.wait_for_selector("#chkall")
            self.assertEqual(pg.inner_text("#chkall"), "Check all sites")
            pg.click("#chkall")
            pg.wait_for_function("document.querySelector('#chk').innerText.includes('No answer from Boat')", timeout=15000)
            self.assertEqual(sorted(pg.evaluate("window._checks")), ["bt", "here", "tb"], "this box and each linked site, once each")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_four_update_buttons_share_one_row_and_each_shows_only_when_it_applies(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            pg.evaluate("""()=>{window._linked=false;window._here=false;window._there=false;const f=window.fetch;
              window.fetch=(u,o)=>{u=String(u);
                if(u.endsWith('/api/sites')&&!(o&&o.method))return f(u,o).then(async r=>{const j=await r.json();j.sites=window._linked?[{id:'tb',name:'Cabin',address:'x',link:{state:'linked'}}]:[];return new Response(JSON.stringify(j))});
                if(u.endsWith('/api/versions'))return f(u,o).then(async r=>{const j=await r.json();if(j.app&&window._here){j.app.needsApply=true;j.app.target='9.9.9';j.app.failed=[]}return new Response(JSON.stringify(j))});
                if(u.endsWith('/api/site/tb/versions'))return Promise.resolve(new Response(JSON.stringify({version:'1.0.0',app:{needsApply:!!window._there,target:'9.9.9',failed:[]},modules:{}})));
                return f(u,o)};
              window.show=async(l,h,t)=>{window._linked=l;window._here=h;window._there=t;hdrSites={};await loadSiteCfg();await hdrPoll();route();await new Promise(r=>setTimeout(r,800));
                return [...document.querySelector('#ch').closest('.row').querySelectorAll('select,button')].map(e=>e.id||(e.tagName==='BUTTON'?e.textContent.trim():'select'))}}""")
            show = lambda l, h, t: pg.evaluate(f"show({str(l).lower()},{str(h).lower()},{str(t).lower()})")
            self.assertEqual(show(False, False, False), ["ch", "Check now"], "the row always has the channel and Check now")
            r = show(False, True, False);  self.assertEqual([x for x in r if x in ("chkall", "upall", "upsites")], ["upall"], "no linked site: Update only")
            r = show(True, False, False);  self.assertEqual([x for x in r if x in ("chkall", "upall", "upsites")], ["chkall"], "a linked site, nothing to install: just the checks")
            r = show(True, False, True);   self.assertEqual([x for x in r if x in ("chkall", "upall", "upsites")], ["chkall", "upsites"], "a site has an update, this box does not")
            r = show(True, True, False);   self.assertEqual([x for x in r if x in ("chkall", "upall", "upsites")], ["chkall", "upall"], "this box has one, the sites do not")
            r = show(True, True, True);    self.assertEqual([x for x in r if x in ("chkall", "upall", "upsites")], ["chkall", "upall", "upsites"], "all four, in that order")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_update_all_sites_appears_after_check_all_sites_and_when_a_site_gets_an_update_with_no_tab_switch(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            pg.evaluate("""()=>{window._there=false;const f=window.fetch;
              window.fetch=(u,o)=>{u=String(u);
                if(u.endsWith('/api/sites')&&!(o&&o.method))return f(u,o).then(async r=>{const j=await r.json();j.sites=[{id:'tb',name:'Cabin',address:'x',link:{state:'linked'}}];return new Response(JSON.stringify(j))});
                if(u.endsWith('/api/site/tb/versions'))return Promise.resolve(new Response(JSON.stringify({version:'1.0.0',app:{needsApply:!!window._there,target:'9.9.9',failed:[]},modules:{}})));
                if(u.endsWith('/api/site/tb/check'))return Promise.resolve(new Response('{}'));
                return f(u,o)};
              window.go=async()=>{hdrSites={};await loadSiteCfg();await hdrPoll();route();await new Promise(r=>setTimeout(r,800))}}""")
            pg.evaluate("go()")
            pg.wait_for_selector("#chkall")
            self.assertEqual(pg.locator("#upsites").count(), 0, "the site has nothing waiting")
            pg.evaluate("window._there=true")                                     # the site now has an update, and the person taps Check all sites
            pg.click("#chkall")
            pg.wait_for_selector("#upsites", timeout=5000)                         # the same page, no tab switch
            pg.evaluate("window._there=false")
            pg.evaluate("hdrPoll()")
            pg.wait_for_function("document.querySelector('#upsites')===null", timeout=5000)    # and it goes again by itself when the update is gone
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_updates_page_offers_what_changed_for_the_app(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            self.assertEqual(pg.locator("[data-sw=app] details").count(), 0, "no notes, no link")
            pg.evaluate("""()=>{const f=window.fetch;window.fetch=(u,o)=>String(u).endsWith('/api/versions')?f(u,o).then(async r=>{const j=await r.json();j.app.changed=[{version:'9.2.0',changes:['The thing now works <b>better</b>.']},{version:'9.1.5',changes:['An earlier fix.']}];return new Response(JSON.stringify(j))}):f(u,o);route()}""")
            pg.wait_for_selector("[data-sw=app] details summary")
            self.assertEqual(pg.inner_text("[data-sw=app] details summary"), "What changed")
            pg.click("[data-sw=app] details summary")
            t = pg.inner_text("[data-sw=app] details")
            self.assertLess(t.index("9.2.0"), t.index("9.1.5"), "newest first")
            self.assertIn("The thing now works <b>better</b>.", t, "shown as text, never as markup")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_big_jump_shows_the_highlights_first_and_everything_on_request(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("[data-sw=app]")
            pg.evaluate("""()=>{const f=window.fetch;window.fetch=(u,o)=>String(u).endsWith('/api/versions')?f(u,o).then(async r=>{const j=await r.json();
              j.app.changed=[{version:'9.2.0',changes:['Full note for 9.2.0 <b>x</b>.']},{version:'9.1.5',changes:['Full note for 9.1.5.']}];
              j.app.highlights=[{version:'9.2.0',text:'Short note for 9.2.0.'}];return new Response(JSON.stringify(j))}):f(u,o);route()}""")
            pg.wait_for_selector("[data-sw=app] details summary")
            pg.click("[data-sw=app] details summary")
            outer = pg.locator("[data-sw=app] details").first
            self.assertIn("Highlights from 2 versions", outer.inner_text())
            self.assertIn("Short note for 9.2.0.", outer.inner_text())
            self.assertFalse(pg.locator("[data-sw=app] details details").first.evaluate("e=>e.open"), "everything stays folded until asked")
            self.assertFalse(pg.get_by_text("Full note for 9.1.5.").is_visible())
            pg.click("[data-sw=app] details details summary")
            self.assertTrue(pg.get_by_text("Full note for 9.1.5.").is_visible())
            self.assertIn("Full note for 9.2.0 <b>x</b>.", outer.inner_text(), "shown as text, never as markup")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_bell_checks_every_15_seconds_when_in_front_at_once_on_return_and_never_twice_at_a_time(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.add_init_script("window._ivs=[];const si=window.setInterval;window.setInterval=(f,ms,...a)=>{window._ivs.push(ms);return si(f,ms,...a)}")
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            self.assertIn(15000, pg.evaluate("window._ivs"))
            self.assertNotIn(60000, pg.evaluate("window._ivs"), "the old once-a-minute check is gone")
            pg.evaluate("""()=>{window._n=0;let rel;const f=window.fetch;window.fetch=(u,o)=>{if(String(u).endsWith('/api/versions')){window._n++;return new Promise(r=>{window._rel=()=>r(f(u,o))})}return f(u,o)}}""")
            pg.evaluate("hdrPoll();hdrPoll();hdrPoll()")
            self.assertEqual(pg.evaluate("window._n"), 1, "a round still waiting is not started again")
            pg.evaluate("window._rel()")
            pg.wait_for_timeout(200); pg.evaluate("window._rel&&window._rel()")           # the one extra round the repeated asks queued
            pg.wait_for_function("hdrRun===null")
            pg.evaluate("""()=>{window._n=0;window.fetch=(u,o)=>{if(String(u).endsWith('/api/versions'))window._n++;return Promise.reject(new Error('x'))};
              Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))}""")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("window._n"), 0, "hidden: nothing is asked")
            pg.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
            pg.wait_for_function("window._n>=1")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_bell_says_when_the_container_image_needs_re_pulling_and_the_updates_page_explains(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.evaluate("hdrSites['']={ver:'',img:true,fu:[],pend:null};hdrSig='';renderHeader()")
            self.assertEqual(pg.inner_text("#hdr .badge").strip(), "1")
            pg.click("#bellbtn"); self.assertIn("The container image needs updating", pg.inner_text("#bell"))
            pg.click("#bell .nitem"); pg.wait_for_function("location.hash==='#/settings/updates'")
            # the page itself: with a stale image the explanation is there, with a current one it is not
            pg.evaluate("""async()=>{const f=window.fetch;window.fetch=(u,o)=>String(u).endsWith('/api/versions')?f(u,o).then(async r=>{const j=await r.json();j.image={have:'1.0.0',wants:'1.2.0',outdated:true};j.imageVersion='1.0.7';return new Response(JSON.stringify(j))}):f(u,o);window._f=f;route()}""")
            pg.wait_for_function("document.querySelector('#m').innerText.includes('The container image needs updating.')")
            t = pg.inner_text("#m")
            self.assertIn("image 1.0.0", t); self.assertIn("· image 1.0.7 (update available) · channel", t, "the line under the page title names the image"); self.assertIn("built for 1.2.0", t); self.assertIn("Pull the new image", t); self.assertNotIn("Update the stack", t)
            pg.evaluate("window.fetch=window._f;route()")
            pg.wait_for_function("!document.querySelector('#m').innerText.includes('The container image needs updating.')&&document.querySelector('#m').innerText.includes('Updates')")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_bell_covers_all_sites_labels_them_skips_silent_ones_and_switches_site(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            ok = {"banner": {"status": "green", "headline": "ok"}, "state": "linked"}
            pg.evaluate("""(ok)=>{siCfg={name:'Here',nameDefault:'Here',sites:[{id:'tb',name:'Tidewater',link:ok},{id:'lk',name:'Lakeside',link:{state:'down'}}]};locBanner={status:'green',headline:'ok'};
              hdrSites={'':{ver:'',fu:[{title:'Plex'},{title:'Cam'}],pend:null},tb:{ver:'',fu:[],pend:{target:'9.9.9',what:'MonitorBox itself'}},lk:{ver:'',fu:[{title:'Stale'}],pend:null}};
              setSite=id=>{window._went=id};hdrSig='';renderHeader()}""", ok)
            self.assertEqual(pg.inner_text("#hdr .badge").strip(), "2", "sums across sites; the silent site adds nothing")
            pg.click("#bellbtn"); pg.wait_for_selector("#bell")
            t = pg.inner_text("#bell")
            self.assertIn("Here: 2 new things found", t); self.assertIn("Tidewater: Update 9.9.9 is ready", t)
            # the real path: what the followups answer carries must reach the bell (a version of this once dropped everything but the title)
            pg.evaluate("""async()=>{const f=window.fetch;window.fetch=(u,o)=>String(u).endsWith('/api/followups')?Promise.resolve(new Response(JSON.stringify({suggestions:[{title:'3 new things on Anchor3',on:'Anchor3',labels:['a','b','c']}]}))):f(u,o);
              const d=await hdrOne('');hdrSites['']=d;hdrSig='';renderHeader();window.fetch=f}""")
            pg.keyboard.press("Escape"); pg.click("#bellbtn"); pg.wait_for_selector("#bell"); t = pg.inner_text("#bell")
            self.assertIn("Here: 3 new things found", t, "counts the things, not the offers"); self.assertIn("On Anchor3", t, "says where they were found")
            self.assertNotIn("Stale", t); self.assertNotIn("Lakeside", t)
            pg.click("#bell .nitem:nth-child(3)")
            pg.wait_for_function("location.hash==='#/settings/updates'")
            self.assertEqual(pg.evaluate("window._went"), "tb", "tapping an item goes to that site first")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_time_zone_defaults_to_the_device_once_and_can_be_changed(self):
        c = self.start(); self.configure(c, [], [])
        import time as _t; old = os.environ.get("TZ")
        def restore():
            os.environ.pop("TZ", None) if old is None else os.environ.__setitem__("TZ", old); _t.tzset()
        self.addCleanup(restore)
        with sync_playwright() as p:
            b = p.chromium.launch(); ctx = b.new_context(timezone_id="America/Chicago", viewport={"width": 1000, "height": 800}); pg = ctx.new_page()
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/box"); pg.wait_for_selector("#tz-sel")
            pg.wait_for_function("document.querySelector('#tz-msg').textContent.includes('device')")
            self.assertEqual(pg.input_value("#tz-sel"), "America/Chicago")
            self.assertEqual(c.get("/api/timezone"), {"timezone": "America/Chicago"})
            pg.select_option("#tz-sel", "Europe/London"); pg.click("button:has-text('Save'):near(#tz-sel)")
            pg.wait_for_function("document.querySelector('#tz-msg').textContent.startsWith('Saved')")
            self.assertEqual(c.get("/api/timezone"), {"timezone": "Europe/London"})
            pg.reload(); pg.wait_for_selector("#tz-sel"); pg.wait_for_function("document.querySelector('#tz-sel').value==='Europe/London'")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_bar_filter_ticks_are_saved_and_come_back(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/history"); pg.wait_for_selector("#bs-row input")
            pg.wait_for_function("[...document.querySelectorAll('#bs-row input')].every(i=>i.checked)")
            pg.uncheck("#bs-row input[data-bs=unknown]"); pg.uncheck("#bs-row input[data-bs=degraded]")
            pg.wait_for_function("document.querySelector('#bs-msg').textContent.startsWith('Saved')")
            self.assertEqual(c.get("/api/barshow"), {"show": ["failed"]})
            pg.reload(); pg.wait_for_selector("#bs-row input")
            pg.wait_for_function("document.querySelector('#bs-row input[data-bs=failed]').checked&&!document.querySelector('#bs-row input[data-bs=unknown]').checked")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_history_page_ranges_filters_custom_dates_and_clear(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/history"); pg.wait_for_selector("#hp-list")
            pg.wait_for_function("!document.querySelector('#hp-list').innerText.includes('Loading')")
            pg.click("#hp-range button[data-d='30']"); pg.wait_for_function("document.querySelector('#hp-range button[data-d=\"30\"]').getAttribute('aria-pressed')==='true'")
            pg.fill("#hp-from", "2020-01-01"); pg.fill("#hp-to", "2020-01-02"); pg.click("button:has-text('Show')")
            pg.wait_for_function("document.querySelector('#hp-list').innerText.includes('Nothing in that range')")
            pg.fill("#hp-from", "2020-02-01"); pg.click("button:has-text('Show')")
            pg.wait_for_function("document.querySelector('#hp-list').innerText.includes('before the start')")
            for st in ("failed", "degraded", "unknown"):
                pg.uncheck(f"#hp-st input[data-st={st}]")
            pg.wait_for_function("document.querySelector('#hp-list').innerText.includes('Tick at least one')")
            pg.click("button:has-text('Clear history')"); pg.wait_for_selector("#ask-ok"); pg.click("#ask-ok")
            pg.wait_for_function("document.querySelector('#msg').textContent==='History cleared.'")
            self.assertEqual(errs, []); b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_updates_page_opens_at_once_and_the_slow_look_at_the_update_server_follows(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            held = []
            pg.route("**/api/check", lambda route: held.append(route))          # the update server "has not answered yet"
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/updates"); pg.wait_for_selector("h1:has-text('Updates and versions')")
            pg.wait_for_selector(".box"); pg.wait_for_function("window.__x=1")
            for _ in range(40):
                if held: break
                time.sleep(0.1)
            self.assertEqual(len(held), 1, "it asked the update server, after showing the page")
            self.assertTrue(pg.is_visible("h1:has-text('Updates and versions')"), "the page is up while the update server has not answered")
            held[0].continue_()
            time.sleep(1.5)
            self.assertEqual(len(held), 1, "the answer refreshed the page once, not in a loop")
            self.assertTrue(pg.is_visible("h1:has-text('Updates and versions')"))
            self.assertEqual(errs, []); b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_the_history_page_hides_brief_blips_unless_ticked(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            asked = []; pg.on("request", lambda r: asked.append(r.url) if "history?events=1" in r.url else None)
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/history"); pg.wait_for_selector("#hp-brief")
            pg.wait_for_function("!document.querySelector('#hp-list').innerText.includes('Loading')")
            self.assertFalse(pg.is_checked("#hp-brief"), "brief blips are off by default")
            self.assertTrue(asked and all("brief=1" not in u for u in asked))
            asked.clear(); pg.click("#hp-brief")
            pg.wait_for_function("!document.querySelector('#hp-list').innerText.includes('Loading')")
            self.assertTrue(asked and all("brief=1" in u for u in asked), "ticked: the list is asked to include them")
            self.assertEqual(errs, []); b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_this_box_measures_the_site_and_shows_timings_and_memory_with_a_copy_button(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            pg.goto(f"http://127.0.0.1:{self.port}/#/settings/advanced"); pg.wait_for_selector("text=Measure this site")
            self.assertFalse(pg.is_visible("#perfcopy"))
            pg.click("text=Measure this site"); pg.wait_for_selector("#perfout >> text=Memory (MB, fair share)", timeout=30000)
            txt = pg.inner_text("#perfout")
            for want in ("reach this box", "status", "GET /api/state", "app"):
                self.assertIn(want, txt)
            self.assertTrue(pg.is_visible("#perfcopy"))
            self.assertIn("MonitorBox performance", pg.evaluate("PERFTXT"))
            self.assertRegex(pg.evaluate("PERFTXT"), r"Memory MB: .*\bapp \d")     # listed by size, so the app is not always first (a heavier helper can top it)
            self.assertEqual(errs, []); b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_settings_opens_without_asking_the_update_server_and_moving_between_pages_reuses_what_it_has(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#bellbtn")
            seen = []; pg.on("request", lambda r: seen.append((r.method, r.url.split("/api/")[-1].split("?")[0]) if "/api/" in r.url else None))
            pg.click("#hdr button[aria-label=Settings]"); pg.wait_for_selector(".hub")
            first = [x for x in seen if x]
            self.assertNotIn(("POST", "check"), first, "the hub does not make the box look at the update server")
            self.assertEqual(sorted(x[1] for x in first if x[1] in ("state", "versions", "config/monitoring", "config/connections", "about", "backups", "alerts", "sites")),
                             sorted(["state", "versions", "config/monitoring", "config/connections", "about", "backups", "alerts", "sites"]), "each asked for once, all at once")
            seen.clear()
            pg.click(".hub:has(b:text-is('Backups'))"); pg.wait_for_selector("h1:has-text('Backups')"); pg.click("text=← Settings"); pg.wait_for_selector(".hub")
            again = [x for x in seen if x and x[1] in ("state", "versions", "config/monitoring", "config/connections", "about", "backups")]
            self.assertEqual(again, [], "moving between settings pages does not ask for it all again")
            seen.clear()
            pg.click(".hub:has(b:text-is('Updates and versions'))"); pg.wait_for_selector("h1:has-text('Updates and versions')")
            self.assertIn(("POST", "check"), [x for x in seen if x], "the Updates page does look at the update server")
            seen.clear()
            pg.click("text=← Settings"); pg.wait_for_selector(".hub"); pg.click(".hub:has(b:text-is('Backups'))"); pg.wait_for_selector("text=Back up settings now")
            pg.click("text=Back up settings now"); pg.wait_for_function("document.querySelectorAll('.bk, .box').length>0")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_site_tabs_scroll_sideways_when_they_do_not_fit(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 390, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#hdr .bar")
            pg.evaluate("""siteTabs=()=>['Bay Harbor','Tidewater','Lakeside cabin','Harbour office','Storage unit'].map((n,i)=>({id:'s'+i,name:n,st:'green',head:'ok'}));hdrSig='';renderHeader()""")
            pg.wait_for_selector("#hdr nav.tabs .tab")
            self.assertTrue(pg.evaluate("(()=>{const n=document.querySelector('#hdr nav.tabs');return n.scrollWidth>n.clientWidth&&getComputedStyle(n).overflowX==='auto'})()"))
            self.assertFalse(pg.evaluate("document.documentElement.scrollWidth>innerWidth"), "the page itself must not scroll sideways")
            pg.evaluate("document.querySelector('#hdr nav.tabs').scrollLeft=120;hdrSig='x';renderHeader()")
            self.assertGreaterEqual(pg.evaluate("document.querySelector('#hdr nav.tabs').scrollLeft"), 100, "a redraw keeps the swipe position")
            self.assertFalse(pg.is_visible("#hdr .ver"), "the version moves to the footer on a phone")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_this_boxs_tab_dot_has_its_colour_at_once_and_on_pages_with_no_live_stream(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector("#hdr .bar")
            pg.evaluate("siCfg={name:'Here',nameDefault:'Here',sites:[{id:'x',name:'Other',link:{}}]};locBanner=null;closeStream();hdrSig='';renderHeader()")
            self.assertEqual(pg.get_attribute("#hdr .tab:first-child", "title"), "checking…")
            pg.evaluate("(()=>{const o=api;api=(p,b)=>p==='sites'?Promise.resolve(siCfg):o(p,b);refreshSites()})()")                                 # settings pages have no stream: the tab still gets its colour
            pg.wait_for_function("document.querySelector('#hdr .tab').title!=='checking…'", timeout=4000)
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_beacon_look_fonts_come_from_the_box_and_the_headline_and_cards_are_styled(self):
        import urllib.request
        c = self.start(); self.configure(c, [], [])
        for f in ("sora", "figtree"):                                      # served by the box itself, before sign-in, never from a font host
            r = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/brand/{f}.ttf")
            self.assertEqual((r.status, r.headers["Content-Type"]), (200, "font/ttf")); self.assertGreater(len(r.read()), 50000)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 800})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            c.post("/api/demo", {"scenario": "headsup"}); pg.wait_for_selector("#m .card .cico")
            self.assertTrue(pg.evaluate("document.fonts.check('700 20px Sora') && document.fonts.check('16px Figtree')"))
            self.assertEqual(pg.inner_text(".head em").strip().rstrip("."), pg.inner_text(".head").split()[-1].rstrip("."), "the last word is the accented one")
            self.assertNotEqual(pg.evaluate("getComputedStyle(document.querySelector('.head em')).color"), pg.evaluate("getComputedStyle(document.querySelector('.head')).color"))
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_stat_tiles_and_each_card_gets_its_24_hour_bar(self):
        c = self.start(); self.configure(c, [], [])
        r = c.get("/api/history?strip=nobody,nothing")
        self.assertEqual((len(r["buckets"]), r["hours"]), (24, 24)); self.assertEqual(set(r["buckets"]), {None})
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            c.post("/api/demo", {"scenario": "yellow"}); pg.wait_for_selector("#m .card .strip", state="attached")
            self.assertEqual(pg.locator(".tile").count(), 3)
            self.assertIn("needs attention", pg.inner_text(".tiles")); self.assertIn("healthy", pg.inner_text(".tiles"))
            pg.evaluate("snap.cards.forEach(c=>{strips[sk(c)]={at:Date.now()+1e9,d:{buckets:Array.from({length:24},(_,k)=>k==5?'failed':'healthy')}}});lastJson='';render()")
            self.assertEqual(pg.locator(".card .strip").first.locator("i").count(), 24)
            self.assertGreaterEqual(pg.locator(".card .strip i.failed").count(), 1)
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_a_card_bar_that_failed_to_load_comes_back_within_seconds_and_a_drawn_bar_is_never_lost_to_a_failure(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            c.post("/api/demo", {"scenario": "yellow"}); pg.wait_for_selector("#m .card .strip", state="attached")
            pg.evaluate("""()=>{window._fail=true;const o=api;api=(p,b)=>p.startsWith('history?strip')?(window._fail?Promise.reject(new Error('dropped')):Promise.resolve({buckets:Array.from({length:24},(_,k)=>k==5?'failed':'healthy')})):o(p,b);
              for(const k in strips)delete strips[k];lastJson='';render()}""")
            pg.wait_for_timeout(500)
            self.assertEqual(pg.locator(".card .strip i").count(), 0, "the request was dropped: no bar yet")
            pg.evaluate("window._fail=false")
            pg.wait_for_function("document.querySelectorAll('.card .strip i').length>=24", timeout=15000)       # asked again by itself, no refresh
            n = pg.locator(".card .strip i").count()
            pg.evaluate("window._fail=true;for(const k in strips)strips[k].at=0;loadStrips()")                    # a later request fails: what is drawn stays
            pg.wait_for_timeout(500)
            self.assertEqual(pg.locator(".card .strip i").count(), n)
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_temperatures_and_drives_fold_under_one_line_each_once_there_are_three(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            got = pg.evaluate("""()=>{const mk=(id,target)=>({id,name:id,group:'Network',state:'healthy',checks:[{type:'unifi-network',target}]});
              const mp=(id)=>({id,name:id,group:'Cameras',state:'healthy',checks:[{type:'unifi-protect',target:'drive'}]});
              const o=snap;snap={cards:[],nodes:{a:mk('a','temperature'),b:mk('b','temperature'),c:mk('c','temperature'),d:mk('d','device'),e:mp('e'),f:mp('f')}};
              const r=cardRows({nodes:['a','b','c','d','e','f']});snap=o;
              return {sections:r.sections.map(s=>[s.name,s.unit,s.nodes.length]),loose:r.loose.map(n=>n.id)}}""")
            self.assertEqual(got["sections"], [["UniFi temperatures", "temperatures", 3]], "three temperatures fold into one line")
            self.assertEqual(sorted(got["loose"]), ["d", "e", "f"], "a device check and two drives (fewer than three) stay as their own lines")
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_edit_monitoring_has_a_warning_limit_for_temperature_checks_only(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            pg.evaluate("""()=>{window._calls=[];const mk=(id,check,params)=>({id,name:id,group:'g',checks:[{type:'module',check,params}]});
              const mon={confirm:{},nodes:[mk('drv','drive',{slot:1,max_c:50}),mk('tmp','temperature',{name:'A'}),mk('dev','device',{name:'A'})]};
              const o=api;api=(p,b)=>p==='config/monitoring'?Promise.resolve({monitoring:mon,revision:1}):(p==='confirm'||p==='limit')?(window._calls.push([p,b]),Promise.resolve({})):o(p,b)}""")
            pg.evaluate("editMonitoring('dev')"); pg.wait_for_selector("#medit")
            self.assertEqual(pg.locator("#me-t").count(), 0, "a plain device check has no temperature limit")
            pg.click("#me-no")
            pg.evaluate("editMonitoring('tmp')"); pg.wait_for_selector("#me-t")
            self.assertEqual(pg.get_attribute("#me-t", "placeholder"), "80", "a device temperature uses 80 unless set")
            pg.click("#me-no")
            pg.evaluate("editMonitoring('drv')"); pg.wait_for_selector("#me-t")
            self.assertEqual((pg.get_attribute("#me-t", "placeholder"), pg.input_value("#me-t")), ("55", "50"), "a drive uses 55 unless set; its own limit is shown")
            pg.fill("#me-t", "58"); pg.click("#me-ok"); pg.wait_for_selector("#medit", state="detached")
            self.assertIn(["limit", {"id": "drv", "max_c": 58}], pg.evaluate("window._calls"))
            b.close()

    def test_the_limit_route_refuses_nonsense_and_an_unknown_item(self):
        c = self.start(); self.configure(c, [], [])
        for body in ({"id": "nope", "max_c": 70}, {"id": "", "max_c": 70}, {"id": "nope", "max_c": 5}):
            self.assertEqual(c.post("/api/limit", body).get("_status"), 400, body)

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_tapping_a_bar_slice_says_what_was_not_healthy_in_that_hour(self):
        c = self.start(); self.configure(c, [], [])
        r = c.get("/api/history?trouble=nobody&from=0&to=3600")
        self.assertEqual((r["items"], r["more"]), ([], 0))
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            c.post("/api/demo", {"scenario": "yellow"}); pg.wait_for_selector("#m .card .strip", state="attached")
            pg.evaluate("""(()=>{const o=api;api=(p,b)=>p.startsWith('history?trouble')?Promise.resolve({items:[{node:Object.keys(snap.nodes)[0],state:'failed',why:'distinct reason 51',from:Date.now()/1000-600,to:Date.now()/1000-120}],more:0}):o(p,b);
              const now=Math.floor(Date.now()/1000);snap.cards.forEach(c=>{strips[sk(c)]={at:Date.now()+1e9,d:{since:now-86400,now,hours:24,buckets:Array.from({length:24},(_,k)=>k==5?'failed':'healthy')}}});lastJson='';render()})()""")
            pg.click(".card .strip >> nth=0", position={"x": 5, "y": 8})
            pg.wait_for_selector("#tsheet .tr")
            self.assertIn("Down", pg.inner_text("#tsheet")); self.assertIn("distinct reason 51", pg.inner_text("#tsheet"), "each line says why, when it was recorded")
            self.assertIn("what the check reported", pg.inner_text("#tsheet"))      # the old note said MonitorBox records "when, not why"; it now records both
            pg.evaluate("document.querySelector('#m').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
            self.assertEqual(pg.locator("#tsheet").count(), 0, "a tap away closes it")
            pg.click(".card .strip >> nth=0"); pg.wait_for_selector("#tsheet"); pg.keyboard.press("Escape")
            self.assertEqual(pg.locator("#tsheet").count(), 0)
            b.close()

    @unittest.skipIf(sync_playwright is None, "playwright not installed")
    def test_two_sites_with_the_same_card_name_never_share_a_bar_and_no_browser_pop_ups(self):
        c = self.start(); self.configure(c, [], [])
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1000, "height": 900})
            dialogs = []; pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
            pg.goto(f"http://127.0.0.1:{self.port}/"); pg.wait_for_selector("input[type=password]")
            pg.fill("input[type=password]", T.PASSWORD); pg.keyboard.press("Enter"); pg.wait_for_selector(".head em")
            c.post("/api/demo", {"scenario": "yellow"}); pg.wait_for_selector("#m .card .strip", state="attached")
            self.assertEqual(pg.evaluate("""(()=>{const c=snap.cards[0],now=Math.floor(Date.now()/1000);
                strips[sk(c)]={at:Date.now()+1e9,d:{since:now-86400,now,hours:24,buckets:Array(24).fill('failed')}};
                const here=stripHtml(c);SITE='other-site';const there=stripHtml(c);SITE='';return [here.includes('failed'),there]})()"""), [True, ""])
            # a question that used to be a browser confirm() is now in the page (iPad Safari suppresses the pop-up)
            self.assertEqual(pg.evaluate("(()=>{window._r=null;askYes('Sure?').then(v=>window._r=v);return !!document.querySelector('#ask-ok')})()"), True)
            pg.click("#ask-ok"); pg.wait_for_function("window._r===true")
            pg.evaluate("window._r=null;alert('Something failed').then(()=>window._r='closed');0"); pg.click("#ask-ok"); pg.wait_for_function("window._r==='closed'")
            self.assertEqual(dialogs, [])
            b.close()

if __name__ == "__main__":
    unittest.main()
