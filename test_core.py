import unittest, urllib.error
import indicators as ind, strategies as st, risk, state, coinbase as cb, telegram as tg

CFG = {"quote_max_age_sec":120,"max_spread_pct":0.65,"max_chase_pct":0.75,"stop_min_pct":1.0,"stop_max_pct":5.0,
       "target_r_multiple":2.5,"min_net_rr":1.25,"round_trip_cost_pct":0.8,"position_size":50}
def mk(closes, vols=None, step=900, spread=0.3):
    out=[]
    for i,c in enumerate(closes):
        out.append({"t":i*step,"o":c-0.1,"h":c+spread,"l":c-spread,"c":c,"v":(vols or [100]*len(closes))[i]})
    return out
def trend(n=60): return [100+i*0.5 for i in range(n)]
CONF = {"confirmed":True,"met":4,"total":4,"conditions":{"x":True},"close":100.0,"swing_low":98.0,"strategy":"A"}
QUOTE = {"bid":99.95,"ask":100.05,"time":1000}
PROD = {"quote_min_size":"1","base_min_size":"0.001"}

class T(unittest.TestCase):
    def test_rsi_all_up_is_100(self): self.assertEqual(ind.rsi([1+i for i in range(30)])[-1], 100.0)
    def test_incomplete_candle_dropped(self):
        cs=[{"t":0,"c":1},{"t":300,"c":1}]; self.assertEqual(len(st.completed(cs,300,500)),1)
    def test_strategy_a_confirms_on_volume_breakout(self):
        closes=[100+i*0.2+(0.8 if i%2 else -0.8) for i in range(60)]; vols=[100]*59+[300]; closes[-1]+=2.5
        r=st.strategy_a(mk(closes,vols)); self.assertTrue(r["confirmed"], r["conditions"])
    def test_strategy_a_not_confirmed_low_volume(self):
        r=st.strategy_a(mk(trend())); self.assertFalse(r["confirmed"])
    def test_good_plan_confirmed(self):
        p=risk.build_plan(CONF,QUOTE,PROD,CFG,1010); self.assertEqual(p["status"],"CONFIRMED",p["reasons"])
        self.assertAlmostEqual(p["risk_pct"],2.0,1); self.assertGreater(p["net_rr"],1.25)
    def test_stale_quote_blocked(self):
        p=risk.build_plan(CONF,QUOTE,PROD,CFG,1500); self.assertEqual(p["status"],"BLOCKED"); self.assertIn("stale",p["reasons"][0])
    def test_wide_spread_blocked(self):
        p=risk.build_plan(CONF,{"bid":99,"ask":100.5,"time":1000},PROD,CFG,1010); self.assertTrue(any("Spread" in r for r in p["reasons"]))
    def test_tight_stop_fails_net_rr(self):
        c=dict(CONF,swing_low=99.9); p=risk.build_plan(c,QUOTE,PROD,CFG,1010)
        self.assertTrue(any("Net reward/risk" in r for r in p["reasons"]))
    def test_below_min_order_blocked(self):
        p=risk.build_plan(CONF,QUOTE,{"quote_min_size":"100","base_min_size":"0"},CFG,1010); self.assertEqual(p["status"],"BLOCKED")
    def test_unconfirmed_is_never_confirmed(self):
        p=risk.build_plan(dict(CONF,confirmed=False,met=3,conditions={"x":False}),QUOTE,PROD,CFG,1010); self.assertEqual(p["status"],"WATCH")
    def test_dedupe_same_candle_and_cooldown(self):
        s={}; self.assertTrue(state.should_alert(s,"BTC-USD","A",100,1000,90))
        s=state.record(s,"BTC-USD","A",100,1000)
        self.assertFalse(state.should_alert(s,"BTC-USD","A",100,1000+9999,90))   # same candle
        self.assertFalse(state.should_alert(s,"BTC-USD","A",200,1000+600,90))    # inside cooldown
        self.assertTrue(state.should_alert(s,"BTC-USD","A",200,1000+6000,90))    # after cooldown
    def test_api_failure_retries_then_raises(self):
        calls=[]
        def bad(*a,**k): calls.append(1); raise urllib.error.URLError("down")
        with self.assertRaises(cb.ApiError): cb.get_json("/x",retries=3,backoff=0,opener=bad)
        self.assertEqual(len(calls),3)
    def test_telegram_without_secrets_does_not_crash(self):
        import os; os.environ.pop("TELEGRAM_BOT_TOKEN",None); self.assertFalse(tg.send("hi")[0])
