"""
Tool: 多视角搜索查询生成器（纯计算）

根据系统类型和目标系统名称，生成覆盖多个视角的标准化搜索查询集。
每条查询标注视角层级（tier 1-3）和优先级（priority 0-3）。
年份过滤器从当前日期动态生成，确保查询始终指向最新数据。

Priority 0 = 近期事件扫描（跨系统类型通用，确保不遗漏最近 30 天的重大事件）。

多语言查询支持（骨架 v1）：
  自动检测系统名称/主题的语言相关性，返回一组匹配语言。
  当前支持 6 种本地语言：中文、阿拉伯语、波斯语、俄语、日语、韩语。
  检测基于 Unicode 字符范围 + 话题关键词，返回 set，可同时触发多个语言。
  英文查询始终存在（基线），本地语言查询为补充。

扩展新语言：在 LANGUAGE_REGISTRY 中添加条目即可。
"""

import re
from datetime import datetime

SYSTEM_TYPES = [
    'geopolitical',       # 地缘政治/国家政权
    'government_agency',  # 政府机构/监管机构
    'public_company',     # 上市公司
    'private_company',    # 私营企业
    'dao',                # DAO/Web3 组织
    'market',             # 行业/市场
    'platform',           # 平台生态
]

# 每个系统类型的视角矩阵
# 格式：(perspective_key, tier, priority, query_template)
# tier: 1=原始/官方文件, 2=机构媒体/分析报告, 3=社区/间接信号
# priority: 1=门控必须执行, 2=建议执行, 3=深度补充
PERSPECTIVE_MATRIX = {
    'geopolitical': [
        ('official_domestic',   1, 1, '{name} official statement OR government announcement {prev_year} OR {year}'),
        ('opposition_dissident',1, 1, '{name} opposition OR dissident OR protest OR resistance {prev_year} OR {year}'),
        ('western_media',       2, 1, '{name} site:reuters.com OR site:ft.com OR site:bbc.com {prev_year} OR {year}'),
        ('regional_neighbors',  2, 1, '{name} Al Jazeera OR regional perspective OR neighboring country {prev_year} OR {year}'),
        ('leadership_power',    1, 1, '{name} leadership succession OR power struggle OR elite faction {prev_year} OR {year}'),
        ('non_western_powers',  2, 2, '{name} Russia OR China perspective OR analysis {prev_year} OR {year}'),
        ('think_tank',          2, 2, '{name} Carnegie OR "Crisis Group" OR "Chatham House" OR RAND analysis {prev_year} OR {year}'),
        ('economic_indicators', 2, 2, '{name} economy OR currency OR sanctions OR GDP {prev_year} OR {year}'),
        ('military_security',   3, 2, '{name} military OR security OR conflict OR ceasefire {prev_year} OR {year}'),
        ('civil_society',       3, 3, '{name} civil society OR NGO OR human rights {prev_year} OR {year}'),
    ],
    'government_agency': [
        ('accountability',      1, 1, '{name} inspector general OR audit report OR GAO {prev_year} OR {year}'),
        ('performance',         2, 1, '{name} backlog OR failure OR cost overrun OR delay {prev_year} OR {year}'),
        ('political',           2, 1, '{name} political controversy OR budget cut OR mandate {prev_year} OR {year}'),
        ('employee_morale',     3, 2, '{name} employee morale OR union grievance OR turnover {prev_year} OR {year}'),
        ('public_trust',        2, 2, '{name} public trust OR polling OR survey OR criticism {prev_year} OR {year}'),
        ('capture',             3, 3, '{name} revolving door OR industry capture OR conflict of interest {prev_year} OR {year}'),
    ],
    'public_company': [
        ('financial',           1, 1, '{name} annual report OR 10-K OR earnings {prev_year} OR {year}'),
        ('operational',         2, 1, '{name} layoffs OR restructuring OR Glassdoor {prev_year} OR {year}'),
        ('competitive',         2, 1, '{name} market share OR activist investor OR short seller {prev_year} OR {year}'),
        ('analyst',             2, 1, '{name} analyst downgrade OR upgrade OR price target {prev_year} OR {year}'),
        ('regulatory_legal',    1, 2, '{name} antitrust OR regulatory fine OR lawsuit {prev_year} OR {year}'),
        ('employee',            3, 2, '{name} employee review OR culture OR CEO approval {prev_year} OR {year}'),
        ('customer',            2, 2, '{name} product recall OR customer complaint OR NPS {prev_year} OR {year}'),
        ('insider',             1, 2, '{name} insider selling OR buyback OR proxy statement {prev_year} OR {year}'),
    ],
    'private_company': [
        ('funding',             1, 1, '{name} funding round OR valuation OR Crunchbase {prev_year} OR {year}'),
        ('leadership',         2, 1, '{name} CEO OR CTO departure OR co-founder conflict {prev_year} OR {year}'),
        ('market_product',      2, 1, '{name} customer reviews OR G2 OR Capterra OR Trustpilot {prev_year} OR {year}'),
        ('employee',            3, 2, '{name} Glassdoor OR hiring freeze OR layoffs {prev_year} OR {year}'),
        ('competitor',          2, 2, '{name} vs competitor OR market position {prev_year} OR {year}'),
        ('legal',               1, 2, '{name} lawsuit OR legal dispute OR breach of contract {prev_year} OR {year}'),
    ],
    'dao': [
        ('governance',          1, 1, '{name} governance proposal OR vote OR treasury {prev_year} OR {year}'),
        ('community',           2, 1, '{name} community conflict OR discord OR forum {prev_year} OR {year}'),
        ('security',            1, 1, '{name} exploit OR hack OR vulnerability OR audit {prev_year} OR {year}'),
        ('tokenomics',          2, 2, '{name} TVL OR token price OR liquidity OR tokenomics {prev_year} OR {year}'),
        ('development',         2, 2, '{name} GitHub contributors OR development activity {prev_year} OR {year}'),
        ('criticism',           3, 2, '{name} criticism OR FUD OR regulatory risk {prev_year} OR {year}'),
    ],
    'market': [
        ('structure',           2, 1, '{name} industry consolidation OR fragmentation OR M&A {prev_year} OR {year}'),
        ('disruption',          2, 1, '{name} startup disruption OR technology substitution {prev_year} OR {year}'),
        ('regulatory',          1, 1, '{name} regulation OR regulatory change OR policy {prev_year} OR {year}'),
        ('competition',         2, 2, '{name} market share OR dominant player OR pricing power {prev_year} OR {year}'),
        ('capital',             2, 2, '{name} investment OR PE activity OR funding {prev_year} OR {year}'),
        ('demand',              3, 3, '{name} consumer sentiment OR demand trend OR adoption {prev_year} OR {year}'),
    ],
    'platform': [
        ('ecosystem',           2, 1, '{name} developer OR API OR third-party policy change {prev_year} OR {year}'),
        ('supply_demand',       2, 1, '{name} seller OR creator OR buyer complaint {prev_year} OR {year}'),
        ('regulatory',          1, 1, '{name} antitrust OR regulatory investigation {prev_year} OR {year}'),
        ('competition',         2, 2, '{name} competitor OR alternative OR multi-homing {prev_year} OR {year}'),
        ('trust',               2, 2, '{name} quality degradation OR spam OR trust issue {prev_year} OR {year}'),
        ('network',             3, 3, '{name} network effects OR user growth OR churn {prev_year} OR {year}'),
    ],
}

