import logging

consolelog = logging.getLogger("consolelog")
consolelog.setLevel(level=logging.INFO)
consolelog.propagate = False
