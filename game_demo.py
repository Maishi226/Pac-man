import pygame
import random
from collections import deque
from player_model import PlayerModel

# --- 初始化与配置 ---
pygame.init()

GRID_SIZE = 25
ROWS, COLS = 25, 25
WIDTH, HEIGHT = COLS * GRID_SIZE, ROWS * GRID_SIZE

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Maze Chase")
clock = pygame.time.Clock()

PLAYER_SPEED = 140

# =========================================================
# GHOST SPEED
# 以后你想自己调鬼的速度，就改这里
# 数值越大，鬼移动越快
# =========================================================
GHOST_SPEED = 140

COIN_COUNT = 10
MIN_GAMES_BEFORE_LEARNING = 10

font = pygame.font.SysFont(None, 32)
big_font = pygame.font.SysFont(None, 64)

player_model = PlayerModel(history_capacity=20)
player_model.load_from_file("player_data.json")


# --- 1. 生成迷宫 ---
def generate_maze(rows, cols):
    maze = [[1 for _ in range(cols)] for _ in range(rows)]

    def dfs(r, c):
        maze[r][c] = 0
        directions = [(0, 2), (0, -2), (2, 0), (-2, 0)]
        random.shuffle(directions)

        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 < nr < rows - 1 and 0 < nc < cols - 1 and maze[nr][nc] == 1:
                maze[r + dr // 2][c + dc // 2] = 0
                dfs(nr, nc)

    dfs(1, 1)

    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            if maze[r][c] == 1 and random.random() < 0.25:
                maze[r][c] = 0

    return maze


maze = generate_maze(ROWS, COLS)


# --- 工具函数 ---
def is_walkable(row, col):
    return 0 <= row < ROWS and 0 <= col < COLS and maze[row][col] == 0


def cell_center(row, col):
    return [
        col * GRID_SIZE + GRID_SIZE / 2,
        row * GRID_SIZE + GRID_SIZE / 2
    ]


def pos_to_cell(pos):
    col = int(pos[0] // GRID_SIZE)
    row = int(pos[1] // GRID_SIZE)
    return row, col


def snap_to_center(pos):
    row, col = pos_to_cell(pos)
    return cell_center(row, col)


def at_cell_center(pos, tolerance=2):
    row, col = pos_to_cell(pos)
    cx, cy = cell_center(row, col)
    return abs(pos[0] - cx) <= tolerance and abs(pos[1] - cy) <= tolerance


def next_cell(row, col, direction):
    if direction == "LEFT":
        return row, col - 1
    if direction == "RIGHT":
        return row, col + 1
    if direction == "UP":
        return row - 1, col
    if direction == "DOWN":
        return row + 1, col
    return row, col


def dir_to_vector(direction):
    if direction == "LEFT":
        return -1, 0
    if direction == "RIGHT":
        return 1, 0
    if direction == "UP":
        return 0, -1
    if direction == "DOWN":
        return 0, 1
    return 0, 0


def find_exit_cell():
    candidates = []
    for r in range(ROWS - 2, 0, -1):
        for c in range(COLS - 2, 0, -1):
            if maze[r][c] == 0 and (r, c) != (1, 1):
                candidates.append((r, c))
    return candidates[0] if candidates else (ROWS - 2, COLS - 2)


def place_coins(count, forbidden_cells):
    walkable_cells = []
    for r in range(ROWS):
        for c in range(COLS):
            if maze[r][c] == 0 and (r, c) not in forbidden_cells:
                walkable_cells.append((r, c))

    random.shuffle(walkable_cells)
    return set(walkable_cells[:count])


def get_available_dirs(cell):
    r, c = cell
    dirs = []
    for direction in ["LEFT", "RIGHT", "UP", "DOWN"]:
        nr, nc = next_cell(r, c, direction)
        if is_walkable(nr, nc):
            dirs.append(direction)
    return dirs


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def midpoint_cell(a, b):
    mr = (a[0] + b[0]) // 2
    mc = (a[1] + b[1]) // 2

    candidates = [
        (mr, mc),
        (mr + 1, mc),
        (mr - 1, mc),
        (mr, mc + 1),
        (mr, mc - 1),
    ]

    for r, c in candidates:
        if is_walkable(r, c):
            return (r, c)

    return b


# --- 2. BFS 寻路 ---
def get_next_ghost_cell(start, goal):
    if start == goal:
        return start

    queue = deque([start])
    parents = {start: start}

    while queue:
        curr = queue.popleft()
        r, c = curr

        for nr, nc in [(r, c + 1), (r, c - 1), (r + 1, c), (r - 1, c)]:
            neighbor = (nr, nc)

            if not is_walkable(nr, nc):
                continue
            if neighbor in parents:
                continue

            parents[neighbor] = curr

            if neighbor == goal:
                step = neighbor
                while parents[step] != start:
                    step = parents[step]
                return step

            queue.append(neighbor)

    return start


def cell_direction(from_cell, to_cell):
    fr, fc = from_cell
    tr, tc = to_cell

    if tr == fr and tc == fc - 1:
        return "LEFT"
    if tr == fr and tc == fc + 1:
        return "RIGHT"
    if tr == fr - 1 and tc == fc:
        return "UP"
    if tr == fr + 1 and tc == fc:
        return "DOWN"
    return None


def choose_best_neighbor_toward_goal(start, goal):
    options = []

    for direction in get_available_dirs(start):
        nr, nc = next_cell(start[0], start[1], direction)
        dist = manhattan((nr, nc), goal)
        options.append((dist, direction))

    if not options:
        return None

    options.sort(key=lambda item: item[0])
    return options[0][1]


# --- 平滑移动 ---
def move_entity(pos, current_dir, wanted_dir, speed, dt, stop_when_no_input=False):
    row, col = pos_to_cell(pos)

    if at_cell_center(pos):
        pos = snap_to_center(pos)
        row, col = pos_to_cell(pos)

        if stop_when_no_input and wanted_dir is None:
            current_dir = None
        elif wanted_dir is not None:
            nr, nc = next_cell(row, col, wanted_dir)
            if is_walkable(nr, nc):
                current_dir = wanted_dir

        if current_dir is not None:
            nr, nc = next_cell(row, col, current_dir)
            if not is_walkable(nr, nc):
                current_dir = None

    if current_dir is not None:
        dx, dy = dir_to_vector(current_dir)
        pos[0] += dx * speed * dt
        pos[1] += dy * speed * dt

        if at_cell_center(pos):
            pos = snap_to_center(pos)

    return pos, current_dir


def choose_ghost_strategy(player_cell, ghost_cell, coins, exit_cell):
    # 前10局：纯追人
    if player_model.games_played < MIN_GAMES_BEFORE_LEARNING:
        return "CHASE", player_cell

    prediction = player_model.predict_next_target(
        player_cell=player_cell,
        coin_cells=coins,
        exit_cell=exit_cell,
        ghost_cell=ghost_cell,
    )

    predicted_target = prediction["target_cell"]
    predicted_type = prediction["target_type"]
    confidence = prediction["confidence"]

    coin_focus = player_model.coin_focus_score()
    endgame_focus = player_model.endgame_coin_commitment_score()

    # 只剩最后一个金币：优先守金币和出口之间
    if len(coins) == 1:
        last_coin = list(coins)[0]
        coin_to_exit = manhattan(last_coin, exit_cell)

        if coin_to_exit <= 8:
            trap_cell = midpoint_cell(last_coin, exit_cell)
            return "TRAP_BETWEEN", trap_cell

        return "INTERCEPT_LAST_COIN", last_coin

    # 玩家明显喜欢吃金币：优先拦金币
    if predicted_type == "coins" and predicted_target is not None:
        if coin_focus >= 0.6 or confidence >= 0.1:
            return "INTERCEPT_COIN", predicted_target

    # 玩家明显喜欢冲出口：靠近时守出口
    player_to_exit = manhattan(player_cell, exit_cell)
    if predicted_type == "exit" and player_to_exit <= 6:
        return "GUARD_EXIT", exit_cell

    # 终局时如果模型认为玩家会清光，也可以更激进守关键点
    if len(coins) <= 2 and endgame_focus >= 0.6:
        if predicted_target is not None:
            return "INTERCEPT_COIN", predicted_target

    return "CHASE", player_cell


def draw_text_center(text, font_obj, color, y):
    surf = font_obj.render(text, True, color)
    rect = surf.get_rect(center=(WIDTH // 2, y))
    screen.blit(surf, rect)


# --- 初始对象 ---
player_start = (1, 1)
ghost_start = find_exit_cell()
exit_cell = find_exit_cell()

if ghost_start == exit_cell:
    ghost_start = (ROWS - 2, COLS - 3) if is_walkable(ROWS - 2, COLS - 3) else (ROWS - 3, COLS - 2)

player_pos = cell_center(*player_start)
ghost_pos = cell_center(*ghost_start)

player_dir = None
ghost_dir = None
last_player_dir = None

coins = place_coins(COIN_COUNT, {player_start, ghost_start, exit_cell})
score = 0

game_over = False
game_result = ""
ghost_strategy_name = "CHASE"


# --- 3. 游戏主循环 ---
running = True
while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if game_over and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

    if not game_over:
        keys = pygame.key.get_pressed()
        player_wanted_dir = None

        if keys[pygame.K_LEFT]:
            player_wanted_dir = "LEFT"
        elif keys[pygame.K_RIGHT]:
            player_wanted_dir = "RIGHT"
        elif keys[pygame.K_UP]:
            player_wanted_dir = "UP"
        elif keys[pygame.K_DOWN]:
            player_wanted_dir = "DOWN"

        player_pos, player_dir = move_entity(
            player_pos,
            player_dir,
            player_wanted_dir,
            PLAYER_SPEED,
            dt,
            stop_when_no_input=True
        )

        player_cell = pos_to_cell(player_pos)
        ghost_cell = pos_to_cell(ghost_pos)

        player_model.record_step(
            cell=player_cell,
            direction=player_dir,
            ghost_cell=ghost_cell,
            coin_cells=coins,
            exit_cell=exit_cell,
            rows=ROWS,
            cols=COLS,
        )

        if player_cell in coins:
            coins.remove(player_cell)
            score += 1
            player_model.record_coin_collection(
                cell=player_cell,
                ghost_cell=ghost_cell,
                remaining_coins_after_pickup=len(coins),
                exit_cell=exit_cell,
            )

        # 鬼魂追踪：保留第一版移动底盘，只换目标
        ghost_cell = pos_to_cell(ghost_pos)
        ghost_wanted_dir = ghost_dir

        if at_cell_center(ghost_pos):
            ghost_pos = snap_to_center(ghost_pos)
            ghost_cell = pos_to_cell(ghost_pos)

            ghost_strategy_name, ghost_goal = choose_ghost_strategy(
                player_cell,
                ghost_cell,
                coins,
                exit_cell
            )

            next_step = get_next_ghost_cell(ghost_cell, ghost_goal)
            next_dir = cell_direction(ghost_cell, next_step)

            # 如果预判目标这一帧不靠谱，退回纯追人
            if next_dir is None:
                next_step = get_next_ghost_cell(ghost_cell, player_cell)
                next_dir = cell_direction(ghost_cell, next_step)

            # 再不行就直接找一个更靠近玩家的方向
            if next_dir is None:
                next_dir = choose_best_neighbor_toward_goal(ghost_cell, player_cell)

            # 再不行保持原方向
            if next_dir is None:
                next_dir = ghost_dir

            ghost_wanted_dir = next_dir

        ghost_pos, ghost_dir = move_entity(
            ghost_pos,
            ghost_dir,
            ghost_wanted_dir,
            GHOST_SPEED,
            dt,
            stop_when_no_input=False
        )

        ghost_cell = pos_to_cell(ghost_pos)
        last_player_dir = player_dir

        if player_cell == ghost_cell:
            game_over = True
            game_result = "You Lose!"
            player_model.record_loss(remaining_coins=len(coins), score=score)
            player_model.finalize_game()
            player_model.save_to_file("player_data.json")

        elif player_cell == exit_cell:
            game_over = True
            game_result = "You Win! Escaped!"
            player_model.record_exit_reached(remaining_coins=len(coins), score=score)
            player_model.finalize_game()
            player_model.save_to_file("player_data.json")

        elif len(coins) == 0:
            game_over = True
            game_result = "You Win! All Coins!"
            player_model.record_all_coins_win(score=score)
            player_model.finalize_game()
            player_model.save_to_file("player_data.json")

    # --- 渲染 ---
    screen.fill((0, 0, 0))

    for r in range(ROWS):
        for c in range(COLS):
            if maze[r][c] == 1:
                pygame.draw.rect(
                    screen,
                    (70, 70, 70),
                    (c * GRID_SIZE, r * GRID_SIZE, GRID_SIZE - 1, GRID_SIZE - 1)
                )

    exit_x = exit_cell[1] * GRID_SIZE
    exit_y = exit_cell[0] * GRID_SIZE
    pygame.draw.rect(
        screen,
        (60, 200, 60),
        (exit_x + 4, exit_y + 4, GRID_SIZE - 8, GRID_SIZE - 8)
    )

    for coin_r, coin_c in coins:
        cx = coin_c * GRID_SIZE + GRID_SIZE // 2
        cy = coin_r * GRID_SIZE + GRID_SIZE // 2
        pygame.draw.circle(screen, (255, 215, 0), (cx, cy), 6)

    pygame.draw.circle(
        screen,
        (255, 50, 50),
        (int(player_pos[0]), int(player_pos[1])),
        10
    )

    pygame.draw.circle(
        screen,
        (50, 50, 255),
        (int(ghost_pos[0]), int(ghost_pos[1])),
        10
    )

    score_text = font.render(f"Score: {score}", True, (255, 255, 255))
    screen.blit(score_text, (10, 10))

    coins_text = font.render(f"Coins: {len(coins)}", True, (255, 255, 255))
    screen.blit(coins_text, (10, 40))

    snapshot = player_model.behavior_snapshot()

    debug_text = font.render(
        f"Games:{snapshot['games_played']} LearnAt:{MIN_GAMES_BEFORE_LEARNING}",
        True,
        (180, 180, 180)
    )
    screen.blit(debug_text, (10, 70))

    model_text = font.render(
        f"CoinFocus:{snapshot['coin_focus_score']:.2f} Risk:{snapshot['risk_tolerance_score']:.2f}",
        True,
        (180, 180, 180)
    )
    screen.blit(model_text, (10, 100))

    strategy_text = font.render(
        f"Ghost:{ghost_strategy_name}",
        True,
        (180, 180, 180)
    )
    screen.blit(strategy_text, (10, 130))

    if game_over:
        overlay = pygame.Surface((WIDTH, HEIGHT))
        overlay.set_alpha(160)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        color = (80, 220, 120) if game_result.startswith("You Win") else (255, 80, 80)
        draw_text_center(game_result, big_font, color, HEIGHT // 2 - 20)
        draw_text_center(f"Final Score: {score}", font, (255, 255, 255), HEIGHT // 2 + 30)
        draw_text_center("Press ESC to quit", font, (220, 220, 220), HEIGHT // 2 + 70)

    pygame.display.flip()

pygame.quit()