# ── 中文补充视角矩阵 ──
# 当系统涉及中文语境时，自动追加这些查询覆盖中文一级信源。
# 与英文视角互补，不替换。
CHINESE_PERSPECTIVES = {
    'geopolitical': [
        ('zh_official_media',  1, 1, '{name} site:gov.cn OR site:xinhuanet.com OR site:people.com.cn 声明 OR 公报 {prev_year} OR {year}'),
        ('zh_quality_media',   2, 1, '{name} site:caixin.com OR site:thepaper.cn OR site:ftchinese.com {prev_year} OR {year}'),
        ('zh_think_tank',      2, 1, '{name} 智库 OR 研究院 OR 政策分析 site:cssn.cn OR site:ciis.org.cn OR 中国社科院 {prev_year} OR {year}'),
        ('zh_social_signal',   3, 3, '{name} site:weibo.com OR site:zhihu.com 舆论 OR 评论 OR 讨论 {prev_year} OR {year}'),
    ],
    'government_agency': [
        ('zh_official_docs',   1, 1, '{name} 政府文件 OR 通知 OR 公告 site:gov.cn {prev_year} OR {year}'),
        ('zh_media_coverage',  2, 1, '{name} site:caixin.com OR site:thepaper.cn 改革 OR 问责 OR 审计 {prev_year} OR {year}'),
        ('zh_public_opinion',  3, 2, '{name} 群众 OR 投诉 OR 效率 OR 满意度 site:weibo.com OR site:zhihu.com {prev_year} OR {year}'),
    ],
    'public_company': [
        ('zh_financial_media', 2, 1, '{name} site:caixin.com OR site:yicai.com OR site:cls.cn 财报 OR 业绩 OR 营收 {prev_year} OR {year}'),
        ('zh_regulatory',      1, 1, '{name} site:csrc.gov.cn OR 证监会 OR 交易所 处罚 OR 问询 OR 监管 {prev_year} OR {year}'),
        ('zh_employee_signal', 3, 2, '{name} site:maimai.cn OR 脉脉 OR 知乎 裁员 OR 加班 OR 内部 {prev_year} OR {year}'),
    ],
    'private_company': [
        ('zh_tech_media',      2, 1, '{name} site:36kr.com OR site:latepost.com OR site:jiemian.com 融资 OR 裁员 OR 业务 {prev_year} OR {year}'),
        ('zh_employee_signal', 3, 2, '{name} site:maimai.cn OR 脉脉 OR 知乎 工作体验 OR 离职 OR 内部 {prev_year} OR {year}'),
    ],
    'market': [
        ('zh_industry_report', 2, 1, '{name} 行业报告 OR 市场分析 site:caixin.com OR site:yicai.com {prev_year} OR {year}'),
        ('zh_policy_impact',   1, 1, '{name} 政策 OR 监管 OR 补贴 OR 产业政策 site:gov.cn {prev_year} OR {year}'),
    ],
    'platform': [
        ('zh_platform_media',  2, 1, '{name} site:36kr.com OR site:thepaper.cn 平台治理 OR 商家投诉 OR 政策 {prev_year} OR {year}'),
        ('zh_user_signal',     3, 2, '{name} site:weibo.com OR site:zhihu.com 体验 OR 问题 OR 吐槽 {prev_year} OR {year}'),
    ],
    'dao': [],
}

