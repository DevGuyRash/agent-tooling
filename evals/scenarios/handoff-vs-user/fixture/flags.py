FLAGS = {"new_checkout": False}


def enabled(name):
    return FLAGS.get(name, False)
