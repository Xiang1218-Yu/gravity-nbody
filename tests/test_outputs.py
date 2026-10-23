"""Behavior tests for the two-dimensional gravity simulator contract."""
from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys
import tempfile


PROGRAM_DIR = pathlib.Path(os.environ.get("PROGRAM_DIR", "/app"))


def _run_sim(req):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        inp = root / "in.json"
        out = root / "out.json"
        inp.write_text(json.dumps(req, allow_nan=True), encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROGRAM_DIR)
        p = subprocess.run(
            [sys.executable, "-m", "gravity_sim", "--input", str(inp), "--output", str(out)],
            cwd=str(PROGRAM_DIR),
            env=env,
            text=True,
            capture_output=True,
        )
        data = None
        raw = None
        if out.exists():
            raw = out.read_bytes()
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
        entries = sorted(item.name for item in root.iterdir())
        return p, data, raw, entries


def _run_sim_with_sentinel(req, sentinel):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        inp = root / "in.json"
        out = root / "out.json"
        inp.write_text(json.dumps(req, allow_nan=True), encoding="utf-8")
        out.write_bytes(sentinel)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROGRAM_DIR)
        p = subprocess.run(
            [sys.executable, "-m", "gravity_sim", "--input", str(inp), "--output", str(out)],
            cwd=str(PROGRAM_DIR),
            env=env,
            text=True,
            capture_output=True,
        )
        raw = out.read_bytes() if out.exists() else None
        entries = sorted(item.name for item in root.iterdir())
        return p, raw, entries


def _body(ident, mass, pos, vel, radius=0.0):
    return {"id": ident, "mass": mass, "position": list(pos), "velocity": list(vel), "radius": radius}


def _base(bodies, **kw):
    request = {"bodies": bodies, "G": 1.0, "dt": 0.01, "steps": 1, "softening": 0.0}
    request.update(kw)
    return request


def _by_id(data, ident):
    return next(item for item in data["bodies"] if item["id"] == ident)


# case_id: GRAV-KIN-001
def test_CASE_KIN_001_free_drift_and_time_grid():
    """case_id=GRAV-KIN-001; requirement=R01; instruction.md#R01: 「`time` 为 `steps * dt`」; behavior: 固定时间网格必须由步数和步长给出，单天体无外力时保持匀速直线运动。; weight: 0.070000; reason: 时间网格错误会直接改变全部动力学轨迹。"""
    req = _base([_body("A", 2, [0, 0], [3, -2])], G=1, dt=0.25, steps=4, softening=0)
    p, data, _, entries = _run_sim(req)
    assert p.returncode == 0
    assert p.stdout == ""
    assert entries == ["in.json", "out.json"]
    assert data["time"] == 1.0
    assert _by_id(data, "A")["position"] == [3.0, -2.0]
    assert _by_id(data, "A")["velocity"] == [3.0, -2.0]


# case_id: GRAV-FORCE-002
def test_CASE_FORCE_002_pairwise_acceleration_direction_and_softening_power():
    """case_id=GRAV-FORCE-002; requirement=R02; instruction.md#R02: 「二体相互作用必须成对计算，满足牛顿第三定律；加速度方向指向另一个天体」; behavior: 成对引力方向、牛顿第三定律和软化距离 r^-3 因子必须同时正确。; weight: 0.120000; reason: 引力方向或软化幂次错误会系统性扭曲所有轨迹。"""
    req = _base(
        [_body("A", 2, [0, 0], [0, 0]), _body("B", 3, [2, 0], [0, 0])],
        dt=0.1,
        steps=1,
        softening=1.0,
    )
    p, data, _, _ = _run_sim(req)
    expected_a = 0.5 * (6 / (5 ** 1.5)) * 0.01
    expected_b = 2.0 - 0.5 * (4 / (5 ** 1.5)) * 0.01
    assert p.returncode == 0
    assert math.isclose(_by_id(data, "A")["position"][0], expected_a, rel_tol=1e-10, abs_tol=1e-12)
    assert math.isclose(_by_id(data, "B")["position"][0], expected_b, rel_tol=1e-10, abs_tol=1e-12)
    assert _by_id(data, "A")["position"][0] > 0 > _by_id(data, "B")["position"][0] - 2