# ── 其他语言补充视角矩阵（骨架 v1：仅 geopolitical 类型） ──
# 非 geopolitical 类型暂不追加本地语言视角，英文查询已足够。
# 扩展方式：为其他系统类型添加 (perspective_key, tier, priority, query_template) 元组。

LOCAL_PERSPECTIVES: dict[str, dict[str, list]] = {
    'ar': {
        'geopolitical': [
            ('ar_official_media',  1, 1, '{name} site:spa.gov.sa OR site:wam.ae OR بيان رسمي OR قرار {prev_year} OR {year}'),
            ('ar_quality_media',   2, 1, '{name} site:aljazeera.net OR site:alarabiya.net OR site:asharqalawsat.com {prev_year} OR {year}'),
            ('ar_think_tank',      2, 2, '{name} مركز دراسات OR تحليل سياسي OR أبحاث {prev_year} OR {year}'),
            ('ar_social_signal',   3, 3, '{name} تويتر OR رأي عام OR نقاش {prev_year} OR {year}'),
        ],
    },
    'fa': {
        'geopolitical': [
            ('fa_official_media',  1, 1, '{name} site:irna.ir OR site:leader.ir OR بیانیه رسمی {prev_year} OR {year}'),
            ('fa_quality_media',   2, 1, '{name} site:isna.ir OR site:farsnews.ir OR site:entekhab.ir {prev_year} OR {year}'),
            ('fa_think_tank',      2, 2, '{name} تحلیل OR پژوهش OR مرکز مطالعات {prev_year} OR {year}'),
        ],
    },
    'ru': {
        'geopolitical': [
            ('ru_official_media',  1, 1, '{name} site:kremlin.ru OR site:government.ru OR заявление {prev_year} OR {year}'),
            ('ru_quality_media',   2, 1, '{name} site:kommersant.ru OR site:rbc.ru OR site:meduza.io {prev_year} OR {year}'),
            ('ru_think_tank',      2, 2, '{name} анализ OR исследование site:carnegie.ru OR Valdai {prev_year} OR {year}'),
        ],
    },
    'ja': {
        'geopolitical': [
            ('ja_official_media',  1, 1, '{name} site:kantei.go.jp OR site:mofa.go.jp OR 声明 OR 発表 {prev_year} OR {year}'),
            ('ja_quality_media',   2, 1, '{name} site:nikkei.com OR site:asahi.com OR site:nhk.or.jp {prev_year} OR {year}'),
            ('ja_think_tank',      2, 2, '{name} 分析 OR 研究 OR 政策提言 {prev_year} OR {year}'),
        ],
    },
    'ko': {
        'geopolitical': [
            ('ko_official_media',  1, 1, '{name} site:president.go.kr OR site:mofa.go.kr OR 성명 OR 발표 {prev_year} OR {year}'),
            ('ko_quality_media',   2, 1, '{name} site:chosun.com OR site:hani.co.kr OR site:donga.com {prev_year} OR {year}'),
            ('ko_think_tank',      2, 2, '{name} 분석 OR 연구 site:kiep.go.kr OR site:kinu.or.kr {prev_year} OR {year}'),
        ],
    },
}

# ── 多语言注册表（骨架 v1） ──
# 每种语言一条配置：Unicode 检测 + 话题关键词 + T1/T2/T3 信源 + P0/P1 查询模板。
# 扩展新语言：添加一条 LANGUAGE_REGISTRY 条目 + LOCAL_PERSPECTIVES 条目即可。

