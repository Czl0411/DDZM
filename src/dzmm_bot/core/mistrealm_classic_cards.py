"""Original Classic catalogue. Numeric IDs and copies are content, not rarity rules."""

FACTIONS = {
    'crown': '烬冠军团', 'raven': '黑鸦议会', 'frost': '寒霜盟约',
    'beast': '荒棘兽群', 'mirror': '镜湖秘会',
}

# id, name, faction, type, rows, power, abilities, hero, copies, effect arguments
_DEFINITIONS = [
    ('001', '烬冠步兵', 'crown', 'unit', [0], 4, ['bond'], False, 3, {}),
    ('002', '赤铜长枪队', 'crown', 'unit', [0], 5, ['bond'], False, 3, {}),
    ('003', '誓约守卫', 'crown', 'unit', [0], 6, [], False, 2, {}),
    ('004', '灰烬统领', 'crown', 'unit', [0], 5, ['morale'], False, 1, {}),
    ('005', '王旗执掌者', 'crown', 'unit', [0], 2, ['morale'], False, 1, {}),
    ('006', '王城密使', 'crown', 'unit', [0], 4, ['spy'], False, 1, {}),
    ('007', '山隘弩手', 'crown', 'unit', [1], 5, [], False, 2, {}),
    ('008', '烬羽弩队', 'crown', 'unit', [1], 4, ['bond'], False, 3, {}),
    ('009', '驿道观察员', 'crown', 'unit', [1], 5, ['spy'], False, 1, {}),
    ('010', '火盆投石车', 'crown', 'unit', [2], 6, ['bond'], False, 3, {}),
    ('011', '裂墙重弩', 'crown', 'unit', [2], 6, [], False, 2, {}),
    ('012', '王庭攻城塔', 'crown', 'unit', [2], 6, [], False, 2, {}),
    ('013', '前线军需官', 'crown', 'unit', [2], 1, ['morale'], False, 1, {}),
    ('014', '战地修械营', 'crown', 'unit', [2], 5, ['medic'], False, 1, {}),
    ('015', '余烬女将', 'crown', 'unit', [0], 10, [], True, 1, {}),
    ('016', '王城守誓者', 'crown', 'unit', [0], 10, [], True, 1, {}),
    ('017', '赤金观星官', 'crown', 'unit', [1], 10, [], True, 1, {}),
    ('018', '最后的城主', 'crown', 'unit', [2], 10, [], True, 1, {}),
    ('019', '余烬摄政·晴空诏令', 'crown', 'leader', [], 0, ['clear'], False, 1, {}),
    ('020', '铁壁亲王·破城号令', 'crown', 'leader', [], 0, ['horn_siege'], False, 1, {}),
    ('021', '雾鸦骑士', 'raven', 'unit', [0], 7, [], False, 2, {}),
    ('022', '断誓刺客', 'raven', 'unit', [0], 5, [], False, 2, {}),
    ('023', '黑羽契卫', 'raven', 'unit', [0], 3, ['bond'], False, 3, {}),
    ('024', '潜城密探', 'raven', 'unit', [0], 5, ['spy'], False, 1, {}),
    ('025', '王座旁听者', 'raven', 'unit', [0], 7, ['spy'], False, 1, {}),
    ('026', '白面使节', 'raven', 'unit', [0], 9, ['spy'], False, 1, {}),
    ('027', '灰羽猎手', 'raven', 'unit', [1], 6, [], False, 2, {}),
    ('028', '夜巷弩手', 'raven', 'unit', [1], 4, ['bond'], False, 3, {}),
    ('029', '鸦群引路人', 'raven', 'unit', [1], 1, ['medic'], False, 1, {}),
    ('030', '黑灯随军官', 'raven', 'unit', [1], 5, ['medic'], False, 1, {}),
    ('031', '密库药师', 'raven', 'unit', [2], 0, ['medic'], False, 1, {}),
    ('032', '哑钟重弩', 'raven', 'unit', [2], 6, [], False, 2, {}),
    ('033', '黑铁攻城车', 'raven', 'unit', [2], 10, [], False, 2, {}),
    ('034', '密令执旗官', 'raven', 'unit', [0], 1, ['morale'], False, 1, {}),
    ('035', '帷幕女爵', 'raven', 'unit', [0], 10, [], True, 1, {}),
    ('036', '无声刽子手', 'raven', 'unit', [0], 10, [], True, 1, {}),
    ('037', '断誓元帅', 'raven', 'unit', [1], 10, [], True, 1, {}),
    ('038', '鸦塔监国', 'raven', 'unit', [2], 10, [], True, 1, {}),
    ('039', '无冠鸦王·缄默王令', 'raven', 'leader', [], 0, ['cancel_leader'], False, 1, {}),
    ('040', '帷幕执政·借尸传信', 'raven', 'leader', [], 0, ['steal_grave'], False, 1, {}),
    ('041', '雪线游侠', 'frost', 'unit', [0, 1], 6, ['agile'], False, 1, {}),
    ('042', '逐风斥候', 'frost', 'unit', [0, 1], 5, ['agile'], False, 1, {}),
    ('043', '白枝猎手', 'frost', 'unit', [0, 1], 6, ['agile'], False, 1, {}),
    ('044', '岩隙守望者', 'frost', 'unit', [0, 1], 5, ['agile'], False, 1, {}),
    ('045', '雪径伏兵·弓', 'frost', 'unit', [1], 3, ['muster'], False, 1, {'group': '雪径伏兵'}),
    ('046', '雪径伏兵·刃', 'frost', 'unit', [0], 3, ['muster'], False, 1, {'group': '雪径伏兵'}),
    ('047', '雪径伏兵·索', 'frost', 'unit', [0], 3, ['muster'], False, 1, {'group': '雪径伏兵'}),
    ('048', '白木护卫·盾', 'frost', 'unit', [0], 3, ['muster'], False, 1, {'group': '白木护卫'}),
    ('049', '白木护卫·矛', 'frost', 'unit', [0], 3, ['muster'], False, 1, {'group': '白木护卫'}),
    ('050', '白木护卫·弩', 'frost', 'unit', [1], 3, ['muster'], False, 1, {'group': '白木护卫'}),
    ('051', '冰湖医者', 'frost', 'unit', [1], 0, ['medic'], False, 1, {}),
    ('052', '风铃祭司', 'frost', 'unit', [1], 2, ['morale'], False, 1, {}),
    ('053', '霜原行者', 'frost', 'unit', [0], 6, [], False, 2, {}),
    ('054', '山隘射手', 'frost', 'unit', [1], 6, [], False, 2, {}),
    ('055', '无声雪客', 'frost', 'unit', [0], 10, [], True, 1, {}),
    ('056', '冬枝女侯', 'frost', 'unit', [1], 10, [], True, 1, {}),
    ('057', '白石守约人', 'frost', 'unit', [0], 10, [], True, 1, {}),
    ('058', '北境巡狩者', 'frost', 'unit', [1], 10, [], True, 1, {}),
    ('059', '霜境女王·冬藏', 'frost', 'leader', [], 0, ['extra_hand'], False, 1, {}),
    ('060', '逐风可汗·长风之歌', 'frost', 'leader', [], 0, ['horn_ranged'], False, 1, {}),
    ('061', '棘狼·灰鬃', 'beast', 'unit', [0], 4, ['muster'], False, 1, {'group': '棘狼'}),
    ('062', '棘狼·裂牙', 'beast', 'unit', [0], 4, ['muster'], False, 1, {'group': '棘狼'}),
    ('063', '棘狼·赤眼', 'beast', 'unit', [0], 4, ['muster'], False, 1, {'group': '棘狼'}),
    ('064', '腐巢虫·镰足', 'beast', 'unit', [0], 4, ['muster'], False, 1, {'group': '腐巢'}),
    ('065', '腐巢虫·骨翼', 'beast', 'unit', [0], 4, ['muster'], False, 1, {'group': '腐巢'}),
    ('066', '腐巢虫·重壳', 'beast', 'unit', [0], 4, ['muster'], False, 1, {'group': '腐巢'}),
    ('067', '腐巢母体', 'beast', 'unit', [2], 6, ['muster'], False, 1, {'group': '腐巢'}),
    ('068', '古林姊妹·根', 'beast', 'unit', [0], 6, ['muster'], False, 1, {'group': '古林姊妹'}),
    ('069', '古林姊妹·枝', 'beast', 'unit', [0], 6, ['muster'], False, 1, {'group': '古林姊妹'}),
    ('070', '古林姊妹·叶', 'beast', 'unit', [0], 6, ['muster'], False, 1, {'group': '古林姊妹'}),
    ('071', '沼泽潜行兽', 'beast', 'unit', [0], 5, [], False, 2, {}),
    ('072', '苔背巨兽', 'beast', 'unit', [0], 6, [], False, 2, {}),
    ('073', '骨翼掠食者', 'beast', 'unit', [1], 6, [], False, 2, {}),
    ('074', '荆棘投掷者', 'beast', 'unit', [2], 6, [], False, 2, {}),
    ('075', '焚巢巨蜥', 'beast', 'unit', [0], 7, ['scorch_melee'], False, 1, {}),
    ('076', '千齿古兽', 'beast', 'unit', [0], 10, [], True, 1, {}),
    ('077', '荒棘之心', 'beast', 'unit', [0], 10, [], True, 1, {}),
    ('078', '无月巨蛾', 'beast', 'unit', [1], 10, [], True, 1, {}),
    ('079', '群巢之母·万兽齐鸣', 'beast', 'leader', [], 0, ['horn_melee'], False, 1, {}),
    ('080', '噬月兽王·荒野回声', 'beast', 'leader', [], 0, ['recover_grave'], False, 1, {}),
    ('081', '镜湖誓卫', 'mirror', 'unit', [0], 4, ['bond'], False, 3, {}),
    ('082', '湖岸弓队', 'mirror', 'unit', [1], 5, ['bond'], False, 3, {}),
    ('083', '青铜舰弩', 'mirror', 'unit', [2], 6, ['bond'], False, 3, {}),
    ('084', '面具侍者·朝', 'mirror', 'unit', [0], 4, ['muster'], False, 1, {'group': '面具侍者'}),
    ('085', '面具侍者·暮', 'mirror', 'unit', [0], 4, ['muster'], False, 1, {'group': '面具侍者'}),
    ('086', '面具侍者·夜', 'mirror', 'unit', [0], 4, ['muster'], False, 1, {'group': '面具侍者'}),
    ('087', '镜湖唤灵者', 'mirror', 'unit', [0], 6, ['muster'], False, 1, {'group': '面具侍者'}),
    ('088', '镜血行者', 'mirror', 'unit', [0], 4, ['transform'], False, 1, {'transform': 't001'}),
    ('089', '幼镜行者', 'mirror', 'unit', [1], 2, ['transform'], False, 3, {'transform': 't002'}),
    ('090', '湖心仪师', 'mirror', 'unit', [0], 2, ['ritual'], False, 1, {}),
    ('091', '雾岸仪师', 'mirror', 'unit', [1], 2, ['ritual'], False, 1, {}),
    ('092', '招魂侍者', 'mirror', 'unit', [1], 0, ['medic'], False, 1, {}),
    ('093', '碎镜鼓手', 'mirror', 'unit', [0], 4, ['morale'], False, 1, {}),
    ('094', '沉舟守卫', 'mirror', 'unit', [2], 6, [], False, 2, {}),
    ('095', '镜湖裁判', 'mirror', 'unit', [2], 8, ['scorch_siege'], False, 1, {}),
    ('096', '白塔遗主', 'mirror', 'unit', [0], 10, [], True, 1, {}),
    ('097', '无面贤者', 'mirror', 'unit', [1], 10, [], True, 1, {}),
    ('098', '湖底圣像', 'mirror', 'unit', [2], 10, [], True, 1, {}),
    ('099', '镜湖女祭司·归流', 'mirror', 'leader', [], 0, ['shuffle_graves'], False, 1, {}),
    ('100', '白塔执印者·薄暮', 'mirror', 'leader', [], 0, ['half_weather'], False, 1, {}),
    ('101', '荒境佣兵', 'neutral', 'unit', [0], 5, [], False, 2, {}),
    ('102', '铁盾卫士', 'neutral', 'unit', [0], 6, [], False, 2, {}),
    ('103', '漂泊弩客', 'neutral', 'unit', [1], 5, [], False, 2, {}),
    ('104', '旧路驮炮', 'neutral', 'unit', [2], 6, [], False, 2, {}),
    ('105', '随军医师', 'neutral', 'unit', [1], 1, ['medic'], False, 1, {}),
    ('106', '战地歌者', 'neutral', 'unit', [0], 2, ['unit_horn'], False, 1, {}),
    ('107', '灰袍调停人', 'neutral', 'unit', [0, 1], 4, ['agile'], False, 1, {}),
    ('108', '失名信使', 'neutral', 'unit', [0], 0, ['spy'], True, 1, {}),
    ('109', '焚旗旅人', 'neutral', 'unit', [0], 7, ['scorch_melee'], False, 1, {}),
    ('110', '无名守誓者', 'neutral', 'unit', [0], 15, [], True, 1, {}),
    ('111', '渡雾剑客', 'neutral', 'unit', [0], 15, [], True, 1, {}),
    ('112', '长夜医者', 'neutral', 'unit', [1], 7, ['medic'], True, 1, {}),
    ('113', '霜白降临', 'neutral', 'special', [], 0, ['weather_melee'], False, 3, {}),
    ('114', '灰幕蔽日', 'neutral', 'special', [], 0, ['weather_ranged'], False, 3, {}),
    ('115', '铁雨倾城', 'neutral', 'special', [], 0, ['weather_siege'], False, 3, {}),
    ('116', '雾散天明', 'neutral', 'special', [], 0, ['clear'], False, 3, {}),
    ('117', '空甲替身', 'neutral', 'special', [], 0, ['decoy'], False, 3, {}),
    ('118', '军阵长鸣', 'neutral', 'special', [], 0, ['horn'], False, 3, {}),
    ('119', '同归余烬', 'neutral', 'special', [], 0, ['scorch'], False, 3, {}),
    ('120', '映身秘仪', 'neutral', 'special', [], 0, ['ritual'], False, 3, {}),
]