# case_id: GRAV-INTEG-003
def test_CASE_INTEG_003_velocity_verlet_uses_new_acceleration():
    """case_id=GRAV-INTEG-003; requirement=R03; instruction.md#R03: 「v_i <- v_i + 0.5*(a_old + a_new)*dt」; behavior: 速度必须使用新旧加速度平均值，而不能退化为显式 Euler。; weight: 0.120000; reason: 积分器退化会改变长期能量与轨迹。"""
    req = _base(
        [_body("A", 1, [0, 0], [0, 0]), _body("B", 1, [1, 0], [0, 0])],
        dt=0.2,
        steps=1,
        softening=0.1,
    )
    p, data, _, _ = _run_sim(req)
    a_old = 1 / (1.01 ** 1.5)
    moved = 0.5 * a_old * 0.2 * 0.2
    separation = 1 - 2 * moved
    r2 = separation * separation + 0.01
    a_new = separation / (r2 * math.sqrt(r2))
    expected_v = 0.5 * (a_old + a_new) * 0.2
    assert p.returncode == 0
    assert math.isclose(_by_id(data, "A")["velocity"][0], expected_v, rel_tol=1e-10, abs_tol=1e-12)
    assert math.isclose(_by_id(data, "B")["velocity"][0], -expected_v, rel_tol=1e-10, abs_tol=1e-12)


# case_id: GRAV-DIAG-004
def test_CASE_DIAG_004_diagnostics_pair_once_and_momentum():
    """case_id=GRAV-DIAG-004; requirement=R07; instruction.md#R07: 「势能对每一对天体只计一次」; behavior: 最终状态的动能、势能、总能量、线动量和角动量必须逐项正确。; weight: 0.080000; reason: 势能重复计数会破坏能量诊断的可信度。"""
    req = _base(
        [_body("A", 2, [0, 0], [0, 1]), _body("B", 3, [2, 0], [0, -1])],
        G=4,
        dt=0.01,
        steps=0,
        softening=0.5,
    )
    p, data, _, _ = _run_sim(req)
    diag = data["diagnostics"]
    expected_potential = -24 / math.sqrt(4.25)
    assert p.returncode == 0
    assert math.isclose(diag["kinetic_energy"], 2.5, rel_tol=1e-12)
    assert math.isclose(diag["potential_energy"], expected_potential, rel_tol=1e-12)
    assert math.isclose(diag["total_energy"], 2.5 + expected_potential, rel_tol=1e-12)
    assert diag["linear_momentum"] == [0.0, -1.0]
    assert math.isclose(diag["angular_momentum"], -6.0, rel_tol=1e-12, abs_tol=1e-12)


# case_id: GRAV-MERGE-005
def test_CASE_MERGE_005_single_collision_conserves_mass_momentum_and_com():
    """case_id=GRAV-MERGE-005; requirement=R04; instruction.md#R04: 「半径为 `sqrt(sum(radius_i^2))`」; behavior: 单次碰撞必须按质量、质心、线动量和面积合成半径合并。; weight: 0.120000; reason: 合并守恒错误会制造不存在的质量与动量。"""
    req = _base(
        [_body("B", 3, [0, 0], [1, 0], 1), _body("A", 1, [1.5, 0], [0, 2], 2)],
        dt=0.1,
        steps=1,
        softening=1.0,
    )
    p, data, _, _ = _run_sim(req)
    assert p.returncode == 0
    assert len(data["bodies"]) == 1
    merged = data["bodies"][0]
    assert merged["id"] == "A"
    assert merged["members"] == ["A", "B"]
    assert math.isclose(merged["mass"], 4.0, rel_tol=1e-12)
    assert math.isclose(merged["velocity"][0], 0.75, rel_tol=1e-10)
    assert math.isclose(merged["velocity"][1], 0.5, rel_tol=1e-10)
    assert math.isclose(merged["radius"], math.sqrt(5), rel_tol=1e-12)
    assert math.isclose(merged["position"][0], 0.45, rel_tol=1e-10, abs_tol=1e-12)
    assert math.isclose(merged["position"][1], 0.05, rel_tol=1e-10, abs_tol=1e-12)


# case_id: GRAV-CHAIN-006
def test_CASE_CHAIN_006_chain_contact_is_one_simultaneous_component():
    """case_id=GRAV-CHAIN-006; requirement=R05; instruction.md#R05: 「碰撞关系的连通分量必须在同一时刻一次性合并，因此链式接触也要合并成一个天体。」; behavior: A-B-C 链式接触必须在单个时刻合并为一个三成员天体。; weight: 0.110000; reason: 按顺序合并会使链式碰撞结果依赖输入排列。"""
    req = _base(
        [_body("C", 1, [2, 0], [0, 0], 0.6), _body("A", 1, [0, 0], [0, 0], 0.6), _body("B", 1, [1, 0], [0, 0], 0.6)],
        dt=1e-9,
        steps=1,
        softening=1.0,
    )
    p, data, _, _ = _run_sim(req)
    assert p.returncode == 0
    assert len(data["bodies"]) == 1
    assert data["bodies"][0]["members"] == ["A", "B", "C"]
    assert data["mergers"] == [{"id": "A", "members": ["A", "B", "C"]}]