LANGUAGE_REGISTRY: dict[str, dict] = {
    'zh': {
        'label': '中文',
        'unicode_pattern': re.compile(r'[一-鿿㐀-䶿]'),
        'topic_keywords': re.compile(
            r'\b(china|chinese|beijing|shanghai|shenzhen|guangzhou|hong\s*kong|taiwan|'
            r'sino|huawei|alibaba|tencent|bytedance|baidu|xiaomi|byd|catl|'
            r'ccp|prc|pla|belt\s*and\s*road|xi\s*jinping|'
            r'us.china|china.us|sino.american|cross.strait)\b',
            re.IGNORECASE,
        ),
        'sources': {
            'T1': ['gov.cn', 'pbc.gov.cn', 'csrc.gov.cn', 'cninfo.com.cn', '裁判文书网'],
            'T2': ['caixin.com', 'thepaper.cn', 'ftchinese.com', 'yicai.com', 'cls.cn', 'CIIS', '中国社科院'],
            'T3': ['weibo.com', 'zhihu.com', 'maimai.cn', '36kr.com'],
        },
        'p0_templates': {
            'recent_breaking':    '{name} 最新消息 OR 快讯 {year}年{month_zh}',
            'recent_developments': '{name} {year}年{month_zh} 协议 OR 峰会 OR 危机 OR 重大事件',
            'recent_analysis':    '{name} 深度分析 OR 解读 OR 影响 site:caixin.com OR site:thepaper.cn {year}年{month_zh}',
        },
    },
    'ar': {
        'label': '阿拉伯语',
        'unicode_pattern': re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]'),
        'topic_keywords': re.compile(
            r'\b(saudi|arabia|uae|emirates|qatar|bahrain|kuwait|oman|yemen|iraq|syria|'
            r'jordan|lebanon|egypt|libya|tunisia|algeria|morocco|sudan|'
            r'arab|arabic|riyadh|dubai|abu\s*dhabi|doha|cairo|'
            r'opec|gcc|arab\s*league|houthi|hezbollah|hamas|'
            r'mbs|mohammed\s*bin\s*salman|al.sisi|'
            r'suez|red\s*sea|strait\s*of\s*hormuz|persian\s*gulf)\b',
            re.IGNORECASE,
        ),
        'sources': {
            'T1': ['官方通讯社 (WAM/SPA/KUNA)', 'GCC 官方公报'],
            'T2': ['aljazeera.net', 'alarabiya.net', 'asharqalawsat.com', 'independentarabia.com', 'Al-Ahram'],
            'T3': ['Twitter/X 阿拉伯语', '阿拉伯语论坛'],
        },
        'p0_templates': {
            'recent_breaking':    '{name} آخر الأخبار OR أحدث التطورات {year}',
            'recent_developments': '{name} اتفاقية OR قمة OR أزمة {month_en} {year}',
            'recent_analysis':    '{name} تحليل OR تقييم site:aljazeera.net OR site:alarabiya.net {year}',
        },
    },
    'fa': {
        'label': '波斯语',
        'unicode_pattern': re.compile(r'[؀-ۿ](?:.*[پچژگی])'),
        'topic_keywords': re.compile(
            r'\b(iran|iranian|tehran|persian|persia|'
            r'khamenei|raisi|rouhani|irgc|quds\s*force|'
            r'jcpoa|nuclear\s*deal|sanctions?\s*iran|'
            r'strait\s*of\s*hormuz|iran.saudi|iran.israel|'
            r'hezbollah|proxy\s*war|shia|shiite)\b',
            re.IGNORECASE,
        ),
        'sources': {
            'T1': ['irna.ir (IRNA)', 'leader.ir (最高领袖办公室)', 'dolat.ir (总统府)'],
            'T2': ['isna.ir', 'farsnews.ir', 'entekhab.ir', 'shargh daily', 'Bourse & Bazaar'],
            'T3': ['Twitter/X 波斯语', 'Clubhouse 波斯语', 'Telegram 频道'],
        },
        'p0_templates': {
            'recent_breaking':    '{name} آخرین اخبار OR تازه‌ترین {year}',
            'recent_developments': '{name} توافق OR بحران OR نشست {month_en} {year}',
            'recent_analysis':    '{name} تحلیل site:isna.ir OR site:farsnews.ir {year}',
        },
    },
    'ru': {
        'label': '俄语',
        'unicode_pattern': re.compile(r'[Ѐ-ӿ]'),
        'topic_keywords': re.compile(
            r'\b(russia|russian|moscow|kremlin|putin|'
            r'ukraine|donbas|crimea|nato\s*russia|'
            r'gazprom|rosneft|sberbank|rosatom|'
            r'sino.russian|russia.china|brics|sco|'
            r'csto|wagner|prigozhin|lavrov|medvedev)\b',
            re.IGNORECASE,
        ),
        'sources': {
            'T1': ['kremlin.ru', 'government.ru', 'duma.gov.ru', 'cbr.ru (央行)'],
            'T2': ['kommersant.ru', 'rbc.ru', 'meduza.io', 'novayagazeta.eu', 'Carnegie Russia/Eurasia'],
            'T3': ['Telegram 频道', 'VK', 'Pikabu'],
        },
        'p0_templates': {
            'recent_breaking':    '{name} последние новости {month_en} {year}',
            'recent_developments': '{name} соглашение OR саммит OR кризис {month_en} {year}',
            'recent_analysis':    '{name} анализ site:kommersant.ru OR site:rbc.ru {year}',
        },
    },
    'ja': {
        'label': '日语',
        'unicode_pattern': re.compile(r'[぀-ゟ゠-ヿ]'),
        'topic_keywords': re.compile(
            r'\b(japan|japanese|tokyo|osaka|'
            r'kishida|fumio|ldp|'
            r'toyota|sony|softbank|nintendo|honda|'
            r'boj|bank\s*of\s*japan|yen|nikkei|'
            r'japan.china|japan.korea|quad|indo.pacific|'
            r'fukushima|okinawa|self.defense\s*force)\b',
            re.IGNORECASE,
        ),
        'sources': {
            'T1': ['kantei.go.jp (首相官邸)', 'mof.go.jp (财务省)', 'boj.or.jp (日本银行)'],
            'T2': ['nikkei.com (日经)', 'asahi.com (朝日)', 'mainichi.jp (每日)', 'nhk.or.jp', 'toyokeizai.net (东洋经济)'],
            'T3': ['Twitter/X 日语', '5ch/2ch', 'Yahoo! Japan 评论'],
        },
        'p0_templates': {
            'recent_breaking':    '{name} 最新ニュース {year}年{month_en}',
            'recent_developments': '{name} 合意 OR 首脳会談 OR 危機 {month_en} {year}',
            'recent_analysis':    '{name} 分析 OR 解説 site:nikkei.com OR site:toyokeizai.net {year}',
        },
    },
    'ko': {
        'label': '韩语',
        'unicode_pattern': re.compile(r'[가-힯ᄀ-ᇿ]'),
        'topic_keywords': re.compile(
            r'\b(korea|korean|seoul|pyongyang|'
            r'north\s*korea|south\s*korea|dprk|rok|'
            r'samsung|hyundai|sk\s*hynix|lg|kia|'
            r'kim\s*jong|yoon\s*suk|'
            r'korea.japan|korea.china|dmz|38th\s*parallel|'
            r'k.pop|hallyu|chaebol)\b',
            re.IGNORECASE,
        ),
        'sources': {
            'T1': ['president.go.kr (青瓦台/龙山)', 'mofa.go.kr (外交部)', 'bok.or.kr (韩国银行)'],
            'T2': ['chosun.com (朝鲜日报)', 'hani.co.kr (韩民族)', 'donga.com (东亚日报)', 'mk.co.kr (每日经济)', 'KBS/MBC'],
            'T3': ['Naver 评论', 'DC Inside', 'Twitter/X 韩语'],
        },
        'p0_templates': {
            'recent_breaking':    '{name} 최신 뉴스 {year}년 {month_en}',
            'recent_developments': '{name} 합의 OR 정상회담 OR 위기 {month_en} {year}',
            'recent_analysis':    '{name} 분석 site:chosun.com OR site:hani.co.kr {year}',
        },
    },
}


