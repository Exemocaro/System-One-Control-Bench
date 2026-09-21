"""Every hand-drawn maze the tests use, in one place.

Hand-built maps matter: they stop the simulator and the oracle passing together
by sharing one bug. Each map below is drawn the way it is laid out, so a failing
test can be understood by looking at the picture.

Legend, as read by `snapshot_from_ascii`:

    #  wall          .  empty floor     G  goal
    K  yellow key    L  lava
    D  locked door   d  closed door     o  open door

Coordinates are (x, y) from the upper left, so the first row is y=0 and the
first character of a row is x=0.
"""

# A dead-end corridor. The goal is two cells east of the only start.
#   x: 01234
CORRIDOR = (
    "#####",
    "#..G#",
    "#####",
)

# The same corridor, one cell wider, for tests that need three free cells.
LONG_CORRIDOR = (
    "######",
    "#...G#",
    "######",
)

# An open room with no obstacles, for counting turns against forward moves.
OPEN_ROOM = (
    "#####",
    "#..G#",
    "#...#",
    "#...#",
    "#####",
)

# The goal sits in the lower left, so from (1,1) it is reachable two ways.
CORNER_ROOM = (
    "#####",
    "#...#",
    "#...#",
    "#G..#",
    "#####",
)

# The goal sits in the lower right, so the cheapest route spends only one turn.
FAR_CORNER_ROOM = (
    "#####",
    "#...#",
    "#...#",
    "#..G#",
    "#####",
)

# The key cannot be walked around: the locked door is the only way to the goal.
KEY_ROOM = (
    "######",
    "#K.D.#",
    "#..#.#",
    "#..#G#",
    "######",
)

# The goal is behind a wall with no opening at all.
SEALED_ROOM = (
    "#####",
    "#.#G#",
    "#.#.#",
    "#####",
)

# Lava sits between the agent and the goal; going around costs more.
LAVA_ROOM = (
    "#####",
    "#.LG#",
    "#####",
)

# From (1,2) facing east, stepping forward is fatal but looks one step closer:
# the goal is five actions away going north, and four from the lava cell.
LAVA_SHORTCUT = (
    "#####",
    "#..G#",
    "#.LL#",
    "#####",
)
