"""Build a deterministic two-round tutorial using the current authoritative rules."""
import json
from pathlib import Path
from random import Random
from dzmm_bot.core import mistrealm_v3_state as game, mistrealm_v3_effects as fx
from dzmm_bot.core.mistrealm_v3_cards import STARTER_DECKS


def build_tutorial():
    rng=Random(19)
    state=game.new_state('tutorial-you',STARTER_DECKS[0],0)
    for seat,action,payload in [(1,'join',dict(uid='tutorial-opponent',deck=STARTER_DECKS[0])),(0,'lock',{}),(1,'lock',{}),(0,'mulligan',dict(cards=[])),(1,'mulligan',dict(cards=[]))]:
        state=game.apply_action(state,seat,action,payload,0,rng)
    state.update(turn=0,first=0,actor=0)
    for p in state['players']:
        for zone in ('hand','deck','discard','spells','resolving'):p[zone]=[]
        p['rows']=[[],[],[]]
    state['players'][1]['leader_used']=True
    seq=0
    def card(cid,seat,zone,row=0):
        nonlocal seq
        seq+=1;c=dict(id=f'tutorial:{seq}',card=cid,owner=seat)
        if zone=='rows':fx.put(state,seat,c,row)
        else:state['players'][seat][zone].append(c)
        return c['id']
    hand={cid:card(cid,0,'hand') for cid in ('c003','c103','c111','c002','c069','c104','c118')}
    own_order=['c010','c101','c081','c111','c008']+['c008']*8
    own_deck=[card(cid,0,'deck') for cid in reversed(own_order)][::-1]
    enemy_guard=card('c003',1,'rows');enemy_archer=card('c103',1,'hand')
    enemy_order=['c084','c093','c108','c113','c118','c081','c103','c001']+['c008']*10
    enemy_deck=[card(cid,1,'deck') for cid in reversed(enemy_order)][::-1]
    scenes=[]
    def scene(key,title,text,action='continue',payload=None,focus='',cta='继续'):
        view=game.project(state,0)
        view.update(tutorial=True,deadline_ms=None,action_log=[],action_frames=[],events=[])
        view['players'][0].update(name='你 · 练习军团',avatar=None)
        view['players'][1].update(name='演练对手',avatar=None)
        scenes.append(dict(key=key,title=title,text=text,state=view,expected=dict(action=action,payload=payload or {}),focus=focus,cta=cta))
    def apply(seat,action,**payload):
        nonlocal state
        assert dict(action=action,payload=payload) in game.legal_moves(state,seat),(action,payload)
        state=game.apply_action(state,seat,action,payload,0,rng)
    def option_for(uid,row=None):
        return next(o['token'] for o in state['pending']['options'] if o.get('card',{}).get('id')==uid and (row is None or o.get('row')==row))
    def play(key,title,text,uid,row):
        scene(key,title,text,'play',dict(card=uid,row=row),f'[data-hand="{uid}"]')
        apply(0,'play',card=uid,row=row)
    def choose(key,title,text,uid,row=None):
        token=option_for(uid,row)
        scene(key,title,text,'choose',dict(option=token),f'[data-inspect="{uid}"]')
        apply(0,'choose',option=token)

    scene('rules','先认识整场胜负','双方各有2点生命。双方停手后，比三排总战力：输家失去1点生命，平分则双方各失去1点。让对手生命归零获胜；通常三局两胜。这里用固定7张手牌练两局，不计战绩。',focus='.gems',cta='开始第一局')
    play('first-card','查看手牌，再使用','点击誓约守卫查看效果，再点「使用」。它是近战单位；独处一排时，3点基础战力加2，共5点。',hand['c003'],0)
    scene('enemy-response','双方轮流行动','你出牌后轮到对手。接下来，对手打出最后一张手牌漂泊弩客，对你的守卫造成2点伤害。',focus='.army.enemy',cta='看对手出牌')
    apply(1,'play',card=enemy_archer,row=1);apply(1,'choose',option=option_for(hand['c003']))
    play('archer','部署技能属于这次行动','你的守卫现在是3战力。打出远程单位漂泊弩客，随后选择伤害目标；不用再额外消耗一张牌。',hand['c103'],1)
    choose('archer-target','选择敌方目标','选择对方的誓约守卫，再点击「确认选择」，造成2点伤害。选中目标后会显示金色标记与结果预览。',enemy_guard)
    scene('enemy-empty','对方无手牌，选择停手','对手手牌已经用完，领袖也已使用，因此选择本局停手。停手后不能再行动；你仍能继续出牌。此时双方6比6，直接停手会平局，双方各失去1点生命。',focus='.army.enemy .muted',cta='对手停手，继续争取胜局')
    apply(1,'pass')
    play('damage-spell','对手停手，你还能行动','打出渡雾剑诀。即时术不占单位格，也不占持续术位；结算完进入弃牌堆。你只需取得领先，就可以留牌停手。',hand['c111'],-1)
    choose('damage-target','战力归零，单位阵亡','选择敌方守卫，造成4点伤害。它当前只有3战力，会阵亡并进入原拥有者的弃牌区。',enemy_guard)
    scene('discard','弃牌区不是牌库','点开己方弃牌堆查看刚用过的即时术。弃牌不会自动回到牌库；只有卡牌明确写出复活、回收或洗回牌库时，才能再次取用。','grave',dict(seat=0),'[data-grave="0"]')
    scene('leader','领袖整场只用一次','现在已领先，实战可以直接停手、保留领袖。这里只为练习发动它：从牌库召集火盆投石车到攻城排，不触发部署。领袖整场仅一次，第二局不会恢复。','leader',focus='#use-leader')
    apply(0,'leader')
    choose('leader-target','从牌库召集到合法战列','选择火盆投石车的攻城位置并确认。它基础战力3，不额外消耗手牌；这就是调度牌库中的资源。',own_deck[0],2)
    scene('pass-first','已经领先，停手留牌','对手已停手，无法再追分。现在你9比3领先，没有必要继续出牌。点击「本局停手」并确认，把剩余4张手牌留到下一局。','pass',focus='#pass')
    apply(0,'pass')
    assert state['phase']=='round_result' and state['lives']==[2,1]
    scene('round-clear','小局获胜，还没赢下整场','本局9比3，对方失去1点生命。进入第二局时，场上单位和持续术会离场，通常进入原拥有者的弃牌区；特殊去向按卡牌效果。小局清场不算阵亡，不触发阵亡技能。',focus='.army',cta='清场，进入第二局')
    state=game.advance(state,state['deadline_ms'],rng)
    assert len(state['players'][0]['hand'])==6 and len(state['players'][0]['discard'])==4
    scene('round-draw','留住的4张＋新抽2张','新局战场清空，剩余手牌保留，再从牌库抽2张，所以你现在有6张。第一局的弃牌仍在弃牌区，没有洗回牌库。第二、第三局都这样补牌，牌库不足则抽取剩余牌。',focus='.hand-area',cta='练习第二局的格子调度')
    play('spear','先布置近战单位','打出赤铜长枪队。每排只有4个单位格；攻城、远程还有空位，也不能让近战单位随意放过去。',hand['c002'],0)
    scene('enemy-mask','观察对方的资源调度','对手会打出面具侍者·朝：查看牌库顶2张，1张入手，另1张进入弃牌区。手牌数量与牌库数量会随着效果变化。',cta='看对手行动')
    apply(1,'play',card=enemy_deck[0],row=0);apply(1,'choose',option=option_for(enemy_deck[2]))
    play('persistent-spell','持续术要留在专属术位','使用军阵庇护。它不会像即时术一样结算后立刻弃置，而会占用己方3个持续术位中的1个；不占四格单位战列。',hand['c118'],-1)
    choose('persistent-target','选择获得持续加成的单位','选择己方赤铜长枪队并确认。军阵庇护在场时，它获得条件战力＋2；术卡离场后，这2点加成会撤销，不是永久强化。',hand['c002'])
    scene('persistent-active','术卡在场，效果才持续','赤铜长枪队由5变7，己方持续术区已有军阵庇护。点击术位中的卡也能查看效果。每张持续术的触发条件不同；3个术位满时，需要先腾出术位。对手接下来用碎镜祝祷抽2张。',focus='.army.self .spell-slots',cta='观察术位，继续')
    apply(1,'play',card=enemy_deck[1],row=-1);apply(1,'choose',option=state['pending']['options'][0]['token'])
    play('third-unit','先布置第二个近战单位','打出镜湖誓卫。你这一小局还没有己方卡牌进入弃牌区，所以它保持4点基础战力；军阵庇护只保护施放时选中的长枪队，不会自动强化新单位。',own_deck[2],0)
    scene('enemy-persistent','对手也能使用持续术','对手接下来施放军阵庇护，保护面具侍者·朝。留意对方持续术区和该单位战力的变化；下一步用荒境佣兵解除它。',focus='.army.enemy .spell-slots',cta='看对手施放持续术')
    apply(1,'play',card=enemy_deck[4],row=-1);apply(1,'choose',option=option_for(enemy_deck[0]))
    play('mercenary','用单位部署技能拆掉持续术','对方面具侍者·朝由2变4。打出荒境佣兵：它占用第三个近战格，并让你选择场上一张持续术摧毁。己方与敌方都可选，这次要拆对方的。',own_deck[1],0)
    token=option_for(enemy_deck[4])
    scene('destroy-persistent','选对方术卡，再确认摧毁','选择敌方持续术区的军阵庇护，再确认。注意别拆掉自己的军阵庇护；摧毁持续术不等于摧毁它保护的单位。','choose',dict(option=token),f'[data-spell="{enemy_deck[4]}"]')
    apply(0,'choose',option=token)
    scene('persistent-destroyed','持续术离场，加成立即消失','敌方军阵庇护已进入对手弃牌区，术位空出；朝从4回到2，仍留在场上。你的军阵庇护仍在，长枪队仍有＋2。这就是摧毁持续术带来的效果。',focus='.army.enemy .spell-slots, .army.enemy [data-grave]',cta='继续练习间谍占位')
    scene('enemy-spy','对方把间谍放到你这边','对手打出失名信使到你的近战排，为自己抽2张牌。间谍的2战力算给你，但也占你的格子：现在你的近战排已满4／4。',focus='.army.self .combat-row[data-row="0"]',cta='看间谍入场')
    apply(1,'play',card=enemy_deck[2],row=0)
    assert len(state['players'][0]['rows'][0])==4
    scene('full-row','满排时，先想办法腾位置','点击手中的古林姊妹·枝。它只能放近战，现在4格已满，因此「使用」不可用。可以通过移动、回手或献祭调度场上的单位；这次练习献祭。','select',dict(card=hand['c069']),f'.army.self .combat-row[data-row="0"], [data-hand="{hand["c069"]}"]')
    play('sacrifice-card','从另一排发动献祭','使用旧路驮炮，它部署在仍有空位的攻城排。它的部署技能可牺牲一名己方普通单位，让自身＋2；接下来选占位的间谍。',hand['c104'],2)
    choose('sacrifice-spy','献祭间谍，腾出近战格','选择己方近战排的失名信使并确认。它现在是你场上的普通单位，可以献祭；离场后回到原拥有者——对手的弃牌区。',enemy_deck[2])
    assert len(state['players'][0]['rows'][0])==3
    scene('space-freed','近战恢复3／4，可继续部署','间谍离场，近战空出1格，驮炮强化到5。腾位置也有代价：你失去了间谍提供的2战力。对手接下来出弩客，对你的誓卫造成2伤害。',focus='.army.self .combat-row[data-row="0"]',cta='看对手回应')
    apply(1,'play',card=enemy_deck[6],row=1);apply(1,'choose',option=option_for(own_deck[2]))
    play('branch','空位让新的部署效果生效','现在使用古林姊妹·枝，放进刚腾出的近战格。它可以牺牲另一名己方普通单位，再抽2张牌。',hand['c069'],0)
    choose('branch-sacrifice','用场上战力换取手牌','选择2战力的荒境佣兵并确认。它进入你的弃牌区，枝从牌库抽2张。这是资源调度：牺牲眼前的战力，换取后续选择。',own_deck[1])
    scene('enemy-oath','对手补充战力','你抽到了渡雾剑诀和烬羽弩队。对手打出镜湖誓卫；本小局已有己方卡进入弃牌区，它部署时强化＋2，变为6战力。',cta='看对手出牌')
    apply(1,'play',card=enemy_deck[5],row=0)
    play('finish-spell','先削弱对面的关键单位','使用新抽到的渡雾剑诀。目标选对手的镜湖誓卫；它已强化到6，这次4点伤害会把它压到2。',own_deck[3],-1)
    choose('finish-target','伤害不一定要击杀','确认对方镜湖誓卫。虽然没击杀，但这4点伤害已足以改变比分；不用为了清空对手的场面浪费手牌。',enemy_deck[5])
    scene('enemy-last-card','对手打出最后一张手牌','对手最后打出烬冠步兵；它与其他单位同排，获得条件战力＋2。之后对手手牌为0，领袖也已用过，没有继续追分的手段。',cta='看对手最后一手')
    apply(1,'play',card=enemy_deck[7],row=0)
    own=sum(game.score_rows(state,0));enemy=sum(game.score_rows(state,1))
    assert own>enemy,(own,enemy)
    scene('pass-second','对手无牌，领先就收手',f'你现在{own}比{enemy}领先。对手虽然还没点停手，但已经没有手牌，领袖也已用过，无法追分。你可以先停手，留住最后1张手牌，不必继续出牌。','pass',focus='#pass')
    apply(0,'pass')
    scene('second-empty','对手也停手，结算整场','你已停手，对手没有可用手牌和领袖，只能停手。双方停手后结算比分；赢下这一局，就让对手最后1点生命归零。',focus='.army.enemy .muted',cta='看对手停手，结算胜负')
    apply(1,'pass')
    assert state['phase']=='finished' and state['winner']==0
    scene('complete','赢下整场，而不只是堆高一局分数','你连赢两局，对手2点生命归零，整场获胜。如果前两局各赢一局，就进入第三局；平局双方各失去1点生命，同时归零则整场平局。记住：留手牌、看比分、调度格子。','finish',focus='.gems',cta='完成教学，返回大厅')
    return scenes


if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'gamefy/mistrealm/publish/v3/tutorial.json'
    path.write_text(json.dumps(build_tutorial(),ensure_ascii=False,separators=(',',':'))+'\n')
    print(path)
