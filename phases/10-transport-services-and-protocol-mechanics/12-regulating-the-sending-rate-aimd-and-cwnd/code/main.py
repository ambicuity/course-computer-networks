"""AIMD control law simulator (Chiu-Jain 1989).

This module implements the four pure control laws (AIMD, AIAD, MIMD, MIAD)
on two flows sharing a 100-unit link and demonstrates the Chiu-Jain
convergence result: only AIMD marches the (x_1, x_2) trajectory into the
intersection of the fairness line ``x_1 = x_2`` and the efficiency line
``x_1 + x_2 = 100``.

Stdlib only, no third-party packages, no network access. Run with
``python3 main.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Control laws
# ---------------------------------------------------------------------------


class Law(str, Enum):
    AIMD = "AIMD"
    AIAD = "AIAD"
    MIMD = "MIMD"
    MIAD = "MIAD"


@dataclass
class Simulator:
    """A two-flow congestion-control simulator.

    The simulator tracks the bandwidth allocation ``(x_1, x_2)`` of two
    flows sharing a single link. Each round, the flows apply the chosen
    control law. If the sum exceeds ``capacity``, a congestion signal
    arrives and the decrease policy fires.
    """

    law: Law
    x1: float
    x2: float
    capacity: float = 100.0
    a: float = 1.0
    beta: float = 0.5

    def step(self) -> tuple[float, float]:
        """Apply one round of the chosen control law.

        Returns the new ``(x_1, x_2)``.
        """
        if self.law in (Law.AIMD, Law.AIAD):
            self.x1 += self.a
            self.x2 += self.a
        else:  # MIMD or MIAD
            self.x1 *= 1.0 + self.a / 100.0
            self.x2 *= 1.0 + self.a / 100.0
        if self.x1 + self.x2 > self.capacity:
            if self.law in (Law.AIMD, Law.MIMD):
                self.x1 *= self.beta
                self.x2 *= self.beta
            else:  # AIAD or MIAD
                self.x1 -= self.a
                self.x2 -= self.a
        return (self.x1, self.x2)

    def run(self, rounds: int) -> list[tuple[float, float]]:
        trajectory: list[tuple[float, float]] = [(self.x1, self.x2)]
        for _ in range(rounds):
            trajectory.append(self.step())
        return trajectory


# ---------------------------------------------------------------------------
# Demonstrations
# ---------------------------------------------------------------------------


def _print_trajectory(label: str, traj: list[tuple[float, float]]) -> None:
    print(f"\n{label}")
    print(f"  start:  x1={traj[0][0]:6.2f}  x2={traj[0][1]:6.2f}  sum={sum(traj[0]):6.2f}")
    for i, (x1, x2) in enumerate(traj[1:], start=1):
        print(f"  round {i:2d}: x1={x1:6.2f}  x2={x2:6.2f}  sum={x1 + x2:6.2f}")


def verify_chiu_jain() -> None:
    """Reproduce the Chiu-Jain convergence claim.

    AIMD starting from ``(95, 5)`` and ``(5, 95)`` should converge to
    ``(50, 50)`` within 10 rounds.
    """
    sim_a = Simulator(Law.AIMD, x1=95.0, x2=5.0)
    _print_trajectory("AIMD from (95, 5):", sim_a.run(12))
    sim_b = Simulator(Law.AIMD, x1=5.0, x2=95.0)
    _print_trajectory("AIMD from (5, 95):", sim_b.run(12))


def show_divergence() -> None:
    """Show that AIAD, MIMD, and MIAD do not reach the optimal point."""
    for law in (Law.AIAD, Law.MIMD, Law.MIAD):
        sim = Simulator(law, x1=80.0, x2=20.0, a=10.0, beta=0.5)
        traj = sim.run(10)
        x1_final, x2_final = traj[-1]
        print(
            f"{law.value} start (80, 20): end ({x1_final:.2f}, {x2_final:.2f})  "
            f"fair? {abs(x1_final - x2_final) < 0.5}  "
            f"efficient? {abs(x1_final + x2_final - 100) < 0.5}"
        )


def main() -> None:
    verify_chiu_jain()
    print("\nControl laws that do not converge to (50, 50):")
    show_divergence()


if __name__ == "__main__":
    main()