# case_id: GRAV-DETERMINISM-007
def test_CASE_DETERMINISM_007_permutation_invariance_of_merger_and_output_order():
    """case_id=GRAV-DETERMINISM-007; requirement=R06; instruction.md#R06: 「输入顺序不应改变结果」; behavior: 输入排列变化不得改变合并结果、成员顺序或输出排序。; weight: 0.090000; reason: 输入顺序敏感会破坏可复现性。"""
    items = [
        _body("z", 1, [0, 0], [0, 0], 1),
        _body("a", 2, [1, 0], [0, 0], 1),
        _body("m", 1, [5, 0], [0, 0], 0.1),
    ]
    p1, d1, _, _ = _run_sim(_base(items, dt=1e-8, steps=1, softening=1.0))
    p2, d2, _, _ = _run_sim(_base(list(reversed(items)), dt=1e-8, steps=1, softening=1.0))
    assert p1.returncode == 0
    assert p2.returncode == 0
    assert d1["bodies"] == d2["bodies"]
    assert d1["mergers"] == d2["mergers"]
    assert [b["id"] for b in d1["bodies"]] == ["a", "m"]
    assert [e["id"] for e in d1["mergers"]] == ["a"]


# case_id: GRAV-VALIDATE-008
def test_CASE_VALIDATE_008_invalid_structure_and_boolean_numbers_are_rejected():
    """case_id=GRAV-VALIDATE-008; requirement=R08; instruction.md#R08: 「布尔值伪装数值」; behavior: 缺失 radius、错误结构和布尔数值都必须在写文件前拒收。; weight: 0.060000; reason: 结构或类型校验缺口会接受不可解释的输入。"""
    p_missing, raw_missing, entries_missing = _run_sim_with_sentinel(
        _base([{"id": "A", "mass": 1, "position": [0, 0], "velocity": [0, 0]}]),
        b"missing-radius-sentinel",
    )
    assert p_missing.returncode != 0
    assert p_missing.stderr.startswith("INPUT_ERROR:")
    assert p_missing.stdout == ""
    assert raw_missing == b"missing-radius-sentinel"
    assert entries_missing == ["in.json", "out.json"]
    p_bool, raw_bool, entries_bool = _run_sim_with_sentinel(
        _base([_body("A", True, [0, 0], [0, 0])]),
        b"boolean-sentinel",
    )
    assert p_bool.returncode != 0
    assert p_bool.stderr.startswith("INPUT_ERROR:")
    assert p_bool.stdout == ""
    assert raw_bool == b"boolean-sentinel"
    assert entries_bool == ["in.json", "out.json"]
    p_steps, raw_steps, entries_steps = _run_sim_with_sentinel(
        _base([_body("A", 1, [0, 0], [0, 0])], steps=True),
        b"steps-sentinel",
    )
    assert p_steps.returncode != 0
    assert p_steps.stderr.startswith("INPUT_ERROR:")
    assert p_steps.stdout == ""
    assert raw_steps == b"steps-sentinel"
    assert entries_steps == ["in.json", "out.json"]


# case_id: GRAV-DOMAIN-009
def test_CASE_DOMAIN_009_invalid_ranges_and_nonfinite_values_preserve_output():
    """case_id=GRAV-DOMAIN-009; requirement=R09; instruction.md#R09: 「非有限数、越界值」; behavior: 质量、半径、步长与非有限输入必须拒收并保持旧输出字节不变。; weight: 0.060000; reason: 越界或非有限值会污染数值结果。"""
    p_mass, raw_mass, entries_mass = _run_sim_with_sentinel(
        _base([_body("A", 0, [0, 0], [0, 0])]),
        b"mass-sentinel",
    )
    assert p_mass.returncode != 0
    assert p_mass.stderr.startswith("INPUT_ERROR:")
    assert p_mass.stdout == ""
    assert raw_mass == b"mass-sentinel"
    assert entries_mass == ["in.json", "out.json"]
    p_dt, raw_dt, entries_dt = _run_sim_with_sentinel(
        _base([_body("A", 1, [0, 0], [0, 0])], dt=0),
        b"dt-sentinel",
    )
    assert p_dt.returncode != 0
    assert p_dt.stderr.startswith("INPUT_ERROR:")
    assert p_dt.stdout == ""
    assert raw_dt == b"dt-sentinel"
    assert entries_dt == ["in.json", "out.json"]
    p_nan, raw_nan, entries_nan = _run_sim_with_sentinel(
        _base([_body("A", 1, [float("nan"), 0], [0, 0])]),
        b"nan-sentinel",
    )
    assert p_nan.returncode != 0
    assert p_nan.stderr.startswith("INPUT_ERROR:")
    assert p_nan.stdout == ""
    assert raw_nan == b"nan-sentinel"
    assert entries_nan == ["in.json", "out.json"]
    p_radius, raw_radius, entries_radius = _run_sim_with_sentinel(
        _base([_body("A", 1, [0, 0], [0, 0], -1)]),
        b"radius-sentinel",
    )
    assert p_radius.returncode != 0
    assert p_radius.stderr.startswith("INPUT_ERROR:")
    assert p_radius.stdout == ""
    assert raw_radius == b"radius-sentinel"
    assert entries_radius == ["in.json", "out.json"]


