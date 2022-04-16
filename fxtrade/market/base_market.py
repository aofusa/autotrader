from abc import  ABCMeta, abstractmethod


class BaseMarket(metaclass=ABCMeta):
    
    @abstractmethod
    def check_latest_trade(self):
        pass

    @abstractmethod
    def check_differential(self):
        pass

    @abstractmethod
    def buy(self):
        pass

    @abstractmethod
    def sell(self):
        pass