def detect_languages(system_name: str, force_langs: set[str] | None = None) -> set[str]:
    """
    检测系统名称/主题涉及哪些本地语言。

    返回语言代码集合（如 {'zh', 'fa'}）。空集 = 仅英文。
    可同时触发多个语言（如 "Saudi-Iran proxy war" → {'ar', 'fa'}）。
    force_langs 用于显式覆盖自动检测。
    """
    if force_langs is not None:
        return force_langs

    matched = set()
    for lang_code, config in LANGUAGE_REGISTRY.items():
        if config['unicode_pattern'].search(system_name):
            matched.add(lang_code)
        elif config['topic_keywords'].search(system_name):
            matched.add(lang_code)
    return matched


def _needs_chinese_queries(system_name: str, system_type: str, force_zh: bool | None = None) -> bool:
    """向后兼容：检测是否需要中文查询。内部转发到 detect_languages。"""
    if force_zh is not None:
        return force_zh
    return 'zh' in detect_languages(system_name)


PERSPECTIVE_LABELS = {
    'official_domestic':  '官方/官媒',
    'opposition_dissident': '反对派/异见',
    'western_media':      '西方主流媒体',
    'regional_neighbors': '区域/邻国媒体',
    'leadership_power':   '领导层/权力结构',
    'non_western_powers': '非西方大国视角',
    'think_tank':         '智库/学术',
    'economic_indicators':'经济指标',
    'military_security':  '军事/安全',
    'civil_society':      '公民社会/NGO',
    'accountability':     '监察/审计',
    'performance':        '履职/绩效',
    'political':          '政治合法性',
    'employee_morale':    '员工士气',
    'public_trust':       '公众信任',
    'capture':            '行业俘获',
    'financial':          '财务/治理',
    'operational':        '运营/文化',
    'competitive':        '竞争叙事',
    'analyst':            '分析师共识',
    'regulatory_legal':   '监管/法律',
    'employee':           '员工信号',
    'customer':           '客户/产品',
    'insider':            '内部人动向',
    'funding':            '融资/投资人',
    'leadership':         '领导层/人事',
    'market_product':     '市场/产品',
    'competitor':         '竞争对手',
    'legal':              '法律纠纷',
    'governance':         '链上治理',
    'community':          '社区健康',
    'security':           '协议安全',
    'tokenomics':         '代币经济',
    'development':        '开发者活跃度',
    'criticism':          '外部批评',
    'structure':          '行业结构',
    'disruption':         '颠覆性信号',
    'regulatory':         '监管冲击',
    'competition':        '竞争动态',
    'capital':            '资金流向',
    'demand':             '消费者需求',
    'ecosystem':          '生态健康',
    'supply_demand':      '供给/需求侧',
    'trust':              '信任/质量',
    'network':            '网络效应',
    'recent_breaking':    '近期突发/快讯',
    'recent_developments':'近期重大进展',
    'recent_analysis':    '近期深度分析',
    'zh_recent_breaking':    '中文近期快讯',
    'zh_recent_developments':'中文近期重大进展',
    'zh_recent_analysis':    '中文近期深度分析',
    'zh_official_media':  '中文官方媒体',
    'zh_quality_media':   '中文优质媒体',
    'zh_think_tank':      '中文智库/研究院',
    'zh_social_signal':   '中文社交信号',
    'zh_official_docs':   '中文政府文件',
    'zh_media_coverage':  '中文媒体报道',
    'zh_public_opinion':  '中文公众舆论',
    'zh_financial_media': '中文财经媒体',
    'zh_regulatory':      '中文监管信号',
    'zh_employee_signal': '中文员工信号',
    'zh_tech_media':      '中文科技媒体',
    'zh_industry_report': '中文行业报告',
    'zh_policy_impact':   '中文政策影响',
    'zh_platform_media':  '中文平台媒体',
    'zh_user_signal':     '中文用户信号',
    # 阿拉伯语
    'ar_recent_breaking':    '阿拉伯语近期快讯',
    'ar_recent_developments':'阿拉伯语近期进展',
    'ar_recent_analysis':    '阿拉伯语近期分析',
    'ar_official_media':  '阿拉伯语官方媒体',
    'ar_quality_media':   '阿拉伯语优质媒体',
    'ar_think_tank':      '阿拉伯语智库',
    'ar_social_signal':   '阿拉伯语社交信号',
    # 波斯语
    'fa_recent_breaking':    '波斯语近期快讯',
    'fa_recent_developments':'波斯语近期进展',
    'fa_recent_analysis':    '波斯语近期分析',
    'fa_official_media':  '波斯语官方媒体',
    'fa_quality_media':   '波斯语优质媒体',
    'fa_think_tank':      '波斯语智库',
    # 俄语
    'ru_recent_breaking':    '俄语近期快讯',
    'ru_recent_developments':'俄语近期进展',
    'ru_recent_analysis':    '俄语近期分析',
    'ru_official_media':  '俄语官方媒体',
    'ru_quality_media':   '俄语优质媒体',
    'ru_think_tank':      '俄语智库',
    # 日语
    'ja_recent_breaking':    '日语近期快讯',
    'ja_recent_developments':'日语近期进展',
    'ja_recent_analysis':    '日语近期分析',
    'ja_official_media':  '日语官方媒体',
    'ja_quality_media':   '日语优质媒体',
    'ja_think_tank':      '日语智库',
    # 韩语
    'ko_recent_breaking':    '韩语近期快讯',
    'ko_recent_developments':'韩语近期进展',
    'ko_recent_analysis':    '韩语近期分析',
    'ko_official_media':  '韩语官方媒体',
    'ko_quality_media':   '韩语优质媒体',
    'ko_think_tank':      '韩语智库',
}