# case_id: GRAV-SINGULAR-010
def test_CASE_SINGULAR_010_zero_softening_coincident_initial_pair_is_rejected():
    """case_id=GRAV-SINGULAR-010; requirement=R10; instruction.md#R10: 「当它为 0 时，不允许初始存在重合位置的两个不同天体。」; behavior: 零软化重合初态必须在修改旧输出前被拒收。; weight: 0.050000; reason: 奇异初态会使引力计算失去定义。"""
    p, raw, entries = _run_sim_with_sentinel(
        _base([_body("A", 1, [0, 0], [0, 0]), _body("B", 1, [0, 0], [0, 0])], softening=0),
        b"old-output",
    )
    assert p.returncode != 0
    assert p.stderr.startswith("INPUT_ERROR:")
    assert p.stdout == ""
    assert raw == b"old-output"
    assert entries == ["in.json", "out.json"]


# case_id: GRAV-ATOMIC-011
def test_CASE_ATOMIC_011_atomic_success_leaves_no_temp_files():
    """case_id=GRAV-ATOMIC-011; requirement=R11; instruction.md#R11: 「成功写文件时也必须采用同目录原子替换」; behavior: 成功输出必须替换旧文件且目录中只留下输入和最终输出。; weight: 0.040000; reason: 非原子写入会在中断时留下半截 JSON。"""
    req = _base([_body("A", 1, [0, 0], [1, 0])], G=1, steps=0)
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        inp = root / "in.json"
        out = root / "out.json"
        inp.write_text(json.dumps(req), encoding="utf-8")
        out.write_bytes(b"previous-output-must-be-replaced")
        previous_inode = out.stat().st_ino
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROGRAM_DIR)
        p = subprocess.run(
            [sys.executable, "-m", "gravity_sim", "--input", str(inp), "--output", str(out)],
            cwd=str(PROGRAM_DIR),
            env=env,
            text=True,
            capture_output=True,
        )
        assert p.returncode == 0
        assert p.stdout == ""
        assert out.exists()
        assert out.stat().st_ino != previous_inode
        assert sorted(item.name for item in root.iterdir()) == ["in.json", "out.json"]
        assert json.loads(out.read_text(encoding="utf-8"))["status"] == "ok"


# case_id: GRAV-SCHEMA-012
def test_CASE_SCHEMA_012_output_schema_is_complete_and_deterministic():
    """case_id=GRAV-SCHEMA-012; requirement=R12; instruction.md#R12: 「每个元素包含 `id`、`mass`、`position`、`velocity`、`radius` 和 `members`」; behavior: 成功输出必须具备完整字段、稳定排序和可重复的诊断结构。; weight: 0.080000; reason: 输出结构或排序不稳定会使结果无法消费。"""
    req = _base([_body("B", 1, [2, 0], [0, 0]), _body("A", 1, [0, 0], [0, 0])], steps=0)
    p, data, _, _ = _run_sim(req)
    assert p.returncode == 0
    assert data["status"] == "ok"
    assert [b["id"] for b in data["bodies"]] == ["A", "B"]
    assert all(set(b) == {"id", "mass", "position", "velocity", "radius", "members"} for b in data["bodies"])
    assert all(b["members"] == [b["id"]] for b in data["bodies"])
    assert data["mergers"] == []
    assert set(data["diagnostics"]) == {
        "kinetic_energy",
        "potential_energy",
        "total_energy",
        "linear_momentum",
        "angular_momentum",
    }
