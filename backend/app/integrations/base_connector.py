from abc import ABC
from abc import abstractmethod


class BaseConnector(ABC):

    @abstractmethod
    def connect(self):
        pass


    @abstractmethod
    def disconnect(self):
        pass


    @abstractmethod
    def test_connection(self):
        pass


    @abstractmethod
    def fetch_data(self, query):
        pass