TIER_LABELS = {
    1: '一级（原始/官方文件）',
    2: '二级（机构媒体/分析报告）',
    3: '三级（社区/间接信号）',
}


MONTH_NAMES_EN = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


def _resolve_years(date_str: str | None = None) -> tuple[int, int]:
    if date_str:
        year = int(date_str[:4])
    else:
        year = datetime.now().year
    return year, year - 1


def _resolve_date_parts(date_str: str | None = None) -> dict:
    if date_str:
        dt = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
    else:
        dt = datetime.now()
    month = dt.month
    prev_month = month - 1 if month > 1 else 12
    return {
        'year': dt.year,
        'prev_year': dt.year - 1,
        'month': month,
        'month_name': MONTH_NAMES_EN[month],
        'prev_month_name': MONTH_NAMES_EN[prev_month],
    }


MONTH_NAMES_ZH = [
    '', '1月', '2月', '3月', '4月', '5月', '6月',
    '7月', '8月', '9月', '10月', '11月', '12月',
]


def _build_recent_events_queries(
    system_name: str,
    date_parts: dict,
    detected_langs: set[str] | None = None,
    include_zh: bool = False,
) -> list[dict]:
    mn = date_parts['month_name']
    pmn = date_parts['prev_month_name']
    yr = date_parts['year']
    mz = MONTH_NAMES_ZH[date_parts['month']]

    if detected_langs is None:
        detected_langs = set()
    if include_zh:
        detected_langs = detected_langs | {'zh'}

    templates: list[tuple[str, int, int, str, str]] = [
        ('recent_breaking',    2, 0, f'{system_name} latest news {mn} {yr}', 'en'),
        ('recent_developments',2, 0, f'{system_name} {mn} OR {pmn} {yr} summit OR deal OR agreement OR crisis OR announcement', 'en'),
        ('recent_analysis',    2, 0, f'{system_name} analysis OR takeaways OR implications {mn} {yr}', 'en'),
    ]

    fmt_vars = {
        'name': system_name, 'year': yr, 'month_en': mn,
        'month_zh': mz, 'prev_month_en': pmn,
    }

    for lang_code in sorted(detected_langs):
        config = LANGUAGE_REGISTRY.get(lang_code)
        if not config or 'p0_templates' not in config:
            continue
        for key, tpl in config['p0_templates'].items():
            perspective = f'{lang_code}_{key}'
            query = tpl.format(**fmt_vars)
            templates.append((perspective, 2, 0, query, lang_code))

    results = []
    for perspective, tier, priority, query, lang in templates:
        results.append({
            'perspective':       perspective,
            'perspective_label': PERSPECTIVE_LABELS.get(perspective, perspective),
            'tier':              tier,
            'tier_label':        TIER_LABELS[tier],
            'priority':          priority,
            'query':             query,
            'lang':              lang,
        })
    return results


