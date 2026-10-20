import test from 'node:test';
import assert from 'node:assert/strict';
import {V3Client} from '../publish/v3/client.js';
import {rankBadge,rankResult} from '../publish/v3/ranked.js';

test('ranked requests stay separate and restored queue mode controls heartbeat/cancel',async()=>{
 const calls=[];const c=new V3Client({sdk:{},apiBase:'',fetchImpl:async(url,o)=>{calls.push({url,body:o.body&&JSON.parse(o.body)});return {ok:true,json:async()=>({})};}});
 await c.startMatchmaking('deck','ranked');await c.heartbeatMatchmaking('ticket','ranked');await c.cancelMatchmaking('ticket','ranked');
 await c.startMatchmaking('deck');await c.heartbeatMatchmaking('casual');
 await c.rankedProfile();await c.rankedLeaderboard(2,1);await c.rankedHonor(1);await c.rankedHonor(null);
 assert.deepEqual(calls.slice(0,3).map(c=>c.url),['/api/mistrealm/v3/ranked/matchmaking','/api/mistrealm/v3/ranked/matchmaking/heartbeat','/api/mistrealm/v3/ranked/matchmaking/cancel']);
 assert.equal(calls[3].url,'/api/mistrealm/v3/matchmaking');assert.equal(calls[4].url,'/api/mistrealm/v3/matchmaking/heartbeat');
 assert.equal(calls[6].url,'/api/mistrealm/v3/ranked/leaderboard?season_id=2&page=1');
 assert.deepEqual(calls[0].body,{deck_id:'deck'});assert.deepEqual(calls[7].body,{season_id:1});assert.deepEqual(calls[8].body,{season_id:null});
});

test('rating result appears only for a settled whole match and uses the viewing seat',()=>{
 const state={phase:'playing',seat:1,ranked:{season_id:3,result:{deltas:[16,-16],before:[1000,1000],after:[1016,984],tiers:[{name:'青铜'},{name:'青铜'}]}}};
 assert.equal(rankResult(state),'');state.phase='round_result';assert.equal(rankResult(state),'');state.phase='finished';
 assert.match(rankResult(state),/-16 分/);assert.match(rankResult(state),/1000 → 984/);assert.match(rankResult(state),/S3/);
 state.ranked.result=null;assert.equal(rankResult(state),'');
 assert.match(rankBadge('crown','王冠'),/♛/);assert.ok(!rankBadge('bronze','<script>').includes('<script>'));
});
