from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Sequence, Tuple


Cell = Tuple[int, int]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class PlayerModel:
    history_capacity: int = 20
    danger_distance: int = 5
    edge_margin: int = 3

    game_history: list = field(default_factory=list)
    current_game: dict = field(default_factory=dict)

    def __post_init__(self):
        self.start_new_game()

    @property
    def games_played(self) -> int:
        return len(self.game_history)

    def start_new_game(self) -> None:
        self.current_game = {
            "steps": 0,
            "junctions": 0,
            "coins_collected": 0,
            "coin_near_exit": 0,
            "coin_under_pressure": 0,
            "endgame_coin_focus": 0,
            "risky_coin_choice": 0,
            "safe_choice": 0,
            "keep_direction": 0,
            "reverse": 0,
            "left": 0,
            "right": 0,
            "straight": 0,
            "edge_steps": 0,
            "center_steps": 0,
            "explore_steps": 0,
            "revisit_steps": 0,
            "switches": 0,
            "switch_under_pressure": 0,
            "rush_exit_choices": 0,
            "collect_coin_choices": 0,
            "won": False,
            "escaped": False,
            "cleared_all_coins": False,
            "score": 0,
        }
        self._visited_this_game = set()
        self._last_direction = None

    def record_step(
        self,
        cell: Cell,
        direction: Optional[str],
        ghost_cell: Optional[Cell],
        coin_cells: Iterable[Cell],
        exit_cell: Optional[Cell],
        rows: int,
        cols: int,
    ) -> None:
        pressure = self.classify_pressure(self._distance_or_none(cell, ghost_cell))
        self.current_game["steps"] += 1

        if self._is_edge(cell, rows, cols):
            self.current_game["edge_steps"] += 1
        else:
            self.current_game["center_steps"] += 1

        if cell in self._visited_this_game:
            self.current_game["revisit_steps"] += 1
        else:
            self.current_game["explore_steps"] += 1
            self._visited_this_game.add(cell)

        if self._last_direction is not None and direction is not None and direction != self._last_direction:
            self.current_game["switches"] += 1
            if pressure in ("medium", "high"):
                self.current_game["switch_under_pressure"] += 1

        self._last_direction = direction

    def record_junction_choice(
        self,
        cell: Cell,
        options: Sequence[str],
        chosen: str,
        incoming_dir: Optional[str],
        ghost_cell: Optional[Cell],
        coin_cells: Iterable[Cell],
        exit_cell: Optional[Cell],
        decision_wait_ticks: int = 0,
    ) -> None:
        coin_cells = set(coin_cells)
        pressure = self.classify_pressure(self._distance_or_none(cell, ghost_cell))
        nearest_coin_distance = self._nearest_distance(cell, coin_cells)
        exit_distance = self._distance_or_none(cell, exit_cell)

        self.current_game["junctions"] += 1

        turn_type = self._turn_type(incoming_dir, chosen)
        if turn_type in ("left", "right", "straight", "reverse"):
            self.current_game[turn_type] += 1

        if chosen == incoming_dir:
            self.current_game["keep_direction"] += 1

        target_choice = self._infer_target_choice(
            nearest_coin_distance=nearest_coin_distance,
            exit_distance=exit_distance,
            remaining_coins=len(coin_cells),
            pressure=pressure,
        )

        if target_choice == "collect_coins":
            self.current_game["collect_coin_choices"] += 1
        else:
            self.current_game["rush_exit_choices"] += 1

        if pressure in ("medium", "high"):
            if target_choice == "collect_coins":
                self.current_game["risky_coin_choice"] += 1
            else:
                self.current_game["safe_choice"] += 1

    def record_coin_collection(
        self,
        cell: Cell,
        ghost_cell: Optional[Cell],
        remaining_coins_after_pickup: int,
        exit_cell: Optional[Cell],
    ) -> None:
        pressure = self.classify_pressure(self._distance_or_none(cell, ghost_cell))
        exit_distance = self._distance_or_none(cell, exit_cell)

        self.current_game["coins_collected"] += 1

        if pressure in ("medium", "high"):
            self.current_game["coin_under_pressure"] += 1

        if exit_distance is not None and exit_distance <= 4:
            self.current_game["coin_near_exit"] += 1

        if remaining_coins_after_pickup <= 2:
            self.current_game["endgame_coin_focus"] += 1

    def record_exit_reached(self, remaining_coins: int, score: int) -> None:
        self.current_game["won"] = True
        self.current_game["escaped"] = True
        self.current_game["score"] = score
        if remaining_coins == 0:
            self.current_game["cleared_all_coins"] = True

    def record_all_coins_win(self, score: int) -> None:
        self.current_game["won"] = True
        self.current_game["cleared_all_coins"] = True
        self.current_game["score"] = score

    def record_loss(self, remaining_coins: int, score: int) -> None:
        self.current_game["won"] = False
        self.current_game["score"] = score

    def finalize_game(self) -> None:
        self.game_history.append(dict(self.current_game))
        if len(self.game_history) > self.history_capacity:
            self.game_history = self.game_history[-self.history_capacity:]
        self.start_new_game()

    def predict_next_target(
        self,
        player_cell: Cell,
        coin_cells: Iterable[Cell],
        exit_cell: Optional[Cell],
        ghost_cell: Optional[Cell],
    ) -> Dict[str, object]:
        coin_cells = set(coin_cells)
        nearest_coin_distance = self._nearest_distance(player_cell, coin_cells)
        exit_distance = self._distance_or_none(player_cell, exit_cell)
        pressure = self.classify_pressure(self._distance_or_none(player_cell, ghost_cell))

        coin_focus = self.coin_focus_score()
        risk = self.risk_tolerance_score()
        endgame = self.endgame_coin_commitment_score()

        coin_score = 0.5
        exit_score = 0.5

        coin_score += 0.55 * coin_focus
        exit_score += 0.55 * (1.0 - coin_focus)

        if len(coin_cells) <= 2:
            coin_score += 0.35 * endgame
            exit_score += 0.15 * (1.0 - endgame)

        if nearest_coin_distance is not None:
            coin_score += clamp((8 - nearest_coin_distance) / 10.0, -0.2, 0.25)

        if exit_distance is not None:
            exit_score += clamp((8 - exit_distance) / 10.0, -0.2, 0.25)

        if pressure == "high":
            coin_score += 0.2 * risk
            exit_score += 0.2 * (1.0 - risk)

        target_type = "coins" if coin_score >= exit_score else "exit"
        target_cell = self.predict_coin_target(player_cell, coin_cells) if target_type == "coins" else exit_cell
        confidence = abs(coin_score - exit_score) / max(coin_score + exit_score, 0.001)

        return {
            "target_type": target_type,
            "target_cell": target_cell,
            "confidence": round(clamp(confidence), 3),
            "coin_score": round(coin_score, 3),
            "exit_score": round(exit_score, 3),
        }

    def behavior_snapshot(self) -> Dict[str, object]:
        return {
            "games_played": self.games_played,
            "coin_focus_score": round(self.coin_focus_score(), 3),
            "risk_tolerance_score": round(self.risk_tolerance_score(), 3),
            "endgame_coin_commitment_score": round(self.endgame_coin_commitment_score(), 3),
        }

    def coin_focus_score(self) -> float:
        pos = sum(g["collect_coin_choices"] + g["coins_collected"] + g["coin_near_exit"] for g in self.game_history)
        neg = sum(g["rush_exit_choices"] + (1 if g["escaped"] and not g["cleared_all_coins"] else 0) for g in self.game_history)
        return self._preference(pos, neg, 0.5)

    def risk_tolerance_score(self) -> float:
        pos = sum(g["coin_under_pressure"] + g["risky_coin_choice"] for g in self.game_history)
        neg = sum(g["safe_choice"] for g in self.game_history)
        return self._preference(pos, neg, 0.5)

    def endgame_coin_commitment_score(self) -> float:
        pos = sum(g["endgame_coin_focus"] + (1 if g["cleared_all_coins"] else 0) for g in self.game_history)
        neg = sum(1 if g["escaped"] and not g["cleared_all_coins"] else 0 for g in self.game_history)
        return self._preference(pos, neg, 0.5)

    def predict_coin_target(self, player_cell: Cell, coin_cells: Iterable[Cell]) -> Optional[Cell]:
        coin_cells = list(coin_cells)
        if not coin_cells:
            return None

        best_coin = None
        best_score = -9999.0
        edge_pref = self.edge_preference_score()

        for coin in coin_cells:
            dist_score = 1.0 / (manhattan(player_cell, coin) + 1)
            edge_bonus = edge_pref if self._cell_looks_edge(coin) else (1.0 - edge_pref)
            score = 0.75 * dist_score + 0.25 * edge_bonus

            if score > best_score:
                best_score = score
                best_coin = coin

        return best_coin

    def edge_preference_score(self) -> float:
        pos = sum(g["edge_steps"] for g in self.game_history)
        neg = sum(g["center_steps"] for g in self.game_history)
        return self._preference(pos, neg, 0.5)

    def save_to_file(self, path: str = "player_data.json") -> None:
        data = {
            "history_capacity": self.history_capacity,
            "game_history": self.game_history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, path: str = "player_data.json") -> None:
        if not os.path.exists(path):
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.history_capacity = data.get("history_capacity", 20)
        self.game_history = data.get("game_history", [])

    def classify_pressure(self, ghost_distance: Optional[int]) -> str:
        if ghost_distance is None:
            return "none"
        if ghost_distance <= self.danger_distance:
            return "high"
        if ghost_distance <= self.danger_distance + 4:
            return "medium"
        return "low"

    def _infer_target_choice(
        self,
        nearest_coin_distance: Optional[int],
        exit_distance: Optional[int],
        remaining_coins: int,
        pressure: str,
    ) -> str:
        if nearest_coin_distance is None:
            return "rush_exit"
        if exit_distance is None:
            return "collect_coins"
        if pressure == "high" and exit_distance < nearest_coin_distance:
            return "rush_exit"
        if remaining_coins <= 2 and nearest_coin_distance <= exit_distance + 2:
            return "collect_coins"
        return "collect_coins" if nearest_coin_distance <= exit_distance else "rush_exit"

    def _turn_type(self, incoming_dir: Optional[str], outgoing_dir: Optional[str]) -> str:
        if incoming_dir is None or outgoing_dir is None:
            return "unknown"
        if incoming_dir == outgoing_dir:
            return "straight"

        mapping = {
            ("UP", "LEFT"): "left",
            ("UP", "RIGHT"): "right",
            ("UP", "DOWN"): "reverse",
            ("DOWN", "LEFT"): "right",
            ("DOWN", "RIGHT"): "left",
            ("DOWN", "UP"): "reverse",
            ("LEFT", "UP"): "right",
            ("LEFT", "DOWN"): "left",
            ("LEFT", "RIGHT"): "reverse",
            ("RIGHT", "UP"): "left",
            ("RIGHT", "DOWN"): "right",
            ("RIGHT", "LEFT"): "reverse",
        }
        return mapping.get((incoming_dir, outgoing_dir), "unknown")

    def _nearest_distance(self, origin: Cell, cells: Iterable[Cell]) -> Optional[int]:
        cells = list(cells)
        if not cells:
            return None
        return min(manhattan(origin, cell) for cell in cells)

    def _distance_or_none(self, a: Cell, b: Optional[Cell]) -> Optional[int]:
        return None if b is None else manhattan(a, b)

    def _is_edge(self, cell: Cell, rows: int, cols: int) -> bool:
        r, c = cell
        return (
            r <= self.edge_margin
            or c <= self.edge_margin
            or r >= rows - 1 - self.edge_margin
            or c >= cols - 1 - self.edge_margin
        )

    def _cell_looks_edge(self, cell: Cell) -> bool:
        r, c = cell
        return r <= self.edge_margin or c <= self.edge_margin

    def _preference(self, positive: float, negative: float, default: float) -> float:
        total = positive + negative
        if total == 0:
            return default
        return clamp(positive / total)
