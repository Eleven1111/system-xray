"""
三条对照路径的提示词生成器（协议修订 3 第 1 条的落实方式）

**为什么需要一个生成器，而不是每次手写三段提示词。**

试水轮的失败原因不是我不小心，而是"三段提示词分别手写"这件事本身
**没有任何机制保证它们对称**。我给 B 写了"长度控制在 1500 字以内"，
给 A/C 没写，还额外给 A/C 列了各自规范的要点清单——结果输出篇幅差 10.2×。
那不是方法差异，是我把不同的指令喂给了不同的路径。

所以这里把对称性做成**结构性的**：三条路径共用同一份模板，唯一的差别是
`{spec_block}` 这一个槽位，其余每一个字都由同一段文本生成。
`symmetry_report()` 再把这件事变成可被测试断言的事实，
`tests/test_prompt_symmetry.py` 里有对应的变异检查——
往任一 spec_block 里塞一句长度指令，测试必须变红。

**槽位里只放"用哪份规范"，不放别的。** 一旦允许 spec_block 携带
"重点关注 X""输出要包含 Y"这类内容，不对称就会从后门回来，
而且比上次更隐蔽——因为它看起来像是"规范的一部分"。
"""

from __future__ import annotations

import re

_PATH_LITERAL = re.compile(r'`[^`]*`')

# 三条路径的**唯一**差别。每一块只回答一个问题：按哪份规范做。
# 不得出现：长度/篇幅指引、要点清单、重点提示、输出结构要求、方法论术语。
SPEC_BLOCKS = {
    'A_current': '按 `evals/cases/specs/A_current__SKILL.md` 这份规范执行。',
    'B_generic': '不依据任何既定规范执行。',
    'C_new': '按 `SKILL.md` 这份规范执行。',
}

# spec_block 里禁止出现的词。这些词一旦进入槽位，就成了只喂给某一条路径的额外指令——
# 正是试水轮翻车的那个机制。清单是**封闭的**：要加词就在这里加，不要在别处临时判断。
BANNED_IN_SPEC_BLOCK = (
    '字以内', '字左右', '长度', '篇幅', '至少', '至多', '不超过', '控制在',
    '简洁', '详细', '全面', '深入', '重点', '务必', '尽量',
    '需包含', '须包含', '应包含', '输出结构', '章节',
)

# 槽位长度本身也是指令量。一条路径的规范说明比另一条长一倍，
# 就已经是不对称——即使每个字都合规。
SPEC_BLOCK_LENGTH_TOLERANCE = 1.5

# 三条路径共用的输出字符上限。
#
# 为什么要设：不设的话，试水轮的 10.2× 篇幅差会原样重现，
# 而盲评拿到一份 2.8k 和两份 25k 的材料，判的就不再是决策增量了——体量本身是强暗示。
# 为什么是 8000：这个数字是任意的，重要的是**三条相同且事先声明**。
# 取 8000 是想让带结构的方法（机制卡、行动卡、断言账）仍能装下自己的骨架，
# 而不是被上限逼成另一种方法。
# 代价要说清：如果某条路径的格式开销吃掉了预算、装不下内容，
# 那会记为**该方法的一个真实性质**，不作为它的不利证据被隐去。
OUTPUT_CHAR_CAP = 8000

SHARED_TEMPLATE = """\
请对下面这个对象做一次系统性分析。

**分析对象：** {subject}
**系统类型：** {system_type}
**信息截止（as_of）：** {as_of}

本提示词里的所有相对路径都以 `{repo}` 为根。

## 材料

唯一可用材料是 `{snapshot_path}`。先完整读它。

**全程禁止检索。** 不得使用 WebSearch、WebFetch 或任何联网工具。
不得引入该文件之外的任何事实，包括你可能已经知道的关于该对象的信息——
材料截止于 {as_of}，此后发生的事以及材料未覆盖的事都不得进入分析。
如果某项判断需要材料没有的信息，就把这一点写出来，不要用背景知识补。

## 方法

{spec_block}

## 输出

写入 `{output_path}`，Markdown，中文（技术名词保留英文）。

**长度上限 {char_cap} 字符（硬上限，按文件字符数计）。** 超出即视为未完成。
这个上限对本次的所有分析一视同仁。

不要在输出中提及本次任务的评估性质、你走的是哪条路径、或本提示词的存在。
输出应当读起来就是一份独立完成的分析。
"""