def generate_queries(
    system_name: str,
    system_type: str,
    date_str: str | None = None,
    force_zh: bool | None = None,
    force_langs: set[str] | None = None,
) -> dict:
    """
    生成标准化多视角搜索查询集。

    参数：
      system_name: 系统名称，如 "伊朗最高决策体系" / "ByteDance"
      system_type: 系统类型，见 SYSTEM_TYPES
      date_str:    可选，YYYYMMDD，控制查询的年份过滤器（默认当前年份）
      force_zh:    可选，强制启用/禁用中文查询（None=自动检测）（向后兼容）
      force_langs: 可选，强制指定本地语言集合（覆盖自动检测）

    返回：
      {
        system_name, system_type, analysis_date, year_filter,
        total_queries, priority_0_count, priority_1_count,
        detected_languages: [str],
        chinese_enabled, chinese_query_count,   # 向后兼容
        local_language_counts: {lang: int},
        perspectives: [{perspective, perspective_label, tier, tier_label, priority, query, lang}],
        required_perspective_coverage: [str],
        p2_perspective_coverage: [str],
      }
    """
    if system_type not in PERSPECTIVE_MATRIX:
        raise ValueError(f"未知系统类型: {system_type}，可用：{SYSTEM_TYPES}")

    date_parts = _resolve_date_parts(date_str)
    year, prev_year = date_parts['year'], date_parts['prev_year']

    if force_langs is not None:
        detected = force_langs
    elif force_zh is not None:
        detected = detect_languages(system_name)
        if force_zh:
            detected = detected | {'zh'}
        else:
            detected = detected - {'zh'}
    else:
        detected = detect_languages(system_name)

    recent = _build_recent_events_queries(system_name, date_parts, detected_langs=detected)

    templates = PERSPECTIVE_MATRIX[system_type]
    structural = []
    for perspective, tier, priority, template in templates:
        structural.append({
            'perspective':       perspective,
            'perspective_label': PERSPECTIVE_LABELS.get(perspective, perspective),
            'tier':              tier,
            'tier_label':        TIER_LABELS[tier],
            'priority':          priority,
            'query':             template.format(name=system_name, year=year, prev_year=prev_year),
            'lang':              'en',
        })

    local_structural: list[dict] = []

    if 'zh' in detected:
        zh_templates = CHINESE_PERSPECTIVES.get(system_type, [])
        for perspective, tier, priority, template in zh_templates:
            local_structural.append({
                'perspective':       perspective,
                'perspective_label': PERSPECTIVE_LABELS.get(perspective, perspective),
                'tier':              tier,
                'tier_label':        TIER_LABELS[tier],
                'priority':          priority,
                'query':             template.format(name=system_name, year=year, prev_year=prev_year),
                'lang':              'zh',
            })

    for lang_code in sorted(detected - {'zh'}):
        lang_matrix = LOCAL_PERSPECTIVES.get(lang_code, {})
        lang_templates = lang_matrix.get(system_type, [])
        for perspective, tier, priority, template in lang_templates:
            local_structural.append({
                'perspective':       perspective,
                'perspective_label': PERSPECTIVE_LABELS.get(perspective, perspective),
                'tier':              tier,
                'tier_label':        TIER_LABELS[tier],
                'priority':          priority,
                'query':             template.format(name=system_name, year=year, prev_year=prev_year),
                'lang':              lang_code,
            })

    perspectives = recent + structural + local_structural
    perspectives.sort(key=lambda x: x['priority'])

    required = [p['perspective'] for p in perspectives if p['priority'] <= 1]
    p2_coverage = [p['perspective'] for p in perspectives if p['priority'] == 2]

    lang_counts: dict[str, int] = {}
    for p in perspectives:
        lang = p.get('lang', 'en')
        if lang != 'en':
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    return {
        'system_name':                  system_name,
        'system_type':                  system_type,
        'analysis_date':                date_str or datetime.now().strftime('%Y%m%d'),
        'year_filter':                  f'{prev_year} OR {year}',
        'month_filter':                 f"{date_parts['month_name']} {year}",
        'total_queries':                len(perspectives),
        'priority_0_count':             len(recent),
        'priority_1_count':             len([p for p in structural + local_structural if p['priority'] == 1]),
        'detected_languages':           sorted(detected),
        'chinese_enabled':              'zh' in detected,
        'chinese_query_count':          lang_counts.get('zh', 0),
        'local_language_counts':        lang_counts,
        'perspectives':                 perspectives,
        'required_perspective_coverage': required,
        'p2_perspective_coverage':      p2_coverage,
    }


