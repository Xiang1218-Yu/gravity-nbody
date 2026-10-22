import json, math, os, pathlib, subprocess, sys, tempfile

PROGRAM_DIR = pathlib.Path(os.environ.get("PROGRAM_DIR", "/app"))


def run_sim(req, sentinel=None):
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        inp = root / "in.json"
        out = root / "out.json"
        inp.write_text(json.dumps(req), encoding="utf-8")
        if sentinel is not None:
            out.write_bytes(sentinel)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROGRAM_DIR)
        p = subprocess.run(
            [sys.executable, "-m", "gravity_sim", "--input", str(inp), "--output", str(out)],
            cwd=PROGRAM_DIR,
            env=env,
            text=True,
            capture_output=True,
        )
        data = None
        if out.exists():
            try:
                data = json.loads(out.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        entries = sorted(item.name for item in root.iterdir())
        return p, data, out.read_bytes() if out.exists() else None, entries


def assert_rejected(req, sentinel):
    """拒收不得产生 stdout、改写旧输出或残留临时/半成品文件。"""
    p, data, raw, entries = run_sim(req, sentinel)
    assert p.returncode != 0
    assert p.stderr.startswith("INPUT_ERROR:")
    assert p.stdout == ""
    assert data is None
    assert raw == sentinel
    assert entries == ["in.json", "out.json"]


def body(ident, mass, pos, vel, radius=0.0):
    return {"id": ident, "mass": mass, "position": list(pos), "velocity": list(vel), "radius": radius}


def base(bodies, **kw):
    x = {"bodies": bodies, "G": 1.0, "dt": 0.01, "steps": 1, "softening": 0.0}
    x.update(kw)
    return x


def get(data, ident):
    return next(b for b in data["bodies"] if b["id"] == ident)


def test_free_drift_and_time_grid():
    """条款：G 为正但两天体远离且步数为零/软化场景仍须按固定时间网格返回。"""
    req = base([body("A", 2, [0, 0], [3, -2])], G=1, dt=0.25, steps=4, softening=0)
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0 and d["time"] == 1.0
    a = get(d, "A")
    assert a["position"] == [3.0, -2.0] and a["velocity"] == [3.0, -2.0]


def test_pairwise_acceleration_direction_and_softening_power():
    """条款：成对引力方向指向对方，软化距离按三次方进入加速度。"""
    req = base([body("A", 2, [0, 0], [0, 0]), body("B", 3, [2, 0], [0, 0])], dt=0.1, steps=1, softening=1.0)
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0
    # a_A = 3*2/(2^2+1)^(3/2), Verlet displacement = .5*a*dt^2
    expected = 0.5 * (6 / (5 ** 1.5)) * 0.01
    assert math.isclose(get(d, "A")["position"][0], expected, rel_tol=1e-10, abs_tol=1e-12)
    assert get(d, "A")["position"][0] > 0 and get(d, "B")["position"][0] < 2


def test_velocity_verlet_uses_new_acceleration():
    """条款：速度必须使用旧、新加速度平均值，而非显式 Euler。"""
    req = base([body("A", 1, [0, 0], [0, 0]), body("B", 1, [1, 0], [0, 0])], dt=0.2, steps=1, softening=0.1)
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0
    x = get(d, "A")
    # displacement is symmetric Verlet; velocity is not simply old acceleration*dt.
    assert x["position"][0] > 0
    assert x["velocity"][0] > 0.2


def test_diagnostics_pair_once_and_momentum():
    """条款：诊断量来自最终状态，势能每对只计一次并报告线动量/角动量。"""
    req = base([body("A", 2, [0, 0], [0, 1]), body("B", 3, [2, 0], [0, -1])], G=4, dt=0.01, steps=0, softening=0.5)
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0
    diag = d["diagnostics"]
    assert math.isclose(diag["kinetic_energy"], 2.5, rel_tol=1e-12)
    assert math.isclose(diag["potential_energy"], -24 / math.sqrt(4.25), rel_tol=1e-12)
    assert diag["linear_momentum"] == [0.0, -1.0]
    assert math.isclose(diag["angular_momentum"], -6.0, abs_tol=1e-12)


def test_single_collision_conserves_mass_momentum_and_com():
    """条款：碰撞合并必须守恒质量、质心位置和线动量，并按面积合成半径。"""
    req = base([body("B", 3, [0, 0], [1, 0], 1), body("A", 1, [1.5, 0], [0, 2], 2)], G=1, dt=0.1, steps=0)
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0
    assert len(d["bodies"]) == 2  # collision occurs after an integration step, not at t=0
    req["steps"] = 1
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0 and len(d["bodies"]) == 1
    m = d["bodies"][0]
    assert m["id"] == "A" and m["members"] == ["A", "B"]
    assert math.isclose(m["mass"], 4.0)
    assert math.isclose(m["velocity"][0], 0.75, rel_tol=1e-8)
    assert math.isclose(m["velocity"][1], 0.5, rel_tol=1e-8)
    assert math.isclose(m["radius"], math.sqrt(5), rel_tol=1e-12)


def test_chain_contact_is_one_simultaneous_component():
    """条款：链式接触必须按同一时刻连通分量一次性合并。"""
    req = base([body("C", 1, [2, 0], [0, 0], 0.6), body("A", 1, [0, 0], [0, 0], 0.6), body("B", 1, [1, 0], [0, 0], 0.6)], steps=0)
    # force the collision check through a zero-length physical step with a tiny dt is not allowed; use G=1 and step.
    req["steps"] = 1; req["dt"] = 1e-9
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0 and len(d["bodies"]) == 1
    assert d["bodies"][0]["members"] == ["A", "B", "C"]


def test_permutation_invariance_of_merger_and_output_order():
    """条款：输入排列不得改变连通分量、成员顺序或最终输出排序。"""
    items = [body("z", 1, [0, 0], [0, 0], 1), body("a", 2, [1, 0], [0, 0], 1), body("m", 1, [5, 0], [0, 0], 0.1)]
    p1, d1, _, _ = run_sim(base(items, steps=1, dt=1e-8))
    p2, d2, _, _ = run_sim(base(list(reversed(items)), steps=1, dt=1e-8))
    assert p1.returncode == p2.returncode == 0
    assert d1["bodies"] == d2["bodies"] and d1["mergers"] == d2["mergers"]


def test_invalid_structure_and_boolean_numbers_are_rejected():
    """条款：错误类型、缺失字段和布尔值伪装数值必须拒收。"""
    cases = [base([body("A", True, [0, 0], [0, 0])]), base([{"id": "A", "mass": 1, "position": [0, 0]}]), base([body("A", 1, [0, 0], [0, 0])], steps=True)]
    for req in cases:
        assert_rejected(req, b"sentinel")


def test_invalid_ranges_and_nonfinite_values_preserve_output():
    """条款：越界和非有限输入拒收且不得改写已有输出。"""
    cases = [base([body("A", 0, [0, 0], [0, 0])]), base([body("A", 1, [0, 0], [0, 0])], dt=0), base([body("A", 1, [0, 0], [0, 0])], softening=-1), base([body("A", 1, [float("nan"), 0], [0, 0])])]
    for req in cases:
        assert_rejected(req, b"sentinel-bytes")


def test_zero_softening_coincident_initial_pair_is_rejected():
    """条款：零软化下初始重合天体必须走拒收路径。"""
    req = base([body("A", 1, [0, 0], [0, 0]), body("B", 1, [0, 0], [0, 0])], softening=0)
    assert_rejected(req, b"old-output")


def test_atomic_success_leaves_no_temp_files():
    """条款：成功输出应完成原子替换，不留下隐藏临时文件。"""
    req = base([body("A", 1, [0, 0], [1, 0])], G=1, steps=0)
    with tempfile.TemporaryDirectory() as td:
        inp, out = pathlib.Path(td)/"i.json", pathlib.Path(td)/"o.json"
        inp.write_text(json.dumps(req), encoding="utf-8")
        env = os.environ.copy(); env["PYTHONPATH"] = str(PROGRAM_DIR)
        p = subprocess.run([sys.executable, "-m", "gravity_sim", "--input", str(inp), "--output", str(out)], cwd=PROGRAM_DIR, env=env, capture_output=True, text=True)
        assert p.returncode == 0 and out.exists()
        assert sorted(x.name for x in pathlib.Path(td).iterdir()) == ["i.json", "o.json"]


def test_output_schema_is_complete_and_deterministic():
    """条款：成功结果必须包含稳定的状态、身体字段、事件字段和诊断字段。"""
    req = base([body("B", 1, [2, 0], [0, 0]), body("A", 1, [0, 0], [0, 0])], steps=0)
    p, d, _, _ = run_sim(req)
    assert p.returncode == 0 and d["status"] == "ok"
    assert [b["id"] for b in d["bodies"]] == ["A", "B"]
    assert set(d["diagnostics"]) == {"kinetic_energy", "potential_energy", "total_energy", "linear_momentum", "angular_momentum"}
