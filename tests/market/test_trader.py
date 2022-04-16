import unittest


from fxtrade.market import Trader, MockStockMarket


class TestTrader(unittest.TestCase):

    def setUp(self):
        pass

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')


if __name__ == '__main__':
    unittest.main()

