from iclr_wrap_up import utils

def load():
    train, test = utils.get_mnist()
    # Instantiate iterable.
    return train, test