def group_into_batches(query_result: dict, max_batches: int = 4) -> list[dict]:
    """
    将 Priority 0 + Priority 1 视角分组为并行 Researcher 批次。

    Batch 0: 近期事件扫描（所有语言，Priority 0）
    Batch 1-N: 英文结构性视角（对立视角同批）
    Batch N+1...: 每种本地语言独立一个批次（确保采集不被跳过）
    """
    p0 = [p for p in query_result['perspectives'] if p['priority'] == 0]
    p1_en = [p for p in query_result['perspectives']
             if p['priority'] == 1 and p.get('lang', 'en') == 'en']

    local_langs = sorted({
        p.get('lang') for p in query_result['perspectives']
        if p['priority'] == 1 and p.get('lang', 'en') != 'en'
    })

    result = []

    if p0:
        result.append({
            'batch_id':     0,
            'perspectives': p0,
            'queries':      [p['query'] for p in p0],
            'batch_label':  '近期事件扫描（Priority 0）',
        })

    OPPOSING_PAIRS = [
        ('official_domestic', 'opposition_dissident'),
        ('financial', 'employee'),
        ('competitive', 'analyst'),
    ]

    batched = []
    assigned = set()

    for a, b in OPPOSING_PAIRS:
        a_items = [p for p in p1_en if p['perspective'] == a and p['perspective'] not in assigned]
        b_items = [p for p in p1_en if p['perspective'] == b and p['perspective'] not in assigned]
        if a_items and b_items:
            batch_perspectives = a_items + b_items
            batched.append(batch_perspectives)
            assigned.update(p['perspective'] for p in batch_perspectives)

    remaining = [p for p in p1_en if p['perspective'] not in assigned]
    if remaining:
        chunk_size = max(1, len(remaining) // max(1, max_batches - len(batched)))
        for i in range(0, len(remaining), chunk_size):
            batched.append(remaining[i:i + chunk_size])

    for i, batch in enumerate(batched, 1):
        labels = [p['perspective_label'] for p in batch]
        result.append({
            'batch_id':    i,
            'perspectives': batch,
            'queries':     [p['query'] for p in batch],
            'batch_label': ' / '.join(labels),
        })

    for lang_code in local_langs:
        p1_lang = [p for p in query_result['perspectives']
                   if p['priority'] == 1 and p.get('lang') == lang_code]
        if p1_lang:
            lang_label = LANGUAGE_REGISTRY.get(lang_code, {}).get('label', lang_code)
            labels = [p['perspective_label'] for p in p1_lang]
            result.append({
                'batch_id':     len(result),
                'perspectives': p1_lang,
                'queries':      [p['query'] for p in p1_lang],
                'batch_label':  f'{lang_label}信源采集: ' + ' / '.join(labels),
            })

    return result


_LANG_FLAGS = {
    'zh': '🇨🇳', 'ar': '🇸🇦', 'fa': '🇮🇷', 'ru': '🇷🇺', 'ja': '🇯🇵', 'ko': '🇰🇷',
}


def format_for_claude(query_result: dict) -> str:
    """将查询集格式化为研究任务清单（供 Claude 执行）。"""
    detected = query_result.get('detected_languages', [])
    if detected:
        lang_labels = [LANGUAGE_REGISTRY.get(l, {}).get('label', l) for l in detected]
        lang_flag = '🌐 多语言: ' + '/'.join(lang_labels)
    else:
        lang_flag = '🔤 英文模式'

    lines = [
        f'## 研究任务清单：{query_result["system_name"]}',
        f'系统类型：{query_result["system_type"]} ｜ 总查询数：{query_result["total_queries"]} ｜ {lang_flag}',
        '',
    ]

    lang_counts = query_result.get('local_language_counts', {})
    if lang_counts:
        for lc, cnt in sorted(lang_counts.items()):
            label = LANGUAGE_REGISTRY.get(lc, {}).get('label', lc)
            lines.append(f'{label}查询数：{cnt} 条')
        lines.append('')

    p0 = [p for p in query_result['perspectives'] if p['priority'] == 0]
    if p0:
        lines += ['### 🔴 近期事件扫描（Priority 0 — 最先执行，确保捕获最近 30 天重大事件）', '']
        for p in p0:
            flag = _LANG_FLAGS.get(p.get('lang', ''), '')
            if flag:
                flag = ' ' + flag
            lines.append(f'**[{p["perspective_label"]}{flag}]** `{p["query"]}`')
        lines.append('')

    p1 = [p for p in query_result['perspectives'] if p['priority'] == 1]
    p1_en = [p for p in p1 if p.get('lang', 'en') == 'en']

    if p1_en:
        lines += ['### ⛔ 门控查询 — 英文信源（Priority 1）', '']
        for p in p1_en:
            lines.append(f'**[{p["perspective_label"]}]** `{p["query"]}`')

    for lang_code in sorted(detected):
        p1_lang = [p for p in p1 if p.get('lang') == lang_code]
        if p1_lang:
            label = LANGUAGE_REGISTRY.get(lang_code, {}).get('label', lang_code)
            flag = _LANG_FLAGS.get(lang_code, '')
            lines += ['', f'### ⛔ 门控查询 — {label}信源 {flag}（Priority 1）', '']
            for p in p1_lang:
                lines.append(f'**[{p["perspective_label"]}]** `{p["query"]}`')

    p_rest = [p for p in query_result['perspectives'] if p['priority'] > 1]
    if p_rest:
        lines += ['', '### 建议查询（Priority 2-3 — 增强分析深度）', '']
        for p in p_rest:
            flag = _LANG_FLAGS.get(p.get('lang', ''), '')
            if flag:
                flag = ' ' + flag
            lines.append(f'[{p["perspective_label"]}{flag} / {p["tier_label"]}] `{p["query"]}`')

    req = ', '.join(query_result['required_perspective_coverage'])
    p2_cov = ', '.join(query_result.get('p2_perspective_coverage', []))
    lines += [
        '',
        '### 研究门控检查清单',
        f'- [ ] 已覆盖所有 P0+P1 必须视角：{req}',
        '- [ ] 每个视角至少记录 1 条有效信源（无结果须标注「未找到」）',
        '- [ ] Priority 0 近期事件已扫描，最近 30 天重大事件已记录',
        '- [ ] 矛盾信号已在 Research Brief 中显式标注',
        f'- [ ] P2 建议视角覆盖率 ≥ 50%：{p2_cov}',
        '- [ ] Research Brief 完成后方可进入六维分析',
    ]

    return '\n'.join(lines)
