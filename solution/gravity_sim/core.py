"""Deterministic 2-D Newtonian n-body simulator used as authoring baseline."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


class InputError(ValueError):
    pass


@dataclass
class Body:
    id: str
    mass: float
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    members: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "mass": self.mass,
            "position": [self.x, self.y],
            "velocity": [self.vx, self.vy],
            "radius": self.radius,
            "members": list(self.members),
        }


def _finite_number(v, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise InputError(f"{name} must be a finite number")
    return float(v)


def _vec(v, name: str) -> tuple[float, float]:
    if not isinstance(v, list) or len(v) != 2:
        raise InputError(f"{name} must be a 2-element list")
    return (_finite_number(v[0], f"{name}[0]"), _finite_number(v[1], f"{name}[1]"))


def parse_request(req: dict) -> tuple[list[Body], float, float, int, float]:
    if not isinstance(req, dict):
        raise InputError("request must be an object")
    raw = req.get("bodies")
    if not isinstance(raw, list) or not raw:
        raise InputError("bodies must be a non-empty list")
    G = _finite_number(req.get("G"), "G")
    dt = _finite_number(req.get("dt"), "dt")
    softening = _finite_number(req.get("softening", 0.0), "softening")
    steps = req.get("steps")
    if isinstance(steps, bool) or not isinstance(steps, int):
        raise InputError("steps must be an integer")
    if G <= 0 or dt <= 0 or steps < 0 or softening < 0:
        raise InputError("G, dt and softening must be positive/non-negative and steps cannot be negative")
    bodies: list[Body] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise InputError(f"bodies[{i}] must be an object")
        ident = item.get("id")
        if not isinstance(ident, str) or not ident or ident in seen:
            raise InputError(f"bodies[{i}].id must be a unique non-empty string")
        seen.add(ident)
        mass = _finite_number(item.get("mass"), f"bodies[{i}].mass")
        radius = _finite_number(item.get("radius"), f"bodies[{i}].radius")
        if mass <= 0 or radius < 0:
            raise InputError(f"bodies[{i}] has invalid mass or radius")
        x, y = _vec(item.get("position"), f"bodies[{i}].position")
        vx, vy = _vec(item.get("velocity"), f"bodies[{i}].velocity")
        bodies.append(Body(ident, mass, x, y, vx, vy, radius, (ident,)))
    bodies.sort(key=lambda b: b.id)
    if softening == 0.0:
        for i, a in enumerate(bodies):
            for b in bodies[i + 1 :]:
                if a.x == b.x and a.y == b.y:
                    raise InputError("coincident bodies require positive softening")
    return bodies, G, dt, steps, softening


def accelerations(bodies: list[Body], G: float, softening: float) -> list[tuple[float, float]]:
    acc = [[0.0, 0.0] for _ in bodies]
    eps2 = softening * softening
    for i, a in enumerate(bodies):
        for j in range(i + 1, len(bodies)):
            b = bodies[j]
            dx, dy = b.x - a.x, b.y - a.y
            r2 = dx * dx + dy * dy + eps2
            if r2 == 0.0:
                raise InputError("singular pair encountered")
            inv_r3 = 1.0 / (r2 * math.sqrt(r2))
            scale = G * inv_r3
            acc[i][0] += scale * b.mass * dx
            acc[i][1] += scale * b.mass * dy
            acc[j][0] -= scale * a.mass * dx
            acc[j][1] -= scale * a.mass * dy
    return [(x, y) for x, y in acc]


def _merge_group(group: list[Body]) -> Body:
    group = sorted(group, key=lambda b: b.id)
    members = tuple(sorted(m for b in group for m in b.members))
    mass = sum(b.mass for b in group)
    x = sum(b.mass * b.x for b in group) / mass
    y = sum(b.mass * b.y for b in group) / mass
    vx = sum(b.mass * b.vx for b in group) / mass
    vy = sum(b.mass * b.vy for b in group) / mass
    radius = math.sqrt(sum(b.radius * b.radius for b in group))
    return Body(members[0], mass, x, y, vx, vy, radius, members)


def merge_collisions(bodies: list[Body]) -> tuple[list[Body], list[dict]]:
    parent = list(range(len(bodies)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for i, a in enumerate(bodies):
        for j in range(i + 1, len(bodies)):
            b = bodies[j]
            if math.hypot(a.x - b.x, a.y - b.y) <= a.radius + b.radius:
                union(i, j)
    groups: dict[int, list[Body]] = {}
    for i, b in enumerate(bodies):
        groups.setdefault(find(i), []).append(b)
    result: list[Body] = []
    events: list[dict] = []
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
        else:
            merged = _merge_group(group)
            result.append(merged)
            events.append({"id": merged.id, "members": list(merged.members)})
    result.sort(key=lambda b: b.id)
    events.sort(key=lambda e: e["id"])
    return result, events


def diagnostics(bodies: list[Body], G: float, softening: float) -> dict:
    kinetic = sum(0.5 * b.mass * (b.vx * b.vx + b.vy * b.vy) for b in bodies)
    potential = 0.0
    px = py = angular = 0.0
    for i, a in enumerate(bodies):
        px += a.mass * a.vx
        py += a.mass * a.vy
        angular += a.mass * (a.x * a.vy - a.y * a.vx)
        for b in bodies[i + 1 :]:
            r = math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + softening**2)
            potential -= G * a.mass * b.mass / r
    return {
        "kinetic_energy": kinetic,
        "potential_energy": potential,
        "total_energy": kinetic + potential,
        "linear_momentum": [px, py],
        "angular_momentum": angular,
    }


def simulate(req: dict) -> dict:
    bodies, G, dt, steps, softening = parse_request(req)
    all_events: list[dict] = []
    for _ in range(steps):
        acc = accelerations(bodies, G, softening)
        for b, (ax, ay) in zip(bodies, acc):
            b.x += b.vx * dt + 0.5 * ax * dt * dt
            b.y += b.vy * dt + 0.5 * ay * dt * dt
        new_acc = accelerations(bodies, G, softening)
        for b, (ax0, ay0), (ax1, ay1) in zip(bodies, acc, new_acc):
            b.vx += 0.5 * (ax0 + ax1) * dt
            b.vy += 0.5 * (ay0 + ay1) * dt
        bodies, events = merge_collisions(bodies)
        all_events.extend(events)
    bodies.sort(key=lambda b: b.id)
    all_events.sort(key=lambda e: e["id"])
    return {
        "status": "ok",
        "time": steps * dt,
        "bodies": [b.as_dict() for b in bodies],
        "mergers": all_events,
        "diagnostics": diagnostics(bodies, G, softening),
    }