CLASSIC_CARDS = {
    'c' + number: dict(name=name, faction=faction, type=kind, rows=rows,
                      power=power, abilities=abilities, hero=hero, copies=copies,
                      art='../assets/classic/c' + number + '.webp', **arguments)
    for number, name, faction, kind, rows, power, abilities, hero, copies, arguments in _DEFINITIONS
}
TRANSFORMS = {
    't001': dict(name='镜角巨灵', faction='mirror', type='unit', rows=[0], power=14,
                 abilities=[], hero=False, art='../assets/classic/t001.webp'),
    't002': dict(name='幼镜巨灵', faction='mirror', type='unit', rows=[1], power=8,
                 abilities=['bond'], hero=False, art='../assets/classic/t002.webp'),
}


def validate_deck(faction, leader, counts):
    """Return an independent canonical snapshot; never trust client totals."""
    if not isinstance(faction, str) or faction not in FACTIONS:
        raise ValueError('未知阵营')
    if not isinstance(leader, str) or leader not in CLASSIC_CARDS:
        raise ValueError('请选择领袖')
    chief = CLASSIC_CARDS[leader]
    if chief['type'] != 'leader' or chief['faction'] != faction:
        raise ValueError('领袖必须属于当前阵营')
    if not isinstance(counts, dict):
        raise ValueError('牌组必须是卡牌数量表')
    normalized = {}
    units = specials = 0
    for cid, count in counts.items():
        if not isinstance(cid, str) or cid not in CLASSIC_CARDS:
            raise ValueError('未知卡牌')
        card = CLASSIC_CARDS[cid]
        if type(count) is not int or count < 0 or count > card['copies']:
            raise ValueError('卡牌数量超出库存或不是整数')
        if card['type'] == 'leader' or card['faction'] not in (faction, 'neutral'):
            raise ValueError('牌组含有不允许的卡牌')
        if count:
            normalized[cid] = count
            if card['type'] == 'unit': units += count
            else: specials += count
    if units < 22: raise ValueError('至少需要22张单位牌')
    if specials > 10: raise ValueError('最多允许10张特殊牌')
    return {'faction': faction, 'leader': leader, 'counts': dict(sorted(normalized.items()))}