class TP(unittest.TestCase):
    def test_small_prices_not_scientific(self):
        self.assertEqual(tg.fp(0.00000501),"0.000005010"); self.assertNotIn("e",tg.fp(0.0000000123))
        self.assertEqual(tg.fp(76649.62),"76,649.62")
class OneAlert(unittest.TestCase):
    def test_best_setup_chosen_and_extras_listed(self):
        import scan
        a=({"strategy":"A"},{"net_rr":1.9},900); b=({"strategy":"B"},{"net_rr":1.7},300)
        self.assertEqual(scan.choose([b,a])[0]["strategy"],"A")
    def test_alert_mentions_other_strategies(self):
        res={'strategy':'A','now':1793340000,'candle_t':1793339700,'gran':300,'rsi':60,'rel_volume':2}
        plan={'quote_time':1793340000,'bid':1,'ask':1.001,'spread_pct':.1,'entry':1.001,'max_entry':1.008,'stop':.97,'risk_pct':3,'target':1.07,'gross_rr':2.5,'net_rr':1.9,'position':50,'profit_if_target_net':3,'loss_if_stop_net':-2}
        self.assertIn("Also confirmed here: B",tg.format_alert('X-USDC',res,plan,'USDC',['B']))
        self.assertNotIn("Also confirmed",tg.format_alert('X-USDC',res,plan,'USDC'))
class Paper(unittest.TestCase):
    import paper as P
    def rec(self,strategy="B: x"):
        return {"id":"i","pair":"X-USDC","strategy":strategy,"candle_t":1000,"created":1400,"entry":100.0,"stop":98.0,"target":105.0,"outcome":"open"}
    def c(self,t,l,h,cl=100): return {"t":t,"o":100,"h":h,"l":l,"c":cl,"v":1}
    def run_one(self,cs,now=2000,strategy="B: x"):
        r=self.rec(strategy); self.P.resolve([r],"X-USDC",cs,now,0.8); return r
    def test_win_net_of_costs(self):
        r=self.run_one([self.c(1300,99,101),self.c(1600,99,106)]); self.assertEqual(r["outcome"],"win"); self.assertAlmostEqual(r["net_pct"],4.2,1)
    def test_stop_first_when_both_touched(self):
        r=self.run_one([self.c(1300,99,101),self.c(1600,97,106)]); self.assertEqual(r["outcome"],"loss"); self.assertAlmostEqual(r["net_pct"],-2.8,1)
    def test_entry_candle_cannot_win(self):
        r=self.run_one([self.c(1300,99,107)]); self.assertEqual(r["outcome"],"open")
    def test_missing_history_is_unknown_not_win(self):
        r=self.run_one([self.c(2000,99,110)]); self.assertEqual(r["outcome"],"unknown"); self.assertNotIn("net_pct",r)
    def test_timeout_marks_to_market(self):
        r=self.run_one([self.c(1300,99,101,100.5)],now=1400+30000); self.assertEqual(r["outcome"],"timeout")
    def test_duplicate_signal_recorded_once(self):
        recs=[]; res={"strategy":"B: x","candle_t":1000}; plan={"status":"BLOCKED","reasons":["spread"],"entry":1,"stop":.9,"target":1.2}
        self.assertTrue(self.P.record_new(recs,"X-USDC",res,plan,5)); self.assertFalse(self.P.record_new(recs,"X-USDC",res,plan,6)); self.assertEqual(recs[0]["group"],"blocked")
class Cfg(unittest.TestCase):
    def test_broken_config_is_reported_not_silent(self):
        import scan, tempfile, os, json, coinbase as cb
        d=tempfile.mkdtemp(); bad=os.path.join(d,"c.json"); open(bad,"w").write('{"watchlist": ["BTC" "ETH"]}')
        cb.tradable_products=lambda:{}
        scan.main(bad,d); h=json.load(open(os.path.join(d,"health.json")))
        self.assertTrue(any("config.json" in e for e in h["errors"]))
