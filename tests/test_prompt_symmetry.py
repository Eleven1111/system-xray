"""
提示词对称性的守卫（协议修订 3 第 1 条）

这套测试守的是一个**容易被静默绕过**的性质：三条对照路径的指令必须只差一个槽位。
试水轮就是在这里翻的车，而且翻得毫无察觉——三段手写提示词看上去都很合理，
只有把它们并排逐字比较才看得出不对称。

按 testing.md 的要求，每条断言都配了变异：把不对称重新引入，测试必须变红。
一条永不失败的检查和没有检查，信息量相同。
"""

import pytest

from evals import prompt_builder as pb

CASE = dict(
    case_id='T-01',
    subject='某测试对象',
    system_type='platform',
    as_of='2026-09-09',
    snapshot_path='materials/snapshot.md',
    output_path='outputs/fixed_material__X.md',
    repo='/repo/system-xray',
)


def test_three_prompts_differ_only_in_spec_block():
    rep = pb.symmetry_report(**CASE)
    assert rep['symmetric'], f'非对称路径：{rep["differing_paths"]}'


def test_mutation_extra_instruction_in_one_path_is_caught():
    """变异：给 B 的槽位加一句长度指令——正是试水轮的那个错误。必须变红。"""
    original = pb.SPEC_BLOCKS['B_generic']
    pb.SPEC_BLOCKS['B_generic'] = original + ' 长度控制在 1500 字以内。'
    try:
        rep = pb.symmetry_report(**CASE)
        # 挖槽位后骨架仍然相同（这正是危险之处——只看骨架发现不了），
        # 所以必须由 banned_words 这一层拦住。
        assert rep['banned_words'], '变异未被拦住：槽位里塞进长度指令却没有任何检查报警'
        assert 'B_generic' in rep['banned_words']
    finally:
        pb.SPEC_BLOCKS['B_generic'] = original


def test_mutation_skeleton_divergence_is_caught():
    """变异：让某条路径的模板多一段。必须变红。"""
    original = pb.SHARED_TEMPLATE
    real_build = pb.build

    def fake_build(*, path, **kw):
        out = real_build(path=path, **kw)
        return out + '\n请特别关注治理结构。\n' if path == 'C_new' else out

    pb.build = fake_build
    try:
        rep = pb.symmetry_report(**CASE)
        assert not rep['symmetric'], '变异未被拦住：某条路径多了一段指令却仍判为对称'
        assert 'C_new' in rep['differing_paths']
    finally:
        pb.build = real_build
        pb.SHARED_TEMPLATE = original


def test_no_op_control_stays_green():
    """空操作对照：改动一个与对称性无关的量（上限数值，三条同改），应保持绿。

    没有这条，上面两个变异"变红了"也可能只是因为我碰了任何东西它都会红。
    """
    rep = pb.symmetry_report(char_cap=12345, **CASE)
    assert rep['symmetric']
    assert not rep['banned_words']


def test_spec_blocks_carry_no_extra_instruction():
    rep = pb.symmetry_report(**CASE)
    assert not rep['banned_words'], f'槽位里混进了额外指令：{rep["banned_words"]}'


def test_spec_block_lengths_are_comparable():
    """槽位长度本身也是指令量——一条比另一条长一倍就已经不对称了。"""
    rep = pb.symmetry_report(**CASE)
    assert rep['length_ok'], (
        f'槽位长度差 {rep["spec_block_length_ratio"]}×：{rep["spec_block_lengths"]}')


def test_mutation_extra_instruction_mass_is_caught():
    """变异：给一条槽位加一句不含违禁词、但确实是额外指示的话。

    这是 banned_words 兜不住的那一类——所以必须由指令量比值兜住。
    """
    original = pb.SPEC_BLOCKS['C_new']
    pb.SPEC_BLOCKS['C_new'] = original + '按它列出的每一节顺序推进，逐节交付其要求的产物。'
    try:
        rep = pb.symmetry_report(**CASE)
        assert not rep['length_ok'], (
            f'变异未被拦住：槽位多了一句指示却仍判为长度相当'
            f'（{rep["spec_block_lengths"]}）')
    finally:
        pb.SPEC_BLOCKS['C_new'] = original


def test_path_length_does_not_count_as_instruction_mass():
    """负控：把 A 的规范挪到一个更长的路径下，不应触发不对称——路径是地址不是指令。"""
    original = pb.SPEC_BLOCKS['A_current']
    pb.SPEC_BLOCKS['A_current'] = (
        '按 `evals/cases/specs/some/deeper/place/A_current__SKILL_v1.md` 这份规范执行。')
    try:
        rep = pb.symmetry_report(**CASE)
        assert rep['length_ok'], '路径变长被误报成指令不对称'
        assert rep['symmetric']
    finally:
        pb.SPEC_BLOCKS['A_current'] = original


def test_char_cap_is_identical_across_paths():
    """长度上限必须在共享模板里，不能是三条各写各的。"""
    prompts = pb.symmetry_report(**CASE)['prompts']
    caps = {p: str(pb.OUTPUT_CHAR_CAP) in t for p, t in prompts.items()}
    assert all(caps.values()), f'有路径没有拿到共同上限：{caps}'


@pytest.mark.parametrize('path', sorted(pb.SPEC_BLOCKS))
def test_prompt_forbids_retrieval_for_every_path(path):
    """固定材料轮的核心约束不能只写给其中一条。"""
    p = pb.build(path=path, **CASE)
    assert '禁止检索' in p


def test_check_output_length():
    assert pb.check_output_length('x' * 100, char_cap=200)['within_cap']
    over = pb.check_output_length('x' * 300, char_cap=200)
    assert not over['within_cap'] and over['overflow'] == 100


def test_unknown_path_rejected():
    with pytest.raises(ValueError):
        pb.build(path='D_something', **CASE)
