from calc.ops import add, average


def test_add():
    assert add(2, 3) == 5


def test_average_of_two_numbers():
    assert average([1, 2]) == 1.5