class GapT(unittest.TestCase):
    import gap as G
    CFG={"gap_fee_cb_pct":0.11,"gap_fee_kr_pct":0.26,"position_size":50,"quote_max_age_sec":120}
    def books(self,cb_ask=100.0,kr_bid=100.5,size=1.0):
        return ({"bid":99.9,"ask":cb_ask,"bid_size":size,"ask_size":size,"time":1000},{"bid":kr_bid,"ask":100.6,"bid_size":size,"ask_size":size})
    def test_gap_math_and_fees(self):
        c,k=self.books(); r=self.G.compare("X","USDC",c,k,self.CFG,1010)
        self.assertAlmostEqual(r["gross_pct"],0.5,3); self.assertAlmostEqual(r["net_pct"],0.13,3); self.assertEqual(r["direction"],"Buy Coinbase, sell Kraken")
    def test_negative_after_costs(self):
        c,k=self.books(kr_bid=100.2); self.assertLess(self.G.compare("X","USDC",c,k,self.CFG,1010)["net_pct"],0)
    def test_thin_and_stale_flagged(self):
        c,k=self.books(size=0.1); r=self.G.compare("X","USDC",c,k,self.CFG,1500); self.assertTrue(r["thin"]); self.assertTrue(r["stale"])
    def test_run_skips_missing_quote_and_survives_kraken_failure(self):
        import tempfile,json,os
        d=tempfile.mkdtemp(); cfg=dict(self.CFG,gap_every_sec=0)
        self.G.kraken_pairs=lambda o=None:{("XBT","USDC"):"XBTUSDC"}
        self.G.cb_book=lambda pid:self.books()[0]; self.G.kraken_book=lambda a,o=None:self.books()[1]
        self.G.time.sleep=lambda s:None
        self.G.run([("BTC","BTC-USDC","USDC"),("PEPE","PEPE-USDC","USDC")],cfg,1010,d)
        j=json.load(open(os.path.join(d,"gap.json"))); self.assertEqual(len(j["rows"]),1); self.assertEqual(j["skipped"][0]["symbol"],"PEPE")
        self.assertEqual(j["stats"]["checks"],0 if j["rows"][0]["stale"] else 1)
        def boom(o=None): raise RuntimeError("kraken down")
        self.G.kraken_pairs=boom; self.G.run([("BTC","BTC-USDC","USDC")],cfg,2000,d)
        self.assertIn("error",json.load(open(os.path.join(d,"gap.json"))))
class LateGuard(unittest.TestCase):
    def cfg(self,**k): return dict(CFG,**k)
    def test_high_rsi_blocked_with_reason(self):
        p=risk.build_plan(dict(CONF,rsi=73.4),QUOTE,PROD,self.cfg(max_rsi=68),1010); self.assertEqual(p["status"],"BLOCKED"); self.assertTrue(any("Likely late: RSI" in x for x in p["reasons"]))
    def test_big_runup_blocked(self):
        p=risk.build_plan(dict(CONF,rsi=60,runup_pct=5.2),QUOTE,PROD,self.cfg(max_runup_pct=3.0),1010); self.assertTrue(any("up 5.2%" in x for x in p["reasons"]))
    def test_calm_signal_passes_and_guard_can_be_off(self):
        self.assertEqual(risk.build_plan(dict(CONF,rsi=60,runup_pct=1.0),QUOTE,PROD,self.cfg(),1010)["status"],"CONFIRMED")
        self.assertEqual(risk.build_plan(dict(CONF,rsi=80,runup_pct=9),QUOTE,PROD,self.cfg(late_guard=False),1010)["status"],"CONFIRMED")
    def test_runup_computed_on_signal_timeframe(self):
        cs=mk([100+i*0.1 for i in range(59)]+[110]); r=st.strategy_a(cs)
        self.assertAlmostEqual(r["runup_pct"],(110/cs[-5]["c"]-1)*100,3)
    def test_muted_strategy_recorded_but_flagged(self):
        import paper as P; recs=[]; res={"strategy":"A: x","candle_t":5}; plan={"status":"CONFIRMED","entry":1,"stop":.9,"target":1.2}
        P.record_new(recs,"X-USDC",res,plan,1,"muted"); self.assertEqual(recs[0]["group"],"muted"); self.assertEqual(recs[0]["blocked_by"],[])
if __name__=="__main__": unittest.main()