def _starter(name, faction, leader, entries):
    counts = {}
    for cid in entries.split(): counts[cid] = counts.get(cid, 0) + 1
    return dict(name=name, **validate_deck(faction, leader, counts))

# Deliberate synergies; each list is a playable deck, not the whole collection.
STARTER_DECKS = [
    _starter('赤铜战线', 'crown', 'c019',
             'c001 c001 c001 c002 c002 c002 c004 c005 c006 c008 c008 c008 c009 c010 c010 c010 c013 c014 c015 c105 c106 c108 c116 c117 c117 c118 c119'),
    _starter('攻城余烬', 'crown', 'c020',
             'c003 c003 c006 c007 c007 c009 c010 c010 c010 c011 c011 c012 c012 c013 c014 c017 c018 c102 c104 c104 c105 c108 c113 c116 c117 c118'),
    _starter('黑羽密令', 'raven', 'c039',
             'c021 c021 c023 c023 c023 c024 c025 c026 c028 c028 c028 c029 c030 c031 c034 c035 c101 c101 c105 c108 c109 c112 c117 c117 c117 c116 c119'),
    _starter('长夜回声', 'raven', 'c040',
             'c022 c022 c024 c025 c026 c027 c027 c029 c030 c031 c032 c032 c033 c033 c034 c038 c102 c102 c104 c105 c108 c112 c113 c116 c117 c117 c118'),
    _starter('白枝伏击', 'frost', 'c059',
             'c041 c042 c043 c044 c045 c046 c047 c048 c049 c050 c051 c052 c053 c053 c054 c054 c055 c101 c101 c105 c107 c108 c113 c116 c117 c118 c119'),
    _starter('长风齐射', 'frost', 'c060',
             'c041 c042 c043 c044 c045 c046 c047 c048 c049 c050 c051 c052 c054 c054 c056 c058 c103 c103 c105 c107 c108 c112 c113 c116 c117 c118'),
    _starter('群巢夜行', 'beast', 'c079',
             'c061 c062 c063 c064 c065 c066 c067 c068 c069 c070 c071 c071 c072 c072 c073 c073 c075 c076 c105 c106 c108 c109 c114 c116 c117 c118 c119'),
    _starter('荒野归途', 'beast', 'c080',
             'c061 c062 c063 c064 c065 c066 c067 c068 c069 c070 c072 c072 c073 c073 c074 c074 c075 c078 c104 c105 c108 c112 c113 c116 c117 c117 c118'),
    _starter('镜血仪式', 'mirror', 'c099',
             'c081 c081 c081 c082 c082 c082 c084 c085 c086 c087 c088 c089 c089 c089 c090 c091 c092 c093 c095 c096 c105 c108 c116 c117 c118 c120 c120'),
    _starter('薄暮阵列', 'mirror', 'c100',
             'c081 c081 c081 c082 c082 c082 c083 c083 c083 c088 c089 c089 c089 c090 c091 c092 c093 c094 c094 c095 c098 c105 c113 c114 c115 c116 c120'),
]