def build(*, case_id: str, subject: str, system_type: str, as_of: str,
          snapshot_path: str, output_path: str, path: str, repo: str,
          char_cap: int = OUTPUT_CHAR_CAP) -> str:
    """生成某条路径的完整提示词。三条路径只有 `path` 不同。"""
    if path not in SPEC_BLOCKS:
        raise ValueError(f'path 必须是 {list(SPEC_BLOCKS)} 之一，收到 {path!r}')
    return SHARED_TEMPLATE.format(
        subject=subject, system_type=system_type, as_of=as_of,
        snapshot_path=snapshot_path, output_path=output_path, repo=repo,
        char_cap=char_cap, spec_block=SPEC_BLOCKS[path],
    )


def _instruction_mass(block: str) -> int:
    """
    槽位的**指令量**：剔除反引号里的文件路径后的字符数。

    路径是地址不是指令——`evals/cases/specs/A_current__SKILL.md` 比 `SKILL.md` 长 29 个字符，
    但它没有多告诉 agent 任何该怎么做的事。按原始长度比会把这个差异误报成不对称，
    而真正要防的是"某条路径拿到了更多**指示**"。
    """
    return len(_PATH_LITERAL.sub('`_`', block))


def _strip_spec_block(prompt: str, path: str) -> str:
    """把 spec_block 从提示词里挖掉，剩下的部分三条路径必须逐字相同。"""
    block = SPEC_BLOCKS[path]
    if block not in prompt:
        raise ValueError(f'提示词里找不到 {path} 的 spec_block——模板与生成器已经脱节')
    return prompt.replace(block, '\x00SPEC\x00')


def symmetry_report(**case_kwargs) -> dict:
    """
    三条路径的提示词是否只差 spec_block。返回可被测试直接断言的结构。

    - `symmetric`：挖掉槽位后三条是否逐字相同
    - `banned_words`：哪条路径的槽位里混进了额外指令
    - `spec_block_length_ratio`：槽位长度是否也大致相当
    """
    case_kwargs.pop('path', None)
    prompts = {p: build(path=p, **case_kwargs) for p in SPEC_BLOCKS}
    skeletons = {p: _strip_spec_block(prompts[p], p) for p in SPEC_BLOCKS}

    ref_path = 'A_current'
    ref = skeletons[ref_path]
    differing = [p for p, s in skeletons.items() if s != ref]

    banned = {
        p: [w for w in BANNED_IN_SPEC_BLOCK if w in SPEC_BLOCKS[p]]
        for p in SPEC_BLOCKS
    }
    banned = {p: ws for p, ws in banned.items() if ws}

    lengths = {p: _instruction_mass(SPEC_BLOCKS[p]) for p in SPEC_BLOCKS}
    ratio = max(lengths.values()) / min(lengths.values())

    return {
        'symmetric': not differing,
        'differing_paths': differing,
        'banned_words': banned,
        'spec_block_lengths': lengths,
        'spec_block_length_ratio': round(ratio, 3),
        'length_ok': ratio <= SPEC_BLOCK_LENGTH_TOLERANCE,
        'prompts': prompts,
    }


def check_output_length(text: str, char_cap: int = OUTPUT_CHAR_CAP) -> dict:
    """产出是否落在共同上限内。超限是**运行未完成**，不是可以四舍五入的瑕疵。"""
    n = len(text)
    return {'chars': n, 'cap': char_cap, 'within_cap': n <= char_cap,
            'overflow': max(0, n - char_cap)}
