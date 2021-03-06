import sys
from src.agents import Pioneer
from typing import List, Tuple
from loguru import logger
import enum
import numpy as np
from analysis import find_doors, passing_door
import remote
from plot import Plot, report_status
from actions import Action, rot_away, rot_towards
from doors import DoorHistory


# ANGLES = np.linspace(-.75*np.pi, .75*np.pi, num=270)
# Future work calibrate automagically using the back wall and
# a slow turn probably can use a hough transform or RANSAC there
ANGLES = np.loadtxt("angles.txt") / 180*np.pi
SIN = np.sin(ANGLES)
COS = np.cos(ANGLES)


def convert(data: List[float]) -> Tuple[np.ndarray, np.ndarray]:
    ranges = np.array(data)
    ranges[90+44] = (ranges[90+43] + ranges[90+45])/2
    x = -1*ranges*SIN
    y = ranges*COS

    data = np.zeros((2, 270))
    return x, y


class BotState(enum.Enum):
    NoDoor = enum.auto()
    TrackingDoor = enum.auto()
    AlignedOnDoor = enum.auto()
    PassingDoor = enum.auto()


class State:
    current: BotState = BotState.NoDoor
    doors: DoorHistory = DoorHistory()
    plot: Plot = Plot()
    # control = remote.Control()


def handle_tracking(state: State, data, ranges) -> Action:
    door = state.doors.best_guss()

    if door is None:
        logger.critical("lost door, dumping data")
        np.savetxt("data2.txt", data)
        np.savetxt("ranges2.txt", ranges)
        # sys.exit()
        state.current = BotState.NoDoor
        return Action.Left

    if abs(door.angle_on()) < 2:
        logger.debug(f"angle on door: {door.angle_on()}")
        if abs(door.center().angle()) < 3:
            logger.debug(f"driving towards door {door.center().angle()}")
            return Action.Forward
        else:
            logger.debug(f"turning towards door {door.center().angle()}")
            return rot_towards(door.center().angle())
    elif abs(door.waypoint().angle()) < 10:
        logger.debug(f"driving towards waypoint {door.waypoint().angle()}")
        return Action.Forward
    else:
        logger.debug(f"turning towards waypoint {door.waypoint().angle()}")
        return rot_towards(door.waypoint().angle())


def brain(state: State, data, ranges) -> Action:
    doors = find_doors(data, ranges)
    state.doors.update(doors)

    if state.current == BotState.NoDoor:
        if len(doors) > 0:
            logger.info("tracking door")
            state.current = BotState.TrackingDoor
        return Action.Right
    elif state.current == BotState.TrackingDoor:
        return handle_tracking(state, data, ranges)
    elif state.current == BotState.AlignedOnDoor:
        if passing_door(data, ranges):
            logger.info("passing door")
            state.current = BotState.PassingDoor
            return Action.Forward
    elif state.current == BotState.PassingDoor:
        if not passing_door(data, ranges):
            logger.info("passed door")
            state.current = BotState.NoDoor
            return Action.Forward
    else:
        sys.exit(f"INVALID STATE: {state.current}")


def loop(agent: Pioneer, state: State):
    ranges = agent.read_lidars()
    ranges = np.array(ranges)
    data = convert(ranges)

    # action = state.control.apply(agent)
    # if action == Action.Save:
    #     np.savetxt("data.txt", data)
    #     np.savetxt("ranges.txt", ranges)
    #     logger.info("stored current ranges and data")

    action = brain(state, data, ranges)
    print(action)

    doors = find_doors(data, ranges)
    state.plot.update(doors, *data, action)
    report_status(doors)

    action.perform(agent)
