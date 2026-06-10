__all__ = ["RobotController"]


def __getattr__(name):
    if name == "RobotController":
        from .controller import RobotController
        return RobotController
    raise AttributeError(f"module 'robot' has no attribute {name!r}")
