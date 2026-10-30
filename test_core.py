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
if __name__=="__main__": unittest.main()
